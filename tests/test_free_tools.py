import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import connectors as c
import free_tools as f
import free_worker as worker
import setup_free_tools as setup
import restore_backup

class FreeModeTests(unittest.TestCase):
    def test_tool_authentication_fields_are_protected_without_masking_contacts(self):
        raw={'master_token':'fixture-secret','authorization_tokens':{'value':'secret'},
             'credentials':{'SID':'secret'},'email':'fixture@example.com','phone':'+12025550123'}
        clean=c.clean(raw)
        for key in ('master_token','authorization_tokens','credentials'):
            self.assertEqual(clean[key],'[REDACTED]')
        self.assertEqual(clean['email'],raw['email'])
        self.assertEqual(clean['phone'],raw['phone'])
    def test_free_evidence_keeps_effective_options(self):
        result=c.run('free_search_links',{'type':'username','identifier':'fixture'}, {'site_limit':2})
        self.assertEqual(result['request_options']['site_limit'],2)
        self.assertEqual(result['request_options']['site_offset'],0)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.w=app.Workbench(Path(self.tmp.name)/'atlas.sqlite3')
        self.case=self.w.create_case('Synthetic free tests')['id']
        self.node=self.w.node(self.case,'username','fixture')
        self.env=patch.dict(os.environ,{'SERPER_API_KEY':'fixture-not-live','OPENAI_API_KEY':'fixture-ai-key','OPENAI_MODEL':'fixture-model'})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.w.store.db.close();self.tmp.cleanup()
    def mode(self,enabled=True):
        return self.w.action({'action':'free-mode','enabled':enabled})
    def test_paid_lookup_is_rejected_and_rolls_back_case(self):
        self.mode()
        before=len(self.w.store.all('cases'))
        with patch.object(c,'fetch') as fetch:
            with self.assertRaisesRegex(ValueError,'Free mode'):
                self.w.action({'action':'lookup','type':'username','value':'fixture','transforms':['username_web_search']})
            fetch.assert_not_called()
        self.assertEqual(len(self.w.store.all('cases')),before)
        self.assertFalse(self.w.state()['ai_ready'])
        self.assertFalse(next(s for s in self.w.sources() if s['id']=='username_web_search')['available'])
    def test_free_mode_survives_restart_and_backup_restore(self):
        self.mode()
        archive=Path(self.tmp.name)/'backup.zip';archive.write_bytes(self.w.backup())
        target=Path(self.tmp.name)/'restored'
        restore_backup.restore(archive,target)
        second=app.Workbench(target/'atlas.sqlite3')
        try:self.assertTrue(second.free_only)
        finally:second.store.db.close()
    def test_enabling_pauses_paid_monitor_and_cancels_queued_paid_job(self):
        job=self.w.queue(self.case,{'node_ids':[self.node['id']],'transforms':['username_web_search']})
        monitor=self.w.action({'action':'monitor','case_id':self.case,'node_id':self.node['id'],'transform_id':'username_web_search'})
        self.mode()
        self.assertEqual(self.w.store.get('jobs',job['id'])['status'],'cancelled')
        self.assertFalse(self.w.store.get('monitors',monitor['id'])['enabled'])
        with self.assertRaisesRegex(ValueError,'free mode'):
            self.w.action({'action':'monitor-set','case_id':self.case,'id':monitor['id'],'enabled':True})
        self.mode(False)
        self.assertFalse(self.w.store.get('monitors',monitor['id'])['enabled'])
    def test_stored_free_job_cannot_be_switched_to_paid(self):
        self.mode()
        job=self.w.queue(self.case,{'node_ids':[self.node['id']],'transforms':['free_search_links']})
        self.mode(False)
        job['transforms']=['username_web_search']
        with patch.object(c,'run') as run:
            self.w.execute_job(job);run.assert_not_called()
        self.assertEqual(self.w.store.get('jobs',job['id'])['failed_runs'],1)
    def test_local_reports_work_ai_calls_do_not(self):
        self.mode()
        self.w.action({'action':'manual-evidence','case_id':self.case,'node_id':self.node['id'],'source':'Synthetic','raw':{'fixture':'value'}})
        with patch.object(c,'ai') as ai:
            report=self.w.report(self.case)
            self.assertIn('Complete investigation',report['text'])
            with self.assertRaisesRegex(ValueError,'Free mode'):self.w.report(self.case,True)
            with self.assertRaisesRegex(ValueError,'Free mode'):
                self.w.action({'action':'question','case_id':self.case,'question':'fixture','ai':True})
            ai.assert_not_called()
    def test_all_supplied_tools_accept_full_attributed_import(self):
        for tool in f.LIBRARY:
            e=self.w.action({'action':'tool-evidence','case_id':self.case,'node_id':self.node['id'],
                'tool_id':tool[0],'raw':{'unknown':['complete'], 'email':'fixture@example.com','sessionid':'testsecret'}})
            self.assertEqual(e['raw']['unknown'],['complete'])
            self.assertEqual(e['raw']['email'],'fixture@example.com')
            self.assertEqual(e['raw']['sessionid'],'[REDACTED]')
            self.assertIn(tool[1],e['source'])
    def test_free_options_validate_before_queue(self):
        for options in ({'site_limit':31},{'crawl_pages':21},{'tool_timeout':301},{'sites':['bad']},{'site_offset':-1}):
            with self.assertRaises(ValueError):self.w.lookup_options({'options':options})
    def test_child_has_no_paid_keys_or_inherited_proxy(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'fixture','INSTAGRAM_SESSION_ID':'fixture-session'}):
            env=f.child_env(Path(self.tmp.name))
        for key in ('SERPER_API_KEY','OPENAI_API_KEY','INSTAGRAM_SESSION_ID','HTTPS_PROXY'):
            self.assertNotIn(key,env)
        self.assertEqual(env['USERPROFILE'],self.tmp.name)
    def test_generated_links_and_gateway_do_not_fetch_or_infer_person_email(self):
        with patch.object(c,'fetch') as fetch:
            links=f.run('free_search_links',self.node,{})
            mapped=f.run('free_sms_gateway',{'identifier':'+1 202 555 0123','type':'phone'},{'gateway_domain':'sms.example.com'})
            fetch.assert_not_called()
        self.assertEqual(links['entities'],[])
        self.assertEqual(mapped['entities'],[])
        self.assertFalse(mapped['raw']['personal_email'])
    def test_instagram_failed_detail_keeps_first_profile(self):
        with patch.dict(os.environ,{'INSTAGRAM_SESSION_ID':'fixture-session'}),patch.object(c,'fetch',side_effect=[{'data':{'user':{'id':'123','username':'fixture'}}},c.SourceError(429,{'message':'limited'})]) as fetch:
            r=f.run('free_toutatis_profile',{'identifier':'fixture','type':'instagram'},{})
        self.assertEqual(fetch.call_count,2)
        self.assertIn('profile',r['raw'])
        self.assertIsNotNone(r['collection']['error'])
    def test_crawl_redirect_cannot_leave_host(self):
        import urllib.request
        request=urllib.request.Request('https://example.com')
        with self.assertRaisesRegex(ValueError,'crawl host'):
            c.Redirect('example.com').redirect_request(request,None,302,'Found',{},'https://elsewhere.example/')

