"""Synthetic offline fixtures. No paid calls, live keys, or personal case data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import connectors as c
import providers as p


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ,{key:'fixture-not-live-'+key.lower() for key in p.CREDENTIAL_ENVS})
        self.env.start()
        self.public = patch.object(c,'public_url',side_effect=lambda url:url)
        self.public.start()

    def tearDown(self):
        self.public.stop()
        self.env.stop()

    def run_source(self, transform, kind, value, raw=None, options=None):
        with patch.object(c,'fetch',return_value={} if raw is None else raw) as fetch:
            result = c.run(transform,{'type':kind,'identifier':value},options)
        return result,fetch.call_args

    def test_phone_email_name_and_address_are_not_masked(self):
        raw={'full_name':'Synthetic Person','phone':'+12025550123','email':'synthetic@example.com',
             'street_address':'123 Example Street','description':'Unrestricted returned text',
             'next_token':'next-page-123','continuationToken':'page-456','authorization':'Bearer private',
             'url':'https://example.com/?next_token=page-123&access_token=secret-value'}
        result,_=self.run_source('email_osint_industries','email','synthetic@example.com',raw)
        for key in ('full_name','phone','email','street_address','description','next_token','continuationToken'):
            self.assertEqual(result['raw'][key],raw[key])
        self.assertEqual(result['raw']['authorization'],'[REDACTED]')
        self.assertIn('next_token=page-123',result['raw']['url'])
        self.assertNotIn('secret-value',json.dumps(result))
        self.assertFalse(result['visibility']['content_masking'])
        self.assertEqual(c.clean('Basic Zml4dHVyZTpwYXNz'), 'Basic [REDACTED]')

    def test_extraction_preserves_more_than_former_limits(self):
        raw={'records':[{'email':f'person{i}@example.com'} for i in range(1205)]}
        self.assertEqual(len(p.entities(raw)),1205)

    def test_all_scrape_routes_match_documentation_snapshot(self):
        contract=json.loads((Path(__file__).parent/'fixtures/scrapecreators-contracts.json').read_text())
        for transform,row in p.SCRAPE.items():
            with self.subTest(transform=transform):
                route,param,types,_,cursor,_=row
                spec=contract['routes'][route]
                self.assertIn(param,spec['query_parameters'])
                if cursor:self.assertIn(cursor,spec['query_parameters'])
                value='https://example.com/profile/test' if param=='url' else 'fixture_user'
                result,call=self.run_source(transform,types[0],value,{'success':True,'unknown_field':{'kept':True}})
                parsed=urllib.parse.urlsplit(call.args[0]);q=urllib.parse.parse_qs(parsed.query)
                self.assertEqual(parsed.hostname,'api.scrapecreators.com')
                self.assertEqual(parsed.path,route)
                self.assertIn(param,q)
                self.assertNotIn('trim',q)
                self.assertTrue(result['raw']['unknown_field']['kept'])

    def test_scrape_pagination_and_resume(self):
        first={'items':[{'email':'a@example.com'}],'next_max_id':'cursor-first'}
        second={'items':[{'email':'b@example.com'}],'next_max_id':'cursor-second'}
        with patch.object(c,'fetch',side_effect=[first,second]) as fetch:
            r=c.run('instagram_posts',{'type':'instagram','identifier':'fixture_user'},{'max_pages':2})
        self.assertEqual(r['raw'],{'pages':[first,second]})
        self.assertEqual(r['collection']['next_cursor'],'cursor-second')
        self.assertEqual(r['collection']['stop_reason'],'page_limit')
        self.assertIn('next_max_id=cursor-first',fetch.call_args_list[1].args[0])
        r,call=self.run_source('instagram_posts','instagram','fixture_user',{'items':[]},{'cursor':'cursor-second'})
        self.assertIn('next_max_id=cursor-second',call.args[0])
        self.assertFalse(r['collection']['more_available'])

    def test_scrape_success_envelope_with_private_profile_is_failure(self):
        raw = {'success': True, 'credits_charged': 1, 'error': 'not_found',
               'errorStatus': 404, 'message': 'Profile is private'}
        with patch.object(c, 'fetch', return_value=raw) as fetch:
            with self.assertRaisesRegex(c.SourceError, 'Profile is private') as caught:
                c.run('instagram_profile', {'type': 'instagram', 'identifier': 'fixture_user'})
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(caught.exception.status, 200)
        self.assertEqual(caught.exception.response, raw)
        for payload in ({'success': False}, {'errorStatus': '404'}, {'error': {'code': 'blocked'}}):
            self.assertTrue(p.scrape_failed(payload))
        self.assertFalse(p.scrape_failed({'success': True, 'error': None, 'errorStatus': 0}))

    def test_scrape_embedded_error_after_page_keeps_partial_data(self):
        first = {'items': [1], 'next_max_id': 'next'}
        denied = {'success': True, 'error': 'blocked', 'message': 'Access denied'}
        with patch.object(c, 'fetch', side_effect=[first, denied]) as fetch:
            r = c.run('instagram_posts', {'type': 'instagram', 'identifier': 'fixture_user'}, {'max_pages': 3})
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(r['raw'], first)
        self.assertEqual(r['collection']['pages_fetched'], 1)
        self.assertEqual(r['collection']['error']['response'], denied)
        self.assertEqual(r['collection']['stop_reason'], 'provider_error')

    def test_pagination_partial_failure_retains_successful_page(self):
        first={'items':[1],'next_max_id':'next'}
        with patch.object(c,'fetch',side_effect=[first,c.SourceError(429,{'detail':'quota'})]):
            r=c.run('instagram_posts',{'type':'instagram','identifier':'fixture_user'},{'max_pages':3})
        self.assertEqual(r['raw'],first)
        self.assertEqual(r['collection']['pages_fetched'],1)
        self.assertEqual(r['collection']['stop_reason'],'provider_error')
        self.assertEqual(r['collection']['next_cursor'],'next')

    def test_repeated_cursor_does_not_loop(self):
        with patch.object(c,'fetch',return_value={'next_max_id':'same'}) as fetch:
            r=c.run('instagram_posts',{'type':'instagram','identifier':'fixture_user'},{'max_pages':20})
        self.assertEqual(fetch.call_count,2)
        self.assertIsNotNone(r['collection']['error'])

    def test_cancel_before_request_produces_no_fake_empty_result(self):
        with patch.object(c,'fetch') as fetch:
            with self.assertRaisesRegex(ValueError,'cancelled'):
                c.run('instagram_posts',{'type':'instagram','identifier':'fixture_user'},{'_cancelled':lambda:True})
            fetch.assert_not_called()

    def test_youtube_channel_and_profile_urls(self):
        self.assertEqual(p.handle('https://www.youtube.com/@fixture/videos'),'fixture')
        self.assertEqual(p.handle('https://bsky.app/profile/test.bsky.social'),'test.bsky.social')
        _,call=self.run_source('youtube_channel_videos','youtube','https://www.youtube.com/channel/UCfixture/videos')
        self.assertIn('channelId=UCfixture',call.args[0])

    def test_osint_search_types_and_explicit_premium(self):
        for kind in ('email','phone','person','username','wallet'):
            _,call=self.run_source(kind+'_osint_industries',kind,'fixture',options={'premium':True})
            self.assertEqual(call.args[1]['type'],'name' if kind=='person' else kind)
            self.assertTrue(call.args[1]['premium'])
            self.assertFalse(call.args[1]['exact_match'])
            self.assertFalse(call.args[1]['premium_modules_only'])

    def test_name_enrichment_requires_context_before_charge(self):
        with patch.object(c,'fetch') as fetch:
            with self.assertRaisesRegex(ValueError,'name plus'):
                c.run('person_pdl_enrichment',{'type':'person','identifier':'Synthetic Person'})
            fetch.assert_not_called()
        _,call=self.run_source('person_pdl_enrichment','person','Synthetic Person',options={'location':'Example City'})
        self.assertEqual(call.args[1]['location'],'Example City')
        self.assertNotIn('data_include',call.args[1])

    def test_no_match_is_distinct_from_account_failure(self):
        for source in ('email_pdl_enrichment','email_breach_data'):
            with patch.object(c,'fetch',side_effect=c.SourceError(404,{'status':404})):
                r=c.run(source,{'type':'email','identifier':'fixture@example.com'})
                self.assertTrue(r['no_match'])
            with patch.object(c,'fetch',side_effect=c.SourceError(401,{'status':401})):
                with self.assertRaises(c.SourceError):c.run(source,{'type':'email','identifier':'fixture@example.com'})

    def test_specialist_request_contracts(self):
        fixtures=[
          ('phone_line_lookup','phone','+1 (202) 555-0123','lookups.twilio.com','/v2/PhoneNumbers/%2B12025550123'),
          ('domain_builtwith','domain','example.com','api.builtwith.com','/v25/api.json'),
          ('domain_subdomains','domain','example.com','api.securitytrails.com','/v1/domain/example.com/subdomains'),
          ('ip_hostsdomains','ip','8.8.8.8','api.securitytrails.com','/v1/domains/list'),
          ('ip_reputation','ip','8.8.8.8','api.abuseipdb.com','/api/v2/check'),
          ('ip_geolocation','ip','8.8.8.8','api.ipinfo.io','/lookup/8.8.8.8'),
          ('image_google_lens','image','https://example.com/image.jpg','serpapi.com','/search.json'),
          ('image_yandex_images','image','https://example.com/image.jpg','serpapi.com','/search.json'),
          ('image_scene_analysis','image','https://example.com/image.jpg','api.sightengine.com','/1.0/check.json'),
          ('image_moderation','image','https://example.com/image.jpg','api.sightengine.com','/1.0/check.json'),
          ('domain_safe_browsing','domain','example.com','webrisk.googleapis.com','/v1/uris:search'),
          ('twitter_username_history','twitter','fixture_user','api.memory.lol','/v1/tw/fixture_user')]
        for transform,kind,value,host,path in fixtures:
            with self.subTest(transform=transform):
                _,call=self.run_source(transform,kind,value,{'unknown_field':'retained'})
                parsed=urllib.parse.urlsplit(call.args[0]);self.assertEqual((parsed.hostname,parsed.path),(host,path))

    def test_serper_scopes_and_page(self):
        for source in ('person_social_search','email_web_search','phone_web_search','username_web_search','linkedin_search','facebook_search','domain_linkedin','domain_places','maps_listing'):
            kind=p.ADAPTERS[source][1][0]
            _,call=self.run_source(source,kind,'example.com',options={'page':3})
            self.assertEqual(call.args[1]['page'],3)
            self.assertIn('X-API-KEY',call.args[2])
            self.assertNotIn('safe',call.args[1])

    def test_tineye_returns_full_match_details_and_page_offset(self):
        raw={'code':200,'results':{'matches':[{'image_url':'https://example.com/image.jpg','backlinks':[{'backlink':'https://example.com/page'}]}]},'stats':{'total_results':101}}
        r,call=self.run_source('image_reverse_search','image','https://example.com/seed.jpg',raw,{'page':2})
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(call.args[0]).query)
        self.assertEqual(q['offset'],['100'])
        self.assertEqual(q['limit'],['100'])
        self.assertEqual(r['raw'],raw)


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.w=app.Workbench(Path(self.directory.name)/'test.sqlite3')
        self.env=patch.dict(os.environ,{'OSINT_INDUSTRIES_API_KEY':'fixture-not-live','SCRAPECREATORS_API_KEY':'fixture-not-live'})
        self.env.start()

    def tearDown(self):
        self.env.stop();self.w.store.db.close();self.directory.cleanup()

    def test_embedded_profile_error_counts_as_failed_without_retry(self):
        lookup = self.w.action({'action': 'lookup', 'type': 'instagram', 'value': 'fixture_user', 'transforms': ['instagram_profile']})
        raw = {'success': True, 'error': 'not_found', 'errorStatus': 404, 'message': 'Profile is private', 'credits_charged': 1}
        with patch.object(c, 'fetch', return_value=raw) as fetch:
            self.w.execute_job(self.w.store.get('jobs', lookup['job_id']))
        self.assertEqual(fetch.call_count, 1)
        job = self.w.store.get('jobs', lookup['job_id'])
        self.assertEqual((job['completed_runs'], job['failed_runs']), (0, 1))
        run = self.w.store.all('runs', lookup['case_id'])[0]
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['source_response'], raw)
        self.assertEqual(self.w.store.all('evidence', lookup['case_id']), [])

    def test_standalone_lookup_persists_full_evidence_and_options(self):
        for kind in ('phone','email','person','username'):
            result=self.w.action({'action':'lookup','type':kind,'value':'Synthetic identifier','transforms':[kind+'_osint_industries'],'options':{'premium':True}})
            job=self.w.store.get('jobs',result['job_id'])
            self.assertTrue(job['options']['premium'])
            with patch.object(c,'fetch',return_value={'email':'fixture@example.com','private_unknown_field':'full value'}):
                self.w.execute_job(job)
            evidence=self.w.store.all('evidence',result['case_id'])[0]
            self.assertEqual(evidence['raw']['private_unknown_field'],'full value')
            self.assertEqual(len(self.w.store.all('nodes',result['case_id'])),1)

    def test_invalid_lookup_leaves_no_empty_case(self):
        with self.assertRaises(ValueError):
            self.w.action({'action':'lookup','type':'phone','value':'fixture','transforms':['phone_eyecon']})
        self.assertEqual(self.w.store.all('cases'),[])
        self.assertEqual(self.w.store.all('nodes'),[])

    def test_partial_run_and_continuation_keep_provenance(self):
        r=self.w.action({'action':'lookup','type':'instagram','value':'fixture','transforms':['instagram_posts'],'options':{'max_pages':2}})
        with patch.object(c,'fetch',side_effect=[{'next_max_id':'next-page','items':[1]},c.SourceError(429,{'error':'quota'})]):
            self.w.execute_job(self.w.store.get('jobs',r['job_id']))
        run=self.w.store.all('runs',r['case_id'])[0]
        self.assertEqual(run['status'],'partial')
        evidence=self.w.store.get('evidence',run['evidence_id'])
        job=self.w.action({'action':'continue','case_id':r['case_id'],'evidence_id':evidence['id'],'max_pages':3})
        self.assertEqual(job['options']['cursor'],'next-page')
        with patch.object(c,'fetch',return_value={'items':[2]}):self.w.execute_job(job)
        self.assertEqual(len(self.w.store.all('evidence',r['case_id'])),2)

    def test_page_limits_are_explicit(self):
        for opts in ({'max_pages':0},{'max_pages':21},{'page':101},{'premium':'yes'}):
            with self.assertRaises(ValueError):self.w.lookup_options({'options':opts})

    def test_server_cannot_share_an_existing_port(self):
        first=app.LocalServer(('127.0.0.1',0),app.BaseHTTPRequestHandler)
        try:
            with self.assertRaises(OSError):app.LocalServer(('127.0.0.1',first.server_port),app.BaseHTTPRequestHandler)
        finally:first.server_close()


if __name__ == '__main__': unittest.main()
