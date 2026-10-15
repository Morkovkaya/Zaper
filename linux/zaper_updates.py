"""GitHub Linux release discovery and SHA256-verified downloads; no saved tokens."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

REPO='Morkovkaya/Zaper'
API='https://api.github.com/repos/'+REPO
MAX_ARCHIVE=256*1024*1024


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(newurl).scheme!='https': raise ValueError('Небезопасный адрес обновления')
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(newurl).hostname!='api.github.com': result.remove_header('Authorization')
        return result


def request(url,token='',binary=False):
    if not url.startswith(API+'/'): raise ValueError('Недопустимый API обновления')
    headers={'User-Agent':'Zaper-Linux','Accept':'application/octet-stream' if binary else 'application/vnd.github+json'}
    if token:
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_]+',token.strip()):raise ValueError('Некорректный формат токена GitHub')
        headers['Authorization']='Bearer '+token.strip()
    from zaper_proxy import detected_proxy
    proxy=detected_proxy()
    handler=urllib.request.ProxyHandler({'http':proxy,'https':proxy}) if proxy else urllib.request.ProxyHandler()
    return urllib.request.build_opener(handler,Redirect()).open(urllib.request.Request(url,headers=headers),timeout=30)


def select(releases):
    candidates=[]
    for release in releases:
        if release.get('draft'): continue
        match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)-linux\.(\d+)',release.get('tag_name',''))
        if not match:continue
        for asset in release.get('assets',[]):
            if re.fullmatch(r'Zaper-\d+\.\d+\.\d+-linux\.\d+-universal\.tar\.gz',asset.get('name','')) and re.fullmatch(r'sha256:[a-fA-F0-9]{64}',asset.get('digest') or ''):
                candidates.append((tuple(map(int,match.groups())),dict(tag=release['tag_name'],prerelease=release['prerelease'],url=release['html_url'],name=asset['name'],id=asset['id'],sha256=asset['digest'][7:].lower(),size=asset['size'])))
    if not candidates: raise RuntimeError('Нет доступного Linux-релиза с SHA256; проверьте доступ к приватному репозиторию')
    return max(candidates,key=lambda item:item[0])[1]


def check(token=''):
    with request(API+'/releases?per_page=100',token) as response:
        data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024: raise ValueError('Ответ GitHub слишком большой')
    return select(json.loads(data))


def download(directory,token=''):
    release=check(token)
    if not 0<release['size']<=MAX_ARCHIVE: raise ValueError('Некорректный размер архива')
    directory=Path(directory).expanduser().resolve();directory.mkdir(parents=True,exist_ok=True)
    target=directory/release['name']
    descriptor,temp=tempfile.mkstemp(prefix='.zaper-download-',dir=directory)
    try:
        digest=hashlib.sha256();size=0
        with os.fdopen(descriptor,'wb') as output,request(API+'/releases/assets/'+str(int(release['id'])),token,True) as response:
            while True:
                chunk=response.read(65536)
                if not chunk:break
                size+=len(chunk)
                if size>release['size']:raise ValueError('Размер загруженного файла превышен')
                output.write(chunk);digest.update(chunk)
            output.flush();os.fsync(output.fileno())
        if size!=release['size'] or digest.hexdigest()!=release['sha256']:raise ValueError('Размер или SHA256 обновления не совпадает с GitHub')
        os.chmod(temp,0o644);os.replace(temp,target)
        return dict(**release,path=str(target),verified=True,instructions='Распакуйте архив, затем sudo ./install.sh install. Настройки сохраняются.')
    finally:Path(temp).unlink(missing_ok=True)
