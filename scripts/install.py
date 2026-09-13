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
from evidence import DEFAULT_STATE, DEFAULT_TYPES, EvidenceError, activation_message, load_consent, material_types

FILES = ('SKILL.md', 'agents/openai.yaml', 'references/contract.md',
         'scripts/evidence.py', 'scripts/install.py', 'README.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timezone', help='IANA timezone, e.g. Asia/Shanghai')
    parser.add_argument('--types', default=DEFAULT_TYPES)
    parser.add_argument('--install-only', action='store_true', help='Do not activate reading.')
    parser.add_argument('--update', action='store_true', help='Compatibility flag; existing installs are always backed up.')
    args = parser.parse_args()
    selected = material_types(args.types)
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
    print('如客户端尚未发现 Skill，请新建一个对话。')
    try:
        load_consent(DEFAULT_STATE)
    except EvidenceError:
        pass
    else:
        print('已启用，保留原有读取范围。')
        return 0
    if args.install_only:
        print('已安装，尚未启用读取。')
        return 0
    if not sys.stdin.isatty():
        print('已安装，等待一次确认：' + activation_message(selected))
        print(f'得到用户同意后，运行：{sys.executable} "{target / "scripts/evidence.py"}" setup --yes'
              + (f' --timezone {args.timezone}' if args.timezone else '') + f' --types {args.types}')
        return 0
    command = [sys.executable, str(target / 'scripts/evidence.py'), 'setup', '--types', args.types]
    if args.timezone:
        command.extend(['--timezone', args.timezone])
    return subprocess.call(command)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, EvidenceError) as error:
        print(f'Installation stopped: {error}', file=sys.stderr)
        sys.exit(1)
