# Codex 完成提示音：macOS / Windows

[English](README.md) · [macOS 详细说明](docs/macos-CN.md) · [Windows 详细说明](docs/windows.md)

本项目在 Codex 回复结束后播放本地提示音。macOS 和 Windows 共用音效库与管理命令，两端采用独立的通知实现。

| 项目 | macOS | Windows |
|---|---|---|
| 运行环境 | Python 3.9+、系统自带 afplay | Python 3.9+、Windows PowerShell、winsound |
| 触发方式 | notify 回调的 agent-turn-complete 事件 | 主会话日志新增 final_answer 记录 |
| 持久配置 | ~/.codex/config.toml | 用户登录计划任务 CodexSoundNotifications |
| 原有 notify | 默认替换，可选转发 | 保持原样 |
| 后台监控 | 无 | 隐藏 Python 进程，每秒检查一次 |
| 默认音效 | celebration.wav | celebration.wav |

提示音表示回复结束，不代表任务执行成功。目前不支持 Linux。

## macOS 安装

```bash
git clone https://github.com/Qin-jiahao/codex-sound-alerts.git ~/.codex/skills/codex-sound-alerts
cd ~/.codex/skills/codex-sound-alerts
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav
```

安装后完全退出并重新打开 Codex。原通知转发、ZIP 音效导入和排错方法见 [macOS 说明](docs/macos-CN.md)。

## Windows 安装（PowerShell）

```powershell
git clone https://github.com/Qin-jiahao/codex-sound-alerts.git "$env:USERPROFILE\.codex\skills\codex-sound-alerts"
Set-Location "$env:USERPROFILE\.codex\skills\codex-sound-alerts"
python scripts/setup_sound_notifications.py --sound-file celebration.wav
```

安装入口会自动选择 Windows 实现。程序会启动后台监控并注册用户登录任务。程序不会修改 Codex 的 notify 配置。自定义路径、旧版迁移和停用方法见 [Windows 说明](docs/windows.md)。请保留安装目录和 Python 解释器路径。

## 切换与试听（两端共用）

macOS 将下列命令的 python 换成 python3：

```text
python scripts/manage_sound_notifications.py --list
python scripts/manage_sound_notifications.py --preview notification.wav
python scripts/manage_sound_notifications.py --apply button.wav --yes
python scripts/manage_sound_notifications.py
```

音效包含 button.wav、notification.wav、celebration.wav 等。Windows 使用原生音频播放，macOS 使用 afplay。带有 loop 名称的文件也只完整播放一次。

## 更新与测试

```text
python scripts/manage_sound_notifications.py --check-update
python scripts/manage_sound_notifications.py --update
python -m unittest discover -s scripts -p "test*.py"
```

Windows 更新代码后，请用选定音效重新运行安装命令以重启监控。Git 更新会拒绝覆盖本地修改。CI 分别在 Windows 和 macOS 运行测试；macOS 专用测试在其他系统上跳过。自动测试不能代替扬声器实际试听。

## 来源

原始项目由 [zty42](https://github.com/zty42/codex-sound-notifications) 创建。本仓库保留 Qin-jiahao 的 macOS 实现，并参考 [YANG301 的 Windows 项目](https://github.com/YANG301/codex-sound-notifications) 的日志监控方式，加入独立的 Python Windows 实现。两个平台共用原有音效库，不包含塔科夫音效。音效来源见 [ASSETS.md](ASSETS.md)，代码许可见 [LICENSE](LICENSE)。
