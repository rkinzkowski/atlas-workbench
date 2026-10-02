"""Atlas: a single-user, localhost investigation workbench. Python 3.11+."""
import argparse
import base64
import contextlib
import datetime as dt
import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import io
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import connectors
import providers
import settings
import workflows
import free_tools

ROOT = Path(__file__).resolve().parent
TABLES = ('cases', 'nodes', 'edges', 'evidence', 'runs', 'jobs', 'events', 'reports', 'monitors', 'answers', 'plans')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def response_changes(before, after):
    """Compare exact JSON types and array positions; never infer entity identity."""
    rows = []
    unchanged = 0
    def walk(left, right, path):
        nonlocal unchanged
        if type(left) is dict and type(right) is dict:
            for key in sorted(left.keys() | right.keys()):
                child = path + '[' + json.dumps(key, ensure_ascii=False) + ']'
                if key not in left:
                    rows.append(dict(path=child, kind='added', after=right[key]))
                elif key not in right:
                    rows.append(dict(path=child, kind='removed', before=left[key]))
                else:
                    walk(left[key], right[key], child)
            if not left and not right:
                unchanged += 1
        elif type(left) is list and type(right) is list:
            for i in range(max(len(left), len(right))):
                child = f'{path}[{i}]'
                if i >= len(left):
                    rows.append(dict(path=child, kind='added', after=right[i]))
                elif i >= len(right):
                    rows.append(dict(path=child, kind='removed', before=left[i]))
                else:
                    walk(left[i], right[i], child)
            if not left and not right:
                unchanged += 1
        elif type(left) is type(right) and left == right:
            unchanged += 1
        else:
            rows.append(dict(path=path, kind='changed', before=left, after=right))
    walk(before, after, '$')
    return {'changes': rows, 'counts': {kind: sum(r['kind'] == kind for r in rows)
            for kind in ('added', 'removed', 'changed')}, 'unchanged_fields': unchanged}


def canonical(kind, value):
    value = str(value).strip()
    if kind in ('domain', 'subdomain', 'email', 'username', 'instagram', 'github'):
        return value.casefold().rstrip('.')
    if kind == 'phone':
        return re.sub(r'[^0-9+]', '', value)
    return value


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.in_transaction = False
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        for table in TABLES:
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL, data TEXT NOT NULL)')
            self.db.execute(f'CREATE INDEX IF NOT EXISTS {table}_case ON {table}(case_id)')
        self.db.commit()

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN')
            self.in_transaction = True
            try:
                yield
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            finally:
                self.in_transaction = False

    def commit(self):
        if not self.in_transaction:
            self.db.commit()

    def all(self, table, case=None):
        with self.lock:
            sql = f'SELECT id,case_id,data FROM {table}' + (' WHERE case_id=?' if case is not None else '') + ' ORDER BY id'
            return [dict(json.loads(d), id=i, case_id=c) for i, c, d in self.db.execute(sql, (case,) if case is not None else ())]

    def get(self, table, identity, case=None):
        with self.lock:
            row = self.db.execute(f'SELECT case_id,data FROM {table} WHERE id=?', (int(identity),)).fetchone()
            if not row or (case is not None and row[0] != case):
                raise ValueError('Record not found in this case.')
            return dict(json.loads(row[1]), id=int(identity), case_id=row[0])

    def add(self, table, case, data):
        with self.lock:
            cursor = self.db.execute(f'INSERT INTO {table}(case_id,data) VALUES(?,?)', (case, json.dumps(connectors.clean(data))))
            self.commit()
            return self.get(table, cursor.lastrowid)

    def update(self, table, identity, **fields):
        with self.lock:
            row = self.get(table, identity)
            case = row.pop('case_id')
            row.pop('id')
            row.update(connectors.clean(fields))
            self.db.execute(f'UPDATE {table} SET data=? WHERE id=?', (json.dumps(row), identity))
            self.commit()
            return self.get(table, identity, case)


