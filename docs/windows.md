# Windows 安装与维护 / Windows guide

Windows uses a hidden Python monitor and `winsound`. macOS uses `notify` and `afplay`; do not use the macOS configuration steps on Windows.

## 安装与音效

在仓库根目录的 PowerShell 中运行：

```powershell
python scripts/setup_sound_notifications.py --sound-file celebration.wav
python scripts/manage_sound_notifications.py --preview celebration.wav
python scripts/manage_sound_notifications.py --apply notification.wav --yes
```

自定义 WAV 和会话目录：

```powershell
python scripts/setup_sound_notifications.py --sound-path "C:\Sounds\custom.wav"
python scripts/setup_sound_notifications.py --sessions-root "D:\Codex\sessions" --sound-file celebration.wav
```

Windows supports PCM WAV files readable by Python's `wave` module and Windows `winsound`. ZIP import and `--preserve-existing-notify` are macOS-only options. Windows never edits `config.toml`.

## 自启动 / Startup

The installer registers the current user's `CodexSoundNotifications` logon task. A hidden WScript launcher starts the Python monitor. Python remains installed and is required at every login. No administrator run level is requested, although machine policy may restrict task registration.

```powershell
# Configure logon startup without starting the monitor now:
python scripts/setup_sound_notifications.py --no-start
# Start now, removing this tool's existing logon task if present:
python scripts/setup_sound_notifications.py --no-task
```

Both setup commands stop a running monitor from the same installation first. The shared sound manager preserves the previously configured sessions directory and logon preference.

Paths (under `CODEX_HOME`, or `%USERPROFILE%\.codex` by default):

| File | Purpose |
|---|---|
| `windows-sound-notifications.json` | Selected sound, sessions directory, startup preference |
| `codex-sound-notifications-launcher.vbs` | Generated launcher with absolute local paths |
| `codex-sound-notifications.log` | Diagnostic events, no reply text |

## 从 YANG301 版迁移 / Migration

If the old Windows version occupies the intended installation directory, back it up or rename it before cloning this repository. Do not clone into a non-empty directory. Stop its old monitor first to avoid two processes playing sounds:

```powershell
# Run from the OLD installation root. Match only that exact script path.
$oldMonitor = (Resolve-Path .\scripts\codex_sound_session_monitor.ps1).Path
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.Name -eq 'powershell.exe' -and
    $_.CommandLine -and $_.CommandLine.Contains($oldMonitor)
} | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

The new installer replaces the same `CodexSoundNotifications` logon task. If files were updated in place, it also stops the old PowerShell monitor in that same scripts directory. Monitors installed in other directories require the migration step above. The shared default is `celebration.wav`; the Tarkov asset is not included.

## 排错 / Troubleshooting

```powershell
Get-ScheduledTask -TaskName CodexSoundNotifications
Get-Content "$env:USERPROFILE\.codex\codex-sound-notifications.log" -Tail 20
python scripts/manage_sound_notifications.py --preview celebration.wav
```

Use the corresponding `CODEX_HOME` log path if customized. `playback-returned` means the Windows playback call returned; it does not measure actual speaker output. If preview is quiet too, check the selected output device, system volume, per-app volume and audio enhancements.

The monitor ignores historical records present at startup, skips recognized subagent sessions, and buffers incomplete JSONL records until their newline arrives. Changes to Codex's session format may require an update. It polls once per second; large session directories can add overhead. The monitor reads local session files but logs no conversation content and sends no session data over the network.

## 停用 / Disable

From this installation's root, stop its monitor and remove its logon task:

```powershell
$monitor = (Resolve-Path .\scripts\windows_sound_notifications.py).Path
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.Name -in @('python.exe','pythonw.exe') -and
    $_.CommandLine -and $_.CommandLine.Contains($monitor) -and
    $_.CommandLine.Contains('--monitor')
} | ForEach-Object { Stop-Process -Id $_.ProcessId }
Unregister-ScheduledTask -TaskName CodexSoundNotifications -Confirm:$false
```

These commands leave the repository, selected sound and logs intact.
