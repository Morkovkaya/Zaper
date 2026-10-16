import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_publish_only_missing_linux_and_exact_digest(self):
        version=release.metadata(); calls=[]
        with tempfile.TemporaryDirectory() as temp:
            asset=Path(temp)/f"Zaper-{version['linux']}-universal.tar.gz";asset.write_bytes(b'tested CI bytes')
            def gh(*args):
                calls.append(args)
                if args[0]=='api': return json.dumps([[dict(tag_name='v'+version['windows'],draft=False)]])
                if args[:2]==('release','view'):return json.dumps(dict(assets=[dict(name=asset.name,size=asset.stat().st_size,digest='sha256:'+hashlib.sha256(asset.read_bytes()).hexdigest())]))
                return ''
            self.assertEqual(release.publish(temp,'owner/repo','commit',gh),['v'+version['linux']])
            self.assertEqual(calls[-1][-1],'--latest=false')
            self.assertTrue(any('--draft' in call for call in calls))
            self.assertFalse(any('v'+version['windows'] in call for call in calls if call[0]=='release'))

    def test_missing_artifact_never_creates_release(self):
        calls=[]
        def gh(*args):calls.append(args);return '[]'
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):release.publish(temp,'repo','commit',gh)
        self.assertTrue(all(call[0]=='api' for call in calls))

    def test_wrong_uploaded_digest_keeps_draft(self):
        versions=release.metadata();calls=[]
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/f"Zapret2Manager-Setup-{versions['windows']}-x64.exe").write_bytes(b'exe')
            def gh(*args):
                calls.append(args)
                return '[]' if args[0]=='api' else '{"assets": []}' if args[:2]==('release','view') else ''
            with self.assertRaises(ValueError):release.publish(temp,'repo','commit',gh)
            self.assertFalse(any(call[:2]==('release','edit') for call in calls))

    def test_draft_from_another_commit_is_not_overwritten(self):
        versions=release.metadata()
        def gh(*args):return json.dumps([[dict(tag_name='v'+versions['windows'],draft=True,target_commitish='other')]])
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):release.publish(temp,'repo','commit',gh)

    def test_installer_version_drift_is_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'src').mkdir();(root/'installer').mkdir()
            shutil.copy2(release.ROOT/'src/AssemblyInfo.cs',root/'src')
            (root/'installer/setup.iss').write_text('AppVersion=0.0.0\n')
            with self.assertRaises(ValueError):release.metadata(root)

    def test_retry_own_draft_and_publish_both_platforms(self):
        versions=release.metadata();calls=[]
        with tempfile.TemporaryDirectory() as temp:
            assets={}
            for name in (f"Zapret2Manager-Setup-{versions['windows']}-x64.exe",f"Zaper-{versions['linux']}-universal.tar.gz"):
                path=Path(temp)/name;path.write_bytes(name.encode());assets[name]=path
            def gh(*args):
                calls.append(args)
                if args[0]=='api':return json.dumps([[dict(tag_name='v'+versions['windows'],draft=True,target_commitish='commit')]])
                if args[:2]==('release','view'):
                    name=next(name for name in assets if args[2][1:] in name)
                    path=assets[name]
                    return json.dumps(dict(assets=[dict(name=name,size=path.stat().st_size,digest='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest())]))
                return ''
            self.assertEqual(len(release.publish(temp,'repo','commit',gh)),2)
            edits=[call for call in calls if call[:2]==('release','edit')]
            self.assertEqual([call[-1] for call in edits],['--latest=true','--latest=false'])
            self.assertEqual(len([call for call in calls if call[:2]==('release','create')]),1)