class Workbench:
    def __init__(self, path):
        self.store = Store(path)
        self.free_mode_path = Path(path).parent / 'free-mode.json'
        try:
            self.free_only = json.loads(self.free_mode_path.read_text()).get('enabled') is True
        except (OSError, ValueError):
            self.free_only = False
        self.settings = settings.Settings(Path(path).parent)
        self.stop = threading.Event()
        self.token = secrets.token_urlsafe(32)
        self.catalog = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
        # An uncertain paid request is never silently retried after a restart.
        for table in ('jobs', 'runs'):
            for row in self.store.all(table):
                if row.get('status') in ('running', 'cancel_requested'):
                    self.store.update(table, row['id'], status='interrupted', completed_at=now(), message='Server restarted. Review before retrying; the previous request may have incurred provider charges.')

    def event(self, case, message, **fields):
        return self.store.add('events', case, dict(created_at=now(), message=message, **fields))

    def create_case(self, title, description='', demo=False):
        if not str(title).strip():
            raise ValueError('Give the case a name.')
        case = self.store.add('cases', 0, {'title': str(title).strip(), 'description': str(description), 'created_at': now(), 'demo': demo})
        self.event(case['id'], 'Case created')
        return case

    def node(self, case, kind, value, deduplicate=True, **fields):
        value, kind = str(value).strip(), str(kind).strip().lower()
        if not value or len(value) > 1500 or not re.fullmatch(r'[a-z0-9_ -]{1,50}', kind):
            raise ValueError('Enter an entity type and a value under 1,500 characters.')
        with self.store.lock:
            key = kind + ':' + canonical(kind, value)
            for row in (self.store.all('nodes', case) if deduplicate else []):
                if row['key'] == key:
                    return row
            return self.store.add('nodes', case, {**dict(type=kind, identifier=value, label=value, key=key, depth=0,
                review='unreviewed', notes='', position=None, created_at=now()), **fields})

    def edge(self, case, source, target, evidence=None, relationship='related', manual=False, deduplicate=True):
        self.store.get('nodes', source, case)
        self.store.get('nodes', target, case)
        if evidence is not None:
            self.store.get('evidence', evidence, case)
        for e in (self.store.all('edges', case) if deduplicate else []):
            if (e['from'], e['to'], e['evidence_id'], e['relationship']) == (source, target, evidence, relationship):
                return e
        return self.store.add('edges', case, {'from': source, 'to': target, 'evidence_id': evidence, 'relationship': str(relationship), 'manual': manual})

    def sources(self):
        unique = {}
        for category in self.catalog['entities']:
            for t in category['transforms']:
                row = unique.setdefault(t['id'], {'id': t['id'], 'label': t['label'], 'description': t.get('description', ''), 'types': [], 'reference_cost': t.get('credit_cost')})
                types = category.get('entity_type', category['id'])
                row['types'].extend(types if isinstance(types, list) else [types])
        for key, (label, types, credential) in connectors.ADAPTERS.items():
            row = unique.setdefault(key, {'id': key, 'label': label, 'description': 'Atlas connector', 'reference_cost': None})
            row.update(label=label, types=types, credential_env=credential, implemented=True,
                       available=connectors.available(key), status='ready' if connectors.available(key) else 'needs credentials')
            row.update(providers.metadata(key))
            row.update(free_tools.metadata(key))
            if self.free_only and not free_tools.is_free(key):
                row.update(available=False,status='disabled in free mode')
        for row in unique.values():
            row.setdefault('implemented', False)
            row.setdefault('available', False)
            row.setdefault('status', 'connector not built')
            row['types'] = sorted(set(row['types']))
        return list(unique.values())

    def state(self, case=None):
        result = {'cases': self.store.all('cases'), 'sources': self.sources(), 'csrf': self.token,
                  'ai_ready': bool(not self.free_only and os.environ.get('OPENAI_API_KEY') and os.environ.get('OPENAI_MODEL')),
                  'free_only': self.free_only,
                  'ai_context_limit': int(os.environ.get('ATLAS_AI_MAX_CONTEXT_CHARS','200000'))}
        result['archived_cases'] = [c for c in result['cases'] if c.get('archived')]
        result['cases'] = [c for c in result['cases'] if not c.get('archived')]
        if case:
            result['case'] = self.store.get('cases', case)
            for table in TABLES[1:]:
                result[table] = self.store.all(table, case)
            # Large raw responses are loaded on demand from the evidence endpoint.
            result['evidence'] = [{k: v for k, v in e.items() if k != 'raw'} for e in result['evidence']]
            result['reports'] = [{k:v for k,v in r.items() if k != 'text'} for r in result['reports']]
            result['trash'] = [{**r, 'table': t} for t in ('nodes', 'edges', 'answers', 'monitors')
                               for r in result[t] if r.get('archived')]
            for table in ('nodes', 'edges', 'answers', 'monitors'):
                result[table] = [r for r in result[table] if not r.get('archived')]
            visible = {n['id'] for n in result['nodes']}
            result['edges'] = [e for e in result['edges'] if e['from'] in visible and e['to'] in visible]
        return result

    def readiness(self):
        sources = self.sources()
        runs = self.store.all('runs')
        with self.store.lock:
            database_ok = self.store.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        for source in sources:
            recent = [r for r in runs if r.get('transform_id') == source['id'] and r.get('status') in ('done', 'failed', 'partial', 'interrupted')]
            source['last_outcome'] = ({k: recent[-1].get(k) for k in ('id', 'case_id', 'status', 'completed_at', 'message')}
                                      if recent else None)
        return {'configured_sources': sum(s['available'] for s in sources),
                'implemented_sources': sum(s['implemented'] for s in sources),
                'sources': sources, 'storage': 'Local SQLite', 'keys': self.settings.status(),
                'active_jobs': sum(j['status'] in ('queued', 'running', 'cancel_requested') for j in self.store.all('jobs')),
                'checks': {'database': database_ok,
                           'hermes_bridge': (ROOT / 'hermes_mcp.py').is_file(),
                           'static_files': all((ROOT / 'static' / f).is_file() for f in ('app.js', 'style.css', 'index.html'))}}

    def backup(self):
        # SQLite's backup API produces a consistent snapshot while the app is running.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='atlas-backup-') as directory:
            path = Path(directory) / 'atlas.sqlite3'
            with self.store.lock:
                target = sqlite3.connect(path)
                try:
                    self.store.db.backup(target)
                finally:
                    target.close()
            database = path.read_bytes()
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('atlas.sqlite3', database)
            archive.writestr('manifest.json', json.dumps({'format': 'atlas-backup-v1', 'created_at': now(),
                'sha256': hashlib.sha256(database).hexdigest(), 'credentials_included': False, 'free_only':self.free_only,
                'note': 'Complete local case database. Restore with Restore-Atlas.ps1 while Atlas is stopped. Provider keys are separate.'}))
        return output.getvalue()

    def save_evidence(self, case, node_id, transform, result, **extra):
        result = connectors.clean(result)
        raw = connectors.clean(result.get('raw', {}))
        entities = connectors.clean(result.get('entities', []))
        for e in entities:
            e['entity_key'] = digest([e.get('type', 'unknown'), canonical(e.get('type', 'unknown'), e.get('identifier', e.get('label', '')))])
        return self.store.add('evidence', case, dict(node_id=node_id, transform_id=transform, source=result.get('source', transform),
            timestamp=now(), url=result.get('url'), snippet=str(result.get('snippet', '')), raw=raw,
            sha256=digest(raw), entities=entities, applied_keys=[], review='unreviewed', notes='',
            collection=result.get('collection', {}), visibility=result.get('visibility', {'authentication_secrets_protected': True, 'content_masking':False}),
            request_options=result.get('request_options', {}), no_match=result.get('no_match', False), **extra))

    def lookup_options(self, request):
        options = request.get('options', {})
        if not isinstance(options, dict):
            raise ValueError('Lookup options must be an object.')
        result = {k: options[k] for k in ('premium','exact_match','caller_name','location','company','school','locality','region','postal_code','cursor') if k in options}
        result['max_pages'] = int(options.get('max_pages', 1))
        result['page'] = int(options.get('page', 1))
        if not 1 <= result['max_pages'] <= 20 or not 1 <= result['page'] <= 100:
            raise ValueError('Choose 1–20 pages per connector and a search page between 1 and 100.')
        if any(not isinstance(result[k],bool) for k in ('premium','exact_match','caller_name') if k in result):
            raise ValueError('Lookup switches must be true or false.')
        for key in ('location','company','school','locality','region','postal_code','cursor'):
            if key in result and (not isinstance(result[key],(str,int)) or len(str(result[key])) > 10000):
                raise ValueError('Invalid lookup context or continuation cursor.')
        result.update(free_tools.options(options))
        return result

    def apply(self, case, evidence_id, keys=None):
        with self.store.lock:
            evidence = self.store.get('evidence', evidence_id, case)
            parent = self.store.get('nodes', evidence['node_id'], case)
            applied = set(evidence.get('applied_keys', []))
            count = 0
            for e in evidence['entities']:
                if e['entity_key'] in applied or (keys is not None and e['entity_key'] not in keys):
                    continue
                value = e.get('identifier') or e.get('label')
                if not value:
                    continue
                n = self.node(case, e.get('type', 'unknown'), value, depth=parent['depth'] + 1, origin='evidence')
                if n['id'] != parent['id']:
                    self.edge(case, parent['id'], n['id'], evidence_id, e.get('relationship', 'observed in source'))
                applied.add(e['entity_key'])
                count += 1
            self.store.update('evidence', evidence_id, applied_keys=sorted(applied))
            self.event(case, f'Applied {count} extracted entities', evidence_id=evidence_id)
            return count

    def queue(self, case, request):
        if self.store.get('cases', case).get('archived'):
            raise ValueError('Restore this case before collecting evidence.')
        ids = [int(i) for i in request.get('node_ids', [])]
        if not ids:
            raise ValueError('Select at least one seed entity.')
        for i in ids:
            if self.store.get('nodes', i, case).get('archived'):
                raise ValueError('Restore removed entities before collecting evidence.')
        transforms = list(dict.fromkeys(request.get('transforms', [])))
        if self.free_only and any(not free_tools.is_free(t) for t in transforms):
            raise ValueError('Free mode blocks paid and AI providers. Choose a free source or explicitly turn off free mode.')
        if not transforms or any(not connectors.available(t) for t in transforms):
            raise ValueError('Choose connected sources. Unconnected sources cannot be queued.')
        if not any(self.store.get('nodes', i, case)['type'] in connectors.ADAPTERS[t][1] or '*' in connectors.ADAPTERS[t][1] for i in ids for t in transforms):
            raise ValueError('None of the selected sources accept the selected entity types.')
        limit, depth = int(request.get('max_runs', 5)), int(request.get('max_depth', 0))
        if not 1 <= limit <= 30 or not 0 <= depth <= 2:
            raise ValueError('Use 1–30 connector runs and 0–2 expansion levels.')
        if depth and not request.get('auto_apply'):
            raise ValueError('Expansion requires automatic application of extracted leads. Otherwise choose seeds only.')
        options = self.lookup_options(request)
        job = self.store.add('jobs', case, {'status': 'queued', 'phase': 'queued', 'created_at': now(), 'node_ids': ids,
            'transforms': transforms, 'max_runs': limit, 'max_depth': depth, 'auto_apply': bool(request.get('auto_apply', False)),
            'completed_runs': 0, 'failed_runs': 0, 'monitor_id': request.get('monitor_id'), 'options':options, 'free_only':self.free_only, 'message': 'Waiting for worker'})
        self.event(case, 'Investigation queued', job_id=job['id'], phase='queued')
        return job

    def phase(self, job, phase):
        self.store.update('jobs', job['id'], phase=phase)
        self.event(job['case_id'], phase.replace('_', ' ').capitalize(), job_id=job['id'], phase=phase)

    def cancelled(self, identity):
        return self.stop.is_set() or self.store.get('jobs', identity)['status'] == 'cancel_requested'

    def execute_job(self, job):
        case, jid = job['case_id'], job['id']
        self.store.update('jobs', jid, status='running', started_at=now(), message='Collecting from connected sources')
        done, failed, attempted = 0, 0, set()
        current = [self.store.get('nodes', i, case) for i in job['node_ids']]
        try:
            stages = list(range(job['max_depth'] + 1)) + (['web'] if 'openai_web_search' in job['transforms'] else [])
            for stage in stages:
                depth = 0 if stage == 'web' else stage
                if stage == 'web':
                    current = [self.store.get('nodes', i, case) for i in job['node_ids']]
                if self.cancelled(jid):
                    break
                if stage != 'web' and not any(t != 'openai_web_search' for t in job['transforms']):
                    continue
                self.phase(job, 'web_corroboration' if stage == 'web' else ('internal_collection', 'graph_expansion', 'deep_graph_expansion')[depth])
                for node in current:
                    for transform in job['transforms']:
                        if (transform == 'openai_web_search') != (stage == 'web'):
                            continue
                        types = connectors.ADAPTERS[transform][1]
                        if node['review'] == 'excluded' or ('*' not in types and node['type'] not in types) or (node['id'], transform) in attempted:
                            continue
                        if self.cancelled(jid) or done + failed >= job['max_runs']:
                            break
                        attempted.add((node['id'], transform))
                        self.phase(job, 'web_corroboration' if transform == 'openai_web_search' else ('internal_collection', 'graph_expansion', 'deep_graph_expansion')[depth])
                        run = self.store.add('runs', case, {'job_id': jid, 'node_id': node['id'], 'transform_id': transform, 'status': 'running', 'started_at': now(), 'evidence_id': None})
                        self.event(case, f'Running {connectors.ADAPTERS[transform][0]}', job_id=jid, run_id=run['id'], node_id=node['id'])
                        try:
                            if (self.free_only or job.get('free_only')) and not free_tools.is_free(transform):
                                raise ValueError('Free mode blocked this source before making a request.')
                            call_options = {**job.get('options',{}), '_cancelled':lambda:self.cancelled(jid)}
                            result = connectors.run(transform, node, options=call_options)
                            evidence = self.save_evidence(case, node['id'], transform, result)
                            partial = bool(result.get('collection',{}).get('error'))
                            self.store.update('runs', run['id'], status='partial' if partial else 'done', completed_at=now(), evidence_id=evidence['id'],
                                              no_entities_extracted=not bool(evidence['entities']), collection=result.get('collection',{}))
                            if job['auto_apply'] and not self.cancelled(jid):
                                self.apply(case, evidence['id'])
                            if job.get('monitor_id'):
                                self.record_monitor_result(case, job['monitor_id'], evidence)
                            if partial:
                                failed += 1
                            else:
                                done += 1
                            self.event(case, 'Evidence captured; extracted entities are available for review.', job_id=jid, evidence_id=evidence['id'])
                        except Exception as error:
                            failed += 1
                            message = str(connectors.clean(str(error)))
                            self.store.update('runs', run['id'], status='failed', completed_at=now(), message=message, source_response=getattr(error,'response',None))
                            self.event(case, 'Source failed: ' + message, job_id=jid, run_id=run['id'])
                        self.store.update('jobs', jid, completed_runs=done, failed_runs=failed)
                if done + failed >= job['max_runs']:
                    break
                if not job['auto_apply']:
                    continue
                # Expand only nodes reached by this job's evidence, not unrelated case nodes.
                evidence_ids = {r['evidence_id'] for r in self.store.all('runs', case) if r.get('job_id') == jid and r.get('evidence_id')}
                next_ids = {e['to'] for e in self.store.all('edges', case) if e['evidence_id'] in evidence_ids}
                current = [n for n in self.store.all('nodes', case) if n['id'] in next_ids]
            if self.cancelled(jid):
                status, message = 'cancelled', 'Stopped after the active request finished. Captured evidence was retained.'
            else:
                if not job.get('monitor_id'):
                    self.phase(job, 'report_synthesis')
                    self.report(case)
                status = 'completed_with_errors' if failed else 'completed'
                message = f'{done} completed, {failed} failed. ' + ('Run limit reached.' if done + failed >= job['max_runs'] else 'Selected sources finished.')
            self.store.update('jobs', jid, status=status, phase=status, completed_at=now(), message=message)
            self.event(case, message, job_id=jid, phase=status)
        except Exception as error:
            self.store.update('jobs', jid, status='failed', message=str(connectors.clean(str(error))), completed_at=now())

    def worker(self):
        while not self.stop.wait(0.4):
            for monitor in self.store.all('monitors'):
                if monitor.get('enabled') and monitor['next_run'] <= time.time():
                    self.store.update('monitors', monitor['id'], next_run=time.time() + monitor['interval_seconds'])
                    active = any(j.get('monitor_id') == monitor['id'] and j['status'] in ('queued', 'running') for j in self.store.all('jobs'))
                    if not active:
                        try:
                            self.queue(monitor['case_id'], {'node_ids': [monitor['node_id']], 'transforms': [monitor['transform_id']], 'max_runs': 1, 'monitor_id': monitor['id']})
                        except ValueError:
                            self.store.update('monitors', monitor['id'], enabled=False)
                            self.event(monitor['case_id'], 'Monitor paused because its connector is unavailable.')
            queued = next((j for j in self.store.all('jobs') if j['status'] == 'queued'), None)
            if queued:
                self.execute_job(queued)

    def compare_evidence(self, case, before_id, after_id):
        self.store.get('cases', case)
        before = self.store.get('evidence', before_id, case)
        after = self.store.get('evidence', after_id, case)
        result = response_changes(before['raw'], after['raw'])
        fields = ('id', 'node_id', 'transform_id', 'source', 'timestamp', 'sha256', 'collection', 'request_options')
        result.update(before={k: before.get(k) for k in fields}, after={k: after.get(k) for k in fields})
        result['same_source_entity'] = all(before.get(k) == after.get(k) for k in ('node_id', 'transform_id'))
        result['same_request_options'] = before.get('request_options', {}) == after.get('request_options', {})
        return result

    def record_monitor_result(self, case, monitor_id, evidence):
        monitor = self.store.get('monitors', monitor_id, case)
        previous_id = monitor.get('last_evidence_id')
        if not previous_id and monitor.get('last_hash'):
            matches = [e for e in self.store.all('evidence', case)
                       if e['id'] < evidence['id'] and e.get('sha256') == monitor['last_hash']
                       and e.get('node_id') == monitor['node_id'] and e.get('transform_id') == monitor['transform_id']]
            previous_id = matches[-1]['id'] if matches else None
        fields = dict(last_hash=evidence['sha256'], last_checked=now(), last_evidence_id=evidence['id'])
        if monitor.get('last_hash') and monitor['last_hash'] != evidence['sha256']:
            counts = self.compare_evidence(case, previous_id, evidence['id'])['counts'] if previous_id else None
            fields.update(previous_evidence_id=previous_id, last_change_evidence_id=evidence['id'], last_change_counts=counts)
            self.event(case, 'Monitor detected a changed source response; compare the complete field values.',
                       monitor_id=monitor_id, evidence_id=evidence['id'], previous_evidence_id=previous_id, change_counts=counts)
        self.store.update('monitors', monitor_id, **fields)

    def evidence_document(self, evidence):
        return f"[E{evidence['id']}] {evidence['source']} | {evidence['timestamp']} | review: {evidence['review']}\n" + json.dumps(connectors.clean(evidence),ensure_ascii=False,indent=2)

    def search_evidence(self, case, query, include_excluded=True):
        terms = set(re.findall(r'\w+', query.lower()))
        results=[]
        def fields(value,path='$'):
            if isinstance(value,dict):
                for k,v in value.items():
                    yield from fields(v,path+'['+json.dumps(k,ensure_ascii=False)+']')
            elif isinstance(value,list):
                for i,v in enumerate(value):
                    yield from fields(v,path+f'[{i}]')
            else:
                yield path,json.dumps(value,ensure_ascii=False)
        for e in self.store.all('evidence',case):
            if not include_excluded and e['review']=='excluded':
                continue
            matches=[{'path':path,'value':value} for path,value in fields(connectors.clean(e)) if any(t in (path+' '+value).lower() for t in terms)]
            if matches:
                results.append({'id':e['id'],'source':e['source'],'review':e['review'],'matches':matches})
        return results

    def context(self, case, question=''):
        evidence = [e for e in self.store.all('evidence', case) if e['review'] != 'excluded']
        context='\n\n'.join(self.evidence_document(e) for e in evidence)
        maximum=int(os.environ.get('ATLAS_AI_MAX_CONTEXT_CHARS','200000'))
        if len(context)>maximum:
            raise ValueError(f'Full evidence requires {len(context):,} characters; the configured AI input limit is {maximum:,}. No excerpts were substituted and no AI request was sent. Generate the complete evidence report, or configure ATLAS_AI_MAX_CONTEXT_CHARS for a model that accepts this input.')
        return evidence,context

    def report(self, case, use_ai=False):
        if use_ai and self.free_only:
            raise ValueError('Free mode uses complete local reports; AI synthesis is disabled.')
        c = self.store.get('cases', case)
        evidence = self.store.all('evidence', case)
        nodes, edges = self.store.all('nodes', case), self.store.all('edges', case)
        failed = [r for r in self.store.all('runs', case) if r['status'] in ('failed', 'interrupted','partial')]
        included = [e for e in evidence if e['review'] != 'excluded']
        lines = [c['title'], f"Prepared {now()}", 'FICTIONAL DEMONSTRATION CASE' if c.get('demo') else 'Complete investigation evidence report',
                 f"{len(nodes)} entities · {len(edges)} links · {len(evidence)} evidence items · {len(failed)} failed or interrupted runs",
                 'Assessment', 'This is an evidence inventory, not a determination of identity. Links express source observations. Corroboration and human review are required.']
        ai_ids = []
        if use_ai:
            selected, context = self.context(case)
            if not selected:
                raise ValueError('Add evidence before requesting AI synthesis.')
            answer = connectors.ai('Write an evidence-grounded interpretation: confirmed observations, possible connections, contradictions, and gaps. Preserve important investigative details. The complete source records are appended separately and must not be replaced by this interpretation. Only cite the supplied evidence.\n' + context)['snippet']
            ai_ids = [e['id'] for e in selected]
            invalid = {int(x) for x in re.findall(r'\[E(\d+)\]', answer)} - set(ai_ids)
            if invalid:
                raise ValueError('AI cited evidence outside its supplied context. The report was not saved.')
            lines += ['AI-assisted interpretation — requires review', answer, f'AI received all fields of all {len(selected)} non-excluded evidence records. Its narrative is an interpretation; complete records follow.']
        lines += ['Complete evidence records', f'All stored fields are included for {len(included)} evidence records. Authentication secrets are protected. No contact-field masking or excerpt limits are applied.']
        for e in included:
            lines.append(self.evidence_document(e))
        excluded=[{'id':e['id'],'source':e['source'],'review':e['review']} for e in evidence if e['review']=='excluded']
        lines += ['Analyst-excluded evidence', json.dumps(excluded,ensure_ascii=False,indent=2),
                  'These explicit analyst exclusions remain available in the vault and complete case export.',
                  'Complete graph snapshot',json.dumps(connectors.clean({'nodes':nodes,'edges':edges}),ensure_ascii=False,indent=2),
                  'Collection outcomes',json.dumps(connectors.clean(self.store.all('runs',case)),ensure_ascii=False,indent=2)]
        lines += ['Gaps and limitations', f'{len(failed)} failed or interrupted source runs; {sum(e["review"] == "unreviewed" for e in evidence)} evidence items await review.',
                  'Unconnected providers were not queried. Source coverage is not exhaustive. Imports are historical evidence, not fresh lookups. Response hashes detect local changes and do not authenticate a source.']
        version = len(self.store.all('reports', case)) + 1
        result = self.store.add('reports', case, {'version': version, 'created_at': now(), 'text': connectors.clean('\n\n'.join(lines)), 'evidence_ids': [e['id'] for e in included], 'ai_evidence_ids': ai_ids, 'ai': use_ai, 'title': c['title'], 'format':'complete-evidence-v2','excluded_evidence_ids':[e['id'] for e in excluded]})
        self.event(case, f'Report version {version} saved', report_id=result['id'])
        return result

    def import_data(self, payload, title='Imported investigation'):
        """Read response bodies only; never retain HAR requests, headers, or cookies."""
        obj = payload
        if isinstance(obj, dict) and 'log' in obj:
            candidates = []
            for entry in obj.get('log', {}).get('entries', []):
                path = urllib.parse.urlsplit(entry.get('request', {}).get('url', '')).path
                if not re.fullmatch(r'/workbench/investigations/\d+', path):
                    continue
                content = entry.get('response', {}).get('content', {})
                try:
                    text = content.get('text', '')
                    if content.get('encoding') == 'base64':
                        text = base64.b64decode(text).decode('utf-8')
                    candidate = json.loads(text)
                    if isinstance(candidate, dict) and 'graph' in candidate:
                        candidates.append(candidate)
                except (ValueError, UnicodeError):
                    pass
            if not candidates:
                raise ValueError('No full investigation response found. Use a HAR with response content or graph/evidence JSON.')
            obj = candidates[-1]
        obj = connectors.clean(obj)
        atlas = isinstance(obj, dict) and obj.get('format') == 'atlas-case-v1'
        if atlas:
            graph = {'nodes': obj.get('nodes', []), 'edges': obj.get('edges', [])}
            items = obj.get('evidence', [])
        else:
            graph = obj.get('graph', {}) if isinstance(obj, dict) else {}
            items = obj if isinstance(obj, list) else obj.get('evidence_items', obj.get('evidence', []))
        if not isinstance(items, list) or not isinstance(graph, dict) or not (items or graph.get('nodes')):
            raise ValueError('Expected graph JSON, a list of evidence items, or an Atlas case export.')
        if len(items) > 5000 or len(graph.get('nodes', [])) > 10000 or len(graph.get('edges', [])) > 30000:
            raise ValueError('This import exceeds the local case size limit.')
        for collection in (items, graph.get('nodes', []), graph.get('edges', [])):
            if any(not isinstance(x, dict) for x in collection):
                raise ValueError('Invalid record in import.')
        for n in graph.get('nodes', []):
            if not n.get('id') or not (n.get('identifier') or n.get('label')):
                raise ValueError('Every imported node needs an ID and an identifier or label.')
        case = self.create_case(title, 'Imported historical records. Source identifiers are retained for traceability.')
        cid, node_map, evidence_map = case['id'], {}, {}
        for n in graph.get('nodes', []):
            metadata = n.get('metadata') or {}
            kind = n.get('type') or n.get('entity_type') or 'unknown'
            node = self.node(cid, kind, n.get('identifier') or n['label'], deduplicate=False, origin='import', source_id=n['id'], source_record=n,
                             depth=int(n.get('depth', metadata.get('depth', 0))), notes=str(n.get('notes') or ''), position=n.get('position') if atlas else None)
            node_map[str(n['id'])] = node['id']
        for e in items:
            old_node = str(e.get('node_id', 'unassigned'))
            if old_node not in node_map:
                node_map[old_node] = self.node(cid, 'unknown', 'Imported node ' + old_node, origin='import', source_id=e.get('node_id'))['id']
            annotations = e.get('entities', e.get('meta', []))
            entities = [dict(a, identifier=a.get('identifier') or a.get('label', '')) for a in annotations if isinstance(a, dict)] if isinstance(annotations, list) else []
            result = {'source': e.get('source', 'Imported evidence'), 'snippet': e.get('snippet', ''), 'url': e.get('url'), 'entities': entities, 'raw': e.get('raw', e)}
            saved = self.save_evidence(cid, node_map[old_node], e.get('transform_id', 'import'), result, origin='import', source_id=e.get('id'), source_timestamp=e.get('timestamp'))
            self.store.update('evidence', saved['id'], timestamp=e.get('timestamp') or saved['timestamp'])
            evidence_map[str(e.get('id'))] = saved['id']
        skipped = 0
        for e in graph.get('edges', []):
            a, b = node_map.get(str(e.get('from'))), node_map.get(str(e.get('to')))
            eid = evidence_map.get(str(e.get('evidence_id')))
            if a and b:
                edge = self.edge(cid, a, b, eid, e.get('relationship') or e.get('label') or 'imported relationship', manual=bool(e.get('manual', e.get('is_manual', False))), deduplicate=False)
                self.store.update('edges', edge['id'], source_id=e.get('id'), source_record=e)
            else:
                skipped += 1
        # Mark already materialized annotations, without assuming every annotation became a node.
        for e in self.store.all('evidence', cid):
            linked = {edge['to'] for edge in self.store.all('edges', cid) if edge['evidence_id'] == e['id']}
            node_keys = {n['key'] for n in self.store.all('nodes', cid) if n['id'] in linked}
            keys = [a['entity_key'] for a in e['entities'] if a.get('type', 'unknown') + ':' + canonical(a.get('type', 'unknown'), a.get('identifier', '')) in node_keys]
            self.store.update('evidence', e['id'], applied_keys=keys)
        for r in (obj.get('transform_runs', obj.get('runs', [])) if isinstance(obj, dict) else []):
            if not isinstance(r, dict):
                continue
            self.store.add('runs', cid, {'origin': 'import', 'source_id': r.get('id'), 'node_id': node_map.get(str(r.get('node_id'))), 'transform_id': r.get('transform_id', ''),
                'status': r.get('status', 'unknown'), 'message': r.get('log', r.get('message', '')), 'started_at': r.get('ran_at', r.get('started_at')), 'completed_at': r.get('completed_at'),
                'evidence_id': evidence_map.get(str(r.get('evidence_item_id', r.get('evidence_id'))))})
        self.event(cid, f'Imported {len(node_map)} source nodes and {len(items)} evidence records; {skipped} dangling edges skipped. No lookups were performed.')
        return case

    def action(self, body):
        if body.get('action') == 'free-mode':
            enabled = body.get('enabled')
            if type(enabled) is not bool:
                raise ValueError('Choose free mode on or off.')
            with self.store.lock:
                if any(j['status'] in ('running','cancel_requested') for j in self.store.all('jobs')):
                    raise ValueError('Stop active collection before changing free mode.')
                pending = self.free_mode_path.with_suffix('.tmp')
                pending.write_text(json.dumps({'enabled':enabled}),encoding='utf-8')
                pending.replace(self.free_mode_path)
                self.free_only = enabled
                if enabled:
                    for monitor in self.store.all('monitors'):
                        if monitor.get('enabled') and not free_tools.is_free(monitor['transform_id']):
                            self.store.update('monitors',monitor['id'],enabled=False)
                            self.event(monitor['case_id'],'Paid monitor paused by free mode.',monitor_id=monitor['id'])
                    for job in self.store.all('jobs'):
                        if job['status']=='queued' and any(not free_tools.is_free(t) for t in job['transforms']):
                            self.store.update('jobs',job['id'],status='cancelled',phase='cancelled',message='Queued paid work cancelled by free mode.')
            return {'free_only':self.free_only}
        if body.get('action') == 'tool-evidence':
            tool = next((t for t in free_tools.LIBRARY if t[0]==body.get('tool_id')),None)
            if not tool:
                raise ValueError('Choose a known tool from the library.')
            return workflows.handle(self,{**body,'action':'manual-evidence','source':tool[1]+' · imported output',
                'url':tool[2], 'notes':'Imported tool output supplied by the analyst; Atlas did not rerun or verify the tool. '+str(body.get('notes',''))})
        if body.get('action') == 'settings':
            if any(workflows.active(self, c['id']) for c in self.store.all('cases')):
                raise ValueError('Stop active collection before changing provider settings.')
            return self.settings.update(body.get('values', {}), body.get('remove', []), bool(body.get('persist', True)))
        if body.get('action') in workflows.ACTIONS:
            return workflows.handle(self, body)
        action = body.get('action')
        if action == 'lookup':
            with self.store.transaction():
                kind, value = str(body.get('type','')).strip(), str(body.get('value','')).strip()
                if not value:
                    raise ValueError('Enter a lookup value.')
                if body.get('attach_case_id'):
                    case = self.store.get('cases', int(body['attach_case_id']))
                else:
                    case = self.create_case(kind.replace('_',' ').title() + ' lookup · ' + value[:100], 'Standalone lookup. Full returned source responses are preserved. Matching identifiers do not establish identity.')
                seed = self.node(case['id'],kind,value,origin='user')
                job = self.queue(case['id'], {'node_ids':[seed['id']], 'transforms':body.get('transforms',[]),
                                              'max_runs':max(1,len(body.get('transforms',[]))), 'options':body.get('options',{})})
            return {'id':case['id'],'case_id':case['id'],'job_id':job['id'],'node_id':seed['id']}
        if action == 'case':
            with self.store.transaction():
                case = self.create_case(body.get('title', ''), body.get('description', ''))
                for seed in body.get('seeds', []):
                    self.node(case['id'], seed['type'], seed['value'], origin='user')
            return case
        if action == 'import':
            with self.store.transaction():
                return self.import_data(body['payload'], body.get('title', 'Imported investigation'))
        if action == 'demo':
            c = self.create_case('Northstar · fictional demo', 'A fictional case showing evidence review and graph relationships. No live searches were performed.', True)
            n = self.node(c['id'], 'domain', 'northstar.example', origin='demo')
            e = self.save_evidence(c['id'], n['id'], 'demo_fixture', {'source': 'Fictional demonstration document', 'snippet': 'This invented page links to hello@northstar.example and a fictional partner, Cedar Studio. These records demonstrate provenance and do not describe real people or companies.',
                'raw': {'fictional': True, 'document': 'Demo contact page'}, 'entities': [connectors.entity('email', 'hello@northstar.example', 'contact address'), connectors.entity('organization', 'Cedar Studio (fictional)', 'listed partner')]}, origin='demo')
            self.apply(c['id'], e['id'])
            self.report(c['id'])
            return c
        case = int(body['case_id'])
        self.store.get('cases', case)
        if action == 'node':
            return self.node(case, body['type'], body['value'], origin='user')
        if action == 'edge':
            return self.edge(case, int(body['from']), int(body['to']), body.get('evidence_id'), body.get('relationship', 'manual relationship'), True)
        if action == 'review':
            table = body['table']
            if table not in ('nodes', 'evidence') or body['review'] not in ('unreviewed', 'supported', 'disputed', 'excluded'):
                raise ValueError('Invalid review status.')
            self.store.get(table, body['id'], case)
            return self.store.update(table, body['id'], review=body['review'], notes=str(body.get('notes', '')))
        if action == 'layout':
            if 'viewport' in body:
                viewport = {k: float(body['viewport'][k]) for k in ('x', 'y', 'k')}
                if not all(-100000 <= viewport[k] <= 100000 for k in ('x', 'y')) or not .01 <= viewport['k'] <= 100:
                    raise ValueError('Invalid graph view.')
                self.store.update('cases', case, viewport=viewport)
            for position in body['positions'][:10000]:
                self.store.get('nodes', position['id'], case)
                x, y = float(position['x']), float(position['y'])
                if not (-100000 <= x <= 100000 and -100000 <= y <= 100000):
                    raise ValueError('Invalid graph position.')
                self.store.update('nodes', position['id'], position={'x': x, 'y': y})
            return {'saved': True}
        if action == 'apply':
            return {'applied': self.apply(case, int(body['evidence_id']), body.get('keys'))}
        if action == 'extract':
            evidence = self.store.get('evidence', int(body['evidence_id']), case)
            entities = providers.entities(evidence['raw'])
            for e in entities:
                e['entity_key'] = digest([e['type'], canonical(e['type'], e['identifier'])])
            merged = {e['entity_key']: e for e in evidence['entities'] + entities}
            return self.store.update('evidence', evidence['id'], entities=list(merged.values()))
        if action == 'queue':
            return self.queue(case, body)
        if action == 'cancel':
            job = self.store.get('jobs', body['id'], case)
            if job['status'] not in ('queued', 'running'):
                raise ValueError('This job is no longer active.')
            return self.store.update('jobs', job['id'], status='cancelled' if job['status'] == 'queued' else 'cancel_requested')
        if action == 'retry':
            run = self.store.get('runs', body['id'], case)
            previous = self.store.get('jobs',run['job_id'],case).get('options',{}) if run.get('job_id') else {}
            return self.queue(case, {'node_ids': [run['node_id']], 'transforms': [run['transform_id']], 'max_runs': 1, 'options':previous})
        if action == 'continue':
            evidence = self.store.get('evidence',body['evidence_id'],case)
            cursor = evidence.get('collection',{}).get('next_cursor')
            if not cursor:
                raise ValueError('This response contains no continuation cursor.')
            return self.queue(case, {'node_ids':[evidence['node_id']], 'transforms':[evidence['transform_id']], 'max_runs':1,
                                    'options':{**evidence.get('request_options',{}),'cursor':cursor,'max_pages':int(body.get('max_pages',1))}})
        if action == 'report':
            return self.report(case, bool(body.get('ai', False)))
        if action == 'question':
            question = str(body['question']).strip()
            if not question or not self.store.all('evidence',case):
                raise ValueError('Enter a question and add evidence to this case.')
            if body.get('ai'):
                if self.free_only:
                    raise ValueError('Free mode uses local evidence search; AI answers are disabled.')
                selected, context = self.context(case, question)
                answer = connectors.ai('Answer this question only using the supplied evidence. Question: ' + json.dumps(question) + '\nEvidence:\n' + context)['snippet']
                if {int(x) for x in re.findall(r'\[E(\d+)\]', answer)} - {e['id'] for e in selected}:
                    raise ValueError('The answer contained an unsupported citation and was not saved.')
            else:
                selected=self.search_evidence(case,question)
                answer = 'Full-field evidence search (includes analyst-excluded records, labelled below):\n\n' + ('\n\n'.join(f"[E{e['id']}] {e['source']} | review: {e['review']}\n" + '\n'.join(m['path']+' = '+m['value'] for m in e['matches']) for e in selected) or 'No matching evidence fields found.')
            return self.store.add('answers', case, {'question': question, 'answer': answer, 'evidence_ids': [e['id'] for e in selected], 'ai': bool(body.get('ai')), 'created_at': now()})
        if action == 'monitor':
            if body.get('id'):
                m = self.store.get('monitors', body['id'], case)
                if m.get('archived') or self.store.get('cases', case).get('archived') or self.store.get('nodes', m['node_id'], case).get('archived'):
                    raise ValueError('Restore this monitor, its entity, and its case before resuming it.')
                if not m['enabled'] and self.free_only and not free_tools.is_free(m['transform_id']):
                    raise ValueError('Paid monitors are disabled in free mode.')
                return self.store.update('monitors', m['id'], enabled=not m['enabled'])
            node = self.store.get('nodes', body['node_id'], case)
            transform = body['transform_id']
            if self.free_only and not free_tools.is_free(transform):
                raise ValueError('Paid monitors are disabled in free mode.')
            if not connectors.available(transform) or ('*' not in connectors.ADAPTERS[transform][1] and node['type'] not in connectors.ADAPTERS[transform][1]):
                raise ValueError('Choose a connected source compatible with this node.')
            interval = max(3600, min(int(body.get('interval_seconds', 86400)), 2592000))
            return self.store.add('monitors', case, {'node_id': node['id'], 'transform_id': transform, 'interval_seconds': interval, 'next_run': time.time() + interval, 'enabled': True, 'last_hash': None})
        raise ValueError('Unknown action.')


