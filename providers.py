"""Documented provider contracts. Responses are retained; interpretation is separate."""
import base64
import ipaddress
import json
import os
import re
import urllib.parse

# route, input parameter, accepted entity types, label, cursor parameter, cursor response keys
SCRAPE = {
 'instagram_profile': ('/v1/instagram/profile','handle',['instagram'],'Instagram profile',None,()),
 'instagram_posts': ('/v2/instagram/user/posts','handle',['instagram'],'Instagram posts','next_max_id',('next_max_id',)),
 'instagram_reels': ('/v1/instagram/user/reels','handle',['instagram'],'Instagram reels','max_id',('max_id','next_max_id')),
 'instagram_search': ('/v1/instagram/search','query',['username','person'],'Instagram search',None,()),
 'tiktok_profile': ('/v1/tiktok/profile','handle',['tiktok'],'TikTok profile',None,()),
 'tiktok_profile_videos': ('/v3/tiktok/profile/videos','handle',['tiktok'],'TikTok profile videos','max_cursor',('max_cursor',)),
 'tiktok_search': ('/v1/tiktok/search/users','query',['username','person'],'TikTok user search','cursor',('cursor',)),
 'facebook_profile_data': ('/v1/facebook/profile','url',['facebook'],'Facebook public profile',None,()),
 'facebook_posts': ('/v1/facebook/profile/posts','url',['facebook'],'Facebook public posts','cursor',('cursor',)),
 'linkedin_profile': ('/v1/linkedin/profile','url',['linkedin'],'LinkedIn profile',None,()),
 'linkedin_company_profile': ('/v1/linkedin/company','url',['linkedin_company'],'LinkedIn company',None,()),
 'linkedin_company_posts': ('/v1/linkedin/company/posts','url',['linkedin_company'],'LinkedIn company posts',None,()),
 'linkedin_post_search': ('/v1/linkedin/search/posts','query',['person','username','linkedin'],'LinkedIn post search','cursor',('cursor',)),
 'twitter_profile': ('/v1/twitter/profile','handle',['twitter'],'X / Twitter profile',None,()),
 'twitter_latest_tweets': ('/v1/twitter/user-tweets','handle',['twitter'],'X / Twitter user tweets',None,()),
 'threads_profile': ('/v1/threads/profile','handle',['threads'],'Threads profile',None,()),
 'threads_posts': ('/v1/threads/user/posts','handle',['threads'],'Threads posts',None,()),
 'bluesky_profile': ('/v1/bluesky/profile','handle',['bluesky'],'Bluesky profile',None,()),
 'bluesky_posts': ('/v1/bluesky/user/posts','handle',['bluesky'],'Bluesky posts',None,()),
 'youtube_channel': ('/v1/youtube/channel','handle',['youtube'],'YouTube channel',None,()),
 'youtube_channel_videos': ('/v1/youtube/channel-videos','handle',['youtube'],'YouTube videos','continuationToken',('continuationToken','continuation')),
 'youtube_channel_shorts': ('/v1/youtube/channel/shorts','handle',['youtube'],'YouTube shorts','continuationToken',('continuationToken','continuation')),
 'truthsocial_profile': ('/v1/truthsocial/profile','handle',['truthsocial'],'Truth Social profile',None,()),
 'truthsocial_posts': ('/v1/truthsocial/user/posts','handle',['truthsocial'],'Truth Social posts','next_max_id',('next_max_id',)),
 'snapchat_profile': ('/v1/snapchat/profile','handle',['snapchat'],'Snapchat public profile',None,()),
 'pinterest_boards': ('/v1/pinterest/user/boards','handle',['pinterest'],'Pinterest boards',None,()),
 'linktree_page': ('/v1/linktree','url',['linktree'],'Linktree page',None,()),
 'komi_page': ('/v1/komi','url',['komi'],'Komi page',None,()),
 'pillar_page': ('/v1/pillar','url',['pillar'],'Pillar page',None,()),
 'linkbio_page': ('/v1/linkbio','url',['linkbio'],'Linkbio page',None,()),
 'amazon_shop_page': ('/v1/amazon/shop','url',['amazon_shop'],'Amazon shop','pageToken',('pageToken','nextPageToken')),
}

