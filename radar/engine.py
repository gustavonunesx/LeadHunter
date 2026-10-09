"""Single durable campaign worker with offline demonstration and paid adapters."""
import statistics
import threading
import time
from .domain import identity, local_fit, normalized, now, score_lead
from .providers import ProviderError


class Cancelled(Exception):
    pass


DEMO_NAMES = ["Ateliê Aurora", "Casa Violeta", "Flor de Rua", "Linha Clara", "Estação Amora", "Essência Boutique", "Vista Bela", "Modo Íris", "Alameda Rosa", "Studio Cora"]


def demo_leads(config):
    for i,name in enumerate(DEMO_NAMES[:config["limit"]]):
        yield {"name":name+" · Exemplo", "category":config["niche"], "city":config["city"],
               "address":f"Endereço fictício {i+1} — apenas demonstração", "borough":["Centro","Vila Prado","Santa Felícia"][i%3],
               "place_id":f"demo-{normalized(config['niche'])}-{normalized(config['city'])}-{i}", "phone":None,
               "website":"https://example.com" if i%3==0 else None,"website_checked":True,
               "rating":[4.8,4.6,4.2,4.9,3.8,4.7,4.5,4.1,4.9,4.3][i],
               "reviews":[12,8,6,112,4,19,43,9,85,7][i], "instagram":None,"instagram_status":"not_searched",
               "rank":[18,23,14,2,32,12,7,27,3,16][i],"source_url":None,"maps_url":None,"collected_at":now()}


