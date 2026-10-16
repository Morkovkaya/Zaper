import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zaper_updates as updates


class UpdatesTests(unittest.TestCase):
    def test_select_linux_asset_ignores_newer_windows_and_unsigned_assets(self):
        def release(tag,name,digest='sha256:'+'1'*64):
            return dict(tag_name=tag,prerelease=False,html_url='https://github.com/test',assets=[dict(name=name,digest=digest,id=1,size=1)])
        data=[release('v4.0.0','Windows.exe'),release('v3.8.1-linux.1','Zaper-3.8.1-linux.1-universal.tar.gz'),release('v3.8.1-linux.2','Zaper-3.8.1-linux.2-universal.tar.gz')]
        self.assertEqual(updates.select(data)['tag'],'v3.8.1-linux.2')
        with self.assertRaises(RuntimeError):updates.select([release('v3.8.1-linux.2','Zaper-3.8.1-linux.2-universal.tar.gz','')])

    def test_verified_download_and_corruption_preserves_existing_file(self):
        data=b'archive fixture'
        release=dict(name='Zaper-3.8.1-linux.2-universal.tar.gz',size=len(data),sha256=hashlib.sha256(data).hexdigest(),id=1)
        with tempfile.TemporaryDirectory() as temp,patch.object(updates,'check',return_value=release):
            path=Path(temp)/release['name'];path.write_bytes(b'previous')
            with patch.object(updates,'request',return_value=io.BytesIO(b'wrong')):
                with self.assertRaises(ValueError):updates.download(temp)
            self.assertEqual(path.read_bytes(),b'previous')
            self.assertEqual(len(list(Path(temp).iterdir())),1)
            with patch.object(updates,'request',return_value=io.BytesIO(data)):
                self.assertTrue(updates.download(temp)['verified'])
            self.assertEqual(path.read_bytes(),data)

    def test_redirect_strips_token_and_rejects_plain_http(self):
        import urllib.request
        request=urllib.request.Request(updates.API+'/releases/assets/1',headers={'Authorization':'Bearer secret'})
        target=updates.Redirect().redirect_request(request,None,302,'',{},'https://release-assets.githubusercontent.com/file')
        self.assertFalse(target.has_header('Authorization'))
        with self.assertRaises(ValueError):updates.Redirect().redirect_request(request,None,302,'',{},'http://example.org/file')
        with self.assertRaises(ValueError):updates.request(updates.API+'/releases',token='bad\nsecret')

    def test_mismatched_asset_and_prerelease_are_not_selected(self):
        item=dict(tag_name='v3.8.1-linux.4',draft=False,prerelease=False,html_url='https://github.com/test',assets=[dict(name='Zaper-3.8.1-linux.3-universal.tar.gz',digest='sha256:'+'1'*64,id=1,size=1)])
        with self.assertRaises(RuntimeError):updates.select([item])
        item['assets'][0]['name']='Zaper-3.8.1-linux.4-universal.tar.gz';item['prerelease']=True
        with self.assertRaises(RuntimeError):updates.select([item])

    def test_current_or_older_version_does_not_download_or_install(self):
        from zaper_version import VERSION
        for version in ('v'+VERSION,'v1.0.0-linux.1'):
            with patch.object(updates.os,'geteuid',return_value=0),patch.object(updates,'check',return_value=dict(tag=version)),patch.object(updates,'download') as download:
                self.assertFalse(updates.install()['updated']);download.assert_not_called()
        with patch.object(updates.os,'geteuid',return_value=1000),self.assertRaises(PermissionError):updates.install()

    def test_archive_rejects_traversal_links_and_oversize(self):
        import tarfile
        for name,kind,size in [('../escape',tarfile.REGTYPE,1),('Zaper-test/link',tarfile.SYMTYPE,0),('/absolute',tarfile.REGTYPE,1),('Other/file',tarfile.REGTYPE,1),('Zaper-test/huge',tarfile.REGTYPE,513*1024*1024)]:
            with tempfile.TemporaryDirectory() as temp:
                archive=Path(temp)/'test.tar.gz'
                with tarfile.open(archive,'w:gz') as output:
                    member=tarfile.TarInfo(name);member.type=kind;member.size=size
                    # A header alone is enough: reject dangerous metadata before reading data.
                    output.fileobj.write(member.tobuf())
                with self.assertRaises(ValueError):updates.extract(archive,Path(temp)/'out','Zaper-test')

    def test_safe_extract_and_failed_installer(self):
        import tarfile
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'test.tar.gz'
            with tarfile.open(archive,'w:gz') as output:
                for name in ('install.sh','zaper_install.py','dependencies.sh','zapret_manager.py','runtime/sha256.json'):
                    member=tarfile.TarInfo('Zaper-99.0.0-linux.1/'+name);member.size=4
                    output.addfile(member,io.BytesIO(b'test'))
            bundle=updates.extract(archive,root/'out','Zaper-99.0.0-linux.1')
            self.assertTrue((bundle/'install.sh').is_file())
            with patch.object(updates.os,'geteuid',return_value=0),patch.object(updates,'check',return_value=dict(tag='v99.0.0-linux.1')),patch.object(updates,'download',return_value=dict(path=str(archive))),patch('subprocess.run',return_value=subprocess.CompletedProcess([],1,stdout='',stderr='fixture installation failed')):
                with self.assertRaisesRegex(RuntimeError,'fixture installation failed'):updates.install()
