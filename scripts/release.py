#!/usr/bin/env python3
"""Publish exact CI artifacts. Only the trusted-main workflow grants write access."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def metadata(root=ROOT):
    windows = re.search(r'AssemblyVersion\("(\d+\.\d+\.\d+)\.0"\)', (root/'src/AssemblyInfo.cs').read_text())[1]
    installer = (root/'installer/setup.iss').read_text()
    if f'AppVersion={windows}\n' not in installer or f'OutputBaseFilename=Zapret2Manager-Setup-{windows}-x64\n' not in installer:
        raise ValueError('Windows assembly and installer versions differ')
    # Import only the simple version module from the checked-out, trusted source.
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_version', root/'linux/zaper_version.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if not re.fullmatch(r'\d+\.\d+\.\d+-linux\.\d+', module.VERSION):
        raise ValueError('Invalid Linux version')
    return dict(windows=windows, linux=module.VERSION, bundle=module.BUNDLE_NAME)


def gh(*args):
    result=subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'GitHub command failed')
    return result.stdout


def publish(directory, repo, commit, run=gh):
    versions = metadata()
    published = []
    for platform in ('windows', 'linux'):
        version = versions[platform]; tag = 'v'+version
        pages = json.loads(run('api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
        releases = [item for page in pages for item in page]
        existing = next((item for item in releases if item['tag_name']==tag), None)
        if existing and not existing['draft']:
            print(f'{tag} already published; leaving it unchanged')
            continue
        if existing and existing['target_commitish'] != commit:
            raise ValueError('Existing draft targets another commit: '+tag)
        name = f'Zapret2Manager-Setup-{version}-x64.exe' if platform=='windows' else f'Zaper-{version}-universal.tar.gz'
        matches = list(Path(directory).rglob(name))
        if len(matches)!=1 or matches[0].stat().st_size==0:
            raise ValueError('Missing or ambiguous tested artifact: '+name)
        artifact = matches[0]
        checksum = artifact.parent/f'SHA256-{version}.txt'
        checksum.write_text(hashlib.sha256(artifact.read_bytes()).hexdigest()+'  '+name+'\n')
        if not existing:
            run('release', 'create', tag, '--repo', repo, '--target', commit, '--draft', '--title', 'Zaper '+version,
                '--notes', f'Автоматический выпуск из проверенной сборки {commit}.\nWindows и Linux: все обязательные проверки CI пройдены.\nПроверяйте SHA256 перед ручной установкой.')
        run('release', 'upload', tag, str(artifact), str(checksum), '--repo', repo, '--clobber')
        # Assert the server received precisely the tested artifact before making it visible.
        assets = json.loads(run('release', 'view', tag, '--repo', repo, '--json', 'assets'))['assets']
        received = next((item for item in assets if item['name']==name), None)
        expected = 'sha256:'+hashlib.sha256(artifact.read_bytes()).hexdigest()
        if not received or received.get('digest')!=expected or received.get('size')!=artifact.stat().st_size:
            raise ValueError('Uploaded artifact digest/size mismatch: '+name)
        # Older Windows versions use releases/latest; a Linux-only release must not take it over.
        latest = platform=='windows'
        if latest:
            newer = [item for item in releases if not item['draft'] and not item['prerelease'] and re.fullmatch(r'v\d+\.\d+\.\d+', item['tag_name'])]
            latest = not any(tuple(map(int, item['tag_name'][1:].split('.'))) > tuple(map(int, version.split('.'))) for item in newer)
        run('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest='+str(latest).lower())
        published.append(tag)
    return published


if __name__=='__main__':
    if sys.argv[1:] == ['metadata']:
        for key,value in metadata().items(): print(f'{key}={value}')
    elif len(sys.argv)==5 and sys.argv[1]=='publish':
        publish(sys.argv[2], sys.argv[3], sys.argv[4])
    else: raise SystemExit('Usage: release.py metadata | publish ARTIFACTS REPO COMMIT')