ADAPTERS = {key: (row[3] + ' · ScrapeCreators', row[2], 'SCRAPECREATORS_API_KEY') for key,row in SCRAPE.items()}
for kind in ('email','phone','username','person','wallet'):
    ADAPTERS[kind + '_osint_industries'] = ('OSINT Industries ' + ('name' if kind == 'person' else kind) + ' lookup', [kind], 'OSINT_INDUSTRIES_API_KEY')
for kind in ('email','phone','person','linkedin'):
    ADAPTERS[kind + '_pdl_enrichment'] = ('People Data Labs ' + kind + ' enrichment', [kind], 'PDL_API_KEY')
ADAPTERS.update({
 'phone_line_lookup': ('Phone validation, carrier & line type · Twilio', ['phone'], 'TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN'),
 'email_breach_data': ('Email breach exposure · Have I Been Pwned', ['email'], 'HIBP_API_KEY'),
 'domain_builtwith': ('Website technologies · BuiltWith', ['domain','website','company_website','subdomain'], 'BUILTWITH_API_KEY'),
 'domain_subdomains': ('Known subdomains · SecurityTrails', ['domain','website','subdomain'], 'SECURITYTRAILS_API_KEY'),
 'ip_hostsdomains': ('IP-associated domains · SecurityTrails', ['ip'], 'SECURITYTRAILS_API_KEY'),
 'ip_reputation': ('IP reputation · AbuseIPDB', ['ip'], 'ABUSEIPDB_API_KEY'),
 'ip_geolocation': ('IP network & location · IPinfo', ['ip'], 'IPINFO_TOKEN'),
 'person_social_search': ('Name / social web search · Serper', ['person'], 'SERPER_API_KEY'),
 'email_web_search': ('Email web search · Serper', ['email'], 'SERPER_API_KEY'),
 'phone_web_search': ('Phone web search · Serper', ['phone'], 'SERPER_API_KEY'),
 'username_web_search': ('Username web search · Serper', ['username'], 'SERPER_API_KEY'),
 'linkedin_search': ('LinkedIn indexed profile search · Serper', ['person','username'], 'SERPER_API_KEY'),
 'facebook_search': ('Facebook indexed profile search · Serper', ['person','username'], 'SERPER_API_KEY'),
 'domain_linkedin': ('LinkedIn indexed company search · Serper', ['domain','website','company_website'], 'SERPER_API_KEY'),
 'domain_places': ('Domain / business places search · Serper', ['domain','website','company_website'], 'SERPER_API_KEY'),
 'maps_listing': ('Maps / places search · Serper', ['location','organization'], 'SERPER_API_KEY'),
 'image_google_lens': ('Google Lens · SerpApi', ['image'], 'SERPAPI_API_KEY'),
 'image_yandex_images': ('Yandex reverse image · SerpApi', ['image'], 'SERPAPI_API_KEY'),
 'image_reverse_search': ('Reverse image matches · TinEye', ['image'], 'TINEYE_API_KEY'),
 'image_scene_analysis': ('Image properties & type · Sightengine', ['image'], 'SIGHTENGINE_API_USER,SIGHTENGINE_API_SECRET'),
 'image_moderation': ('Image content labels (no filtering) · Sightengine', ['image'], 'SIGHTENGINE_API_USER,SIGHTENGINE_API_SECRET'),
 'domain_safe_browsing': ('URL threat-list lookup · Google Web Risk', ['domain','website','company_website','subdomain'], 'GOOGLE_WEBRISK_API_KEY'),
 'twitter_username_history': ('Public username history · memory.lol', ['twitter'], None),
})
CREDENTIAL_ENVS = {v for row in ADAPTERS.values() for v in (row[2] or '').split(',') if v}

