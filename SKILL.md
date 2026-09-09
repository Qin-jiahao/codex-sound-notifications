---
name: codex-sound-notifications
description: Set up persistent Codex sound notifications on macOS and Windows. Use the Windows session-monitor backend on Windows; on macOS configure Codex's official user-level `notify` command, playing bundled WAV files after completed turns, switching or importing sounds, diagnosing missed or duplicate notifications, and checking or applying skill updates. Use when a user wants a sound after every Codex reply, wants to change or preview the sound, needs to repair completion notifications, or wants to update this skill.
---

# Codex Sound Notifications

Configure a persistent local sound for completed Codex turns. Use the bundled scripts so the sound path, completion filter, and user-level `notify` command remain consistent.

## Platform selection

Detect the operating system before installation. `setup_sound_notifications.py` dispatches automatically. Both platforms share the bundled WAV files and `manage_sound_notifications.py` commands.

### Windows

- Require Python 3.9+, Windows PowerShell, and local Codex session logs.
- Run `python scripts/setup_sound_notifications.py --sound-file celebration.wav`.
- The Windows backend starts a hidden Python monitor and registers the current user's `CodexSoundNotifications` logon task. It does not edit Codex `notify` or require restarting Codex.
- Use `--sound-path` for a local PCM WAV, `--sessions-root` for custom logs, `--no-task` to disable logon startup, and `--no-start` to defer starting the monitor.
- Use the shared manager to list, preview, and apply sounds. It preserves the configured session path and startup preference.
- Read `docs/windows.md` before migrating an existing YANG301 installation so an old monitor cannot cause duplicate playback.
- After code updates, rerun setup with the selected sound to restart the monitor.
- Diagnostics live at `CODEX_HOME/codex-sound-notifications.log` (default `~/.codex`). Playback success logs do not prove that the speaker was audible.
- Run `python -m unittest discover -s scripts -p "test*.py"` after changes. macOS-specific tests skip on Windows.
- Never run the macOS notify configuration workflow on Windows.

### macOS

The requirements, installation workflow and notify behavior below apply to macOS only.

## Requirements

- Run on macOS with `afplay` available.
- Use Python 3.9 or later.
- Expect write access to `~/.codex/config.toml`.
- Bundled sounds are stored under `assets/sounds/`.

## Workflow

1. Confirm that the request concerns persistent turn-completion sounds rather than a one-off preview.
2. Inspect the current top-level `notify` value in `~/.codex/config.toml` before changing it.
3. Prefer an existing WAV file under `assets/sounds/`. Import from a local zip only when the requested sound is absent.
4. Run `python3 scripts/test_sound_notifications.py` before installing after any code change.
5. Use `python3 scripts/setup_sound_notifications.py --sound-file <name>.wav` for the default direct mode.
6. Use `--preserve-existing-notify` only when the user needs the previous notifier and its command accepts the Codex JSON payload as its final argument.
7. Tell the user when direct mode replaces an existing notifier. Do not silently claim that incompatible wrappers are preserved.
8. Restart Codex completely after changing `~/.codex/config.toml`.
9. Verify a normal completed reply and inspect `/tmp/codex-sound-notify.log` if playback does not occur.

## Default behavior

- Default sound: `celebration.wav`
- Completion event: `agent-turn-complete`
- Playback command: `afplay`
- Notification mode: direct
- Duplicate-suppression window: 250 milliseconds
- Forwarded notifier timeout: 5 seconds
- Payload text logging: disabled

Direct mode replaces the existing top-level `notify` value. This mode avoids recursive wrappers and stalled helper processes and should be preferred for Codex Desktop reliability.

## Commands

```bash
python3 scripts/test_sound_notifications.py
python3 scripts/manage_sound_notifications.py
python3 scripts/manage_sound_notifications.py --list
python3 scripts/manage_sound_notifications.py --preview celebration.wav
python3 scripts/manage_sound_notifications.py --apply button.wav --yes
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav --preserve-existing-notify
python3 scripts/setup_sound_notifications.py --zip-path /path/to/sounds.zip --sound-file custom.wav
python3 scripts/manage_sound_notifications.py --check-update
python3 scripts/manage_sound_notifications.py --update
```

## Troubleshooting

- If preview works but completed turns stay silent, restart Codex and confirm that `notify` is a top-level key before the first TOML section.
- If playback occurs only once, update the skill. Current cross-process deduplication uses wall-clock time.
- If a turn produces two sounds, check terminal and TUI notification layers. They are separate from `notify`.
- If preservation mode hangs or misses events, return to direct mode. The runtime limits forwarded commands to five seconds, but it cannot make an incompatible notifier accept argv payloads.
- If setup raises a `tomllib` error, replace the installed copy with this version; current setup code supports Python 3.9.

## Privacy

The runtime log contains event and exit-status metadata. It omits payload text by default. Do not enable `--log-payload-preview` without telling the user that the first 200 payload characters may contain conversation text.

## Updates

Run `--check-update` before `--update`. Git checkouts use `git fetch` and `git pull --ff-only` and refuse to overwrite local modifications. Archive-based installations use the GitHub repository API and preserve extra local files such as imported sounds.

Network access may require approval. Do not overwrite local changes to complete an update.

## Sources of truth

- Codex configuration: `https://developers.openai.com/codex/config-reference`
- Codex hooks and notification context: `https://developers.openai.com/codex/hooks`
- Project documentation: `README.md` and `README-CN.md`

