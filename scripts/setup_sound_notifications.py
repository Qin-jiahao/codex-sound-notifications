#!/usr/bin/env python3
"""Install Codex sound notifications from bundled assets or a local sound zip."""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Sequence

DEFAULT_SOUND_FILE = "celebration.wav"
DEFAULT_EVENT = "agent-turn-complete"
BUNDLED_SOUNDS_DIR = Path(__file__).resolve().parents[1] / "assets" / "sounds"
LEGACY_RUNTIME_SOUND_FILE = "current.wav"
LEGACY_RUNTIME_SOUND_META_FILE = "current-sound.txt"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zip-path",
        help="Optional local zip archive with WAV files; bundled assets are used by default",
    )
    parser.add_argument(
        "--sound-file",
        default=DEFAULT_SOUND_FILE,
        help=f"Name of the WAV inside the zip (default: {DEFAULT_SOUND_FILE})",
    )
    parser.add_argument(
        "--config-path",
        default="~/.codex/config.toml",
        help="Codex config.toml path",
    )
    parser.add_argument(
        "--sound-dir",
        default="~/.codex/sounds",
        help="Deprecated and ignored; sounds now play directly from bundled assets",
    )
    parser.add_argument(
        "--event",
        default=DEFAULT_EVENT,
        help=f"Notification event to enable (default: {DEFAULT_EVENT})",
    )
    parser.add_argument(
        "--preserve-existing-notify",
        action="store_true",
        help="Forward the payload to the existing notify command after playback",
    )
    return parser.parse_args(argv)


def expand_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def clean_zip_members(names: Sequence[str]) -> list[str]:
    cleaned = []
    for name in names:
        if name.endswith("/"):
            continue
        if name.startswith("__MACOSX/"):
            continue
        basename = Path(name).name
        if basename.startswith("."):
            continue
        cleaned.append(name)
    return cleaned


def list_bundled_sounds(bundled_sounds_dir: Path | None = None) -> list[str]:
    sounds_dir = bundled_sounds_dir or BUNDLED_SOUNDS_DIR
    if not sounds_dir.exists():
        return []
    return sorted(
        path.name
        for path in sounds_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".wav"
    )


def find_sound_member(names: Sequence[str], sound_file: str) -> str:
    target = Path(sound_file).name.lower()
    matches = [name for name in clean_zip_members(names) if Path(name).name.lower() == target]
    if not matches:
        raise FileNotFoundError(f"{sound_file} not found in archive")
    return sorted(matches)[0]


def extract_sound_file(zip_path: Path, sound_file: str, sound_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        member = find_sound_member(archive.namelist(), sound_file)
        sound_dir.mkdir(parents=True, exist_ok=True)
        destination = sound_dir / Path(sound_file).name
        with archive.open(member) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)
    return destination


def resolve_bundled_sound_file(sound_file: str, bundled_sounds_dir: Path) -> Path:
    source = bundled_sounds_dir / Path(sound_file).name
    if not source.exists():
        raise FileNotFoundError(
            f"{sound_file} not found in bundled sounds: {bundled_sounds_dir}"
        )
    return source.resolve()


def install_sound_file(
    sound_file: str,
    sound_dir: Path,
    zip_path: Path | None = None,
    bundled_sounds_dir: Path | None = None,
) -> Path:
    del sound_dir
    bundled_dir = bundled_sounds_dir or BUNDLED_SOUNDS_DIR
    bundled_dir.mkdir(parents=True, exist_ok=True)

    if zip_path is not None:
        if not zip_path.exists():
            raise FileNotFoundError(f"zip archive not found: {zip_path}")
        return extract_sound_file(zip_path, sound_file, bundled_dir).resolve()

    return resolve_bundled_sound_file(sound_file, bundled_dir)


def quote_toml_string(value: str) -> str:
    return json.dumps(value)


def render_toml_array(values: Sequence[str]) -> str:
    return "[" + ", ".join(quote_toml_string(value) for value in values) + "]"


def split_lines(text: str) -> list[str]:
    if not text:
        return []
    return text.splitlines()


