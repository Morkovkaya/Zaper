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
        if release.get('draft') or release.get('prerelease'): continue
        match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)-linux\.(\d+)',release.get('tag_name',''))
        if not match:continue
        for asset in release.get('assets',[]):
            if asset.get('name') == 'Zaper-'+release['tag_name'][1:]+'-universal.tar.gz' and re.fullmatch(r'sha256:[a-fA-F0-9]{64}',asset.get('digest') or ''):
                candidates.append((tuple(map(int,match.groups())),dict(tag=release['tag_name'],prerelease=release['prerelease'],url=release['html_url'],name=asset['name'],id=asset['id'],sha256=asset['digest'][7:].lower(),size=asset['size'])))
    if not candidates: raise RuntimeError('Нет доступного Linux-релиза с SHA256; проверьте доступ к GitHub')
    return max(candidates,key=lambda item:item[0])[1]


def check(token=''):
    with request(API+'/releases?per_page=100',token) as response:
        data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024: raise ValueError('Ответ GitHub слишком большой')
    return select(json.loads(data))


def download(directory,token='',release=None):
    release=check(token) if release is None else release
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


def version_key(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)-linux\.(\d+)',value)
    if not match: raise ValueError('Некорректная версия Linux')
    return tuple(map(int,match.groups()))


def extract(archive, directory, name):
    """Extract only regular files/directories under the expected release root."""
    import tarfile
    from pathlib import PurePosixPath
    count=0; total=0; seen=set()
    with tarfile.open(archive,'r:gz') as source:
        for item in source:
            path=PurePosixPath(item.name)
            count+=1; total+=item.size
            if (count>20000 or total>512*1024*1024 or item.size<0 or
                path.is_absolute() or '..' in path.parts or not path.parts or
                path.parts[0]!=name or not (item.isfile() or item.isdir()) or
                item.name in seen):
                raise ValueError('Небезопасная структура архива обновления')
            seen.add(item.name)
            target=Path(directory).joinpath(*path.parts)
            if item.isdir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.extractfile(item) as reader,target.open('xb') as writer:
                    import shutil
                    shutil.copyfileobj(reader,writer)
                target.chmod(0o755 if item.mode&0o111 else 0o644)
    bundle=Path(directory)/name
    for required in ('install.sh','zaper_install.py','dependencies.sh','zapret_manager.py','runtime/sha256.json'):
        if not (bundle/required).is_file(): raise ValueError('Неполный архив обновления: '+required)
    return bundle


def install(token=''):
    import subprocess
    from zaper_version import VERSION
    if os.geteuid()!=0: raise PermissionError('Установка обновления требует прав администратора')
    release=check(token)
    if version_key(release['tag'])<=version_key(VERSION):
        return dict(updated=False,installed=VERSION,message='Уже установлена актуальная версия')
    # No user-supplied executable/archive paths cross the privilege boundary.
    # All bytes and metadata are obtained again by this root process over HTTPS.
    with tempfile.TemporaryDirectory(prefix='zaper-update-',dir='/var/tmp') as temp:
        result=download(temp,token,release=release)
        bundle=extract(result['path'],temp,'Zaper-'+release['tag'][1:])
        result=subprocess.run(['/bin/sh',str(bundle/'install.sh'),'install','--with-deps'],capture_output=True,text=True)
        if result.returncode: raise RuntimeError('Не удалось установить обновление: '+(result.stdout+result.stderr)[-6000:])
    return dict(updated=True,installed=release['tag'][1:],verified=True,
                message='Обновление установлено. Закройте и заново откройте панель Zaper; настройки и состояние службы сохранены.')
