import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reminder', Path(__file__).resolve().parents[1] / 'reminder.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class GitChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo with spaces'
        self.repo.mkdir()
        self.g('init', '-b', 'main')
        self.g('config', 'user.name', 'Test')
        self.g('config', 'user.email', 'test@example.invalid')
        self.g('config', 'commit.gpgsign', 'false')
        (self.repo / 'a').write_text('first')
        self.g('add', 'a')
        self.g('commit', '-m', 'first')
        self.g('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.g('config', 'remote.origin.url', str(self.root / 'unused'))
        self.g('config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*')
        self.g('branch', '--set-upstream-to=origin/main')
        self.config = {'repositories': [{'name': 'Test', 'path': str(self.repo)}]}

    def g(self, *args):
        return subprocess.run([r.GIT, '-C', str(self.repo), *args],
                              check=True, capture_output=True)

    def test_clean_repository(self):
        self.assertEqual(r.inspect(self.config), [])

    def test_unpushed_commit(self):
        (self.repo / 'a').write_text('second')
        self.g('add', 'a')
        self.g('commit', '-m', 'second')
        self.assertIn('未推送 1 个提交', r.inspect(self.config)[0]['text'])

    def test_rename_counts_once_and_ignored_files_are_excluded(self):
        self.g('mv', 'a', 'b')
        (self.repo / 'new\nfile').write_text('new')
        (self.repo / 'ignored').write_text('ignored')
        (self.repo / '.git/info/exclude').write_text('ignored\n')
        self.assertIn('未提交 2 个文件', r.inspect(self.config)[0]['text'])

    def test_missing_upstream_is_unknown(self):
        self.g('branch', '--unset-upstream')
        self.assertIn('无法确认推送状态', r.inspect(self.config)[0]['text'])

    def test_missing_repository_is_not_clean(self):
        self.config['repositories'][0]['path'] = str(self.root / 'missing')
        self.assertIn('无法检查仓库', r.inspect(self.config)[0]['text'])

    def test_linked_detached_worktree(self):
        worktree = self.root / 'another worktree'
        self.g('worktree', 'add', '--detach', str(worktree))
        (worktree / 'new').write_text('new')
        rows = r.inspect(self.config)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['key'], str(worktree.resolve()))
        self.assertIn('detached HEAD', rows[0]['text'])


class Notifications(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.base_patch = patch.object(r, 'BASE', self.directory)
        self.state_patch = patch.object(r, 'STATE', self.directory / 'state.json')
        self.base_patch.start(); self.state_patch.start()
        self.addCleanup(self.base_patch.stop); self.addCleanup(self.state_patch.stop)

    def test_dedup_change_and_rearm_after_clean(self):
        a = [{'key': 'repo', 'signature': 'one', 'text': 'one'}]
        b = [{'key': 'repo', 'signature': 'two', 'text': 'two'}]
        with patch.object(r, 'notify') as notify:
            r.deliver(a); r.deliver(a)
            self.assertEqual(notify.call_count, 1)
            r.deliver(b)
            self.assertEqual(notify.call_count, 2)
            r.deliver([]); r.deliver(b)
            self.assertEqual(notify.call_count, 3)

    def test_failed_notification_is_retried(self):
        row = [{'key': 'repo', 'signature': 'one', 'text': 'one'}]
        with patch.object(r, 'notify', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                r.deliver(row)
        self.assertFalse(r.STATE.exists())
        with patch.object(r, 'notify') as notify:
            r.deliver(row)
            notify.assert_called_once()

    def test_corrupt_state_recovers(self):
        r.STATE.write_text('{broken')
        with patch.object(r, 'notify'):
            r.deliver([{'key': 'repo', 'signature': 'one', 'text': 'one'}])
        self.assertEqual(json.loads(r.STATE.read_text()), {'repo': 'one'})

    def test_quiet_hours_boundaries(self):
        for hour in (22, 23, 0, 8):
            self.assertTrue(r.in_quiet_hours(hour, 22, 9))
        for hour in (9, 12, 21):
            self.assertFalse(r.in_quiet_hours(hour, 22, 9))
        self.assertFalse(r.in_quiet_hours(12, 0, 0))
        self.assertTrue(r.in_quiet_hours(12, 10, 14))


if __name__ == '__main__':
    unittest.main()
