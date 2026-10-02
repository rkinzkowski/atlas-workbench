"""Case management and reviewable investigation plans; no provider calls here."""
import time

import connectors

ACTIONS = {'case-update', 'node-update', 'related-node', 'archive', 'restore', 'layout-reset',
           'manual-evidence', 'plan', 'start-plan', 'monitor-update', 'monitor-set', 'save-answer'}


def active(w, case):
    return any(j['status'] in ('queued', 'running', 'cancel_requested') for j in w.store.all('jobs', case))


def handle(w, body):
    from app import canonical, now
    action, case = body['action'], int(body['case_id'])
    w.store.get('cases', case)
    if action == 'save-answer':
        import re
        question, answer = str(body.get('question', '')).strip(), str(body.get('answer', '')).strip()
        if not question or not answer:
            raise ValueError('Supply a question and a complete answer.')
        ids = sorted({int(i) for i in re.findall(r'\[E(\d+)\]', answer)})
        for identity in ids:
            w.store.get('evidence', identity, case)
        record = w.store.add('answers', case, {'question': question, 'answer': answer, 'evidence_ids': ids,
            'ai': True, 'author': str(body.get('author', 'Hermes')), 'created_at': now(),
            'verification': 'Evidence references checked; claims require review.'})
        w.event(case, 'Agent-authored answer saved for review; cited evidence IDs checked.', answer_id=record['id'])
        return record
    if action == 'monitor-set':
        monitor = w.store.get('monitors', body['id'], case)
        if type(body.get('enabled')) is not bool:
            raise ValueError('Choose enabled or paused.')
        if body['enabled']:
            import free_tools
            if w.free_only and not free_tools.is_free(monitor['transform_id']):
                raise ValueError('Paid monitors are disabled in free mode.')
            if monitor.get('archived') or w.store.get('cases', case).get('archived') or w.store.get('nodes', monitor['node_id'], case).get('archived'):
                raise ValueError('Restore the monitor, case and entity before resuming.')
            if not connectors.available(monitor['transform_id']):
                raise ValueError('Connect this source before resuming its monitor.')
        return w.store.update('monitors', monitor['id'], enabled=body['enabled'])
    if action == 'plan':
        ids = list(dict.fromkeys(int(i) for i in body.get('node_ids', [])))
        nodes = [w.store.get('nodes', i, case) for i in ids]
        if not nodes or any(n.get('archived') or n.get('review') == 'excluded' for n in nodes):
            raise ValueError('Choose at least one active seed entity.')
        limit, depth = int(body.get('max_runs', 10)), int(body.get('max_depth', 0))
        if not 1 <= limit <= 30 or not 0 <= depth <= 2:
            raise ValueError('Use 1–30 runs and 0–2 expansion levels.')
        if depth and not body.get('auto_apply'):
            raise ValueError('Expansion requires applying extracted leads. Choose seeds only to review them first.')
        choices = body.get('transforms')
        if choices is not None and (not isinstance(choices, list) or any(not isinstance(t, str) for t in choices)):
            raise ValueError('Choose a list of source IDs.')
        sources = [s for s in w.sources() if depth or any(n['type'] in s['types'] or '*' in s['types'] for n in nodes)]
        chosen = [s for s in sources if s['available'] and (choices is None or s['id'] in choices)]
        if choices and set(choices) - {s['id'] for s in chosen}:
            raise ValueError('One or more selected sources are unavailable or incompatible.')
        pairs = [{'node_id': n['id'], 'transform_id': s['id'], 'source': s['label'],
                  'uses_account': bool(s.get('credential_env'))} for n in nodes for s in chosen
                 if n['type'] in s['types'] or '*' in s['types']]
        if not pairs:
            raise ValueError('Connect a compatible source before creating a plan.')
        plan = w.store.add('plans', case, {'created_at': now(), 'objective': str(body.get('objective', '')).strip(),
            'node_ids': ids, 'transforms': [s['id'] for s in chosen], 'max_runs': limit, 'max_depth': depth,
            'auto_apply': bool(body.get('auto_apply')), 'options': w.lookup_options(body), 'seed_requests': pairs,
            'seed_requests_over_budget': max(0, len(pairs) - limit), 'job_id': None,
            'gaps': [{'id': s['id'], 'label': s['label'], 'status': s['status']} for s in sources if not s['available']],
            'phases': ['internal_collection'] + (['graph_expansion'] if depth else []) +
                      (['deep_graph_expansion'] if depth > 1 else []) +
                      (['web_corroboration'] if any(s['id'] == 'openai_web_search' for s in chosen) else []) + ['report_synthesis']})
        w.event(case, 'Investigation plan prepared; no sources have been queried.', plan_id=plan['id'])
        return plan
    if action == 'start-plan':
        with w.store.transaction():
            plan = w.store.get('plans', body['id'], case)
            if plan.get('job_id'):
                raise ValueError('This plan already started. Create another plan to run it again.')
            job = w.queue(case, plan)
            w.store.update('plans', plan['id'], job_id=job['id'])
            return job
    if action in ('archive', 'restore'):
        table = body['table']
        if table not in ('cases', 'nodes', 'edges', 'answers', 'monitors'):
            raise ValueError('This record type cannot be moved to Trash.')
        identity = int(body['id'])
        record = w.store.get(table, identity, None if table == 'cases' else case)
        if table == 'cases' and identity != case:
            raise ValueError('Case mismatch.')
        if active(w, case):
            raise ValueError('Stop active collection before removing or restoring records.')
        archived = action == 'archive'
        with w.store.transaction():
            fields = {'archived': archived, 'archived_at': now() if archived else None}
            if table == 'monitors':
                fields['enabled'] = False
            result = w.store.update(table, identity, **fields)
            if archived and table in ('cases', 'nodes'):
                for m in w.store.all('monitors', case):
                    if table == 'cases' or m['node_id'] == identity:
                        w.store.update('monitors', m['id'], enabled=False)
            w.event(case, ('Moved to Trash: ' if archived else 'Restored: ') + f'{table} {identity}. Source evidence retained.')
            return result
    if action == 'case-update':
        title = str(body.get('title', '')).strip()
        if not title:
            raise ValueError('Give the case a name.')
        result = w.store.update('cases', case, title=title, description=str(body.get('description', '')))
        w.event(case, 'Case name and scope updated.')
        return result
    if action == 'node-update':
        if active(w, case):
            raise ValueError('Stop active collection before editing an entity identifier.')
        node = w.store.get('nodes', body['id'], case)
        kind, value = str(body.get('type', node['type'])).strip().lower(), str(body.get('value', node['identifier'])).strip()
        import re
        if not value or len(value) > 1500 or not re.fullmatch(r'[a-z0-9_ -]{1,50}', kind):
            raise ValueError('Enter a valid entity type and identifier under 1,500 characters.')
        key = kind + ':' + canonical(kind, value)
        if any(n['id'] != node['id'] and n.get('key') == key and not n.get('archived') for n in w.store.all('nodes', case)):
            raise ValueError('This identifier already exists. Link the existing entity instead of overwriting its provenance.')
        result = w.store.update('nodes', node['id'], type=kind, identifier=value, label=str(body.get('label') or value), key=key)
        w.event(case, 'Entity details edited; original source evidence remains unchanged.', node_id=node['id'],
                previous={'type': node['type'], 'identifier': node['identifier'], 'label': node['label']})
        return result
    if action == 'related-node':
        parent = w.store.get('nodes', body['parent_id'], case)
        with w.store.transaction():
            node = w.node(case, body['type'], body['value'], origin='user', depth=parent.get('depth', 0) + 1)
            edge = w.edge(case, parent['id'], node['id'], body.get('evidence_id'), body.get('relationship', 'manual lead'), True)
            return {'node': node, 'edge': edge}
    if action == 'layout-reset':
        with w.store.transaction():
            for node in w.store.all('nodes', case):
                w.store.update('nodes', node['id'], position=None)
            w.store.update('cases', case, viewport=None)
        return {'reset': True}
    if action == 'manual-evidence':
        node = w.store.get('nodes', body['node_id'], case)
        if not str(body.get('source', '')).strip():
            raise ValueError('Name the source of this evidence.')
        evidence = w.save_evidence(case, node['id'], 'manual_evidence', {'source': body['source'],
            'raw': body.get('raw'), 'url': body.get('url'), 'snippet': str(body.get('notes', '')), 'entities': []}, origin='user')
        w.event(case, 'Analyst-supplied evidence saved. No external source was queried.', evidence_id=evidence['id'])
        return evidence
    if action == 'monitor-update':
        monitor = w.store.get('monitors', body['id'], case)
        interval = int(body['interval_seconds'])
        if not 3600 <= interval <= 2592000:
            raise ValueError('Use a monitor interval between 1 hour and 30 days.')
        return w.store.update('monitors', monitor['id'], interval_seconds=interval, next_run=time.time() + interval)
    raise ValueError('Unknown workflow action.')
