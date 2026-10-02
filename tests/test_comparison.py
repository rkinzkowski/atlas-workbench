import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.w = app.Workbench(Path(self.directory.name) / 'comparison.sqlite3')
        self.case = self.w.create_case('Fictional comparison fixture')['id']
        self.node = self.w.node(self.case, 'domain', 'example.com')

    def tearDown(self):
        self.w.store.db.close()
        self.directory.cleanup()

    def evidence(self, raw, **fields):
        return self.w.save_evidence(self.case, self.node['id'], 'domain_whois',
                                    {'raw': raw, 'source': 'Synthetic fixture', 'entities': [], **fields})

    def test_nested_full_values_absence_and_exact_types(self):
        tail = 'x' * 5000 + 'TAIL'
        before = self.evidence({'contact': {'email': 'old@example.com'}, 'gone': None, 'number': 1,
                                'empty': {}, 'array': ['a', 'b'], 'long': 'old', 'authorization': 'fake-old-secret'})
        after = self.evidence({'contact': {'email': 'new@example.com'}, 'added': None, 'number': True,
                               'empty': {}, 'array': ['b', 'a', {}], 'long': tail, 'authorization': 'fake-new-secret'})
        result = self.w.compare_evidence(self.case, before['id'], after['id'])
        rows = {r['path']: r for r in result['changes']}
        self.assertEqual(rows['$["long"]']['after'], tail)
        self.assertNotIn('before', rows['$["added"]'])
        self.assertIsNone(rows['$["added"]']['after'])
        self.assertNotIn('after', rows['$["gone"]'])
        self.assertEqual(rows['$["number"]']['kind'], 'changed')
        self.assertEqual(rows['$["array"][0]']['after'], 'b')
        self.assertNotIn('fake-old-secret', json.dumps(result))
        self.assertNotIn('$["authorization"]', rows)
        self.assertEqual(self.w.store.get('evidence', before['id'])['raw']['contact']['email'], 'old@example.com')

    def test_empty_roots_reordering_and_type_changes(self):
        self.assertEqual(app.response_changes({}, {})['changes'], [])
        self.assertEqual(app.response_changes({'a': 1, 'b': 2}, {'b': 2, 'a': 1})['changes'], [])
        self.assertEqual(app.response_changes([], {})['changes'][0]['path'], '$')
        self.assertEqual(app.response_changes(1, 1.0)['counts']['changed'], 1)
        self.assertEqual(app.response_changes('', None)['counts']['changed'], 1)

    def test_case_boundaries_and_comparison_scope(self):
        a = self.evidence({'value': 1})
        b = self.evidence({'value': 2}, request_options={'search_page': 2})
        other = self.w.create_case('Other')['id']
        foreign = self.w.save_evidence(other, 999, 'fixture', {'raw': {'value': 3}})
        with self.assertRaises(ValueError):
            self.w.compare_evidence(self.case, a['id'], foreign['id'])
        with self.assertRaises((ValueError, TypeError)):
            self.w.compare_evidence(None, a['id'], b['id'])
        self.assertFalse(self.w.compare_evidence(self.case, a['id'], b['id'])['same_request_options'])
        self.w.store.update('evidence', b['id'], node_id=999)
        self.assertFalse(self.w.compare_evidence(self.case, a['id'], b['id'])['same_source_entity'])

    def test_monitor_keeps_exact_last_changed_pair_after_unchanged_run(self):
        monitor = self.w.action({'action': 'monitor', 'case_id': self.case, 'node_id': self.node['id'],
                                 'transform_id': 'domain_whois', 'interval_seconds': 3600})
        records = []
        for value in ('old', 'new', 'new'):
            e = self.evidence({'value': value})
            records.append(e)
            self.w.record_monitor_result(self.case, monitor['id'], e)
        m = self.w.store.get('monitors', monitor['id'])
        self.assertEqual(m['last_evidence_id'], records[2]['id'])
        self.assertEqual(m['previous_evidence_id'], records[0]['id'])
        self.assertEqual(m['last_change_evidence_id'], records[1]['id'])
        changes = [e for e in self.w.store.all('events', self.case) if e.get('monitor_id') == m['id']]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['change_counts']['changed'], 1)

    def test_old_monitor_resolves_previous_hash_within_source_entity(self):
        a = self.evidence({'value': 'old'})
        self.w.store.add('evidence', self.case, {**a, 'node_id': 999})
        monitor = self.w.store.add('monitors', self.case, {'node_id': self.node['id'], 'transform_id': 'domain_whois', 'last_hash': a['sha256']})
        b = self.evidence({'value': 'new'})
        self.w.record_monitor_result(self.case, monitor['id'], b)
        self.assertEqual(self.w.store.get('monitors', monitor['id'])['previous_evidence_id'], a['id'])

    def test_http_comparison_download_and_invalid_case(self):
        a = self.evidence({'email': 'old@example.com'})
        b = self.evidence({'email': 'new@example.com'})
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.BaseHTTPRequestHandler)
        server.RequestHandlerClass = app.handler_for(self.w, server.server_port)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}/api/evidence-compare?before={a["id"]}&after={b["id"]}'
        try:
            with urllib.request.urlopen(url + f'&case={self.case}&download=1') as response:
                self.assertIn('attachment;', response.headers['Content-Disposition'])
                self.assertEqual(json.load(response)['changes'][0]['after'], 'new@example.com')
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + '&case=999')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
