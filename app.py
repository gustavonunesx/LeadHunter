#!/usr/bin/env python3
"""Run: python app.py. Local-only HTTP application; no external packages required."""
import argparse
import csv
import io
import json
import mimetypes
import secrets
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from radar.domain import STAGES, validate_campaign, safe_url, instagram_url, number, text, now
from radar.storage import Store
from radar.providers import Providers, load_settings
from radar.engine import Engine

ROOT=Path(__file__).resolve().parent


def filter_leads(leads,query):
    search=(query.get("q",[""])[0]).casefold()
    priority=query.get("priority",[""])[0]
    stage=query.get("stage",[""])[0]
    return [lead for lead in leads if (not search or search in " ".join(str(lead.get(k) or "") for k in ("name","address","category","city")).casefold()) and (not priority or lead["analysis"].get("priority")==priority) and (not stage or lead["stage"]==stage)]


def csv_bytes(leads):
    stream=io.StringIO(newline="")
    writer=csv.writer(stream,delimiter=";")
    writer.writerow(["Nome","Categoria","Cidade","Endereço","Telefone","Site","Instagram","Estado Instagram","Nota","Avaliações","Pontos de prioridade","Prioridade","Posição mediana observada","Amostras","Etapa","Observações do operador","Origem","Google Maps","Coletado em","Evidências de busca","Motivos"])
    for lead in leads:
        analysis=lead["analysis"]
        values=[lead.get(k) for k in ("name","category","city","address","phone","website","instagram","instagram_status","rating","reviews")]
        values += [analysis.get("score"),analysis.get("priority"),analysis.get("rank_median"),analysis.get("rank_samples"),lead["stage"],lead["notes"],lead.get("source"),lead.get("maps_url"),lead.get("collected_at"),json.dumps(lead["observations"],ensure_ascii=False)," | ".join(r["text"] for r in analysis.get("reasons",[]))]
        def cell(v):
            s="" if v is None else str(v)
            return "'"+s if s.lstrip().startswith(("=","+","-","@","\t","\r")) else s
        writer.writerow([cell(v) for v in values])
    return ("\ufeff"+stream.getvalue()).encode("utf-8")


def validate_import(data):
    config=validate_campaign({**data.get("config",{}),"source":"import","enrich":False,"use_jev":False})
    rows=data.get("leads")
    if not isinstance(rows,list) or not 1<=len(rows)<=100:
        raise ValueError("Importe de 1 a 100 empresas por arquivo.")
    leads=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("Empresa inválida no arquivo.")
        name=text(row.get("name"),200,True)
        address=text(row.get("address"),500,True)
        city=text(row.get("city") or config["city"],100,True)
        leads.append({"name":name,"address":address,"city":city,"category":text(row.get("category"),200),
                      "place_id":text(row.get("place_id"),250) or None,"phone":text(row.get("phone"),80) or None,
                      "website":safe_url(row.get("website")),"instagram":instagram_url(row.get("instagram")),
                      "instagram_status":"candidate" if instagram_url(row.get("instagram")) else "not_searched",
                      "instagram_source":"Arquivo importado pelo operador.",
                      "rating":number(row.get("rating"),0,5),"reviews":number(row.get("reviews"),0,10000000,True),
                      "source_url":safe_url(row.get("source_url")),"maps_url":safe_url(row.get("maps_url")),
                      "collected_at":now()})
    return config,leads