def report_html(report):
    safe = html.escape(report['text'])
    safe = re.sub(r'\[E(\d+)\]', r'<a href="/?case=' + str(report['case_id']) + r'&evidence=\1">[E\1]</a>', safe)
    return '<!doctype html><meta charset="utf-8"><title>Atlas report</title><style>body{font:16px/1.65 system-ui;max-width:850px;margin:50px auto;padding:20px;color:#172e36}pre{white-space:pre-wrap;font:inherit}button{padding:12px}a{color:#007b77}@media print{button{display:none}body{margin:0}}</style><button onclick="window.print()">Print / save PDF</button><pre>' + safe + '</pre>'


def handler_for(app, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Request paths can contain identifiers; do not log them.

        def respond(self, status, body, content='application/json; charset=utf-8', attachment=None):
            data = json.dumps(connectors.clean(body)).encode() if content.startswith('application/json') else body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(data)))
            if attachment:
                self.send_header('Content-Disposition', 'attachment; filename="' + attachment + '"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {'error': 'Local access only.'})
            path = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(path.query)
            try:
                case = int(query['case'][0]) if query.get('case') else None
                if path.path == '/api/state':
                    return self.respond(200, app.state(case))
                if path.path == '/api/settings':
                    return self.respond(200, app.settings.status())
                if path.path == '/api/readiness':
                    return self.respond(200, app.readiness())
                if path.path == '/api/free-tools':
                    return self.respond(200, {'free_only':app.free_only,'tools':free_tools.library(),
                        'installation':free_tools.manifest(),'runtime_ready':free_tools.python_path().is_file()})
                if path.path == '/api/backup':
                    return self.respond(200, app.backup(), 'application/zip', 'atlas-workspace-backup.zip')
                if path.path == '/api/hermes-config':
                    import hermes_mcp
                    return self.respond(200, hermes_mcp.config(port), 'text/yaml; charset=utf-8', 'atlas-hermes.yaml')
                if path.path == '/api/evidence':
                    return self.respond(200, app.store.get('evidence', int(query['id'][0]), case))
                if path.path == '/api/evidence-search':
                    app.store.get('cases',case)
                    return self.respond(200,{'results':app.search_evidence(case,query.get('q',[''])[0])})
                if path.path == '/api/evidence-compare':
                    comparison = app.compare_evidence(case, int(query['before'][0]), int(query['after'][0]))
                    return self.respond(200, comparison, attachment='atlas-evidence-comparison.json' if query.get('download') == ['1'] else None)
                if path.path == '/api/source-response':
                    evidence = app.store.get('evidence', int(query['id'][0]), case)
                    return self.respond(200, evidence['raw'], attachment=f"atlas-evidence-{evidence['id']}.json")
                if path.path == '/api/export':
                    app.store.get('cases', case)
                    result = {'format': 'atlas-case-v1', 'exported_at': now(), 'case': app.store.get('cases', case)}
                    result.update({t: app.store.all(t, case) for t in TABLES[1:]})
                    return self.respond(200, result)
                if path.path == '/api/report':
                    report=app.store.get('reports',int(query['id'][0]),case)
                    if query.get('format')==['json']:
                        return self.respond(200,report)
                    return self.respond(200, report_html(report), 'text/html; charset=utf-8')
                filenames = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'application/javascript'), '/free-tools.js': ('free-tools.js','application/javascript'), '/style.css': ('style.css', 'text/css')}
                if path.path in filenames:
                    filename, mime = filenames[path.path]
                    return self.respond(200, (ROOT / 'static' / filename).read_bytes(), mime + '; charset=utf-8')
                return self.respond(404, {'error': 'Not found.'})
            except (ValueError, KeyError, TypeError) as error:
                return self.respond(400, {'error': str(error)})

        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Atlas-Token') != app.token or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                return self.respond(403, {'error': 'Reload the local application before making changes.'})
            if self.path != '/api/action':
                return self.respond(404, {'error': 'Not found.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 40_000_000:
                    raise ValueError('Upload limit is 40 MB.')
                body = json.loads(self.rfile.read(length))
                self.respond(200, app.action(body))
            except (ValueError, KeyError, TypeError) as error:
                self.respond(400, {'error': str(connectors.clean(str(error)))[:500]})
            except Exception:
                self.respond(500, {'error': 'The operation could not be completed. No request or credential details were logged.'})
    return Handler


class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        import socket
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', default=str(ROOT / 'data'))
    args = parser.parse_args()
    directory = Path(args.data)
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['ATLAS_FREE_TOOLS_DIR'] = str((directory / 'free-tools').resolve())
    # Own the listening port before recovery can modify any persisted job state.
    server = LocalServer(('127.0.0.1', args.port), BaseHTTPRequestHandler)
    app = Workbench(directory / 'atlas.sqlite3')
    server.RequestHandlerClass = handler_for(app, args.port)
    (directory / 'server.pid').write_text(str(os.getpid()), encoding='ascii')
    threading.Thread(target=app.worker, daemon=True).start()
    print(f'Atlas ready at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
