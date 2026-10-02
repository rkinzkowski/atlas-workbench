import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import connectors


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'test.sqlite3'
        self.w = app.Workbench(self.path)
        self.case = self.w.create_case('Test case')['id']
        self.node = self.w.node(self.case, 'domain', 'example.com')

    def tearDown(self):
        self.w.store.db.close()
        self.directory.cleanup()

    def result(self, value='other.example'):
        return {'raw': {'domain': value}, 'source': 'Test fixture, no live lookup', 'snippet': 'Fixture observation',
                'entities': [connectors.entity('domain', value, 'fixture link')]}

    def test_dedup_keeps_distinct_provenance(self):
        first = self.w.save_evidence(self.case, self.node['id'], 'fixture', self.result())
        second = self.w.save_evidence(self.case, self.node['id'], 'fixture', self.result())
        self.assertEqual(self.w.apply(self.case, first['id']), 1)
        self.assertEqual(self.w.apply(self.case, first['id']), 0)
        self.w.apply(self.case, second['id'])
        self.assertEqual(len(self.w.store.all('nodes', self.case)), 2)
        self.assertEqual(len(self.w.store.all('edges', self.case)), 2)

    def test_cross_case_access_rejected(self):
        other = self.w.create_case('Other')['id']
        with self.assertRaises(ValueError):
            self.w.action({'action': 'review', 'case_id': other, 'table': 'nodes', 'id': self.node['id'], 'review': 'supported'})

    def test_budget_and_recursive_expansion(self):
        job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois'], 'max_runs': 2, 'max_depth': 2, 'auto_apply': True})
        with patch.object(connectors, 'run', side_effect=lambda t, n, **kw: self.result('next-' + n['identifier'])) as run:
            self.w.execute_job(job)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(self.w.store.all('nodes', self.case)), 3)
        self.assertEqual(self.w.store.get('jobs', job['id'])['status'], 'completed')
        self.assertEqual(len(self.w.store.all('reports', self.case)), 1)

    def test_collection_does_not_apply_without_opt_in(self):
        job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois']})
        with patch.object(connectors, 'run', return_value=self.result()):
            self.w.execute_job(job)
        self.assertEqual(len(self.w.store.all('nodes', self.case)), 1)
        self.assertEqual(len(self.w.store.all('evidence', self.case)), 1)

    def test_cancellation_retains_inflight_evidence_stops_next_request(self):
        job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois', 'domain_contacts']})
        def callback(*_, **kw):
            self.w.action({'action': 'cancel', 'case_id': self.case, 'id': job['id']})
            return self.result()
        with patch.object(connectors, 'run', side_effect=callback) as run:
            self.w.execute_job(job)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(self.w.store.all('evidence', self.case)), 1)
        self.assertEqual(self.w.store.get('jobs', job['id'])['status'], 'cancelled')

    def test_failures_are_recorded_without_fake_evidence(self):
        job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois']})
        with patch.object(connectors, 'run', side_effect=ValueError('Provider failed')):
            self.w.execute_job(job)
        self.assertEqual(self.w.store.all('evidence', self.case), [])
        self.assertEqual(self.w.store.get('jobs', job['id'])['status'], 'completed_with_errors')

    def test_restart_does_not_replay_uncertain_paid_request(self):
        job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois']})
        self.w.store.update('jobs', job['id'], status='running')
        other = app.Workbench(self.path)
        try:
            self.assertEqual(other.store.get('jobs', job['id'])['status'], 'interrupted')
        finally:
            other.store.db.close()

    def test_har_import_uses_only_target_response_and_remaps_links(self):
        graph = {'graph': {'nodes': [{'id': 900, 'type': 'domain', 'label': 'example.com'}, {'id': 901, 'type': 'email', 'label': 'a@example.com'}],
                           'edges': [{'from': 900, 'to': 901, 'evidence_id': 70, 'relationship': 'contact'}]},
                 'evidence_items': [{'id': 70, 'node_id': 900, 'source': 'fixture', 'timestamp': '2026-01-01T00:00:00Z', 'snippet': 'Contact', 'meta': [{'type': 'email', 'label': 'a@example.com'}]}]}
        har = {'log': {'entries': [{'request': {'url': 'https://webvetted.com/workbench/investigations/18440', 'headers': [{'name': 'Authorization', 'value': 'SECRET-NOT-TO-KEEP'}]}, 'response': {'content': {'text': json.dumps(graph)}}}]}}
        case = self.w.action({'action': 'import', 'payload': har})['id']
        edges = self.w.store.all('edges', case)
        evidence = self.w.store.all('evidence', case)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]['evidence_id'], evidence[0]['id'])
        self.assertNotIn('SECRET-NOT-TO-KEEP', json.dumps(self.w.state(case)))
        self.assertEqual(evidence[0]['timestamp'], '2026-01-01T00:00:00Z')
        self.assertEqual(len(evidence[0]['applied_keys']), 1)

    def test_invalid_import_rolls_back_all_changes(self):
        before = len(self.w.store.all('cases'))
        payload = {'graph': {'nodes': [{'id': 1, 'type': 'domain', 'label': 'ok.example'}, {'id': 2, 'type': 'bad/type', 'label': 'not-valid'}]}}
        with self.assertRaises(ValueError):
            self.w.action({'action': 'import', 'payload': payload})
        self.assertEqual(len(self.w.store.all('cases')), before)
        self.assertEqual(len(self.w.store.all('nodes')), 1)

    def test_import_preserves_repeated_identifiers_as_distinct_source_records(self):
        payload = {'graph': {'nodes': [{'id': 1, 'type': 'person', 'label': 'Same Name'}, {'id': 2, 'type': 'person', 'label': 'Same Name'}],
                             'edges': [{'id': 5, 'from': 1, 'to': 2}, {'id': 6, 'from': 1, 'to': 2}]}}
        case = self.w.action({'action': 'import', 'payload': payload})['id']
        self.assertEqual(len(self.w.store.all('nodes', case)), 2)
        self.assertEqual(len(self.w.store.all('edges', case)), 2)
        self.assertEqual({n['source_id'] for n in self.w.store.all('nodes', case)}, {1, 2})

    def test_report_versions_are_immutable_and_exclude_rejected_evidence(self):
        e = self.w.save_evidence(self.case, self.node['id'], 'fixture', self.result())
        first = self.w.report(self.case)
        self.w.store.update('evidence', e['id'], review='excluded')
        second = self.w.report(self.case)
        self.assertIn(e['id'], first['evidence_ids'])
        self.assertNotIn(e['id'], second['evidence_ids'])
        self.assertEqual(self.w.store.get('reports', first['id'])['text'], first['text'])
        self.assertEqual(second['version'], 2)

    def test_ai_citation_validation(self):
        self.w.save_evidence(self.case, self.node['id'], 'fixture', self.result())
        with patch.object(connectors, 'ai', return_value={'snippet': 'Claim [E999999]'}):
            with self.assertRaises(ValueError):
                self.w.report(self.case, True)
        self.assertEqual(self.w.store.all('reports', self.case), [])

    def test_web_stage_follows_collection(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-key-not-live', 'OPENAI_MODEL': 'fixture-model'}):
            job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['openai_web_search', 'domain_whois'], 'max_runs': 4})
            with patch.object(connectors, 'run', return_value=self.result()) as run:
                self.w.execute_job(job)
            self.assertEqual([c.args[0] for c in run.call_args_list], ['domain_whois', 'openai_web_search'])

    def test_unimplemented_transform_cannot_be_queued(self):
        with self.assertRaises(ValueError):
            self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['username_breach_data']})

    def test_public_source_metadata_survives_response_redaction(self):
        sources = connectors.clean(self.w.sources())
        public = next(s for s in sources if s['id'] == 'domain_whois')
        paid = next(s for s in sources if s['id'] == 'instagram_profile')
        self.assertIsNone(public['credential_env'])
        self.assertEqual(paid['credential_env'], 'SCRAPECREATORS_API_KEY')

    def test_redaction_and_private_network_block(self):
        value = connectors.clean({'api-key': 'sensitive', 'nested': {'password': 'sensitive'}, 'text': 'Bearer pretend-secret and https://a.example/?token=pretend-secret'})
        self.assertNotIn('sensitive', json.dumps(value))
        self.assertNotIn('pretend-secret', json.dumps(value))
        with self.assertRaises(ValueError):
            connectors.public_url('http://127.0.0.1/')
        with self.assertRaises(ValueError):
            connectors.public_url('http://user:password@example.com/')

    def test_dns_rebinding_cannot_connect_to_private_address(self):
        public = [(2, 1, 6, '', ('93.184.216.34', 443))]
        private = [(2, 1, 6, '', ('127.0.0.1', 443))]
        with patch.object(connectors.socket, 'getaddrinfo', side_effect=[public, private]):
            connectors.public_url('https://example.com/')
            with patch.object(connectors.socket, 'create_connection') as connect:
                with self.assertRaises(ValueError):
                    connectors.public_connection(('example.com', 443))
                connect.assert_not_called()

    def test_monitor_records_changes_without_applying_entities(self):
        monitor = self.w.action({'action': 'monitor', 'case_id': self.case, 'node_id': self.node['id'], 'transform_id': 'domain_whois', 'interval_seconds': 1})
        self.assertEqual(monitor['interval_seconds'], 3600)
        for value in ('first.example', 'changed.example'):
            job = self.w.queue(self.case, {'node_ids': [self.node['id']], 'transforms': ['domain_whois'], 'max_runs': 1, 'monitor_id': monitor['id']})
            with patch.object(connectors, 'run', return_value=self.result(value)):
                self.w.execute_job(job)
        changes = [e for e in self.w.store.all('events', self.case) if e.get('monitor_id') == monitor['id']]
        self.assertEqual(len(changes), 1)
        self.assertEqual(len(self.w.store.all('nodes', self.case)), 1)
        self.assertEqual(self.w.store.all('reports', self.case), [])
        paused = self.w.action({'action': 'monitor', 'case_id': self.case, 'id': monitor['id']})
        self.assertFalse(paused['enabled'])

    def test_null_mx_is_not_an_empty_entity(self):
        with patch.object(connectors, 'fetch', return_value={'Answer': [{'type': 15, 'data': '0 .'}]}):
            result = connectors.run('atlas_dns', self.node)
        self.assertEqual(result['entities'], [])

    def test_connector_contracts_without_paid_calls(self):
        with patch.dict(os.environ, {'OSINT_INDUSTRIES_API_KEY': 'fixture-key-not-live'}):
            with patch.object(connectors, 'fetch', return_value={'result': {'email': 'lead@example.com'}}) as fetch:
                r = connectors.run('email_osint_industries', {'type': 'email', 'identifier': 'seed@example.com'})
            self.assertEqual(fetch.call_args.args[0], 'https://api.osint.industries/v2/request')
            self.assertFalse(fetch.call_args.args[1]['premium'])
            self.assertEqual(r['entities'][0]['identifier'], 'lead@example.com')
        with patch.dict(os.environ, {'SCRAPECREATORS_API_KEY': 'fixture-key-not-live'}):
            with patch.object(connectors, 'fetch', return_value={'success': True, 'items': []}) as fetch:
                connectors.run('instagram_posts', {'type': 'instagram', 'identifier': 'sample_user'})
            self.assertIn('/v2/instagram/user/posts?handle=sample_user', fetch.call_args.args[0])

    def test_http_requires_local_host_and_write_token(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.BaseHTTPRequestHandler)
        port = server.server_port
        server.RequestHandlerClass = app.handler_for(self.w, port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{port}'
        try:
            with urllib.request.urlopen(url + '/api/state') as r:
                self.assertIn('csrf', json.load(r))
            evidence=self.w.save_evidence(self.case,self.node['id'],'fixture',{'raw':{'email':'synthetic@example.com','next_token':'page-2','authorization':'do-not-export'},'entities':[]})
            with urllib.request.urlopen(url + f"/api/source-response?case={self.case}&id={evidence['id']}") as r:
                self.assertIn('attachment;',r.headers['Content-Disposition'])
                raw=json.load(r)
                self.assertEqual(raw['email'],'synthetic@example.com')
                self.assertEqual(raw['next_token'],'page-2')
                self.assertEqual(raw['authorization'],'[REDACTED]')
            for headers in ({'Content-Type': 'application/json'}, {'Content-Type': 'application/json', 'X-Atlas-Token': self.w.token, 'Origin': 'https://evil.example'}):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(urllib.request.Request(url + '/api/action', data=b'{"action":"demo"}', headers=headers))
                self.assertEqual(e.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(url + '/api/state', headers={'Host': 'evil.example'}))
            self.assertEqual(e.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
