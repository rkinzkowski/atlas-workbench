"""No-credit source adapters and a local tool library. No arbitrary command execution."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse

ROOT = Path(__file__).resolve().parent
PUBLIC_IDS = {'domain_whois', 'domain_contacts', 'atlas_dns', 'github_public_profile', 'twitter_username_history'}
ADAPTERS = {
    'free_phone_metadata': ('Phone numbering metadata · local', ['phone'], None),
    'free_email_domain': ('Email format and mail domain · public DNS', ['email'], None),
    'free_blackbird_username': ('Username discovery · Blackbird / WhatsMyName rules', ['username'], None),
    'free_blackbird_email': ('Email presence · Blackbird read-only rules', ['email'], None),
    'free_detectdee_username': ('Username discovery · DetectDee read-only rules', ['username'], None),
    'free_detectdee_email': ('Email presence · DetectDee read-only rules', ['email'], None),
    'free_detectdee_phone': ('Phone presence · DetectDee read-only rules', ['phone'], None),
    'free_instagram_profile': ('Instagram public profile · direct', ['instagram'], None),
    'free_toutatis_profile': ('Instagram profile · Toutatis-compatible session lookup', ['instagram'], 'INSTAGRAM_SESSION_ID'),
    'free_ghunt_email': ('Google email evidence · GHunt', ['email'], None),
    'free_ghunt_gaia': ('Google account ID evidence · GHunt', ['google_id'], None),
    'free_ghunt_drive': ('Google Drive source evidence · GHunt', ['website'], None),
    'free_scrapy_crawl': ('Website crawl · Scrapy', ['domain', 'website'], None),
    'free_search_links': ('Public-information search links · local', ['person','email','phone','username','domain','organization'], None),
    'free_sms_gateway': ('SMS gateway address · supplied gateway domain', ['phone'], None),
}
LIBRARY = [
    ('blackbird','Blackbird','https://github.com/antoniaci/blackbird','Read-only template adapter; preserves full responses and every outcome.', ['free_blackbird_username','free_blackbird_email']),
    ('toutatis','Toutatis','https://github.com/megadose/toutatis','Profile-only compatible adapter. Enter your session locally in Logins; no recovery lookup is triggered.', ['free_toutatis_profile']),
    ('007','007-TheBond','https://github.com/Deadshot0x7/007-TheBond','Selected equivalent functions: direct Instagram, local phone metadata, mail-domain checks and search links. Its incorrect breach check is not used.', ['free_instagram_profile','free_phone_metadata','free_email_domain','free_search_links']),
    ('ghunt','GHunt','https://github.com/mxrch/GHunt','Runs the installed GHunt package with JSON output. Requires login in the isolated local tool profile.', ['free_ghunt_email','free_ghunt_gaia','free_ghunt_drive']),
    ('detectdee','DetectDee','https://github.com/Yvesssn/DetectDee','Read-only GET rules and chained checks. Unsupported POST/authentication steps stay visible as skipped.', ['free_detectdee_username','free_detectdee_email','free_detectdee_phone']),
    ('phoneinfoga','PhoneInfoga','https://github.com/sundowndev/phoneinfoga','Equivalent local numbering metadata and public search-link workflow. External paid scanners are not run.', ['free_phone_metadata','free_search_links']),
    ('email2phonenumber','email2phonenumber','https://github.com/martinvigo/email2phonenumber','Import existing research output as attributed evidence. Legacy recovery/brute-force routines are not an automated lookup.', []),
    ('dorks','All Dorks in One Place','https://github.com/RhackrExplorer/All-Dorks-in-one-place','Curated public profile, domain and document search templates; links are not fetched search results.', ['free_search_links']),
    ('phone2email','phone2email','https://github.com/whitef0x0/phone2email','Local SMS gateway mapping using a gateway domain you supply. Derived address, not a personal email; no Twilio call.', ['free_sms_gateway']),
    ('scrapy','Scrapy','https://www.scrapy.org/','Installed Scrapy extracts pages through Atlas public-network checks with same-host and page limits.', ['free_scrapy_crawl']),
    ('handbook','OSINT Handbook','https://www.osinthandbook.com/','Linked research directory and attributed manual-evidence import. No bulk catalog copy.', []),
]

def directory():
    return Path(os.environ.get('ATLAS_FREE_TOOLS_DIR', str(ROOT / 'data' / 'free-tools')))

def python_path():
    return directory() / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

def manifest():
    try:
        return json.loads((directory() / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def availability(transform):
    if transform not in ADAPTERS:
        return False
    installed = manifest()
    if 'blackbird' in transform or 'detectdee' in transform:
        name = ('blackbird-email' if transform.endswith('email') else 'blackbird-username') if 'blackbird' in transform else 'detectdee'
        return (directory() / (name + '.json')).is_file() and python_path().is_file() and 'regex' in installed.get('packages', {})
    if transform in ('free_phone_metadata','free_sms_gateway'):
        return python_path().is_file() and 'phonenumbers' in installed.get('packages', {})
    if transform == 'free_scrapy_crawl':
        return python_path().is_file() and 'scrapy' in installed.get('packages', {})
    if 'ghunt' in transform:
        return python_path().is_file() and 'ghunt' in installed.get('packages', {}) and (directory()/'home'/'.malfrats'/'ghunt'/'creds.m').is_file()
    if transform == 'free_toutatis_profile':
        return bool(os.environ.get('INSTAGRAM_SESSION_ID'))
    return True

def is_free(transform):
    return transform in PUBLIC_IDS or transform in ADAPTERS

def metadata(transform):
    if transform not in ADAPTERS:
        return {'free_eligible': is_free(transform)}
    ready = availability(transform)
    coverage = {
        'free_phone_metadata':'Offline numbering-plan validity, region, original carrier and possible time zones; not live service or owner verification.',
        'free_email_domain':'Format and complete public MX/A/AAAA responses. No mailbox or account-existence claim.',
        'free_instagram_profile':'One direct public profile request. Source restrictions and errors remain visible.',
        'free_toutatis_profile':'Two profile GET requests using your locally configured Instagram session. Does not invoke recovery endpoints.',
        'free_sms_gateway':'Derived SMS gateway address from supplied domain, US/Canada only. Not a personal email or delivery verification.',
        'free_search_links':'Generates research URLs locally. These are query suggestions, not collected evidence about the subject.',
        'free_scrapy_crawl':'Same-host HTML pages, complete bodies retained; 1–20 page limit, no JavaScript rendering.',
    }.get(transform, 'Full tool output retained. Site/account matches remain leads; readiness does not verify source access.')
    return {'provider':'Local / public sources','free_eligible':True,'coverage':coverage,
            'status':'ready' if ready else ('needs local session' if 'toutatis' in transform else 'needs local Google login' if 'ghunt' in transform and 'ghunt' in manifest().get('packages',{}) else 'install free tools'),
            'default_selected':transform in ('free_phone_metadata','free_email_domain')}

def library():
    return [{'id':i,'name':name,'url':url,'description':description,'transforms':transforms,
             'available':sum(availability(t) for t in transforms), 'mode':'adapter' if transforms else 'reference and import'}
            for i,name,url,description,transforms in LIBRARY]

def options(source):
    result = {}
    for key, default, maximum in [('site_limit',5,30),('site_offset',0,10000),('crawl_pages',3,20),('tool_timeout',90,300)]:
        value = source.get(key, default)
        if type(value) is not int or not (0 if key == 'site_offset' else 1) <= value <= maximum:
            raise ValueError('Invalid free-tool request limit: ' + key)
        result[key] = value
    for key in ('sites','gateway_domain'):
        value = source.get(key, '')
        if not isinstance(value,str) or len(value) > 2000:
            raise ValueError('Invalid free-tool option: ' + key)
        result[key] = value
    return result

def child_env(home):
    # Do not give optional tools the server's provider keys, proxy config or shell startup variables.
    allowed = ('SystemRoot','WINDIR','COMSPEC','PATH','TEMP','TMP','LANG','LC_ALL')
    env = {k:os.environ[k] for k in allowed if k in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONNOUSERSITE='1')
    return env

def worker(task, value, opts):
    import connectors as c
    home = directory() / 'home'
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-free-') as tmp:
        output = Path(tmp) / 'result.jsonl'
        request = {'task':task,'value':value,'options':{k:v for k,v in opts.items() if not k.startswith('_')},
                   'data_dir':str(directory().resolve()),'output':str(output)}
        with (Path(tmp)/'stdout').open('wb') as stdout, (Path(tmp)/'stderr').open('wb') as stderr:
            process = subprocess.Popen([str(python_path()), str(ROOT/'free_worker.py')], stdin=subprocess.PIPE,
                stdout=stdout, stderr=stderr, cwd=tmp, env=child_env(home),
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            process.stdin.write(json.dumps(request).encode('utf-8'))
            process.stdin.close()
            started = time.monotonic()
            stopped = None
            while process.poll() is None:
                if opts.get('_cancelled',lambda:False)():
                    stopped = 'cancelled'
                elif time.monotonic()-started > opts.get('tool_timeout',90):
                    stopped = 'timeout'
                if stopped:
                    process.kill()
                    process.wait()
                    break
                time.sleep(.1)
        records = []
        incomplete = False
        if output.exists():
            for line in output.read_text(encoding='utf-8').splitlines():
                try: records.append(json.loads(line))
                except ValueError: incomplete = True
        raw = {'records':records, 'stdout':(Path(tmp)/'stdout').read_text(encoding='utf-8',errors='replace'),
               'stderr':(Path(tmp)/'stderr').read_text(encoding='utf-8',errors='replace'),
               'exit_code':process.returncode, 'stop_reason':stopped, 'incomplete_record':incomplete,
               'tool_versions':manifest().get('packages',{})}
        failed = stopped or incomplete or process.returncode != 0 or any(r.get('fatal') for r in records)
        if failed and not records:
            raise c.SourceError(200, {'message':'Local tool failed or stopped before returning a record.', 'tool_output':raw})
        return raw, bool(failed)

def pack(transform, raw, entities=None, error=None, summary=None):
    return {'source':ADAPTERS[transform][0], 'raw':raw, 'entities':entities or [], 'url':None,
            'snippet':summary or 'Complete local/public-source result. Review the source observations before linking identities.',
            'collection':{'error':{'message':str(error)} if error else None,'provider_credits_used':0},
            'visibility':{'content_masking':False,'relevance_filter_applied':False,'authentication_secrets_protected':True,'full_returned_payload_preserved':True}}

def run(transform,node,opts):
    import connectors as c
    import providers as p
    value = node['identifier'].strip()
    settings = {**options(opts), '_cancelled':opts.get('_cancelled',lambda:False)}
    if settings['_cancelled']():
        raise ValueError('Cancelled before a source request.')
    if transform in ('free_instagram_profile','free_toutatis_profile'):
        handle = p.handle(value)
        if not re.fullmatch(r'[A-Za-z0-9_.]{1,30}',handle):
            raise ValueError('Enter a valid Instagram handle.')
        headers = {'x-ig-app-id':'936619743392459'}
        if transform == 'free_toutatis_profile':
            headers['Cookie'] = 'sessionid=' + os.environ['INSTAGRAM_SESSION_ID']
        endpoint = 'https://i.instagram.com' if 'toutatis' in transform else 'https://www.instagram.com'
        raw = c.fetch(endpoint+'/api/v1/users/web_profile_info/?'+urllib.parse.urlencode({'username':handle}),headers=headers)
        user = raw.get('data',{}).get('user') if isinstance(raw,dict) else None
        if not user:
            raise c.SourceError(200,raw)
        failure = None
        if 'toutatis' in transform:
            uid = str(user.get('id',''))
            if not uid.isdigit(): raise ValueError('Instagram returned no usable numeric user ID.')
            if settings['_cancelled']():
                failure = 'Cancelled before the second profile request.'
            else:
                try:
                    detail = c.fetch('https://i.instagram.com/api/v1/users/'+uid+'/info/',headers=headers)
                    raw = {'profile':raw,'details':detail}
                    if not detail.get('user'): failure = 'The detailed profile response did not contain a user.'
                except Exception as exc:
                    failure = str(exc)
                    raw = {'profile':raw,'detail_error':{'message':str(exc),'response':getattr(exc,'response',None)}}
        return pack(transform,raw,p.entities(raw),failure)
    if transform == 'free_email_domain':
        syntax = bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value))
        raw = {'input':value,'basic_format_valid':syntax,'mailbox_exists':'not checked','dns':{}}
        if syntax:
            domain = value.rsplit('@',1)[1].encode('idna').decode()
            for kind in ('MX','A','AAAA'):
                if settings['_cancelled'](): return pack(transform,raw,error='Cancelled between DNS queries.')
                try: raw['dns'][kind] = c.fetch('https://dns.google/resolve?'+urllib.parse.urlencode({'name':domain,'type':kind}))
                except Exception as exc:
                    raw['dns'][kind]={'error':str(exc),'response':getattr(exc,'response',None)}
                    return pack(transform,raw,error=str(exc))
            mx = raw['dns']['MX'].get('Answer',[])
            raw['null_mx'] = any(r.get('type')==15 and r.get('data','').strip()=='0 .' for r in mx)
        return pack(transform,raw,summary='Basic address syntax and mail-domain observations. No mailbox was contacted or verified.')
    if transform == 'free_search_links':
        identifier = value.replace('"','')
        quoted = '"'+identifier+'"'
        queries = [('Exact identifier',quoted),('Public profiles',quoted+' (site:instagram.com OR site:github.com OR site:linkedin.com/in/)'),
                   ('Public documents',quoted+' (filetype:pdf OR filetype:docx)'),('Public mentions',quoted+' -site:pinterest.com')]
        if node['type']=='domain': queries.append(('Domain pages','site:'+p.domain(value)))
        raw = {'kind':'generated research links, not search results','queries':[{'title':t,'query':q,'search_url':'https://www.google.com/search?'+urllib.parse.urlencode({'q':q})} for t,q in queries]}
        return pack(transform,raw,summary='Research links generated locally. Open a link to search; no search engine or paid API was queried.')
    if transform == 'free_sms_gateway':
        number = re.sub(r'[\s()+.-]','',value)
        domain = settings['gateway_domain'].strip().lower()
        if not re.fullmatch(r'1[2-9][0-9]{2}[2-9][0-9]{6}',number) or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}',domain):
            raise ValueError('Supply a +1 phone number and a verified SMS gateway domain in Free tool options. US/Canada use only.')
        metadata,failed=worker('phone','+'+number,settings)
        if failed or not metadata['records'] or metadata['records'][0].get('region_code') not in ('US','CA'):
            raise ValueError('SMS gateway mapping supports US/Canadian numbering regions only.')
        raw = {'input_phone':value,'supplied_gateway_domain':domain,'derived_sms_address':number[1:]+'@'+domain,
               'personal_email':False,'carrier_verified':False,'delivery_tested':False,'country_scope':'US/Canada','number_metadata':metadata}
        return pack(transform,raw,summary='Derived gateway address only. The supplied gateway and delivery have not been verified; no message was sent.')
    tasks = {'free_phone_metadata':'phone','free_scrapy_crawl':'crawl',
             'free_ghunt_email':'ghunt-email','free_ghunt_gaia':'ghunt-gaia','free_ghunt_drive':'ghunt-drive'}
    task = tasks.get(transform,transform.removeprefix('free_'))
    if task.startswith('ghunt-'):
        if value.startswith('-'): raise ValueError('Identifiers cannot begin with an option prefix.')
        if task=='ghunt-gaia' and not value.isdigit(): raise ValueError('Use a numeric Google account ID.')
        if task=='ghunt-drive':
            parsed=urllib.parse.urlsplit(value)
            host = parsed.hostname
            if host not in ('drive.google.com','docs.google.com'): raise ValueError('Use a Google Drive or Docs link.')
            match=re.search(r'/(?:d|folders)/([A-Za-z0-9_-]+)',parsed.path)
            file_id=match.group(1) if match else urllib.parse.parse_qs(parsed.query).get('id',[''])[0]
            if not re.fullmatch(r'[A-Za-z0-9_-]{5,}',file_id): raise ValueError('The link contains no supported Google Drive file or folder ID.')
            value=file_id
    raw,failed = worker(task,value,settings)
    leads = []
    for row in raw['records']:
        if row.get('outcome')=='candidate' and row.get('profile_url'):
            leads.append(c.entity('website',row['profile_url'],'candidate site match, unverified ownership'))
        if task in ('crawl','ghunt-email','ghunt-gaia','ghunt-drive'):
            leads.extend(p.entities(row))
    if any(row.get('outcome') in ('error','unsupported','ambiguous') for row in raw['records']): failed=True
    if not any(row.get('outcome') in ('candidate','not_found') for row in raw['records']) and ('blackbird' in task or 'detectdee' in task): failed=True
    return pack(transform,raw,leads,'Some tool checks failed, were unsupported, or could not be classified. See all outcomes.' if failed else None)
