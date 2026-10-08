#!/usr/bin/env python3
"""Read-only local Git checks. Uses no network, AI, or third-party packages."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
STATE = BASE / 'state.json'
GIT = shutil.which('git') or '/usr/bin/git'

def git(path, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    result = subprocess.run([GIT, '-C', str(path), *args], capture_output=True,
                            timeout=30, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip()[:300])
    return result.stdout

def inspect(config):
    findings = []
    for repo in config['repositories']:
        try:
            repo = dict(repo, path=str(Path(repo['path']).expanduser().resolve()))
            raw = git(repo['path'], 'worktree', 'list', '--porcelain', '-z')
            paths = [part[9:].decode(errors='surrogateescape') for part in raw.split(b'\0')
                     if part.startswith(b'worktree ')]
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            findings.append({'key': repo['path'], 'text': repo['name'] + ': 无法检查仓库',
                             'detail': str(exc), 'signature': 'repository-unavailable'})
            continue
        for path in paths:
            try:
                if git(path, 'rev-parse', '--is-bare-repository').strip() == b'true':
                    continue
                status = git(path, 'status', '--porcelain=v1', '-z')
                parts = status.split(b'\0')
                count, index = 0, 0
                while index < len(parts):
                    entry = parts[index]
                    if entry:
                        count += 1
                        if b'R' in entry[:2] or b'C' in entry[:2]:
                            index += 1
                    index += 1
                branch = git(path, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip()
                ahead = 0
                tracking = ''
                if branch != 'HEAD':
                    upstream = git(path, 'for-each-ref', '--format=%(upstream)',
                                   'refs/heads/' + branch).decode().strip()
                    if upstream:
                        ahead = int(git(path, 'rev-list', '--count', upstream + '..HEAD'))
                    else:
                        # An absent upstream is not evidence that all history is unpushed.
                        tracking = '未设置 upstream，无法确认推送状态'
                elif count:
                    tracking = 'detached HEAD'
                if count or ahead or tracking:
                    label = repo['name'] + ' / ' + branch
                    if path != repo['path']:
                        label += ' (' + Path(path).name + ')'
                    text = f'{label}: 未提交 {count} 个文件，未推送 {ahead} 个提交'
                    if tracking:
                        text = f'{label}: 未提交 {count} 个文件；{tracking}'
                    fingerprint = hashlib.sha256(status + str(ahead).encode() + tracking.encode()).hexdigest()
                    findings.append({'key': path, 'text': text, 'signature': fingerprint})
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                findings.append({'key': path, 'text': repo['name'] + ': 无法检查工作区',
                                 'detail': str(exc), 'signature': 'worktree-unavailable'})
    return findings

def notify(body):
    # Arguments are passed as data, never interpolated into AppleScript source.
    source = '''on run argv
display notification (item 1 of argv) with title "Git 提交 / 推送提醒"
end run'''
    subprocess.run(['/usr/bin/osascript', '-e', source, body], check=True, timeout=20)

def save_state(value):
    fd, name = tempfile.mkstemp(dir=BASE, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=True)
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def in_quiet_hours(hour, start, end):
    return (hour >= start or hour < end) if start > end else start <= hour < end

def deliver(findings):
    try:
        previous = json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    current = {item['key']: item['signature'] for item in findings}
    changed = [item for item in findings if previous.get(item['key']) != item['signature']]
    if changed:
        body = '\n'.join(item['text'] for item in changed[:4])
        if len(changed) > 4:
            body += f'\n另有 {len(changed) - 4} 个工作区需要检查。'
        notify(body)
    save_state(current)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Inspect without notification or state writes')
    parser.add_argument('--test-notification', action='store_true')
    args = parser.parse_args()
    if args.test_notification:
        notify('本地 Git 提醒已配置，不使用 AI Token。')
        print('通知请求已提交给 macOS；显示由系统通知设置决定。')
        return
    config = json.loads((BASE / 'config.json').read_text())
    timezone = config.get('timezone')
    now = datetime.datetime.now(ZoneInfo(timezone)) if timezone else datetime.datetime.now().astimezone()
    start, end = config['quiet_hours']
    quiet = in_quiet_hours(now.hour, start, end)
    if quiet and not args.dry_run:
        return
    findings = inspect(config)
    print(json.dumps({'checked_at': now.isoformat(), 'findings': findings,
                      'note': '未推送数量依据本地 upstream 引用；未联网 fetch。'}, ensure_ascii=True))
    if args.dry_run:
        return
    deliver(findings)

if __name__ == '__main__':
    main()
