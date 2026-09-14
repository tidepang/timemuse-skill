import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install.py'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.env = dict(os.environ, HOME=str(self.home), CODEX_HOME=str(self.home / '.codex'), TZ='Asia/Shanghai')
        self.target = self.home / '.codex/skills/timemuse-skill'
        self.consent = self.home / 'Library/Application Support/TimeMuseSkill/consent.json'

    def run_install(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              input='', capture_output=True, text=True, env=self.env)

    def test_install_is_self_contained_without_consent_or_database(self):
        result = self.run_install('--install-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / 'scripts/evidence.py').is_file())
        self.assertTrue((self.target / 'references/contract.md').is_file())
        self.assertFalse(self.consent.exists())
        self.assertFalse((self.home / 'Library/Application Support/TimeMuse').exists())
        status = subprocess.run([sys.executable, str(self.target / 'scripts/evidence.py'), 'status'],
                                env=self.env, capture_output=True, text=True)
        self.assertIn('configuration_required_run_setup', status.stdout)

    def test_update_preserves_previous_files_and_consent(self):
        self.assertEqual(self.run_install('--install-only').returncode, 0)
        (self.target / 'personal.txt').write_text('keep my changes')
        self.consent.parent.mkdir(parents=True)
        consent = json.dumps(dict(version=1, consent='external_ai_selected_evidence',
                                  database=str(self.home/'absent.sqlite'), profile='local-profile',
                                  timezone='Asia/Shanghai', types=['block_notes']))
        self.consent.write_text(consent)
        result = self.run_install('--types', 'blocks,activity', '--timezone', 'America/New_York')
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((self.home / '.codex/skill-backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'personal.txt').read_text(), 'keep my changes')
        self.assertEqual(self.consent.read_text(), consent)
        self.assertIn('已启用，保留原有读取范围', result.stdout)
        self.assertNotIn('等待一次确认', result.stdout)

    def test_unknown_directory_and_symlink_are_never_replaced(self):
        self.target.mkdir(parents=True)
        marker = self.target / 'personal.txt'
        marker.write_text('untouched')
        self.assertNotEqual(self.run_install('--install-only', '--update').returncode, 0)
        self.assertEqual(marker.read_text(), 'untouched')
        marker.unlink()
        self.target.rmdir()
        self.target.symlink_to(self.home, target_is_directory=True)
        self.assertNotEqual(self.run_install('--install-only', '--update').returncode, 0)
        self.assertTrue(self.target.is_symlink())

    def test_noninteractive_install_configures_reading_without_database(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.target.exists())
        config = json.loads(self.consent.read_text())
        self.assertTrue(config['enabled'])
        self.assertEqual(config['types'], ['blocks', 'block_notes', 'thoughts', 'reviews', 'todos', 'weekly_contexts'])
        self.assertEqual(config['timezone'], 'Asia/Shanghai')
        self.assertFalse((self.home / 'Library/Application Support/TimeMuse').exists())
        status = subprocess.run([sys.executable, str(self.target / 'scripts/evidence.py'), 'status'],
                                env=self.env, capture_output=True, text=True)
        self.assertTrue(json.loads(status.stdout)['active'])

    def test_old_unconfigured_install_gets_defaults_on_update(self):
        self.assertEqual(self.run_install('--install-only').returncode, 0)
        self.assertFalse(self.consent.exists())
        self.assertEqual(self.run_install().returncode, 0)
        self.assertTrue(json.loads(self.consent.read_text())['enabled'])

    def test_revoke_survives_update_until_explicit_setup(self):
        self.assertEqual(self.run_install().returncode, 0)
        helper = [sys.executable, str(self.target / 'scripts/evidence.py')]
        revoked = subprocess.run(helper + ['revoke'], env=self.env, capture_output=True, text=True)
        self.assertEqual(revoked.returncode, 0, revoked.stderr)
        disabled = self.consent.read_bytes()
        self.assertEqual(self.run_install().returncode, 0)
        self.assertEqual(self.consent.read_bytes(), disabled)
        resumed = subprocess.run(helper + ['setup'], env=self.env, input='', capture_output=True, text=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertTrue(json.loads(self.consent.read_text())['enabled'])
