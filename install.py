#!/usr/bin/env python3
"""Install a per-user macOS LaunchAgent with an absolute Python path."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

LABEL = 'com.local.git-reminder'
SOURCE = Path(__file__).resolve().parent
TARGET = Path.home() / 'Library/Application Support/GitReminder'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')

def validate(config):
    if not isinstance(config.get('repositories'), list) or not config['repositories']:
        raise ValueError('Configure at least one repository')
    for item in config['repositories']:
        if not isinstance(item.get('name'), str) or not isinstance(item.get('path'), str):
            raise ValueError('Each repository requires a name and a path')
        item['path'] = str(Path(item['path']).expanduser().resolve())
    hours = config.get('quiet_hours', [22, 9])
    if not isinstance(hours, list) or len(hours) != 2 or any(type(h) is not int or not 0 <= h <= 23 for h in hours):
        raise ValueError('quiet_hours must contain two hours between 0 and 23')
    config['quiet_hours'] = hours
    if config.get('timezone'):
        ZoneInfo(config['timezone'])
    return config

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Private JSON configuration to install')
    parser.add_argument('--interval-hours', type=int, default=4)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Installation requires macOS')
    if sys.version_info < (3, 9):
        parser.error('Python 3.9 or later is required')
    service = f'gui/{os.getuid()}/{LABEL}'
    if args.uninstall:
        subprocess.run(['/bin/launchctl', 'bootout', service], capture_output=True)
        PLIST.unlink(missing_ok=True)
        print(f'Uninstalled LaunchAgent. Kept private configuration and logs in {TARGET}')
        return
    if args.interval_hours < 1:
        parser.error('--interval-hours must be at least 1')
    config_path = args.config or TARGET / 'config.json'
    if not config_path.is_file():
        parser.error('Copy config.example.json to config.json, edit your repositories, then use --config config.json')
    config = validate(json.loads(config_path.read_text()))
    # Validate everything before stopping an existing installation.
    subprocess.run(['/bin/launchctl', 'bootout', service], capture_output=True)
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / 'reminder.py', TARGET / 'reminder.py')
    (TARGET / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    definition = {
        'Label': LABEL,
        'ProgramArguments': [str(Path(sys.executable).resolve()), str(TARGET / 'reminder.py')],
        'StartInterval': args.interval_hours * 3600,
        'RunAtLoad': True,
        'ProcessType': 'Background',
        'StandardOutPath': str(TARGET / 'check.log'),
        'StandardErrorPath': str(TARGET / 'error.log'),
        'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'},
    }
    PLIST.write_bytes(plistlib.dumps(definition))
    subprocess.run(['/bin/launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
    print(f'Installed {LABEL}: every {args.interval_hours} hours. Configuration: {TARGET / "config.json"}')

if __name__ == '__main__':
    main()