PROVIDER_DETAILS = {
 'OSINT_INDUSTRIES_API_KEY': ('OSINT Industries','https://docs.osint.industries/reference/search-1'),
 'SCRAPECREATORS_API_KEY': ('ScrapeCreators','https://docs.scrapecreators.com'),
 'PDL_API_KEY': ('People Data Labs','https://docs.peopledatalabs.com/docs/reference-person-enrichment-api'),
 'TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN': ('Twilio','https://www.twilio.com/docs/lookup/quickstart'),
 'HIBP_API_KEY': ('Have I Been Pwned','https://haveibeenpwned.com/API/v3'),
 'BUILTWITH_API_KEY': ('BuiltWith','https://api.builtwith.com/domain-api'),
 'SECURITYTRAILS_API_KEY': ('SecurityTrails','https://docs.securitytrails.com/reference/search-old-1'),
 'ABUSEIPDB_API_KEY': ('AbuseIPDB','https://docs.abuseipdb.com'),
 'IPINFO_TOKEN': ('IPinfo Core','https://ipinfo.io/developers/core-api'),
 'SERPER_API_KEY': ('Serper','https://serper.dev'),
 'SERPAPI_API_KEY': ('SerpApi','https://serpapi.com/google-lens-api'),
 'TINEYE_API_KEY': ('TinEye','https://github.com/TinEye/pytineye'),
 'SIGHTENGINE_API_USER,SIGHTENGINE_API_SECRET': ('Sightengine','https://sightengine.com/docs/getstarted'),
 'GOOGLE_WEBRISK_API_KEY': ('Google Web Risk','https://docs.cloud.google.com/web-risk/docs/lookup-api'),
}


def metadata(transform):
    native = {
        'openai_web_search': ('OpenAI','https://developers.openai.com/api/reference/resources/responses/methods/create','AI web corroboration; at most two billed tool calls per connector run. Full API response retained.'),
        'domain_whois': ('RDAP','https://about.rdap.org/','Current domain registration response. Registries can withhold fields.'),
        'domain_contacts': ('Public website','',"One page's full HTML, parsed text, and links. No website crawl or JavaScript rendering."),
        'atlas_dns': ('Google public DNS','https://developers.google.com/speed/public-dns/docs/doh/json','A, AAAA, MX, NS, and TXT DNS response bodies.'),
        'github_public_profile': ('GitHub','https://docs.github.com/en/rest/users/users#get-a-user','Public profile fields from the GitHub user API. Anonymous rate limits apply.'),
    }
    if transform in native:
        name,docs,coverage=native[transform]
        return {'provider':name,'docs':docs,'coverage':coverage}
    if transform in SCRAPE:
        row = SCRAPE[transform]
        return {'provider': 'ScrapeCreators', 'pagination_supported': bool(row[4]), 'docs': 'https://docs.scrapecreators.com' + row[0] + '/',
                'coverage': 'Public source response. No trimmed-response option is requested.'}
    if transform.endswith('_osint_industries'):
        return {'provider':'OSINT Industries', 'docs':'https://docs.osint.industries/reference/search-1', 'coverage':'Full returned module responses; premium and name matching are user-selectable.'}
    if transform.endswith('_pdl_enrichment'):
        return {'provider':'People Data Labs', 'docs':'https://docs.peopledatalabs.com/docs/reference-person-enrichment-api', 'coverage':'One matched provider record. Field access depends on the purchased bundle.'}
    name,docs = PROVIDER_DETAILS.get(ADAPTERS.get(transform,('',[],None))[2], ('Public source',''))
    if transform == 'twitter_username_history': name,docs='memory.lol','https://github.com/travisbrown/memory.lol'
    return {'provider':name, 'docs':docs, 'coverage': {
        'email_breach_data':'Breach names, dates and exposed data classes; not leaked credential contents.',
        'domain_linkedin':'Indexed company search results, not direct company-profile enrichment.',
        'linkedin_search':'Indexed web matches, not a native LinkedIn search.',
        'facebook_search':'Indexed web matches, not a native Facebook people search.',
        'image_scene_analysis':'Image properties and type annotations only; no face identification or suppression.',
        'image_moderation':'Optional content annotations only. Scores never hide or blur the image or other results.',
        'domain_subdomains':'Provider-known subdomains, not an exhaustive active scan.',
        'ip_hostsdomains':'Provider-known domains associated with an IPv4 address, one results page per request.',
        'image_reverse_search':'TinEye image and backlink matches, 100 results per search page; no face identification.',
        'domain_safe_browsing':'Google Web Risk list matches for a URL. Adds an annotation; never hides results.',
        'twitter_username_history':'Public historical observations only. memory.lol restricts its unauthenticated history window; no full-history access is claimed.',
    }.get(transform, 'Full provider response for the requested page; provider account limits still apply.')}


