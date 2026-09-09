#!/usr/bin/env python3
"""Windows backend: incremental session monitoring and per-user logon startup.

Session-monitor approach inspired by YANG301/codex-sound-notifications.
This implementation uses Python/winsound, independently of the macOS notify hook.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
STATE = HOME / "windows-sound-notifications.json"
LOG = HOME / "codex-sound-notifications.log"
TASK = "CodexSoundNotifications"


def read_settings() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + message + "\n")


def primary(meta: dict) -> bool:
    if not isinstance(meta, dict) or not isinstance(meta.get("payload"), dict):
        return False
    payload = meta.get("payload", {})
    source = payload.get("source")
    return (meta.get("type") == "session_meta"
            and payload.get("thread_source") != "subagent"
            and not (isinstance(source, dict) and "subagent" in source))


def final_answer(item: dict) -> bool:
    p = item.get("payload", {})
    return (item.get("type") == "response_item" and p.get("type") == "message"
            and p.get("role") == "assistant" and p.get("phase") == "final_answer")


class Tail:
    """Keep incomplete JSONL bytes until the next scan; skip existing history."""
    def __init__(self, root: Path):
        self.offsets = {p: p.stat().st_size for p in root.rglob("*.jsonl")}
        self.pending = {}

    def scan(self, path: Path) -> int:
        with path.open("rb") as stream:
            try:
                meta = json.loads(stream.readline())
            except ValueError:
                return 0
            if not primary(meta):
                return 0
            size = path.stat().st_size
            offset = self.offsets.get(path, 0)
            if size < offset:
                offset = 0
                self.pending.pop(path, None)
            stream.seek(offset)
            data = self.pending.get(path, b"") + stream.read()
            self.offsets[path] = stream.tell()
        lines = data.split(b"\n")
        self.pending[path] = lines.pop()
        count = 0
        for line in lines:
            try:
                count += bool(final_answer(json.loads(line)))
            except (ValueError, AttributeError, TypeError):
                continue
        return count


def monitor() -> None:
    import msvcrt
    HOME.mkdir(parents=True, exist_ok=True)
    # The lock is released by Windows even if the process terminates unexpectedly.
    with (HOME / "codex-sound-notifications.lock").open("a+b") as lock:
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        run_monitor()


def run_monitor() -> None:
    import winsound
    settings = read_settings()
    root = Path(settings["sessions_root"])
    tail = Tail(root)
    log("monitor-start backend=windows-python")
    while True:
        try:
            for path in root.rglob("*.jsonl"):
                try:
                    count = tail.scan(path)
                    for _ in range(count):
                        sound = read_settings()["sound_path"]
                        winsound.PlaySound(sound, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                        log("playback-returned")
                except (OSError, ValueError, KeyError, RuntimeError):
                    log("playback-or-session-error")
        except OSError:
            log("scan-error")
        time.sleep(1)


def quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def powershell(code: str) -> None:
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; " + code], check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def install(sound: Path, sessions_root: Path | None = None,
            start: bool = True, register_task: bool | None = None) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Windows backend requires Windows")
    sound = sound.resolve()
    with wave.open(str(sound), "rb") as audio:
        if audio.getnframes() == 0:
            raise ValueError("WAV file is empty")
    previous = read_settings()
    sessions = (sessions_root or Path(previous.get("sessions_root", str(HOME / "sessions")))).resolve()
    sessions.mkdir(parents=True, exist_ok=True)
    if register_task is None:
        register_task = previous.get("register_task", True)
    settings = {"sound_path": str(sound), "sessions_root": str(sessions),
                "register_task": register_task}
    HOME.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    temp.replace(STATE)
    script = Path(__file__).resolve()
    # Stop only Python monitors and the old PowerShell monitor in this installation.
    legacy = script.with_name("codex_sound_session_monitor.ps1")
    powershell(
        "$targets=@(" + quote_ps(str(script)) + "," + quote_ps(str(legacy)) + "); "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.ProcessId -ne $PID -and $_.ProcessId -ne " + str(os.getpid()) + " -and "
        "$_.Name -in @('python.exe','pythonw.exe','powershell.exe') -and "
        "$_.CommandLine -and (($_.CommandLine.Contains($targets[0]) -and "
        "$_.CommandLine.Contains('--monitor')) -or $_.CommandLine.Contains($targets[1])) "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }")
    # Scheduled tasks use an absolute interpreter path, never a PATH-dependent python alias.
    command = subprocess.list2cmdline([sys.executable, str(script), "--monitor"])
    launcher = HOME / "codex-sound-notifications-launcher.vbs"
    launcher.write_text('CreateObject("WScript.Shell").Run "' + command.replace('"', '""')
                        + '", 0, False\r\n', encoding="utf-16")
    if register_task:
        powershell(
            "$a=New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "
            + quote_ps('//B //Nologo "' + str(launcher) + '"') + "; "
            "$u=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            "$t=New-ScheduledTaskTrigger -AtLogOn -User $u; "
            "$p=New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited; "
            "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
            "-DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero); "
            "Register-ScheduledTask -TaskName '" + TASK + "' -Action $a -Trigger $t "
            "-Principal $p -Settings $s -Force | Out-Null")
    else:
        powershell("Get-ScheduledTask -TaskName '" + TASK + "' -ErrorAction SilentlyContinue "
                   "| Unregister-ScheduledTask -Confirm:$false")
    if start:
        subprocess.Popen([sys.executable, str(script), "--monitor"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    return {**settings, "started": start, "backend": "windows",
            "selected_sound": sound.name}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sound-file", default="celebration.wav")
    parser.add_argument("--sound-path", type=Path)
    parser.add_argument("--sessions-root", type=Path)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--no-task", action="store_true")
    args = parser.parse_args(argv)
    if args.monitor:
        monitor()
    else:
        sound = args.sound_path or ROOT / "assets" / "sounds" / Path(args.sound_file).name
        print(json.dumps(install(sound, args.sessions_root, not args.no_start,
                                 not args.no_task), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
