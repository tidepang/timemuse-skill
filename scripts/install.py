#!/usr/bin/env python3
"""Install this reviewed local package; never download code or read TimeMuse data."""
import argparse
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

FILES = ('SKILL.md', 'agents/openai.yaml', 'references/contract.md',
         'scripts/evidence.py', 'scripts/install.py', 'README.md')
DEFAULT_TYPES = 'blocks,block_notes,thoughts,reviews,todos,weekly_contexts'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timezone', help='IANA timezone, e.g. Asia/Shanghai')
    parser.add_argument('--types', default=DEFAULT_TYPES)
    parser.add_argument('--install-only', action='store_true', help='Do not activate reading.')
    parser.add_argument('--update', action='store_true', help='Back up an existing Skill before replacement.')
    args = parser.parse_args()
    if not args.install_only:
        if not args.timezone or not sys.stdin.isatty():
            parser.error('Activation needs --timezone and your interactive terminal; use --install-only to defer.')
        ZoneInfo(args.timezone)
    root = Path(__file__).resolve().parents[1]
    for name in FILES:
        source = root / name
        if not source.is_file() or source.is_symlink() or any((root / p).is_symlink() for p in source.relative_to(root).parents if p != Path('.')):
            raise ValueError('Package is incomplete or contains a symlink.')
    base = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().resolve()
    target = base.expanduser().resolve() / 'skills/timemuse-skill'
    if target.is_symlink():
        raise ValueError('Existing Skill is a symlink; leave it unchanged and manage it manually.')
    if target.exists():
        if not args.update:
            raise ValueError('Skill already exists. Review it first, then use --update to keep a backup and replace.')
        if not target.is_dir() or not (target / 'SKILL.md').is_file() or not (target / 'scripts/evidence.py').is_file():
            raise ValueError('Existing path is not a recognized TimeMuse Skill; left unchanged.')
        if 'name: timemuse-skill' not in (target / 'SKILL.md').read_text():
            raise ValueError('Existing Skill has a different identity; left unchanged.')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.timemuse-install-', dir=target.parent))
    backup = None
    try:
        for name in FILES:
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, destination)
        if target.exists():
            stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup_root = base / 'skill-backups'
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / ('timemuse-skill-' + stamp)
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f'Installed: {target}')
    if backup:
        print(f'Previous version retained: {backup}')
    print('Existing consent is unchanged. Start a new conversation if the host has not discovered the Skill.')
    if args.install_only:
        print('Reading was not activated. Follow README to activate or check existing consent.')
        return 0
    return subprocess.call([sys.executable, str(target / 'scripts/evidence.py'), 'setup',
                            '--timezone', args.timezone, '--types', args.types])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f'Installation stopped: {error}', file=sys.stderr)
        sys.exit(1)