def make_handler(store,engine,settings,token):
    class Handler(BaseHTTPRequestHandler):
        server_version="RadarLocal/1.0"
        def log_message(self,*args):
            pass

        def send(self,status,body,content_type="application/json; charset=utf-8",filename=None):
            if not isinstance(body,bytes):
                body=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def guard(self,write=False):
            port=self.server.server_address[1]
            if self.headers.get("Host") not in {f"127.0.0.1:{port}",f"localhost:{port}"}:
                self.send(403,{"error":"Acesso permitido somente pelo endereço local do aplicativo."});return False
            origin=self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{port}",f"http://localhost:{port}"}:
                self.send(403,{"error":"Origem não autorizada."});return False
            if write and not secrets.compare_digest(self.headers.get("X-Radar-Token",""),token):
                self.send(403,{"error":"Atualize a página antes de continuar."});return False
            return True

        def body(self):
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=1_000_000:
                raise ValueError("Arquivo vazio ou acima de 1 MB.")
            if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                raise ValueError("Envie dados em JSON.")
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError("Objeto JSON esperado.")
            return data

        def do_GET(self):
            if not self.guard():return
            p=urlparse(self.path); parts=p.path.strip("/").split("/"); query=parse_qs(p.query)
            try:
                if p.path=="/api/status":
                    return self.send(200,{"token":token,"dataforseo":bool(settings["dfs_login"] and settings["dfs_password"]),"jev":bool(settings["jev_key"]),"jev_model":settings["jev_model"],"run_limit":settings["run_limit"],"daily_limit":settings["daily_limit"],"version":"1.0.0"})
                if p.path=="/api/campaigns":
                    return self.send(200,{"campaigns":store.campaigns()})
                if len(parts)>=3 and parts[:2]==["api","campaigns"]:
                    cid=parts[2]; campaign=store.campaign(cid)
                    if not campaign:return self.send(404,{"error":"Campanha não encontrada."})
                    leads=filter_leads(store.leads(cid),query)
                    if len(parts)==4 and parts[3]=="export":
                        return self.send(200,csv_bytes(leads),"text/csv; charset=utf-8",f"radar-{campaign['config']['source']}-{cid[:8]}.csv")
                    return self.send(200,{"campaign":campaign,"leads":leads,"usage":store.usage(cid)})
                if p.path=="/api/backup":
                    with tempfile.TemporaryDirectory() as temp:
                        path=Path(temp)/"radar.sqlite3";store.backup(path)
                        return self.send(200,path.read_bytes(),"application/octet-stream","radar-backup.sqlite3")
                paths={"/":"index.html","/app.js":"app.js","/style.css":"style.css","/favicon.svg":"favicon.svg","/example.json":"example.json","/plan":"../docs/PLANO_COMPLETO.md"}
                if p.path not in paths:return self.send(404,{"error":"Página não encontrada."})
                path=ROOT/"web"/paths[p.path]
                mime="text/plain; charset=utf-8" if p.path=="/plan" else (mimetypes.guess_type(path)[0] or "application/octet-stream")
                return self.send(200,path.read_bytes(),mime)
            except Exception:
                return self.send(500,{"error":"Não foi possível carregar os dados."})

        def do_POST(self):
            if not self.guard(True):return
            try:
                data=self.body();p=urlparse(self.path).path;parts=p.strip("/").split("/")
                if p=="/api/campaigns":
                    config=validate_campaign(data)
                    if config["source"]=="import":raise ValueError("Use a importação de arquivo para esta origem.")
                    if config["source"]=="live" and not (settings["dfs_login"] and settings["dfs_password"]):
                        raise ValueError("Configure as credenciais DataForSEO no .env e reinicie. Nenhuma busca foi iniciada.")
                    if config["source"]=="live":
                        expected=len(config["keywords"])*max(1,len(config["coordinates"]))+config["limit"]*(int(config["enrich"])+int(config["use_jev"] and bool(settings["jev_key"])))
                        if expected>settings["run_limit"]:raise ValueError("A campanha pode exceder o limite de chamadas. Reduza termos, pontos ou empresas.")
                    cid=store.create_campaign(config)
                    return self.send(201,{"id":cid})
                if p=="/api/import":
                    config,leads=validate_import(data)
                    cid=store.create_campaign(config,"importing")
                    try:
                        for lead in leads:store.upsert_lead(cid,lead,"import")
                        store.update_campaign(cid,state="queued")
                    except Exception:
                        store.update_campaign(cid,state="failed",message="Importação interrompida.")
                        raise
                    return self.send(201,{"id":cid})
                if len(parts)==4 and parts[:2]==["api","campaigns"] and parts[3]=="cancel":
                    campaign=store.campaign(parts[2])
                    if not campaign:return self.send(404,{"error":"Campanha não encontrada."})
                    if campaign["state"] not in {"queued","running"}:raise ValueError("Esta campanha já foi finalizada.")
                    store.update_campaign(parts[2],cancel_requested=1)
                    return self.send(200,{"ok":True})
                return self.send(404,{"error":"Ação não encontrada."})
            except (ValueError,TypeError,KeyError) as exc:
                return self.send(400,{"error":str(exc) if isinstance(exc,ValueError) else "Campos inválidos."})
            except Exception:
                return self.send(500,{"error":"Não foi possível concluir a operação."})

        def do_PATCH(self):
            if not self.guard(True):return
            try:
                data=self.body();parts=urlparse(self.path).path.strip("/").split("/")
                if len(parts)!=3 or parts[:2]!=["api","leads"]:return self.send(404,{"error":"Ação não encontrada."})
                lead=store.lead(parts[2])
                if not lead:return self.send(404,{"error":"Empresa não encontrada."})
                stage=data.get("stage",lead["stage"])
                if stage not in STAGES:raise ValueError("Etapa inválida.")
                notes=text(data.get("notes",lead["notes"]),5000)
                if "instagram_status" in data:
                    status=data["instagram_status"]
                    if status not in {"confirmed","rejected","candidate"}:raise ValueError("Estado do Instagram inválido.")
                    url=instagram_url(data.get("instagram",lead.get("instagram")))
                    if status!="rejected" and not url:raise ValueError("Informe o link de um perfil válido do Instagram.")
                    store.patch_data(lead["id"],{"instagram":url,"instagram_status":status,"instagram_source":"Revisão manual do operador.","instagram_verified_at":now()})
                store.update_lead(lead["id"],stage,notes)
                for cid in store.campaigns_for_lead(lead["id"]):engine.recalculate(cid)
                return self.send(200,{"ok":True})
            except (ValueError,TypeError) as exc:return self.send(400,{"error":str(exc)})
            except Exception:return self.send(500,{"error":"Não foi possível salvar a ficha."})

        def do_DELETE(self):
            if not self.guard(True):return
            parts=urlparse(self.path).path.strip("/").split("/")
            if len(parts)!=3 or parts[:2]!=["api","leads"]:return self.send(404,{"error":"Ação não encontrada."})
            ids=store.campaigns_for_lead(parts[2])
            if any(store.campaign(cid)["state"] in {"running","queued"} for cid in ids):
                return self.send(409,{"error":"Aguarde ou cancele a campanha antes de excluir."})
            store.delete_lead(parts[2])
            for cid in ids:engine.recalculate(cid)
            return self.send(200,{"ok":True})
    return Handler


def main():
    parser=argparse.ArgumentParser(description="Radar Local — painel de prospecção local")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--data-dir",type=Path,default=ROOT/"data")
    args=parser.parse_args()
    settings=load_settings(ROOT)
    store=Store(args.data_dir/"radar.sqlite3")
    providers=Providers(store,settings)
    engine=Engine(store,providers,settings)
    handler=make_handler(store,engine,settings,secrets.token_urlsafe(32))
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler)
    server.daemon_threads=True
    engine.start()
    print(f"Radar Local disponível em http://127.0.0.1:{args.port}",flush=True)
    print("Use Ctrl+C para encerrar. Dados preservados em",args.data_dir,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        engine.stopped.set();server.server_close()


if __name__=="__main__":main()
