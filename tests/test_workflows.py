import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import sqlite3
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import hermes_mcp
import settings
import restore_backup


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.w = app.Workbench(Path(self.directory.name) / 'test.sqlite3')
        self.case = self.w.create_case('Fictional workflow test')['id']
        self.node = self.w.node(self.case, 'domain', 'example.com')

    def tearDown(self):
        self.w.store.db.close()
        self.directory.cleanup()

    def action(self, action, **fields):
        return self.w.action({'action': action, 'case_id': self.case, **fields})

    def test_plan_is_no_call_and_can_start_only_once(self):
        with patch.object(app.connectors, 'run') as run:
            plan = self.action('plan', node_ids=[self.node['id']], transforms=['domain_whois'], max_runs=2, objective='Domain history')
            self.assertEqual(len(plan['seed_requests']), 1)
            self.assertEqual(self.w.store.all('jobs', self.case), [])
            job = self.action('start-plan', id=plan['id'])
            self.assertEqual(job['status'], 'queued')
            with self.assertRaises(ValueError):
                self.action('start-plan', id=plan['id'])
            run.assert_not_called()

    def test_plan_rejects_unavailable_or_wrong_case_and_requires_expansion_opt_in(self):
        with self.assertRaises(ValueError):
            self.action('plan', node_ids=[self.node['id']], transforms=['unknown'])
        with self.assertRaises(ValueError):
            self.action('plan', node_ids=[self.node['id']], max_depth=1)
        other = self.w.create_case('Other')['id']
        node = self.w.node(other, 'domain', 'example.org')
        with self.assertRaises(ValueError):
            self.action('plan', node_ids=[node['id']])

    def test_archive_restore_preserves_evidence_links_and_pauses_monitor(self):
        evidence = self.action('manual-evidence', node_id=self.node['id'], source='Fixture', raw={'detail': 'complete'})
        related = self.action('related-node', parent_id=self.node['id'], type='domain', value='example.org', evidence_id=evidence['id'])
        monitor = self.action('monitor', node_id=self.node['id'], transform_id='domain_whois')
        self.action('archive', table='nodes', id=self.node['id'])
        state = self.w.state(self.case)
        self.assertEqual(len(state['nodes']), 1)
        self.assertEqual(state['edges'], [])
        self.assertEqual(len(state['evidence']), 1)
        self.assertFalse(state['monitors'][0]['enabled'])
        with self.assertRaises(ValueError):
            self.action('monitor', id=monitor['id'])
        self.action('restore', table='nodes', id=self.node['id'])
        self.assertEqual(self.w.state(self.case)['edges'][0]['id'], related['edge']['id'])
        self.assertFalse(self.w.state(self.case)['monitors'][0]['enabled'])
        self.action('archive', table='cases', id=self.case)
        self.assertEqual(self.w.state()['cases'], [])
        self.assertEqual(len(self.w.state()['archived_cases']), 1)
        self.action('restore', table='cases', id=self.case)
        self.assertEqual(len(self.w.state()['cases']), 1)

    def test_edits_preserve_source_and_layout_reset(self):
        evidence = self.action('manual-evidence', node_id=self.node['id'], source='Fixture', raw='original source')
        self.action('node-update', id=self.node['id'], value='example.org', label='Renamed')
        self.assertEqual(self.w.store.get('evidence', evidence['id'])['raw'], 'original source')
        self.assertIn('example.com', json.dumps(self.w.store.all('events', self.case)))
        self.action('layout', positions=[{'id': self.node['id'], 'x': 20, 'y': 40}], viewport={'x': 3, 'y': 4, 'k': 1.5})
        self.assertEqual(self.w.state(self.case)['case']['viewport']['k'], 1.5)
        self.action('layout-reset')
        self.assertIsNone(self.w.state(self.case)['nodes'][0]['position'])
        self.assertIsNone(self.w.state(self.case)['case']['viewport'])

    def test_active_collection_blocks_removal_and_credential_changes(self):
        self.action('queue', node_ids=[self.node['id']], transforms=['domain_whois'])
        with self.assertRaises(ValueError):
            self.action('archive', table='cases', id=self.case)
        with self.assertRaises(ValueError):
            self.action('settings', values={}, persist=False)

    def test_settings_session_only_validation_and_no_secret_echo(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.action('settings', values={'SERPER_API_KEY': 'fictional-only-secret'}, persist=False)
            self.assertEqual(os.environ['SERPER_API_KEY'], 'fictional-only-secret')
            self.assertNotIn('fictional-only-secret', json.dumps(result))
            self.assertFalse(self.w.settings.path.exists())
            with self.assertRaises(ValueError):
                self.action('settings', values={'PATH': 'bad'}, persist=False)
            self.action('settings', values={}, remove=['SERPER_API_KEY'], persist=False)
            self.assertNotIn('SERPER_API_KEY', os.environ)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_windows_saved_keys_encrypted_reload_and_remove(self):
        with patch.dict(os.environ, {}, clear=True):
            self.w.settings.update({'SERPER_API_KEY': 'fictional-persisted-secret'})
            self.assertNotIn(b'fictional-persisted-secret', self.w.settings.path.read_bytes())
            os.environ.pop('SERPER_API_KEY')
            reloaded = settings.Settings(self.directory.name)
            self.assertEqual(os.environ['SERPER_API_KEY'], 'fictional-persisted-secret')
            reloaded.update({}, remove=['SERPER_API_KEY'])
            self.assertNotIn('SERPER_API_KEY', settings.Settings(self.directory.name).saved)

    def test_mcp_protocol_and_complete_evidence_over_local_http(self):
        evidence = self.action('manual-evidence', node_id=self.node['id'], source='Fixture', raw={'detail': 'Complete fixture field'})
        server = app.LocalServer(('127.0.0.1', 0), app.BaseHTTPRequestHandler)
        server.RequestHandlerClass = app.handler_for(self.w, server.server_port)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'atlas_evidence', 'arguments': {'case_id': self.case, 'evidence_id': evidence['id']}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'atlas_case', 'arguments': {'case_id': self.case}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'atlas_case', 'arguments': {'case_id': 'bad'}}},
        ]
        try:
            result = subprocess.run([sys.executable, str(Path(hermes_mcp.__file__)), '--port', str(server.server_port)],
                input='\n'.join(json.dumps(m) for m in messages)+'\n', capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(replies), 5)
            self.assertEqual(len(replies[1]['result']['tools']), 24)
            self.assertIn('Complete fixture field', replies[2]['result']['content'][0]['text'])
            self.assertNotIn(self.w.token, result.stdout)
            self.assertNotIn('csrf', replies[3]['result']['content'][0]['text'])
            self.assertTrue(replies[4]['result']['isError'])
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_mcp_invalid_requests_do_not_break_session(self):
        incoming = io.StringIO('bad json\n{"jsonrpc":"2.0","id":2,"method":"initialize","params":null}\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n')
        outgoing = io.StringIO()
        hermes_mcp.serve(None, incoming, outgoing)
        replies = [json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual(replies[-1]['result'], {})

    def test_backup_restores_all_history_without_replaying_requests(self):
        evidence = self.action('manual-evidence', node_id=self.node['id'], source='Fixture', raw={'value': 'complete'})
        report = self.action('report')
        self.action('monitor', node_id=self.node['id'], transform_id='domain_whois')
        self.action('queue', node_ids=[self.node['id']], transforms=['domain_whois'])
        payload = self.w.backup()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(set(archive.namelist()), {'atlas.sqlite3', 'manifest.json'})
            self.assertFalse(json.loads(archive.read('manifest.json'))['credentials_included'])
        backup = Path(self.directory.name) / 'backup.zip'
        backup.write_bytes(payload)
        destination = Path(self.directory.name) / 'restored'
        restored = restore_backup.restore(backup, destination)
        connection = sqlite3.connect(restored)
        try:
            self.assertEqual(json.loads(connection.execute('SELECT data FROM evidence WHERE id=?', (evidence['id'],)).fetchone()[0])['raw']['value'], 'complete')
            self.assertEqual(json.loads(connection.execute('SELECT data FROM reports WHERE id=?', (report['id'],)).fetchone()[0])['text'], report['text'])
            self.assertEqual(json.loads(connection.execute('SELECT data FROM jobs').fetchone()[0])['status'], 'interrupted')
            self.assertFalse(json.loads(connection.execute('SELECT data FROM monitors').fetchone()[0])['enabled'])
        finally:
            connection.close()
        with self.assertRaises(ValueError):
            restore_backup.restore(backup, destination)

    def test_backup_rejects_bad_hash_and_readiness_makes_no_provider_requests(self):
        backup = Path(self.directory.name) / 'bad.zip'
        with zipfile.ZipFile(backup, 'w') as archive:
            archive.writestr('atlas.sqlite3', b'bad database')
            archive.writestr('manifest.json', json.dumps({'format': 'atlas-backup-v1', 'sha256': 'bad'}))
        with self.assertRaises(ValueError):
            restore_backup.restore(backup, Path(self.directory.name) / 'new')
        with patch.object(app.connectors, 'run') as run:
            readiness = self.w.readiness()
            self.assertTrue(all(readiness['checks'].values()))
            self.assertEqual(readiness['implemented_sources'], 83)
            run.assert_not_called()

    def test_agent_answers_validate_case_citations_and_monitor_set_is_explicit(self):
        e = self.action('manual-evidence', node_id=self.node['id'], source='Fixture', raw='Full evidence')
        answer = self.action('save-answer', question='What is known?', answer=f'Synthetic source [E{e["id"]}]', author='Hermes fixture')
        self.assertEqual(answer['evidence_ids'], [e['id']])
        with self.assertRaises(ValueError):
            self.action('save-answer', question='Test', answer='Unsupported [E99999]')
        m = self.action('monitor', node_id=self.node['id'], transform_id='domain_whois')
        self.action('monitor-set', id=m['id'], enabled=False)
        self.action('monitor-set', id=m['id'], enabled=False)
        self.assertFalse(self.w.store.get('monitors', m['id'])['enabled'])

    def test_deep_plan_can_include_sources_for_new_entity_types(self):
        p = self.action('plan', node_ids=[self.node['id']], transforms=['domain_whois', 'github_public_profile'],
                        max_depth=1, auto_apply=True)
        self.assertIn('github_public_profile', p['transforms'])
        self.assertEqual(len(p['seed_requests']), 1)


if __name__ == '__main__':
    unittest.main()
