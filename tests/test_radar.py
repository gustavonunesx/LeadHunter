import csv
import io
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

from radar.domain import identity, local_fit, score_lead, validate_campaign, instagram_url
from radar.storage import Store
from radar.engine import Engine
from radar.providers import Providers, ProviderError, parse_maps
from app import make_handler, csv_bytes, filter_leads, validate_import


SETTINGS={"dfs_login":"test","dfs_password":"test","jev_key":"test","jev_model":"jev-1.13.0","run_limit":30,"daily_limit":100}


def campaign(**kwargs):
    return validate_campaign({"niche":"Loja de moda feminina","city":"São Carlos,São Paulo,Brazil","service":"google","source":"demo","limit":10,**kwargs})


def company(**kwargs):
    return {"name":"Loja A","category":"Moda feminina","city":"São Carlos","address":"Rua Teste 1","phone":None,"website":None,"reviews":None,"rating":None,**kwargs}


def maps_response(items):
    return {"status_code":20000,"cost":.002,"tasks":[{"status_code":20000,"result":[{"check_url":"https://www.google.com/maps/search/moda","items":items}]}]}


class DomainTests(unittest.TestCase):
    def test_missing_numbers_are_not_zero_or_bad_ranking(self):
        lead=company()
        result=score_lead(lead,[],local_fit(lead,'moda feminina'),'google')
        self.assertIsNone(result['rank_median']);self.assertEqual(result['visibility'],'not_measured')
        self.assertEqual(result['score'],25)

    def test_missing_website_import_is_not_a_verified_gap(self):
        result=score_lead(company(),[],local_fit(company(),'moda feminina'),'website')
        self.assertEqual(result['score'],25)

    def test_median_only_observed_ranks(self):
        score=score_lead(company(),[{'rank':12},{'rank':None},{'rank':20}],{'choice':'unknown'},'google')
        self.assertEqual(score['rank_median'],16);self.assertEqual(score['rank_samples'],2)
        self.assertEqual(score['priority'],'review')

    def test_uncertain_and_excluded_jev(self):
        lead=company(phone='123',rating=4.8,reviews=10)
        result=score_lead(lead,[{'rank':18}],{'choice':'match','confidence':.6,'method':'jev'},'google',30)
        self.assertEqual(result['priority'],'review')
        result=score_lead(lead,[],{'choice':'no_match','confidence':.95,'method':'jev'},'google')
        self.assertEqual(result['priority'],'excluded')

    def test_instagram_only_profile_urls(self):
        self.assertIsNone(instagram_url('javascript:alert(1)'))
        self.assertIsNone(instagram_url('https://instagram.com.evil.test/a'))
        self.assertIsNone(instagram_url('https://instagram.com/p/xyz'))
        self.assertEqual(instagram_url('https://instagram.com/loja/?x=1'),'https://www.instagram.com/loja/')

    def test_validation_rejects_excessive_and_nonfinite_input(self):
        for data in ({'limit':1000},{'limit':float('nan')},{'coordinates':'999,0,14z'},{'keywords':['a','b','c','d']}):
            with self.assertRaises(ValueError):campaign(**data)

    def test_identity_preserves_branches_and_demo_separation(self):
        first=company(phone='555')
        second=company(phone='555',address='Rua Teste 2')
        self.assertNotEqual(identity(first,'live'),identity(second,'live'))
        self.assertNotEqual(identity(first,'live'),identity(first,'demo'))

    def test_ads_are_not_imported_and_organic_rank_is_used(self):
        items=[{'type':'maps_paid_item','title':'Anúncio','rank_group':1},
               {'type':'maps_search','title':'Loja','rank_group':3,'rank_absolute':4,'rating':None}]
        rows=parse_maps(maps_response(items))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rank'],3)
        self.assertIsNone(rows[0]['reviews'])

    def test_import_allows_missing_and_rejects_invalid_numbers(self):
        config,leads=validate_import({'config':campaign(),'leads':[company()]})
        self.assertEqual(config['source'],'import');self.assertFalse(config['use_jev'])
        self.assertIsNone(leads[0]['rating'])
        with self.assertRaises(ValueError):validate_import({'config':campaign(),'leads':[company(rating=9)]})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.db')
        self.cid=self.store.create_campaign(campaign())
    def tearDown(self):self.temp.cleanup()

    def test_same_place_three_queries_one_lead_three_observations(self):
        for q in ['a','b','c']:
            self.store.upsert_lead(self.cid,company(place_id='p1'),'live',{'query':q,'location':'SC','rank':5,'depth':30})
        leads=self.store.leads(self.cid)
        self.assertEqual(len(leads),1);self.assertEqual(len(leads[0]['observations']),3)

    def test_manual_instagram_and_do_not_contact_survive_refresh(self):
        lid=self.store.upsert_lead(self.cid,company(place_id='p1'),'live')
        self.store.patch_data(lid,{'instagram':'https://www.instagram.com/correto/','instagram_status':'confirmed'})
        self.store.update_lead(lid,'do_not_contact','Não abordar')
        other=self.store.create_campaign(campaign())
        self.store.upsert_lead(other,company(place_id='p1',instagram='https://www.instagram.com/errado/',instagram_status='candidate'),'live')
        lead=self.store.leads(other)[0]
        self.assertEqual(lead['instagram'],'https://www.instagram.com/correto/')
        self.assertEqual(lead['stage'],'do_not_contact')

    def test_budget_reserved_before_call_and_recovery_no_auto_retry(self):
        self.store.reserve_call(self.cid,'test','test',1,1)
        with self.assertRaises(ValueError):self.store.reserve_call(self.cid,'test','test',1,1)
        self.store.update_campaign(self.cid,state='running')
        self.store.recover()
        self.assertEqual(self.store.campaign(self.cid)['state'],'interrupted')
        self.assertEqual(self.store.usage(self.cid)[0]['incomplete'],1)

    def test_backup_is_consistent_and_usable(self):
        self.store.upsert_lead(self.cid,company(),'import')
        path=Path(self.temp.name)/'backup.db';self.store.backup(path)
        self.assertEqual(len(Store(path).leads(self.cid)),1)

    def test_offline_demo_never_calls_provider(self):
        provider=Mock();engine=Engine(self.store,provider,SETTINGS)
        engine.run(self.cid)
        self.assertEqual(self.store.campaign(self.cid)['state'],'completed')
        self.assertEqual(len(self.store.leads(self.cid)),10)
        self.assertEqual(self.store.usage(self.cid),[])
        provider.maps.assert_not_called();provider.classify.assert_not_called()

    def test_cancel_before_start_performs_no_calls(self):
        self.store.update_campaign(self.cid,cancel_requested=1)
        provider=Mock();Engine(self.store,provider,SETTINGS).run(self.cid)
        self.assertEqual(self.store.campaign(self.cid)['state'],'cancelled')
        provider.maps.assert_not_called()

    def test_jev_contract_and_invalid_response(self):
        def transport(url,payload,headers):
            self.assertEqual(url,'https://api.typesafe.ai/v1/systemone')
            self.assertEqual(payload['questions']['niche_fit']['type'],'choice')
            return {'model':'jev-1.13.0','usage':{'input_tokens':200},'answers':{'niche_fit':{'type':'choice','choice':'match','confidence':.92}}}
        p=Providers(self.store,SETTINGS,transport)
        self.assertEqual(p.classify(self.cid,company(),'moda feminina')['confidence'],.92)
        p.transport=lambda *args:{'answers':{'niche_fit':{'choice':'invented'}}}
        with self.assertRaises(ProviderError):p.classify(self.cid,company(),'moda feminina')

    def test_instagram_search_returns_candidate_not_confirmation(self):
        p=Providers(self.store,SETTINGS,lambda *args:{'status_code':20000,'tasks':[{'status_code':20000,'result':[{'items':[{'type':'organic','url':'https://instagram.com/loja/','title':'Loja'}]}]}]})
        found=p.instagram(self.cid,company(),'São Carlos')
        self.assertEqual(found['instagram_status'],'candidate')

    def test_live_selects_opportunities_beyond_first_ten(self):
        cid=self.store.create_campaign(campaign(source='live',limit=2,use_jev=False,enrich=False))
        provider=Mock()
        provider.maps.return_value=[company(place_id=str(i),name=f'Loja {i}',rank=i,rating=4.8,reviews=10) for i in range(1,21)]
        Engine(self.store,provider,SETTINGS).run(cid)
        leads=self.store.leads(cid)
        self.assertEqual(len(leads),2)
        self.assertTrue(all(l['analysis']['rank_median']>10 for l in leads))

    def test_missing_credentials_do_not_simulate_live_data(self):
        cid=self.store.create_campaign(campaign(source='live'))
        settings={**SETTINGS,'dfs_login':'','dfs_password':''}
        Engine(self.store,Mock(),settings).run(cid)
        self.assertEqual(self.store.campaign(cid)['state'],'failed')
        self.assertEqual(self.store.leads(cid),[])

    def test_partial_results_survive_later_search_error(self):
        cid=self.store.create_campaign(campaign(source='live',keywords=['a','b'],enrich=False,use_jev=False))
        provider=Mock();provider.maps.side_effect=[[company(place_id='one',rank=18)],ProviderError('Falha esperada')]
        Engine(self.store,provider,SETTINGS).run(cid)
        self.assertEqual(self.store.campaign(cid)['state'],'partial')
        self.assertEqual(len(self.store.leads(cid)),1)

    def test_csv_formula_injection_and_filter(self):
        lead=company(name='=HYPERLINK("evil")',notes='+formula',stage='new',analysis={'priority':'review'},observations=[])
        encoded=csv_bytes([lead]).decode('utf-8-sig')
        row=list(csv.reader(io.StringIO(encoded),delimiter=';'))[1]
        self.assertTrue(row[0].startswith("'="));self.assertTrue(row[15].startswith("'+"))
        self.assertEqual(filter_leads([lead],{'priority':['high']}),[])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.db')
        settings={**SETTINGS,'dfs_login':'','dfs_password':'','jev_key':''}
        self.engine=Engine(self.store,Mock(),settings)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.engine,settings,'test-token'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,data=None,method='GET',headers=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json','X-Radar-Token':'test-token',**(headers or {})})
        return urllib.request.urlopen(req,timeout=5)

    def test_full_offline_journey_with_persistence_export_and_edit(self):
        with self.request('/api/campaigns',campaign(),'POST') as r:cid=json.load(r)['id']
        self.engine.run(cid)
        with self.request('/api/campaigns/'+cid) as r:data=json.load(r)
        self.assertEqual(len(data['leads']),10)
        lid=data['leads'][0]['id']
        with self.request('/api/leads/'+lid,{'stage':'interested','notes':'Conferir fonte'},'PATCH') as r:self.assertEqual(r.status,200)
        self.assertEqual(Store(self.store.path).lead(lid)['notes'],'Conferir fonte')
        with self.request('/api/campaigns/'+cid+'/export?stage=interested') as r:
            rows=list(csv.reader(io.StringIO(r.read().decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),2)
        with self.request('/api/leads/'+lid,None,'DELETE') as r:self.assertEqual(r.status,200)
        self.assertEqual(len(self.store.leads(cid)),9)

    def test_csrf_origin_and_dns_rebinding_rejected(self):
        for headers in ({'X-Radar-Token':'wrong'},{'Origin':'https://evil.test'},{'Host':'evil.test'}):
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/campaigns',campaign(),'POST',headers)
            self.assertEqual(e.exception.code,403)

    def test_live_without_credentials_rejected_before_queue(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/campaigns',campaign(source='live'),'POST')
        self.assertEqual(e.exception.code,400);self.assertEqual(self.store.campaigns(),[])

    def test_static_assets_and_status_do_not_expose_secret(self):
        for path in ['/','/app.js','/style.css','/favicon.svg','/example.json','/plan']:
            with self.request(path) as r:self.assertEqual(r.status,200)
        with self.request('/api/status') as r:data=json.load(r)
        self.assertNotIn('dfs_password',data);self.assertNotIn('jev_key',data)
        with self.assertRaises(urllib.error.HTTPError):self.request('/.env')


if __name__=='__main__':unittest.main()
