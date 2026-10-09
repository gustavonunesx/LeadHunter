"""SQLite storage with durable campaigns and conservative deduplication."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from .domain import now, identity


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
              INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
              CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                config TEXT NOT NULL, state TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
                progress INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
                warnings TEXT NOT NULL DEFAULT '[]');
              CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'new',
                notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS campaign_leads (
                campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
                lead_id TEXT REFERENCES leads(id) ON DELETE CASCADE,
                analysis TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(campaign_id,lead_id));
              CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
                lead_id TEXT REFERENCES leads(id) ON DELETE CASCADE, query TEXT NOT NULL,
                location TEXT NOT NULL, rank INTEGER, depth INTEGER NOT NULL,
                observed_at TEXT NOT NULL, source_url TEXT, UNIQUE(campaign_id,lead_id,query,location));
              CREATE INDEX IF NOT EXISTS idx_observations_campaign_lead ON observations(campaign_id,lead_id);
              CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY, campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
                provider TEXT NOT NULL, operation TEXT NOT NULL, created_at TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', cost REAL, tokens INTEGER, model TEXT);
              CREATE INDEX IF NOT EXISTS idx_api_calls_campaign ON api_calls(campaign_id);
              CREATE INDEX IF NOT EXISTS idx_api_calls_date ON api_calls(created_at);
              PRAGMA optimize;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE campaigns SET state='interrupted',message='Execução interrompida pelo reinício. Resultados preservados.',updated_at=? WHERE state IN ('running','importing')", (now(),))
            db.execute("UPDATE api_calls SET state='unknown' WHERE state='pending'")

    def create_campaign(self, config, state="queued"):
        cid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO campaigns(id,created_at,updated_at,config,state) VALUES(?,?,?,?,?)", (cid, now(), now(), json.dumps(config, ensure_ascii=False), state))
        return cid

    def campaign(self, cid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        row = dict(row)
        row["config"] = json.loads(row["config"])
        row["warnings"] = json.loads(row["warnings"])
        return row

    def campaigns(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM campaigns ORDER BY created_at DESC,rowid DESC LIMIT 200")]
        return [self.campaign(cid) for cid in ids]

    def update_campaign(self, cid, **fields):
        allowed = {"state", "message", "progress", "cancel_requested", "warnings"}
        if not fields.keys() <= allowed:
            raise ValueError("Invalid campaign update")
        fields["updated_at"] = now()
        if "warnings" in fields:
            fields["warnings"] = json.dumps(fields["warnings"], ensure_ascii=False)
        with self.connect() as db:
            db.execute("UPDATE campaigns SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", [*fields.values(), cid])

    def queued(self):
        with self.connect() as db:
            row = db.execute("SELECT id FROM campaigns WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
        return row[0] if row else None

    def upsert_lead(self, cid, lead, source, observation=None):
        lead=dict(lead)
        lid = identity(lead, source)
        with self.connect() as db:
            existing = db.execute("SELECT data FROM leads WHERE id=?", (lid,)).fetchone()
            incoming_sources={k:{"source":source,"url":lead.get("source_url") or lead.get("maps_url"),"observed_at":lead.get("collected_at") or now()} for k in ("name","category","address","city","phone","website","rating","reviews","instagram") if lead.get(k) is not None and lead.get(k)!=""}
            if existing:
                old = json.loads(existing[0])
                manual_instagram = {k: old.get(k) for k in ("instagram", "instagram_status", "instagram_source", "instagram_verified_at")} if old.get("instagram_status") in {"confirmed", "rejected"} else {}
                provenance=old.get("field_sources",{})
                if manual_instagram:
                    incoming_sources.pop("instagram",None)
                provenance.update(incoming_sources)
                old.update({k: v for k, v in lead.items() if v is not None})
                old.update(manual_instagram)
                old["field_sources"]=provenance
                lead = old
            else:
                lead["field_sources"]=incoming_sources
            lead.update({"id": lid, "source": source, "updated_at": now()})
            db.execute("INSERT INTO leads(id,data,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at", (lid,json.dumps(lead,ensure_ascii=False),now(),now()))
            db.execute("INSERT OR IGNORE INTO campaign_leads(campaign_id,lead_id) VALUES(?,?)", (cid,lid))
            if observation:
                db.execute("INSERT OR IGNORE INTO observations(campaign_id,lead_id,query,location,rank,depth,observed_at,source_url) VALUES(?,?,?,?,?,?,?,?)", (cid,lid,observation["query"],observation["location"],observation.get("rank"),observation["depth"],observation.get("observed_at",now()),observation.get("source_url")))
        return lid

    def patch_data(self, lid, values):
        with self.connect() as db:
            row = db.execute("SELECT data FROM leads WHERE id=?", (lid,)).fetchone()
            if not row:
                raise ValueError("Empresa não encontrada.")
            data = json.loads(row[0]); data.update(values)
            db.execute("UPDATE leads SET data=?,updated_at=? WHERE id=?", (json.dumps(data,ensure_ascii=False),now(),lid))

    def lead(self, lid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        data.update({"id":row["id"],"stage":row["stage"],"notes":row["notes"]})
        return data

    def campaigns_for_lead(self, lid):
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT campaign_id FROM campaign_leads WHERE lead_id=?",(lid,))]

    def delete_lead(self,lid):
        with self.connect() as db:
            db.execute("DELETE FROM leads WHERE id=?",(lid,))

    def set_analysis(self, cid, lid, analysis):
        with self.connect() as db:
            db.execute("UPDATE campaign_leads SET analysis=? WHERE campaign_id=? AND lead_id=?", (json.dumps(analysis,ensure_ascii=False),cid,lid))

    def keep_campaign_leads(self,cid,ids):
        with self.connect() as db:
            current=[r[0] for r in db.execute("SELECT lead_id FROM campaign_leads WHERE campaign_id=?",(cid,))]
            for lid in current:
                if lid not in ids:
                    db.execute("DELETE FROM observations WHERE campaign_id=? AND lead_id=?",(cid,lid))
                    db.execute("DELETE FROM campaign_leads WHERE campaign_id=? AND lead_id=?",(cid,lid))
                    db.execute("DELETE FROM leads WHERE id=? AND stage='new' AND notes='' AND NOT EXISTS(SELECT 1 FROM campaign_leads WHERE lead_id=?)",(lid,lid))

    def update_lead(self, lid, stage, notes):
        with self.connect() as db:
            db.execute("UPDATE leads SET stage=?,notes=?,updated_at=? WHERE id=?", (stage,notes,now(),lid))

    def leads(self, cid):
        with self.connect() as db:
            rows = db.execute("SELECT l.*,cl.analysis FROM leads l JOIN campaign_leads cl ON l.id=cl.lead_id WHERE cl.campaign_id=?", (cid,)).fetchall()
            obs = [dict(r) for r in db.execute("SELECT * FROM observations WHERE campaign_id=? ORDER BY observed_at,id", (cid,))]
        results = []
        for row in rows:
            data = json.loads(row["data"])
            data.update({"id":row["id"],"stage":row["stage"],"notes":row["notes"],"analysis":json.loads(row["analysis"]),"observations":[o for o in obs if o["lead_id"]==row["id"]]})
            results.append(data)
        return sorted(results,key=lambda x:x["analysis"].get("score",0),reverse=True)

    def reserve_call(self, cid, provider, operation, run_limit, daily_limit):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT count(*) FROM api_calls WHERE campaign_id=?", (cid,)).fetchone()[0]
            day = db.execute("SELECT count(*) FROM api_calls WHERE created_at>=?", (now()[:10],)).fetchone()[0]
            if run >= run_limit or day >= daily_limit:
                raise ValueError("Limite de chamadas atingido. Resultados anteriores foram preservados.")
            return db.execute("INSERT INTO api_calls(campaign_id,provider,operation,created_at) VALUES(?,?,?,?)", (cid,provider,operation,now())).lastrowid

    def finish_call(self, call_id, state, cost=None, tokens=None, model=None):
        with self.connect() as db:
            db.execute("UPDATE api_calls SET state=?,cost=?,tokens=?,model=? WHERE id=?", (state,cost,tokens,model,call_id))

    def usage(self, cid):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT provider,count(*) AS calls,sum(cost) AS cost,sum(tokens) AS tokens,sum(CASE WHEN state!='success' THEN 1 ELSE 0 END) AS incomplete FROM api_calls WHERE campaign_id=? GROUP BY provider",(cid,))]

    def backup(self, destination):
        with self.connect() as db:
            with sqlite3.connect(destination) as target:
                db.backup(target)
