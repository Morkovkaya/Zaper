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
