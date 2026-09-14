import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evidence.py'
spec = importlib.util.spec_from_file_location('evidence', SCRIPT)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'fixture.sqlite'
        self.state = self.root / 'consent.json'
        self.db = sqlite3.connect(self.database)
        self.addCleanup(self.db.close)
        self.db.executescript('''
        CREATE TABLE projects (profile_id TEXT, id TEXT, name TEXT);
        CREATE TABLE time_blocks (profile_id TEXT, id TEXT, project_id TEXT, start_at TEXT, end_at TEXT,
          title TEXT, label TEXT, status TEXT, source TEXT, is_user_edited INTEGER, metadata_json TEXT, updated_at TEXT);
        CREATE TABLE morning_thoughts (profile_id TEXT, local_date_key TEXT, text TEXT, updated_at TEXT);
        CREATE TABLE action_todos (profile_id TEXT, id TEXT, title TEXT, note TEXT, project_id TEXT,
          address_kind TEXT, address_key TEXT, state TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE project_weekly_contexts (profile_id TEXT, local_week_start_key TEXT, project_id TEXT,
          goal_text TEXT, time_reference_kind TEXT, duration_minutes INTEGER, updated_at TEXT);
        CREATE TABLE daily_reviews (profile_id TEXT, id TEXT, local_date_key TEXT, progress_kind TEXT,
          progress_text TEXT, progress_provided INTEGER, signal_text TEXT, tomorrow_kind TEXT,
          tomorrow_provided INTEGER, updated_at TEXT);
        CREATE TABLE activity_events (profile_id TEXT, id TEXT, started_at TEXT, ended_at TEXT,
          event_type TEXT, app_name TEXT, bundle_id TEXT, window_title TEXT, url TEXT, metadata_json TEXT);
        INSERT INTO projects VALUES ('local-profile','p','TimeMuse'), ('local-profile','q','Other');
        INSERT INTO morning_thoughts VALUES ('local-profile','2026-09-01','Try a different direction','2026-09-03T00:00:00.000Z');
        INSERT INTO action_todos VALUES ('local-profile','todo','Ship','Current edited note','p','week','2026-08-31','completed','2026-08-30T00:00:00Z','2026-09-03T00:00:00Z');
        INSERT INTO project_weekly_contexts VALUES ('local-profile','2026-08-31','p','Explore direction','desired',120,'2026-09-01T00:00:00Z');
        INSERT INTO daily_reviews VALUES ('local-profile','review','2026-09-01','text','Changed direction',1,'A useful signal','none',0,'2026-09-02T00:00:00Z');
        INSERT INTO activity_events VALUES ('local-profile','event','2026-09-01T00:00:00Z','2026-09-01T01:00:00Z','foreground','Editor','app.editor','SECRET_TITLE','SECRET_URL','SECRET_OCR');
        ''')
        self.block('b', '2026-08-31T18:00:00.000Z', '2026-08-31T20:00:00.000Z')
        self.db.commit()
        self.consent = dict(version=1, consent='external_ai_selected_evidence', database=str(self.database),
                            profile='local-profile', timezone='Asia/Shanghai', types=list(e.TYPES))
        # Synthetic fixture consent, never a real user's activation.
        self.state.write_text(json.dumps(self.consent))

    def block(self, identity, start, end, status='confirmed', profile='local-profile'):
        meta = json.dumps(dict(userNote='I changed direction', note='SECRET_SYSTEM_NOTE',
                               evidence=['SECRET_OCR'], secondaryProjectID='q', secondaryProjectFraction=.25))
        self.db.execute('INSERT INTO time_blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (profile, identity, 'p', start, end, 'Semantic work', 'work', status, 'generated', 0, meta, '2026-09-04T00:00:00Z'))

    def run_query(self, types='blocks', **kwargs):
        args = type('Args', (), dict(types=types, date_from='2026-09-01', date_to='2026-09-01',
                                    limit=40, project=None, text=None) | kwargs)
        return e.query(args, self.consent)

    def cli(self, *args):
        process = subprocess.run([sys.executable, str(SCRIPT), '--state', str(self.state), *args],
                                 text=True, capture_output=True)
        return process, json.loads(process.stdout)

    def test_missing_configuration_and_persistent_revoke(self):
        self.state.unlink()
        process, result = self.cli('query', '--from', '2026-09-01', '--to', '2026-09-01', '--types', 'blocks')
        self.assertEqual(result['error'], 'configuration_required_run_setup')
        self.assertEqual(process.returncode, 1)
        self.state.write_text(json.dumps(self.consent))
        self.assertFalse(self.cli('revoke')[1]['active'])
        self.assertEqual(json.loads(self.state.read_text()), dict(version=1, enabled=False))
        self.assertFalse(self.cli('status')[1]['active'])
        self.assertEqual(self.cli('query', '--from', '2026-09-01', '--to', '2026-09-01', '--types', 'blocks')[1]['error'], 'reading_disabled')
        self.assertTrue(self.cli('setup', '--timezone', 'Asia/Shanghai')[1]['active'])

    def test_material_allowlist_denies_before_open(self):
        self.consent.update(types=['blocks'], database='/not/a/database')
        with self.assertRaisesRegex(e.EvidenceError, 'materials_not_enabled'):
            self.run_query('block_notes')

    def test_invalid_configuration_is_reported_without_overwrite(self):
        self.state.write_text('[]')
        process, result = self.cli('status')
        self.assertEqual(process.returncode, 1)
        self.assertEqual(result['error'], 'invalid_configuration')
        self.assertEqual(self.state.read_text(), '[]')

    def test_setup_without_input_or_database_read(self):
        args = type('Args', (), dict(types='blocks,thoughts', timezone='Asia/Shanghai',
                                    database=str(self.root/'absent.sqlite'), profile='local-profile', yes=False))
        with patch('builtins.input', side_effect=AssertionError('must not prompt')), patch.object(sqlite3, 'connect', side_effect=AssertionError('must not open database')):
            e.setup(args, self.state)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(e.load_consent(self.state)['types'], ['blocks','thoughts'])

    def test_legacy_yes_flag_uses_defaults_without_database_read(self):
        with patch.dict(os.environ, {'TZ': 'Asia/Shanghai'}):
            process, result = self.cli('setup', '--yes', '--database', str(self.root/'absent.sqlite'))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(result['active'])
        consent = e.load_consent(self.state)
        self.assertEqual(consent['types'], list(e.TYPES[:-1]))
        self.assertEqual(consent['timezone'], 'Asia/Shanghai')
        self.assertFalse((self.root/'absent.sqlite').exists())

    def test_local_timezone_uses_iana_zone_and_rejects_unknown(self):
        with patch.dict(os.environ, {'TZ': ''}), patch.object(Path, 'resolve', return_value=Path('/var/db/timezone/zoneinfo/Asia/Shanghai')):
            self.assertEqual(e.local_timezone(), 'Asia/Shanghai')
        with patch.dict(os.environ, {'TZ': 'America/New_York'}):
            self.assertEqual(e.local_timezone(), 'America/New_York')
        with patch.dict(os.environ, {'TZ': 'Not/AZone'}):
            with self.assertRaisesRegex(e.EvidenceError, 'timezone_not_detected'):
                e.local_timezone()

    def test_day_clipping_split_allocation_and_privacy(self):
        result = self.run_query('blocks,block_notes,activity')
        block = result['items'][0]
        self.assertEqual(block['time']['duration_seconds'], 3600)
        self.assertEqual([x['seconds'] for x in result['allocation']['totals']], [2700,900])
        self.assertEqual(result['items'][1]['authority'], 'user_prose')
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('userNote', json.dumps(self.run_query('blocks')))

    def test_open_rows_do_not_invent_time_and_skipped_profile_excluded(self):
        self.block('open', '2026-09-01T00:00:00Z', None)
        self.block('old-open', '2026-08-01T00:00:00Z', None)
        self.block('hidden', '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z', 'skipped')
        self.block('foreign', '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z', profile='another')
        self.db.commit()
        result = self.run_query()
        self.assertEqual(len(result['items']), 2)
        self.assertIsNone(result['items'][0]['time']['duration_seconds'])
        self.assertEqual(sum(x['seconds'] for x in result['allocation']['totals']),3600)

    def test_dst_uses_utc_elapsed_time(self):
        self.consent['timezone']='America/New_York'
        self.block('dst','2026-10-31T07:00:00Z','2026-11-01T08:00:00Z')
        self.db.commit()
        result=self.run_query(date_from='2026-10-31',date_to='2026-10-31')
        self.assertEqual(result['items'][0]['time']['duration_seconds'],25*3600)

    def test_week_address_and_mutable_current_text(self):
        result=self.run_query('todos,weekly_contexts,thoughts,reviews')
        self.assertEqual(len(result['items']),4)
        todo=result['items'][0]
        self.assertEqual(todo['authority'],'intent')
        self.assertEqual(todo['state'],'completed')
        self.assertEqual(todo['date_key'],'2026-08-31')
        self.assertTrue(todo['mutable'])
        self.assertEqual(result['items'][2]['date_semantics'],'calendar_address')
        self.assertEqual(result['items'][3]['date_semantics'],'review_evidence_day')

    def test_project_secondary_search_and_unsupported_filter(self):
        self.assertEqual(len(self.run_query(project='Other')['items']),1)
        result=self.run_query('blocks,thoughts',project='TimeMuse')
        self.assertEqual(result['coverage']['thoughts']['status'],'unsupported_filter')
        self.assertEqual(len(self.run_query('block_notes',text='DIRECTION')['items']),1)
        self.assertEqual(len(self.run_query('blocks',text='SECRET')['items']),0)
        with self.assertRaises(e.EvidenceError):
            self.run_query(project="' OR 1=1 --")

    def test_review_unprovided_fields_do_not_expose_stale_judgments(self):
        self.db.execute("UPDATE daily_reviews SET progress_provided=0, tomorrow_provided=0")
        self.db.commit()
        result=self.run_query('reviews')
        review=result['items'][0]
        self.assertIsNone(review['progress_kind'])
        self.assertIsNone(review['progress_text'])
        self.assertIsNone(review['tomorrow_kind'])
        self.assertEqual(review['signal_text'],'A useful signal')
        self.assertIsNotNone(e.instant(result['generated_at']))

    def test_missing_schema_and_bounds(self):
        self.db.execute('DROP TABLE daily_reviews')
        self.db.commit()
        result=self.run_query('reviews,blocks')
        self.assertEqual(result['coverage']['reviews']['reason'],'missing_table')
        self.assertEqual(len(result['items']),1)
        with self.assertRaisesRegex(e.EvidenceError,'invalid_query_bounds'):
            self.run_query(date_to='2027-01-01')

    def test_truncation_is_explicit(self):
        self.block('second','2026-09-01T00:00:00Z','2026-09-01T01:00:00Z')
        self.db.execute('UPDATE morning_thoughts SET text=?',('x'*5000,))
        self.db.commit()
        self.assertTrue(self.run_query(limit=1)['coverage']['blocks']['result_truncated'])
        self.assertEqual(self.run_query('thoughts')['coverage']['thoughts']['text_truncated'],1)
        with patch.object(e,'SCAN_LIMIT',1):
            # Catalog must remain under the same scan bound for this test.
            self.db.execute("DELETE FROM projects WHERE id='q'")
            self.db.commit()
            self.assertTrue(self.run_query()['coverage']['blocks']['scan_truncated'])

    def test_cli_wal_story_and_no_database_mutation(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute("INSERT INTO morning_thoughts VALUES ('local-profile','2026-09-02','New direction in WAL','2026-09-02T00:00:00Z')")
        self.db.commit()
        before=self.database.read_bytes()
        wal_before=Path(str(self.database)+'-wal').read_bytes()
        process,result=self.cli('query','--from','2026-09-01','--to','2026-09-07','--types','thoughts,todos','--text','direction')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(len(result['items']),2)
        self.assertEqual(result['items'][0]['source_id'],'morning_thoughts:local-profile:2026-09-02')
        self.assertEqual(self.database.read_bytes(),before)
        self.assertEqual(Path(str(self.database)+'-wal').read_bytes(),wal_before)


if __name__=='__main__':
    unittest.main()
