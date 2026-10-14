#!/usr/bin/env python3
"""Build a universal tarball from a pinned official engine release."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v1.0.5.2'
HASHES = {
    'x86_64': 'de1414b1e0f9a5659d438cddcb0c7e9099b4533bf5c8a3cf841c7bc7e5aa1473',
    'arm64': '8788877cd4b3140357dd10524832ca508d47055efae072bc426b887bfea253a7',
}
# Pin the complete archive too: Lua is executed as root, not just the engine.
ARCHIVE_SHA256 = 'fb3bcf69e7d86b9fa2d60bd53c956ac06d9dcc3adf9392afd84865f1d94b1158'


def package(archive, output):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Upstream archive SHA256 mismatch')
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        with tarfile.open(archive) as tar:
            tar.extractall(temp, filter='data')
        upstream = temp / ('zapret2-' + VERSION)
        dest = output / 'Zapret2Manager-3.6.3-linux.1'
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ROOT / 'linux', dest, ignore=shutil.ignore_patterns('__pycache__', 'runtime'))
        runtime = dest / 'runtime'
        runtime.mkdir()
        vendor = ROOT / 'vendor/runtime'
        for name in ('lua', 'lists', 'files'):
            shutil.copytree(vendor / name, runtime / name)
        shutil.copy2(vendor / 'manager-base.template', runtime)
        shutil.copytree(vendor / 'licenses', runtime / 'licenses')
        shutil.copy2(ROOT / 'LICENSE', dest)
        shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', dest)
        # Bundle corresponding engine source, including its license.
        source_archive = dest / ('zapret2-' + VERSION + '-source.tar.gz')
        shutil.copy2(archive, source_archive)
        for arch, expected in HASHES.items():
            binary = upstream / 'binaries' / ('linux-' + arch) / 'nfqws2'
            if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
                raise ValueError('Engine SHA256 mismatch: ' + arch)
            target = runtime / 'bin' / arch
            target.mkdir(parents=True)
            shutil.copy2(binary, target)
            (target / 'nfqws2').chmod(0o755)
        hashes = {str(x.relative_to(runtime)): hashlib.sha256(x.read_bytes()).hexdigest()
                  for x in sorted(runtime.rglob('*')) if x.is_file()}
        (runtime / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
        result = output / (dest.name + '-universal.tar.gz')
        with tarfile.open(result, 'w:gz') as tar:
            tar.add(dest, arcname=dest.name)
        print(result)
        return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.archive:
        package(args.archive, args.output)
    else:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'upstream.tar.gz'
            urllib.request.urlretrieve(f'https://github.com/bol-van/zapret2/releases/download/{VERSION}/zapret2-{VERSION}.tar.gz', archive)
            package(archive, args.output)
