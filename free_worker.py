"""Bounded optional-library worker. Requests arrive on stdin; complete records use JSONL."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.robotparser

sys.path.insert(0,str(Path(__file__).resolve().parent))
import connectors as c

def emit(path, row):
    with Path(path).open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(c.clean(row),ensure_ascii=False)+'\n')

def observe(url):
    try:
        result = c.fetch(url,json_response=False,timeout=15,include_transport=True)
        return result['http_status'], result['body'], result['final_url']
    except c.SourceError as exc:
        text = exc.response.get('message') if isinstance(exc.response,dict) else None
        return exc.status, text if isinstance(text,str) else json.dumps(exc.response), url

def regex_match(pattern,text):
    import regex
    return bool(regex.search(pattern,text,timeout=.15))

def account_value(value, operation):
    if operation in (None,''): return value
    if operation in ('hash-sha256','hash-md5','hash-sha1'):
        return hashlib.new(operation[5:],value.strip().lower().encode()).hexdigest()
    raise ValueError('Unsupported input operation: '+str(operation))

def scan(request):
    task,value,opts,path = request['task'],request['value'],request['options'],request['output']
    blackbird = task.startswith('blackbird')
    kind = task.rsplit('_',1)[-1]
    catalog_name = ('blackbird-email' if kind=='email' else 'blackbird-username') if blackbird else 'detectdee'
    raw = (Path(request['data_dir'])/(catalog_name+'.json')).read_bytes()
    data = json.loads(raw)
    sites = [(r['name'],r) for r in data['sites']] if blackbird else list(data.items())
    selected = [s.strip().casefold() for s in opts.get('sites','').split(',') if s.strip()]
    if selected:
        available = {name.casefold() for name,row in sites}
        if set(selected)-available: raise ValueError('Unknown site names: '+', '.join(sorted(set(selected)-available)))
        sites = [(name,row) for name,row in sites if name.casefold() in selected]
    if not blackbird:
        sites = [(name,row) for name,row in sites if any(kind in step.get('type','') for step in row.get('detect',[]))]
    total = len(sites)
    offset,limit = opts['site_offset'],opts['site_limit']
    sites = sites[offset:offset+limit]
    emit(path,{'catalog':catalog_name,'catalog_sha256':hashlib.sha256(raw).hexdigest(),'eligible_sites':total,
               'selected_sites':[name for name,row in sites],'offset':offset,'limit':limit,
               'next_offset':offset+len(sites) if offset+len(sites)<total else None,
               'content_category_filter':False,'network_mode':'read-only GET templates'})
    for name,rule in sites:
        result = {'site':name,'outcome':'ambiguous','responses':[], 'category':rule.get('cat',rule.get('type'))}
        try:
            if blackbird:
                if rule.get('method','GET').upper()!='GET' or rule.get('data') or rule.get('pre_check') or rule.get('headers'):
                    result.update(outcome='unsupported',reason='Rule requires a body, headers, authentication or pre-check; no request made.')
                else:
                    encoded = urllib.parse.quote(account_value(value,rule.get('input_operation')),safe='')
                    url = rule['uri_check'].replace('{account}',encoded)
                    status,text,final = observe(url)
                    result['responses'].append({'request_url':url,'final_url':final,'http_status':status,'body':text})
                    positive = bool(rule.get('e_string')) and rule['e_string'] in text and status==rule.get('e_code')
                    negative = bool(rule.get('m_string')) and rule['m_string'] in text
                    if status in (401,403,429) or status>=500: outcome='error'
                    elif negative or (status==rule.get('m_code') and status!=rule.get('e_code')): outcome='not_found'
                    elif positive: outcome='candidate'
                    else: outcome='ambiguous'
                    result.update(outcome=outcome,profile_url=rule.get('uri_pretty',rule['uri_check']).replace('{account}',encoded))
            else:
                steps=rule.get('detect',[])
                if not steps or len(steps)>5 or any(s.get('body') or s.get('header') or s.get('search') or s.get('status') is False for s in steps):
                    result.update(outcome='unsupported',reason='Rule requires unsupported request steps or is disabled; no request made.')
                elif rule.get('nameCheck') and kind=='username' and not regex_match(rule['nameCheck'],value):
                    result.update(outcome='not_found',reason='Identifier does not fit the site template format; no request made.')
                else:
                    positive=False
                    for step in steps:
                        url=step.get('url','').replace('%s',urllib.parse.quote(value,safe=''))
                        status,text,final=observe(url)
                        result['responses'].append({'request_url':url,'final_url':final,'http_status':status,'body':text})
                        if status in (401,403,429) or status>=500:
                            result['outcome']='error';break
                        negative=bool(step.get('nonExistRegex')) and regex_match(step['nonExistRegex'],text)
                        expected=step.get('statusCode')
                        if negative or status==404:
                            result['outcome']='not_found';break
                        if expected and str(status)!=str(expected):
                            result['outcome']='ambiguous';break
                        if step.get('existRegex'):
                            if not regex_match(step['existRegex'],text):
                                result['outcome']='ambiguous';break
                            positive=True
                        result['profile_url']=step.get('userPage',url).replace('%s',urllib.parse.quote(value,safe=''))
                    else:
                        result['outcome']='candidate' if positive else 'ambiguous'
                        if not positive: result['reason']='Status-only rule; no content evidence proving an account.'
            # Do not convert a redirected login page into an account hit.
            if result['outcome']=='candidate' and any('/login' in r['final_url'] or '/signin' in r['final_url'] for r in result['responses']):
                result.update(outcome='ambiguous',reason='Request redirected to a login page.')
        except Exception as exc:
            result.update(outcome='error',reason=str(exc))
        emit(path,result)
        time.sleep(.2)

def phone(request):
    import phonenumbers as p
    from phonenumbers import carrier,geocoder,timezone
    number=p.parse(request['value'],None)
    region=p.region_code_for_number(number)
    raw={'input':request['value'],'e164':p.format_number(number,p.PhoneNumberFormat.E164),
         'international':p.format_number(number,p.PhoneNumberFormat.INTERNATIONAL),'national':p.format_number(number,p.PhoneNumberFormat.NATIONAL),
         'possible':p.is_possible_number(number),'numbering_plan_valid':p.is_valid_number(number),'region_code':region,
         'region_description':geocoder.description_for_number(number,'en'),'original_carrier':carrier.name_for_number(number,'en'),
         'possible_time_zones':list(timezone.time_zones_for_number(number)),
         'number_type':p.PhoneNumberType.to_string(p.number_type(number)),
         'active_service':'not checked','current_carrier':'not checked','owner':'not checked','network_requests':0}
    emit(request['output'],raw)

def crawl(request):
    from scrapy import Selector
    value=request['value']
    start=value if '://' in value else 'https://'+value
    c.public_url(start)
    parsed=urllib.parse.urlsplit(start)
    host=parsed.hostname
    robots_url=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,'/robots.txt','',''))
    robots=urllib.robotparser.RobotFileParser()
    try:
        text=c.fetch(robots_url,json_response=False,scope_host=host,timeout=15)
        robots.parse(text.splitlines())
        emit(request['output'],{'kind':'robots','url':robots_url,'body':text})
    except c.SourceError as exc:
        emit(request['output'],{'kind':'robots','http_status':exc.status,'response':exc.response})
        if exc.status not in (404,410): raise ValueError('Robots policy could not be retrieved; crawl stopped.')
        robots.parse([])
    queue=[start];seen=set();maximum=request['options']['crawl_pages'];visited=0
    while queue and visited<maximum:
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        if not robots.can_fetch('Atlas-Local-Workbench',url):
            emit(request['output'],{'url':url,'outcome':'unsupported','reason':'Disallowed by site robots policy.'})
            continue
        visited+=1
        try:
            page=c.fetch(url,json_response=False,scope_host=host,timeout=15,include_transport=True)
            selector=Selector(text=page['body'])
            links=selector.css('a::attr(href)').getall()
            emit(request['output'],{'kind':'page','url':page['final_url'],'http_status':page['http_status'],'html':page['body'],
                 'title':selector.css('title::text').getall(),'text':selector.xpath('//body//text()').getall(),'links':links})
            for link in links:
                target=urllib.parse.urldefrag(urllib.parse.urljoin(page['final_url'],link))[0]
                p=urllib.parse.urlsplit(target)
                if p.scheme in ('http','https') and p.hostname==host and target not in seen and target not in queue:
                    queue.append(target)
        except Exception as exc:
            emit(request['output'],{'url':url,'outcome':'error','reason':str(exc),'response':getattr(exc,'response',None)})
        time.sleep(.3)
    emit(request['output'],{'kind':'crawl_summary','page_attempts':visited,'page_limit':maximum,'remaining_links':queue,
                           'stop_reason':'page_limit' if queue else 'links_exhausted'})

def ghunt(request):
    result=Path(request['output']).with_suffix('.ghunt.json')
    module=request['task'].split('-',1)[1]
    sys.argv=['ghunt',module,request['value'],'--json',str(result)]
    entry=next(e for e in importlib.metadata.distribution('ghunt').entry_points if e.name=='ghunt')
    try: entry.load()()
    except SystemExit as exc:
        if exc.code not in (None,0): raise ValueError('GHunt exited unsuccessfully; check local login and input.')
    if not result.exists(): raise ValueError('GHunt produced no JSON. Complete local tool login first; this is not a no-match result.')
    emit(request['output'],{'kind':'ghunt','data':json.loads(result.read_text(encoding='utf-8'))})

def main():
    request=json.load(sys.stdin)
    try:
        task=request['task']
        if task=='phone': phone(request)
        elif task=='crawl': crawl(request)
        elif task.startswith('ghunt-'): ghunt(request)
        else: scan(request)
    except Exception as exc:
        emit(request['output'],{'fatal':True,'message':str(exc)})
        sys.exit(1)

if __name__=='__main__': main()
