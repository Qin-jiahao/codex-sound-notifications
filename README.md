# Codex Sound Notifications — macOS & Windows

[简体中文](README-CN.md) · [macOS guide](docs/macos.md) · [Windows guide](docs/windows.md)

Play a local sound when Codex finishes a reply. Both platforms share the bundled WAV collection and sound manager; their notification backends are separate.

| | macOS | Windows |
|---|---|---|
| Runtime | Python 3.9+ and `afplay` | Python 3.9+, Windows PowerShell and `winsound` |
| Trigger | Codex `notify`: `agent-turn-complete` | New primary-session assistant `final_answer` records |
| Persistence | User-level `~/.codex/config.toml` | Per-user `CodexSoundNotifications` logon task |
| Existing `notify` | Replaced by default; optional forwarding | Unchanged |
| Background monitor | None | Hidden Python process, one-second polling |
| Default sound | `celebration.wav` | `celebration.wav` |

A final reply does not guarantee that the underlying task succeeded. Linux is currently unsupported.

## Install on macOS

```bash
git clone https://github.com/Qin-jiahao/codex-sound-notifications.git ~/.codex/skills/codex-sound-notifications
cd ~/.codex/skills/codex-sound-notifications
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav
```

Restart Codex completely after setup. See the [macOS guide](docs/macos.md) for existing-notifier forwarding, ZIP imports and troubleshooting.

## Install on Windows (PowerShell)

```powershell
git clone https://github.com/Qin-jiahao/codex-sound-notifications.git "$env:USERPROFILE\.codex\skills\codex-sound-notifications"
Set-Location "$env:USERPROFILE\.codex\skills\codex-sound-notifications"
python scripts/setup_sound_notifications.py --sound-file celebration.wav
```

Setup automatically selects the Windows backend. It starts the monitor and registers logon startup. See the [Windows guide](docs/windows.md) for custom paths, migration and removal. Keep the installed repository and Python interpreter at their installation paths.

## Choose a sound (both platforms)

Use `python3` on macOS and `python` on Windows:

```text
python scripts/manage_sound_notifications.py --list
python scripts/manage_sound_notifications.py --preview notification.wav
python scripts/manage_sound_notifications.py --apply button.wav --yes
python scripts/manage_sound_notifications.py
```

The manager uses `afplay` on macOS and Windows native playback on Windows. It supports the same bundled sounds, including `button.wav`, `notification.wav`, and `celebration.wav`. Files named `*_loop.wav` are finite WAV files; the monitor does not loop them indefinitely.

## Updates and tests

```text
python scripts/manage_sound_notifications.py --check-update
python scripts/manage_sound_notifications.py --update
python -m unittest discover -s scripts -p "test*.py"
```

After updating Windows code, rerun setup with your chosen sound to restart the monitor. Git updates refuse to overwrite local changes. CI runs on Windows and macOS; macOS-specific tests are skipped on other platforms. Actual speaker loudness requires a listening check on the target computer.

## Credits

The original sound-notification project is by [zty42](https://github.com/zty42/codex-sound-notifications). This repository retains the Qin-jiahao macOS implementation and adds a Windows backend inspired by the session-monitor approach in [YANG301's Windows project](https://github.com/YANG301/codex-sound-notifications). The Windows backend here is implemented in Python and shares the existing sound collection; it does not bundle the Tarkov sound. See [ASSETS.md](ASSETS.md) for audio provenance and [LICENSE](LICENSE) for the repository code license.
