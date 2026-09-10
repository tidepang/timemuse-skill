#!/usr/bin/env python3
"""Bounded local TimeMuse evidence. No third-party packages or database writes."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = 1
TYPES = ('blocks', 'block_notes', 'thoughts', 'reviews', 'todos', 'weekly_contexts', 'activity')
DEFAULT_STATE = Path.home() / 'Library/Application Support/TimeMuseSkill/consent.json'
DEFAULT_DB = Path.home() / 'Library/Application Support/TimeMuse/timemuse.sqlite'
SCAN_LIMIT = 2000
TEXT_LIMIT = 4000


class EvidenceError(Exception):
    pass


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False))


def material_types(value):
    selected = list(dict.fromkeys(value.split(',')))
    if not selected or any(x not in TYPES for x in selected):
        raise EvidenceError('invalid_material_types')
    return selected


def load_consent(path):
    if not path.exists():
        raise EvidenceError('consent_required')
    try:
        value = json.loads(path.read_text())
        if (value['version'] != VERSION or value['consent'] != 'external_ai_selected_evidence'
                or not isinstance(value['database'], str) or not Path(value['database']).is_absolute()
                or not isinstance(value['profile'], str) or not value['profile']
                or not isinstance(value['types'], list)
                or not value['types'] or any(x not in TYPES for x in value['types'])):
            raise ValueError()
        ZoneInfo(value['timezone'])
        return value
    except (ValueError, KeyError, TypeError, ZoneInfoNotFoundError):
        raise EvidenceError('invalid_consent') from None


def setup(args, path):
    selected = material_types(args.types)
    ZoneInfo(args.timezone)
    if not sys.stdin.isatty():
        raise EvidenceError('setup_requires_user_terminal')
    print('TimeMuse Skill: selected records will be returned to your AI conversation and may', file=sys.stderr)
    print('be processed by its external AI service. No publishing permission is granted.', file=sys.stderr)
    print('This grants these material types across history; each query is bounded to 93 days.', file=sys.stderr)
    print('User prose may itself contain private information. No raw titles/URLs, OCR or images.', file=sys.stderr)
    print(f'Database: {Path(args.database).expanduser().resolve()}\nProfile: {args.profile}', file=sys.stderr)
    print(f'Timezone: {args.timezone}\nMaterials: {", ".join(selected)}', file=sys.stderr)
    print('Type ALLOW TIMEMUSE EVIDENCE to activate, anything else to cancel:', file=sys.stderr)
    if input().strip() != 'ALLOW TIMEMUSE EVIDENCE':
        raise EvidenceError('setup_cancelled')
    value = dict(version=VERSION, consent='external_ai_selected_evidence',
                 database=str(Path(args.database).expanduser().resolve()), profile=args.profile,
                 timezone=args.timezone, types=selected, granted_at=dt.datetime.now(dt.timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle)
    return dict(version=VERSION, active=True, types=selected)


def instant(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone_required')
    return result.astimezone(dt.timezone.utc)


def day(value):
    result = dt.date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError('invalid_date')
    return result


def interval(row, start_col, end_col, begin, finish):
    start = instant(row[start_col])
    end = instant(row[end_col]) if row[end_col] else None
    if end is not None and end <= start:
        raise ValueError('invalid_interval')
    if start >= finish or (end is not None and end <= begin):
        return None
    # A historical open row has no defensible end. Include only its start day.
    if end is None and start < begin:
        return None
    return dict(start_at=start.isoformat(), end_at=end.isoformat() if end else None,
                clipped_start=max(start, begin).isoformat(),
                clipped_end=min(end, finish).isoformat() if end else None,
                duration_seconds=(min(end, finish)-max(start, begin)).total_seconds() if end else None,
                duration_known=end is not None, date_semantics='evidence_day_03:00')


def query(args, consent):
    kinds = material_types(args.types)
    if not set(kinds) <= set(consent['types']):
        raise EvidenceError('materials_not_authorized')
    first, last = day(args.date_from), day(args.date_to)
    if not 0 <= (last-first).days < 93 or not 1 <= args.limit <= 200:
        raise EvidenceError('invalid_query_bounds')
    if args.text is not None and not 1 <= len(args.text) <= 200:
        raise EvidenceError('invalid_search_text')
    zone = ZoneInfo(consent['timezone'])
    begin = dt.datetime.combine(first, dt.time(3), zone).astimezone(dt.timezone.utc)
    finish = dt.datetime.combine(last+dt.timedelta(days=1), dt.time(3), zone).astimezone(dt.timezone.utc)
    dbpath = Path(consent['database'])
    if not dbpath.is_file():
        raise EvidenceError('database_unavailable')
    db = sqlite3.connect(dbpath.as_uri()+'?mode=ro', uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('BEGIN')
        return retrieve(db, args, consent, kinds, first, last, begin, finish)
    finally:
        db.close()


def retrieve(db, args, consent, kinds, first, last, begin, finish):
    coverage, items = {}, []
    profile = consent['profile']
    # Only named tables/columns are projected. No SELECT *, metadata dumps or raw SQL interface.
    def rows(table, columns, where='1', bindings=(), order='rowid'):
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            raise EvidenceError('missing_table')
        available = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
        if not set(columns.split(', ')) <= available or 'profile_id' not in available:
            raise EvidenceError('unsupported_columns')
        return db.execute(f'SELECT {columns} FROM {table} WHERE profile_id=? AND ({where}) ORDER BY {order} LIMIT ?',
                          (profile, *bindings, SCAN_LIMIT+1)).fetchall()

    projects = {}
    try:
        project_rows = rows('projects', 'id, name', order='id')
        if len(project_rows) > SCAN_LIMIT:
            raise EvidenceError('project_catalog_too_large')
        projects = {r['id']: r['name'] for r in project_rows}
    except EvidenceError as error:
        if args.project:
            raise EvidenceError('project_catalog_unavailable') from error
    project_id = None
    if args.project:
        matches = [key for key, name in projects.items() if key == args.project or name == args.project]
        if len(matches) != 1:
            raise EvidenceError('project_not_found_or_ambiguous')
        project_id = matches[0]

    def allocations(row, meta):
        primary = row['project_id']
        secondary, fraction = meta.get('secondaryProjectID'), meta.get('secondaryProjectFraction')
        valid = (primary and secondary in projects and secondary != primary
                 and type(fraction) in (int, float) and math.isfinite(fraction) and 0 < fraction < 1)
        if valid:
            fraction = min(.99, max(.01, fraction))
            values = [(primary, 1-fraction), (secondary, fraction)]
        else:
            values = [(primary, 1)]
        return [dict(project_id=key, project_name=projects.get(key), fraction=weight) for key, weight in values]

    for kind in kinds:
        report = dict(status='available', scanned=0, returned=0, scan_truncated=False,
                      result_truncated=False, invalid_rows=0, text_truncated=0)
        coverage[kind] = report
        if project_id and kind in ('thoughts', 'reviews', 'activity'):
            report.update(status='unsupported_filter', reason='no_canonical_project_link')
            continue
        try:
            if kind in ('blocks', 'block_notes'):
                source = 'time_blocks'
                data = rows(source, 'id, project_id, start_at, end_at, title, label, status, source, is_user_edited, metadata_json, updated_at',
                            "julianday(start_at) < julianday(?) AND (julianday(end_at) > julianday(?) OR (end_at IS NULL AND julianday(start_at) >= julianday(?))) AND status != 'skipped'",
                            (finish.isoformat(), begin.isoformat(), begin.isoformat()), 'start_at DESC, id')
            elif kind == 'activity':
                source = 'activity_events'
                data = rows(source, 'id, started_at, ended_at, event_type, app_name, bundle_id',
                            'julianday(started_at) < julianday(?) AND (julianday(ended_at) > julianday(?) OR (ended_at IS NULL AND julianday(started_at) >= julianday(?)))',
                            (finish.isoformat(), begin.isoformat(), begin.isoformat()), 'started_at DESC, id')
            elif kind in ('thoughts', 'reviews'):
                source = 'morning_thoughts' if kind == 'thoughts' else 'daily_reviews'
                cols = ('local_date_key, text, updated_at' if kind == 'thoughts' else
                        'id, local_date_key, progress_kind, progress_text, progress_provided, signal_text, tomorrow_kind, tomorrow_provided, updated_at')
                data = rows(source, cols, 'local_date_key >= ? AND local_date_key <= ?',
                            (first.isoformat(), last.isoformat()), 'local_date_key DESC')
            else:
                source = 'action_todos' if kind == 'todos' else 'project_weekly_contexts'
                cols = ('id, title, note, project_id, address_kind, address_key, state, created_at, updated_at' if kind == 'todos' else
                        'local_week_start_key, project_id, goal_text, time_reference_kind, duration_minutes, updated_at')
                key = 'address_key' if kind == 'todos' else 'local_week_start_key'
                # Weekly addresses intersect the requested calendar range, not Evidence Day.
                where = (f"{key} <= ? AND (" + (f"(address_kind='day' AND {key} >= ?) OR (address_kind='week' AND date({key}, '+6 days') >= ?)" if kind == 'todos' else f"date({key}, '+6 days') >= ?") + ')')
                params = (last.isoformat(), first.isoformat(), first.isoformat()) if kind == 'todos' else (last.isoformat(), first.isoformat())
                if project_id:
                    where += ' AND project_id = ?'
                    params += (project_id,)
                data = rows(source, cols, where, params, key+' DESC')
        except EvidenceError as error:
            report.update(status='unavailable', reason=str(error))
            continue
        report['scan_truncated'] = len(data) > SCAN_LIMIT
        for raw in data[:SCAN_LIMIT]:
            report['scanned'] += 1
            r = dict(raw)
            try:
                record = dict(material=kind, source_table=source, profile_id=profile)
                if kind in ('blocks', 'block_notes'):
                    meta = json.loads(r['metadata_json'])
                    if not isinstance(meta, dict):
                        raise ValueError()
                    span = interval(r, 'start_at', 'end_at', begin, finish)
                    if not span:
                        continue
                    assigned = allocations(r, meta)
                    if project_id and project_id not in [p['project_id'] for p in assigned]:
                        continue
                    record.update(source_id=f"{source}:{r['id']}", time=span, allocations=assigned,
                                  updated_at=r['updated_at'])
                    if kind == 'block_notes':
                        if not isinstance(meta.get('userNote'), str) or not meta['userNote'].strip():
                            continue
                        record.update(source_id=record['source_id']+':userNote', text=meta['userNote'],
                                      authority='user_prose', mutable=True)
                    else:
                        record.update(title=r['title'], label=r['label'], status=r['status'],
                                      origin=r['source'], is_user_edited=bool(r['is_user_edited']),
                                      authority='recorded_semantic_time', mutable=True)
                elif kind == 'activity':
                    span = interval(r, 'started_at', 'ended_at', begin, finish)
                    if not span:
                        continue
                    record.update(source_id=f"{source}:{r['id']}", time=span, authority='observed_app_activity',
                                  event_type=r['event_type'], app_name=r['app_name'], bundle_id=r['bundle_id'])
                else:
                    key = r.get('local_date_key') or r.get('address_key') or r.get('local_week_start_key')
                    day(key)
                    identity = r.get('id') or (profile+':'+key+(':'+r['project_id'] if kind == 'weekly_contexts' else ''))
                    record.update(source_id=source+':'+identity, date_key=key,
                                  date_semantics='review_evidence_day' if kind == 'reviews' else 'calendar_address',
                                  authority='intent' if kind in ('todos', 'weekly_contexts') else 'user_prose', mutable=True)
                    record.update({k: v for k, v in r.items() if k != 'id'})
                    if kind == 'reviews':
                        if not r['progress_provided']:
                            record.update(progress_kind=None, progress_text=None)
                        if not r['tomorrow_provided']:
                            record['tomorrow_kind'] = None
                    if 'project_id' in r:
                        record['project_name'] = projects.get(r['project_id'])
                searchable = [record.get(k) for k in ('text', 'title', 'note', 'goal_text', 'progress_text', 'signal_text', 'app_name', 'label')]
                searchable += [projects.get(r.get('project_id'))]
                if args.text and not any(args.text.casefold() in v.casefold() for v in searchable if isinstance(v, str)):
                    continue
                for key, value in list(record.items()):
                    if isinstance(value, str) and len(value) > TEXT_LIMIT:
                        record[key] = value[:TEXT_LIMIT]
                        record.setdefault('truncated_fields', []).append(key)
                        report['text_truncated'] += 1
                if report['returned'] >= args.limit:
                    report['result_truncated'] = True
                    continue
                items.append(record)
                report['returned'] += 1
            except (ValueError, TypeError, KeyError, OverflowError):
                report['invalid_rows'] += 1
    totals = {}
    for item in items:
        if item['material'] == 'blocks' and item['time']['duration_known']:
            for allocation in item['allocations']:
                key = allocation['project_id']
                totals[key] = totals.get(key, 0) + item['time']['duration_seconds']*allocation['fraction']
    return dict(version=VERSION, generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                query=dict(date_from=first.isoformat(), date_to=last.isoformat(),
                timezone=consent['timezone'], evidence_start=begin.isoformat(), evidence_end_exclusive=finish.isoformat(),
                types=kinds, project_id=project_id, text=args.text, limit_per_type=args.limit),
                coverage=coverage, items=items,
                allocation=dict(scope='returned_closed_blocks_only_not_verified_attention_or_completion',
                                totals=[dict(project_id=k, project_name=projects.get(k), seconds=v) for k, v in totals.items()]),
                limitations=['No capture completeness guarantee; missing records are not inactivity.',
                             'Open rows are included only when their start lies in range; duration is unknown.',
                             'Editable prose is current text, not a historical snapshot.',
                             'Not supported: review drafts, weekly judgments, Backlog, recurrence templates, Focus/Break, Muse messages, raw titles/URLs, OCR or screenshots.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE, help='Consent file (isolated fixtures or alternate installation).')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('revoke')
    setup_parser = commands.add_parser('setup', help='User-operated interactive consent; does not read database.')
    setup_parser.add_argument('--database', default=str(DEFAULT_DB))
    setup_parser.add_argument('--profile', default='local-profile')
    setup_parser.add_argument('--timezone', required=True)
    setup_parser.add_argument('--types', required=True)
    q = commands.add_parser('query')
    q.add_argument('--from', dest='date_from', required=True)
    q.add_argument('--to', dest='date_to', required=True)
    q.add_argument('--types', required=True)
    q.add_argument('--project')
    q.add_argument('--text')
    q.add_argument('--limit', type=int, default=40)
    args = parser.parse_args()
    try:
        if args.command == 'revoke':
            args.state.unlink(missing_ok=True)
            result = dict(version=VERSION, active=False)
        elif args.command == 'setup':
            result = setup(args, args.state)
        else:
            consent = load_consent(args.state)
            result = (dict(version=VERSION, active=True, types=consent['types'], timezone=consent['timezone'])
                      if args.command == 'status' else query(args, consent))
        emit(result)
        return 0
    except EvidenceError as error:
        emit(dict(version=VERSION, error=str(error)))
    except (sqlite3.Error, OSError):
        emit(dict(version=VERSION, error='local_read_or_state_failure'))
    except (ValueError, TypeError, ZoneInfoNotFoundError, EOFError):
        emit(dict(version=VERSION, error='invalid_input_or_data'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