class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'out.jsonl'
    def tearDown(self): self.tmp.cleanup()
    def request(self,task,sites):
        filename='blackbird-username.json' if task.startswith('blackbird') else 'detectdee.json'
        (self.root/filename).write_text(json.dumps(sites))
        return {'task':task,'value':'fixture','output':str(self.path),'data_dir':str(self.root),'options':f.options({})}
    def rows(self):return [json.loads(l) for l in self.path.read_text().splitlines()]
    def test_blackbird_preserves_unknown_errors_and_content_category(self):
        rules={'sites':[{'name':'Adult fixture','cat':'xx NSFW xx','uri_check':'https://example.com/{account}',
             'e_code':200,'e_string':'account-present','m_code':404,'m_string':'missing'},
             {'name':'Blocked fixture','uri_check':'https://example.com/{account}','e_code':200,'e_string':'account-present','m_code':404,'m_string':'missing'}]}
        with patch.object(worker,'observe',side_effect=[(200,'account-present FULL DETAILS','https://example.com/fixture'),(403,'blocked-body','https://example.com/fixture')]),patch.object(worker.time,'sleep'):
            worker.scan(self.request('blackbird_username',rules))
        rows=self.rows();self.assertEqual(rows[1]['outcome'],'candidate');self.assertEqual(rows[2]['outcome'],'error')
        self.assertEqual(rows[1]['responses'][0]['body'],'account-present FULL DETAILS')
        self.assertFalse(rows[0]['content_category_filter'])
    def test_blackbird_status_alone_is_ambiguous_and_post_is_not_sent(self):
        rules={'sites':[{'name':'Status','uri_check':'https://example.com/{account}','e_code':200,'e_string':'','m_code':404,'m_string':'missing'},
               {'name':'Post','uri_check':'https://example.com/{account}','method':'POST'}]}
        with patch.object(worker,'observe',return_value=(200,'login page','https://example.com/login')) as observe,patch.object(worker.time,'sleep'):
            worker.scan(self.request('blackbird_username',rules))
        self.assertEqual(observe.call_count,1)
        self.assertEqual([r['outcome'] for r in self.rows()[1:]],['ambiguous','unsupported'])
    def test_site_budget_and_offset_are_explicit(self):
        rules={'sites':[{'name':str(i),'uri_check':'https://example.com/{account}','e_code':200,'e_string':'account','m_code':404,'m_string':'missing'} for i in range(8)]}
        request=self.request('blackbird_username',rules);request['options'].update(site_offset=2,site_limit=2)
        with patch.object(worker,'observe',return_value=(200,'account','https://example.com/fixture')) as observe,patch.object(worker.time,'sleep'):
            worker.scan(request)
        self.assertEqual(observe.call_count,2);self.assertEqual(self.rows()[0]['next_offset'],4)
    def test_detectdee_chain_requires_body_evidence(self):
        rules={'fixture':{'detect':[{'type':'username','url':'https://example.com/%s','statusCode':'200'},
                                    {'url':'https://example.com/api/%s','existRegex':'account-present'}]}}
        request=self.request('detectdee_username',rules)
        with patch.object(worker,'observe',return_value=(200,'account-present','https://example.com/fixture')),patch.object(worker,'regex_match',side_effect=lambda pattern,text:pattern in text),patch.object(worker.time,'sleep'):
            worker.scan(request)
        self.assertEqual(self.rows()[1]['outcome'],'candidate')
        self.assertEqual(len(self.rows()[1]['responses']),2)
    def test_repair_only_invalid_json_escape_preserves_valid_regex(self):
        raw=b'{"valid":"\\\\[\\\\]", "invalid":"\\.example"}'
        parsed,fixed,count=setup.repair_catalog(raw)
        self.assertEqual(count,1);self.assertEqual(parsed['valid'],r'\[\]');self.assertEqual(parsed['invalid'],r'\.example')
        self.assertEqual(json.loads(fixed),parsed)

if __name__=='__main__':unittest.main()
