"""Install optional tools in an isolated Atlas directory; never run subject lookups."""
import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

ROOT=Path(__file__).resolve().parent
CATALOGS={
    'blackbird-username':('WebBreacher/WhatsMyName','wmn-data.json','https://github.com/WebBreacher/WhatsMyName'),
    'blackbird-email':('antoniaci/blackbird','data/email-data.json','https://github.com/antoniaci/blackbird'),
    'detectdee':('Yvesssn/DetectDee','data.json','https://github.com/Yvesssn/DetectDee'),
}

def repair_catalog(raw):
    text=raw.decode('utf-8')
    repairs=0
    for _ in range(100):
        try: return json.loads(text),text.encode('utf-8'),repairs
        except json.JSONDecodeError as exc:
            if 'Invalid \\escape' not in str(exc): raise
            text=text[:exc.pos]+'\\'+text[exc.pos:]
            repairs+=1
    raise ValueError('Too many invalid escapes in upstream catalog.')

def download(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Atlas-free-tools-setup','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as response:
        raw=response.read(20_000_001)
    if len(raw)>20_000_000: raise ValueError('Setup download exceeds 20 MB.')
    return raw

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default=str(ROOT/'data'/'free-tools'))
    parser.add_argument('--login-ghunt',action='store_true')
    args=parser.parse_args()
    target=Path(args.directory).resolve()
    target.mkdir(parents=True,exist_ok=True)
    os.environ['ATLAS_FREE_TOOLS_DIR']=str(target)
    import free_tools
    runtime=free_tools.python_path()
    if args.login_ghunt:
        if not runtime.exists(): raise SystemExit('Install the free tools first.')
        home=target/'home';home.mkdir(exist_ok=True)
        command=[str(runtime.parent/('ghunt.exe' if os.name=='nt' else 'ghunt')),'login']
        raise SystemExit(subprocess.call(command,env=free_tools.child_env(home)))
    if not runtime.exists():
        venv.EnvBuilder(with_pip=True).create(target/'venv')
    pinned=[]
    for package in ('phonenumbers','regex','scrapy','ghunt'):
        version=json.loads(download('https://pypi.org/pypi/'+package+'/json'))['info']['version']
        pinned.append(package+'=='+version)
    subprocess.run([str(runtime),'-m','pip','install','--disable-pip-version-check',*pinned],check=True)
    versions=json.loads(subprocess.check_output([str(runtime),'-c',
        'import importlib.metadata as m,json; print(json.dumps({p:m.version(p) for p in ("phonenumbers","regex","scrapy","ghunt")}))'],text=True))
    manifest={'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'packages':versions,'catalogs':{}}
    for name,(repo,path,source) in CATALOGS.items():
        commit=json.loads(download('https://api.github.com/repos/'+repo+'/commits/HEAD'))['sha']
        url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+path
        raw=download(url)
        original=raw
        normalization=None
        try:
            data=json.loads(raw)
        except json.JSONDecodeError as exc:
            # Some DetectDee rules contain literal regex escapes in JSON strings.
            # Preserve downloaded bytes and record the exact compatibility repair.
            if name!='detectdee' or 'Invalid \\escape' not in str(exc): raise
            data,raw,repairs=repair_catalog(raw)
            normalization=f'Escaped {repairs} invalid JSON backslash(es); original bytes retained separately.'
            (target/(name+'.original.json')).write_bytes(original)
        if not isinstance(data,dict): raise ValueError('Unexpected catalog structure: '+name)
        if name.startswith('blackbird') and not isinstance(data.get('sites'),list): raise ValueError('Catalog lacks sites: '+name)
        pending=target/(name+'.tmp')
        pending.write_bytes(raw);pending.replace(target/(name+'.json'))
        manifest['catalogs'][name]={'source':source,'commit':commit,'download_url':url,'sha256':hashlib.sha256(raw).hexdigest(),
            'original_sha256':hashlib.sha256(original).hexdigest(),'normalization':normalization,
            'sites':len(data['sites']) if name.startswith('blackbird') else len(data)}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    lock=subprocess.check_output([str(runtime),'-m','pip','freeze'],text=True)
    (target/'requirements-installed.txt').write_text(lock,encoding='utf-8')
    print(json.dumps(manifest,indent=2))
    print('Installed. GHunt still needs local login. No account lookup or paid API call was made.')

if __name__=='__main__': main()