def handle(value):
    if value.startswith(('http://','https://')):
        parsed = urllib.parse.urlsplit(value)
        parts = [p for p in parsed.path.split('/') if p]
        if not parts:
            raise ValueError('Enter a profile handle or a full profile URL.')
        if parts[0] in ('profile','channel','user','c','add') and len(parts) > 1:
            return parts[1].lstrip('@')
        return parts[0].lstrip('@')
    return value.strip().lstrip('@')


def domain(value):
    return urllib.parse.urlsplit(value if '://' in value else 'https://' + value).hostname or ''


def next_cursor(raw, keys):
    if not isinstance(raw, dict):
        return None
    for container in (raw, raw.get('data', {}), raw.get('pagination', {})):
        if isinstance(container, dict):
            if container.get('has_more') is False or container.get('hasMore') is False:
                continue
            for key in keys:
                cursor = container.get(key)
                if cursor not in (None, '', False, '0', 0) and isinstance(cursor, (str,int)):
                    return cursor
    return None


def entities(raw):
    import connectors as c
    found = c.extract(raw)
    aliases = {'full_name':'person','fullName':'person','display_name':'person','username':'username',
               'phone_number':'phone','mobile_phone':'phone','work_email':'email','personal_email':'email',
               'location_name':'location','street_address':'location','company_name':'organization',
               'job_company_name':'organization','linkedin_url':'linkedin','profile_url':'website',
               'link':'website','website':'website','url':'website','permalink':'website','backlink':'website','image_url':'image'}
    def walk(value, parent=''):
        if isinstance(value, dict):
            for key,item in value.items():
                kind = aliases.get(key)
                if parent == 'emails' and key == 'address':
                    kind = 'email'
                if kind and isinstance(item, str) and item.strip() and item != '[REDACTED]':
                    if kind not in ('website','linkedin') or item.startswith(('http://','https://')):
                        found.append(c.entity(kind, item, 'reported in source'))
                if isinstance(item, list) and key in ('phone_numbers','personal_emails'):
                    found.extend(c.entity('phone' if key == 'phone_numbers' else 'email', x, 'reported in source') for x in item if isinstance(x,str) and x)
                if isinstance(item, (dict,list)):
                    walk(item, key)
        elif isinstance(value, list):
            for item in value:
                walk(item, parent)
    walk(raw)
    return list({(e['type'],e['identifier']):e for e in found}.values())


def result(transform, raw, snippet=None, **extra):
    leads = entities(raw)
    summary = snippet or (ADAPTERS[transform][0] + ' returned source data. Open the full response to inspect every field.')
    if leads:
        summary += '\n\nSource-reported leads (not verified identity matches):\n' + '\n'.join(e['type'] + ': ' + e['identifier'] for e in leads)
    return {'source':ADAPTERS[transform][0], 'raw':raw, 'entities':leads,
            'snippet':summary,
            'url':None, 'visibility':{'content_masking':False, 'relevance_filter_applied':False,
                                    'authentication_secrets_protected':True, 'full_returned_payload_preserved':True}, **extra}


def scrape_failed(raw):
    """Transport/envelope success can still contain a failed profile lookup."""
    if not isinstance(raw, dict):
        return False
    status = raw.get('errorStatus')
    return (raw.get('success') is False or bool(raw.get('error')) or
            (str(status).isdigit() and int(status) >= 400))


