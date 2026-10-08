# macOS Git Reminder

本地检查 Git 仓库，提醒忘记提交或推送的修改。无需 AI、Token、网络连接或 Python 第三方依赖。

- 定时检查多个仓库及其 Git worktree，默认每 4 小时一次。
- 统计未提交文件及当前分支相对 upstream 的未推送提交。
- macOS 系统通知；同一状态不重复提醒，恢复正常后再次出现问题会提醒。
- 默认 22:00–09:00 静音，使用本机时区，可指定 IANA 时区。
- 只读取 Git 状态，不暂存、提交、推送或 fetch。

## 安装

需要 macOS、Git 和 Python 3.9+（推荐使用 Homebrew Python）。

```sh
git clone https://github.com/yiqiangchen2026/macos-git-reminder.git
cd macos-git-reminder
cp config.example.json config.json
```

编辑 `config.json` 的项目名称和路径，然后：

```sh
python3 reminder.py --dry-run
python3 reminder.py --test-notification
python3 install.py --config config.json
```

安装器将脚本、配置及日志放入 `~/Library/Application Support/GitReminder`，并创建用户级 LaunchAgent `~/Library/LaunchAgents/com.local.git-reminder.plist`。登录后自动运行，卸载源仓库不影响已安装任务。安装后修改项目请编辑 Application Support 中的配置。

自定义间隔：`python3 install.py --config config.json --interval-hours 2`。

卸载定时任务：`python3 install.py --uninstall`。保留私有配置及日志，方便重新安装。

## 配置

```json
{
  "repositories": [
    {"name": "My project", "path": "~/Projects/my-project"}
  ],
  "quiet_hours": [22, 9],
  "timezone": "Asia/Tokyo"
}
```

`timezone` 为 `null` 或省略时使用本机时区。两个静音小时相等可禁用静音。

## 行为和限制

- 文件数量、路径/状态或未推送数量发生变化才再次提醒。持续编辑同一个文件不会反复通知。
- 未推送数量依据本地 upstream 引用，远端可能滞后；可自行执行 `git fetch` 更新引用。没有 upstream 会提示无法判断。
- detached HEAD 仅检查未提交文件，不计算未推送提交；未检出的本地分支也不检查。
- 休眠或关机期间不会检查。launchd 的间隔不是固定整点时间。
- 系统通知受通知权限和专注模式影响；osascript 调用成功不保证通知横幅显示。请检查“脚本编辑器 / Script Editor”通知权限。
- 通知失败不写入已提醒状态，下次运行可重试。静音期间不消费待提醒状态。
- `check.log`、`error.log`、`state.json` 保存在安装目录。日志包含本地路径和项目名，请勿公开。
- `config.json`、状态及日志已加入 `.gitignore`；发布配置时使用示例文件。

## 测试

```sh
python3 -m unittest discover -s tests -v
```

MIT License.