def join_lines(lines: Sequence[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def find_top_level_end(lines: Sequence[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return index
    return len(lines)


def find_key_index(lines: Sequence[str], start: int, end: int, key: str) -> int | None:
    prefix = f"{key} ="
    for index in range(start, end):
        if lines[index].lstrip().startswith(prefix):
            return index
    return None


def parse_assignment_value(key: str, line: str) -> object:
    del key
    _, raw_value = line.split("=", 1)
    return ast.literal_eval(raw_value.strip())


def iter_nested_commands(command: Sequence[str]) -> list[list[str]]:
    commands = [list(command)]
    for token in command:
        try:
            nested = json.loads(token)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(nested, list) and all(isinstance(item, str) for item in nested):
            commands.extend(iter_nested_commands(nested))
    return commands


def read_current_sound_from_config(config_path: Path) -> str | None:
    if sys.platform == "win32":
        from windows_sound_notifications import read_settings
        sound = read_settings().get("sound_path")
        return Path(sound).name if sound else None
    if not config_path.exists():
        return None
    notify = load_existing_notify(split_lines(config_path.read_text()))
    if not notify:
        return None
    for nested in iter_nested_commands(notify):
        for index, token in enumerate(nested):
            if token == "--sound-path" and index + 1 < len(nested):
                sound_path = Path(str(nested[index + 1]))
                if sound_path.name == LEGACY_RUNTIME_SOUND_FILE:
                    metadata_path = sound_path.with_name(LEGACY_RUNTIME_SOUND_META_FILE)
                    if metadata_path.exists():
                        value = metadata_path.read_text(encoding="utf-8").strip()
                        if value:
                            return value
                return sound_path.name
    return None


def command_uses_notifier(command: Sequence[str], notifier_path: Path) -> bool:
    wanted = str(notifier_path)
    wanted_name = notifier_path.name
    for nested in iter_nested_commands(command):
        for token in nested:
            if token == wanted:
                return True
            candidate = Path(token)
            if candidate.suffix == ".py" and candidate.name == wanted_name:
                return True
    return False


def build_notify_command(
    notifier_path: Path,
    sound_path: Path,
    event_name: str,
    existing_notify: Sequence[str] | None = None,
) -> list[str]:
    command = [
        "python3",
        str(notifier_path),
        "--sound-path",
        str(sound_path),
        "--event",
        event_name,
    ]
    if existing_notify:
        command.extend(
            [
                "--forward-command-json",
                json.dumps(list(existing_notify), separators=(",", ":")),
            ]
        )
    return command


def upsert_top_level_notify(lines: list[str], notify_command: Sequence[str]) -> None:
    rendered = f"notify = {render_toml_array(notify_command)}"
    end = find_top_level_end(lines)
    index = find_key_index(lines, 0, end, "notify")
    if index is not None:
        lines[index] = rendered
        return
    insert_at = end
    if insert_at > 0 and lines[insert_at - 1].strip():
        lines.insert(insert_at, "")
        insert_at += 1
    lines.insert(insert_at, rendered)


def load_existing_notify(lines: Sequence[str]) -> list[str] | None:
    end = find_top_level_end(lines)
    index = find_key_index(lines, 0, end, "notify")
    if index is None:
        return None
    value = parse_assignment_value("notify", lines[index])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("existing notify must be an array of strings")
    return value


def update_config_text(
    original_text: str,
    notifier_path: Path,
    sound_path: Path,
    event_name: str,
    preserve_existing_notify: bool = False,
) -> str:
    lines = split_lines(original_text)
    existing_notify = load_existing_notify(lines) if preserve_existing_notify else None
    if existing_notify and command_uses_notifier(existing_notify, notifier_path):
        existing_notify = None

    notify_command = build_notify_command(
        notifier_path=notifier_path,
        sound_path=sound_path,
        event_name=event_name,
        existing_notify=existing_notify,
    )
    upsert_top_level_notify(lines, notify_command)
    return join_lines(lines)


def install(
    sound_file: str,
    sound_dir: Path,
    config_path: Path,
    event_name: str,
    zip_path: Path | None = None,
    bundled_sounds_dir: Path | None = None,
    preserve_existing_notify: bool = False,
) -> dict[str, str]:
    if sys.platform == "win32":
        from windows_sound_notifications import install as install_windows
        sound = install_sound_file(sound_file, sound_dir, zip_path, bundled_sounds_dir)
        return install_windows(sound)
    if sys.platform != "darwin":
        raise RuntimeError("this installer supports macOS and Windows only")

    notifier_path = Path(__file__).with_name("codex_sound_notify.py").resolve()
    if not notifier_path.exists():
        raise FileNotFoundError(f"notifier script not found: {notifier_path}")

    sound_path = install_sound_file(
        sound_file=sound_file,
        sound_dir=sound_dir,
        zip_path=zip_path,
        bundled_sounds_dir=bundled_sounds_dir,
    )
    original_text = config_path.read_text() if config_path.exists() else ""
    updated_text = update_config_text(
        original_text=original_text,
        notifier_path=notifier_path,
        sound_path=sound_path,
        event_name=event_name,
        preserve_existing_notify=preserve_existing_notify,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated_text)

    return {
        "config_path": str(config_path),
        "sound_path": str(sound_path),
        "selected_sound": Path(sound_file).name,
        "notifier_path": str(notifier_path),
        "event": event_name,
        "notify_mode": "preserve" if preserve_existing_notify else "direct",
    }


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        from windows_sound_notifications import main as windows_main
        return windows_main(argv)
    args = parse_args(argv)
    result = install(
        sound_file=args.sound_file,
        sound_dir=expand_path(args.sound_dir),
        config_path=expand_path(args.config_path),
        event_name=args.event,
        zip_path=expand_path(args.zip_path) if args.zip_path else None,
        preserve_existing_notify=args.preserve_existing_notify,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