def scrape(transform, node, opts):
    import connectors as c
    route, param, types, label, cursor_param, cursor_keys = SCRAPE[transform]
    value = node['identifier'].strip()
    params = {param:handle(value) if param == 'handle' else value}
    if param == 'url':
        if not value.startswith(('http://','https://')):
            raise ValueError('This source requires the full public profile/page URL.')
        c.public_url(value)
    if 'youtube' in transform and '/channel/' in value:
        params = {'channelId':urllib.parse.urlsplit(value).path.split('/channel/',1)[1].split('/')[0]}
    if transform == 'linkedin_company_posts':
        params['page'] = int(opts.get('page',1))
    cursor = opts.get('cursor')
    pages, seen, failure = [], set(), None
    maximum = int(opts.get('max_pages', 1)) if cursor_param else 1
    for _ in range(maximum):
        if opts.get('_cancelled', lambda:False)():
            if not pages:
                raise ValueError('Collection cancelled before a provider request was made.')
            break
        if cursor is not None and cursor_param:
            params[cursor_param] = cursor
        try:
            raw = c.fetch('https://api.scrapecreators.com' + route + '?' + urllib.parse.urlencode(params), headers={'x-api-key':os.environ['SCRAPECREATORS_API_KEY']}, timeout=90)
            if scrape_failed(raw):
                raise c.SourceError(200, raw)
        except Exception as error:
            if not pages:
                raise
            failure = {'message':str(c.clean(str(error))), 'response':getattr(error,'response',None)}
            break
        pages.append(raw)
        new_cursor = next_cursor(raw, cursor_keys)
        if new_cursor is None:
            cursor = None
            break
        if str(new_cursor) in seen or str(new_cursor) == str(cursor):
            failure = {'message':'Provider repeated the pagination cursor; stopped to avoid repeating charged requests.'}
            cursor = new_cursor
            break
        seen.add(str(new_cursor))
        cursor = new_cursor
    raw = pages[0] if len(pages) == 1 else {'pages':pages}
    r = result(transform, raw, f'{label}: {len(pages)} page(s) retrieved. Full returned fields are retained; related accounts are leads, not identity conclusions.',
               collection={'pages_fetched':len(pages),'page_limit':maximum,'pagination_supported':bool(cursor_param),
                           'next_cursor':cursor,'more_available':bool(cursor),'stop_reason':'provider_error' if failure else 'cancelled' if opts.get('_cancelled',lambda:False)() else 'page_limit' if cursor else 'no_cursor_returned',
                           'error':failure}, request_options={k:v for k,v in opts.items() if not k.startswith('_')})
    return r


