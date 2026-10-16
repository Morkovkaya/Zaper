import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zaper_install as installer


class InstallerTests(unittest.TestCase):
    def test_snapshot_restores_previous_files_symlinks_and_removes_new_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';backup=Path(temp)/'backup';backup.mkdir()
            app=root/'opt/zapret2-manager';app.mkdir(parents=True);(app/'previous').write_text('keep')
            alias=root/'usr/local/bin/zaper';alias.parent.mkdir(parents=True);alias.symlink_to('zapret2-manager')
            installer.snapshot(root,backup)
            (app/'previous').write_text('broken');(app/'new').write_text('new');alias.unlink()
            wrapper=root/'usr/local/bin/zapret2-manager';wrapper.write_text('bad update')
            installer.restore(root,backup)
            self.assertEqual((app/'previous').read_text(),'keep');self.assertFalse((app/'new').exists())
            self.assertEqual(os.readlink(alias),'zapret2-manager');self.assertFalse(wrapper.exists())

    def test_dependency_plans_do_not_upgrade_the_system_or_install_drivers(self):
        source=(Path(__file__).resolve().parents[1]/'dependencies.sh').read_text()
        for distro,manager in [('arch','pacman'),('ubuntu','apt-get'),('fedora','dnf'),('opensuse-tumbleweed','zypper')]:
            script=source.replace('. /etc/os-release',f'ID={distro}; ID_LIKE=')
            result=subprocess.run(['/bin/sh','-c',script],env=dict(os.environ,ZAPER_PRINT_DEPENDENCIES='1'),capture_output=True,text=True,check=True)
            words=result.stdout.splitlines();self.assertEqual(words[0],manager)
            self.assertNotIn('-Syu',words);self.assertNotIn('upgrade',words)
            self.assertTrue(any('cairo' in word for word in words))
        script=source.replace('. /etc/os-release','ID=unknown; ID_LIKE=')
        self.assertNotEqual(subprocess.run(['/bin/sh','-c',script],capture_output=True).returncode,0)