class Engine:
    def __init__(self, store, providers, settings):
        self.store,self.providers,self.settings = store,providers,settings
        self.stopped = threading.Event()
        self.thread = None

    def start(self):
        self.store.recover()
        self.thread=threading.Thread(target=self.loop,daemon=True)
        self.thread.start()

    def loop(self):
        while not self.stopped.is_set():
            cid=self.store.queued()
            if cid:
                self.run(cid)
            else:
                self.stopped.wait(.4)

    def check(self,cid):
        campaign=self.store.campaign(cid)
        if not campaign or campaign["cancel_requested"] or self.stopped.is_set():
            raise Cancelled()

    def recalculate(self,cid,fits=None):
        campaign=self.store.campaign(cid)
        leads=self.store.leads(cid)
        fits=fits or {lead["id"]:lead["analysis"].get("fit") or local_fit(lead,campaign["config"]["niche"]) for lead in leads}
        comparable=[]
        for lead in leads:
            fit=fits.get(lead["id"],{})
            if fit.get("choice")=="match" and (fit.get("method")=="rules" or (fit.get("confidence") or 0)>=.8) and lead.get("reviews") is not None:
                comparable.append(lead["reviews"])
        median=statistics.median(comparable) if len(comparable)>=5 else None
        for lead in leads:
            self.store.set_analysis(cid,lead["id"],score_lead(lead,lead["observations"],fits.get(lead["id"]),campaign["config"]["service"],median))

    def run(self,cid):
        config=self.store.campaign(cid)["config"]
        warnings=[]; fits={}
        try:
            self.check(cid)
            self.store.update_campaign(cid,state="running",message="Buscando empresas…",progress=5)
            if config["source"]=="demo":
                warnings.append("Demonstração: todas as empresas, posições e avaliações são fictícias. Nenhuma API foi consultada.")
                for lead in demo_leads(config):
                    self.check(cid)
                    for offset,query in enumerate(config["keywords"]):
                        self.store.upsert_lead(cid,lead,"demo",{"query":query,"location":config["city"],"rank":lead["rank"]+offset,"depth":50,"observed_at":now(),"source_url":None})
            elif config["source"]=="live":
                if not self.settings["dfs_login"] or not self.settings["dfs_password"]:
                    raise ProviderError("Configure DATAFORSEO_LOGIN e DATAFORSEO_PASSWORD no .env e reinicie o aplicativo.")
                candidates={}; outside=0; missing_city=0
                points=config["coordinates"] or [None]
                for query in config["keywords"]:
                    for point in points:
                        self.check(cid)
                        self.store.update_campaign(cid,message=f"Consultando: {query}",progress=15)
                        batch=self.providers.maps(cid,query,config["city"],point,depth=max(30,config["limit"]))
                        for lead in batch:
                            target_city=normalized(config["city"].split(",")[0].split("–")[0].split(" - ")[0])
                            if lead.get("city") and normalized(lead["city"]) != target_city:
                                outside+=1; continue
                            if not lead.get("city"):
                                missing_city+=1
                                lead["region_review"]=True
                            lid=identity(lead,"live")
                            observation={"query":query,"location":point or config["city"],"rank":lead.get("rank"),"depth":max(30,config["limit"]),"observed_at":now(),"source_url":lead.get("source_url")}
                            if lid not in candidates:
                                candidates[lid]={"lead":lead,"observations":[]}
                            candidates[lid]["observations"].append(observation)
                        # Re-rank the candidate pool after each successful query. This
                        # preserves a useful partial result if a later call fails.
                        ordered=sorted(candidates.values(),key=lambda c:score_lead(c["lead"],c["observations"],local_fit(c["lead"],config["niche"]),config["service"])["score"],reverse=True)
                        chosen=ordered[:config["limit"]]
                        chosen_ids=[]
                        for candidate in chosen:
                            for obs in candidate["observations"]:
                                chosen_ids.append(self.store.upsert_lead(cid,candidate["lead"],"live",obs))
                        self.store.keep_campaign_leads(cid,set(chosen_ids))
                if outside:
                    warnings.append(f"{outside} resultados fora da cidade informada foram excluídos.")
                if missing_city:
                    warnings.append("Há resultados sem cidade estruturada; confira a região na ficha.")
            # Imported leads are validated and inserted by the API before queuing.
            leads=self.store.leads(cid)
            for index,lead in enumerate(leads):
                self.check(cid)
                self.store.update_campaign(cid,message=f"Analisando {index+1} de {len(leads)}: {lead['name']}",progress=40+int(50*(index+1)/max(1,len(leads))))
                fit=local_fit(lead,config["niche"])
                if config["source"]!="demo" and config["use_jev"] and self.settings["jev_key"]:
                    try:
                        fit=self.providers.classify(cid,lead,config["niche"])
                    except (ProviderError,ValueError) as exc:
                        warnings.append(f"Jev: {exc}")
                        fit={"choice":"unknown","confidence":None,"method":"error","model":None}
                elif config["source"]!="demo" and config["use_jev"]:
                    warnings.append("Jev não configurado: classificação por regras locais, sujeita a revisão.")
                fits[lead["id"]]=fit
                if lead.get("region_review"):
                    fit={**fit,"choice":"unknown"}
                    fits[lead["id"]]=fit
                self.store.set_analysis(cid,lead["id"],score_lead(lead,lead["observations"],fit,config["service"]))
                self.check(cid)
                if config["source"]=="live" and config["enrich"] and lead.get("instagram_status") not in {"confirmed","rejected"}:
                    try:
                        found=self.providers.instagram(cid,lead,config["city"],(config["coordinates"] or [None])[0])
                        self.store.patch_data(lead["id"],found)
                    except (ProviderError,ValueError) as exc:
                        warnings.append(f"Instagram: {exc}")
                        self.store.patch_data(lead["id"],{"instagram_status":"error"})
            self.recalculate(cid,fits)
            self.check(cid)
            warnings=list(dict.fromkeys(warnings))
            has_error=any(w.startswith(("Jev:","Instagram:")) for w in warnings)
            self.store.update_campaign(cid,state="partial" if has_error else "completed",progress=100,message=f"{len(leads)} empresas organizadas." if leads else "Nenhuma empresa retornada para os filtros consultados.",warnings=warnings)
        except Cancelled:
            self.recalculate(cid)
            self.store.update_campaign(cid,state="cancelled",message="Campanha cancelada. Resultados já coletados foram preservados.",warnings=list(dict.fromkeys(warnings)))
        except (ProviderError,ValueError) as exc:
            self.recalculate(cid)
            partial=bool(self.store.leads(cid))
            self.store.update_campaign(cid,state="partial" if partial else "failed",message=str(exc),warnings=list(dict.fromkeys(warnings)))
        except Exception:
            import traceback
            traceback.print_exc()
            self.store.update_campaign(cid,state="failed",message="Falha interna no processamento. Consulte o terminal; dados anteriores preservados.")