def run(transform, node, opts):
    import connectors as c
    value = node['identifier'].strip()
    if transform in SCRAPE:
        return scrape(transform,node,opts)
    if transform == 'twitter_username_history':
        username = handle(value)
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', username):
            raise ValueError('Enter a single X / Twitter handle or profile URL.')
        raw = c.fetch('https://api.memory.lol/v1/tw/' + username)
        r = result(transform,raw,'Public archived username observations. Dates describe observations, not complete ownership history. Provider restrictions remain visible in the response.')
        for account in raw.get('accounts',[]):
            for name in account.get('screen_names',account.get('screen-names',{})):
                r['entities'].append(c.entity('twitter',name,'historical screen-name observation'))
        return r
    if transform == 'domain_safe_browsing':
        url = value if value.startswith(('http://','https://')) else 'https://' + value
        c.public_url(url)
        params = [('uri',url),('key',os.environ['GOOGLE_WEBRISK_API_KEY'])] + [('threatTypes',t) for t in ('MALWARE','SOCIAL_ENGINEERING','UNWANTED_SOFTWARE')]
        raw = c.fetch('https://webrisk.googleapis.com/v1/uris:search?' + urllib.parse.urlencode(params))
        return result(transform,raw,'Google Web Risk list matches for this URL at collection time. An empty response means no listed match, not a guarantee of safety. Results are not suppressed.')
    if transform.endswith('_osint_industries'):
        kind = 'name' if node['type'] == 'person' else node['type']
        payload = {'type':kind,'query':value,'timeout':80,'premium':bool(opts.get('premium',False)),
                   'premium_modules_only':False,'exact_match':bool(opts.get('exact_match',False))}
        raw = c.fetch('https://api.osint.industries/v2/request',payload,{'api-key':os.environ['OSINT_INDUSTRIES_API_KEY']},timeout=100)
        return result(transform,raw, 'OSINT Industries module results. Full returned fields are retained. A broad name match can refer to a different person.',
                      collection={'timeout_seconds':80,'premium':payload['premium'],'exact_match':payload['exact_match'],'coverage':'Modules that finish within the provider timeout.'})
    if transform.endswith('_pdl_enrichment'):
        kind = node['type']
        params = {'include_if_matched':True}
        if kind == 'person':
            params['name'] = value
            for field in ('location','company','school','locality','region','postal_code'):
                if opts.get(field):
                    params[field] = str(opts[field])
            if len(params) == 2:
                raise ValueError('People Data Labs needs a name plus a location, company, school, region, or postal code. Add that context to the lookup.')
        else:
            params['profile' if kind == 'linkedin' else kind] = value
        try:
            raw = c.fetch('https://api.peopledatalabs.com/v5/person/enrich',params,{'X-Api-Key':os.environ['PDL_API_KEY']})
        except c.SourceError as error:
            if error.status != 404:
                raise
            return result(transform,{'status':404,'provider_response':error.response}, 'The provider returned no matching record.', no_match=True)
        return result(transform,raw, 'People Data Labs returned a candidate match. Inspect the provider likelihood, matched fields, and account field entitlements before accepting it.')
    if transform == 'phone_line_lookup':
        value = re.sub(r'[\s()-]','',value)
        if not re.fullmatch(r'\+[1-9][0-9]{6,14}', value):
            raise ValueError('Use an international phone number beginning with + and its country code.')
        auth = base64.b64encode((os.environ['TWILIO_ACCOUNT_SID']+':'+os.environ['TWILIO_AUTH_TOKEN']).encode()).decode()
        fields = 'line_type_intelligence' + (',caller_name' if opts.get('caller_name') else '')
        raw = c.fetch('https://lookups.twilio.com/v2/PhoneNumbers/' + urllib.parse.quote(value,safe='') + '?' + urllib.parse.urlencode({'Fields':fields}), headers={'Authorization':'Basic '+auth})
        return result(transform,raw,'Phone validation and carrier metadata. Caller name availability depends on country and account access.')
    if transform == 'email_breach_data':
        try:
            raw = c.fetch('https://haveibeenpwned.com/api/v3/breachedaccount/' + urllib.parse.quote(value,safe='') + '?truncateResponse=false&includeUnverified=true', headers={'hibp-api-key':os.environ['HIBP_API_KEY']})
        except c.SourceError as error:
            if error.status != 404:
                raise
            raw = []
        return result(transform,raw,f'{len(raw) if isinstance(raw,list) else "Provider"} breach exposure records. This API returns breach metadata, not stolen password contents.', no_match=raw==[])
    if transform == 'domain_builtwith':
        raw = c.fetch('https://api.builtwith.com/v25/api.json?' + urllib.parse.urlencode({'LOOKUP':domain(value)}), headers={'Authorization':'API '+os.environ['BUILTWITH_API_KEY']})
        if isinstance(raw,dict) and raw.get('Errors'):
            raise c.SourceError(200,raw)
        return result(transform,raw)
    if transform in ('domain_subdomains','ip_hostsdomains'):
        h = {'APIKEY':os.environ['SECURITYTRAILS_API_KEY']}
        if transform == 'domain_subdomains':
            host = domain(value)
            raw = c.fetch('https://api.securitytrails.com/v1/domain/' + urllib.parse.quote(host,safe='') + '/subdomains',headers=h)
            r = result(transform,raw)
            r['entities'].extend(c.entity('subdomain',x+'.'+host,'known subdomain') for x in raw.get('subdomains',[]) if isinstance(x,str))
            return r
        if ipaddress.ip_address(value).version != 4:
            raise ValueError('This SecurityTrails reverse-domain connector currently supports documented IPv4 filters only. IPinfo and AbuseIPDB also accept IPv6.')
        raw = c.fetch('https://api.securitytrails.com/v1/domains/list?' + urllib.parse.urlencode({'page':int(opts.get('page',1)),'include_ips':'true'}),{'filter':{'ipv4':value}},h)
        return result(transform,raw,collection={'page':int(opts.get('page',1)), 'coverage':'One provider results page. Choose a later search page to retrieve more records.'})
    if transform == 'ip_reputation':
        ipaddress.ip_address(value)
        raw = c.fetch('https://api.abuseipdb.com/api/v2/check?' + urllib.parse.urlencode({'ipAddress':value,'maxAgeInDays':90,'verbose':'true'}),headers={'Key':os.environ['ABUSEIPDB_API_KEY']})
        return result(transform,raw,'AbuseIPDB reports and reputation scores. These are source assertions, not proof of wrongdoing.')
    if transform == 'ip_geolocation':
        ipaddress.ip_address(value)
        raw = c.fetch('https://api.ipinfo.io/lookup/' + urllib.parse.quote(value,safe=''),headers={'Authorization':'Bearer '+os.environ['IPINFO_TOKEN']})
        return result(transform,raw,'IP network and approximate location data. This does not locate a specific person or device.')
    if transform in ('person_social_search','email_web_search','phone_web_search','username_web_search','linkedin_search','facebook_search','domain_linkedin','domain_places','maps_listing'):
        query = value
        if transform in ('email_web_search','phone_web_search','username_web_search'):
            query = '"' + value.replace('"','') + '"'
        if transform == 'linkedin_search': query += ' site:linkedin.com/in/'
        if transform == 'facebook_search': query += ' site:facebook.com'
        if transform == 'domain_linkedin': query = domain(value) + ' site:linkedin.com/company/'
        route = 'places' if transform in ('domain_places','maps_listing') else 'search'
        raw = c.fetch('https://google.serper.dev/' + route, {'q':query,'page':int(opts.get('page',1))}, {'X-API-KEY':os.environ['SERPER_API_KEY']})
        if isinstance(raw,dict) and raw.get('error'):
            raise c.SourceError(200,raw)
        return result(transform,raw,'Indexed search results. A mention of an identifier is not proof of account ownership.', collection={'page':int(opts.get('page',1)),'coverage':'One provider results page; no content category filtering requested.'})
    if transform in ('image_google_lens','image_yandex_images'):
        c.public_url(value)
        params = {'engine':'google_lens' if transform=='image_google_lens' else 'yandex_images','url':value,'api_key':os.environ['SERPAPI_API_KEY']}
        raw = c.fetch('https://serpapi.com/search.json?' + urllib.parse.urlencode(params))
        if isinstance(raw,dict) and raw.get('error'):
            raise c.SourceError(200,raw)
        return result(transform,raw,'Reverse-image search results. Visual matches are candidate source pages, not proof of a person’s identity.')
    if transform == 'image_reverse_search':
        c.public_url(value)
        page = int(opts.get('page',1))
        params = {'image_url':value,'offset':(page-1)*100,'limit':100,'sort':'score','order':'desc'}
        raw = c.fetch('https://api.tineye.com/rest/search/?' + urllib.parse.urlencode(params),headers={'x-api-key':os.environ['TINEYE_API_KEY']})
        if raw.get('code') != 200:
            raise c.SourceError(200,raw)
        return result(transform,raw,'TinEye image matches and backlinks. Choose another search page to collect additional matches.',collection={'page':page,'offset':params['offset'],'page_size':100,'coverage':'One results page; no content filters requested.'})
    if transform in ('image_scene_analysis','image_moderation'):
        c.public_url(value)
        models = 'properties,type' if transform == 'image_scene_analysis' else 'nudity-2.1,weapon,gore-2.0'
        params = {'url':value,'models':models,'api_user':os.environ['SIGHTENGINE_API_USER'],'api_secret':os.environ['SIGHTENGINE_API_SECRET']}
        raw = c.fetch('https://api.sightengine.com/1.0/check.json?' + urllib.parse.urlencode(params))
        if raw.get('status') == 'failure':
            raise c.SourceError(200,raw)
        return result(transform,raw,'Image annotations. These labels do not hide, blur, or suppress the source results.')
    raise ValueError('No implementation is registered for this source.')
