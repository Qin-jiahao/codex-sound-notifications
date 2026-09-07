#!/usr/bin/env python3
"""Play a local sound when Codex emits a matching notification payload."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_EVENTS = ("agent-turn-complete",)
DEFAULT_LOG_PATH = Path("/tmp/codex-sound-notify.log")
DEFAULT_DEDUPE_PATH = Path("/tmp/codex-sound-notify.last-play")
DEFAULT_DEDUPE_WINDOW_MS = 250
DEFAULT_FORWARD_TIMEOUT_SECONDS = 5.0
MAX_PREVIEW_CHARS = 200
INPUT_MESSAGE_KEYS = ("input-messages", "input_messages")
EVENT_KEYS = (
    "event",
    "event_name",
    "eventName",
    "notification",
    "notification_name",
    "notificationName",
    "type",
)
LEGACY_KEYS = (
    "thread-id",
    "thread_id",
    "turn-id",
    "turn_id",
    "last-assistant-message",
    "last_assistant_message",
)
EVENT_ALIASES = {
    "after-agent": "agent-turn-complete",
    "after_agent": "agent-turn-complete",
    "turn-completed": "agent-turn-complete",
    "turn-complete": "agent-turn-complete",
    "turn/completed": "agent-turn-complete",
}
INTERNAL_PROMPT_PREFIXES = ("you are",)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sound-path", required=True, help="WAV file to play")
    parser.add_argument(
        "--player",
        default="afplay",
        help="Playback command to execute (default: afplay)",
    )
    parser.add_argument(
        "--log-path",
        default=str(DEFAULT_LOG_PATH),
        help=f"Log file path (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--dedupe-path",
        default=str(DEFAULT_DEDUPE_PATH),
        help=f"Recent-play state path (default: {DEFAULT_DEDUPE_PATH})",
    )
    parser.add_argument(
        "--dedupe-window-ms",
        type=int,
        default=DEFAULT_DEDUPE_WINDOW_MS,
        help=f"Suppress duplicate calls within this interval (default: {DEFAULT_DEDUPE_WINDOW_MS})",
    )
    parser.add_argument(
        "--event",
        action="append",
        dest="events",
        default=[],
        help="Notification event to play for; repeat to allow multiple",
    )
    parser.add_argument(
        "--payload-json",
        help="Optional raw JSON payload passed explicitly as an argument",
    )
    parser.add_argument(
        "--forward-command-json",
        help="Optional JSON array containing an existing notify command",
    )
    parser.add_argument(
        "--forward-timeout",
        type=float,
        default=DEFAULT_FORWARD_TIMEOUT_SECONDS,
        help=f"Maximum seconds allowed for a forwarded notifier (default: {DEFAULT_FORWARD_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--log-payload-preview",
        action="store_true",
        help="Include the first 200 payload characters in the debug log",
    )
    parser.add_argument(
        "forward",
        nargs=argparse.REMAINDER,
        help="Optional payload JSON and/or forwarded notify command after '--'",
    )
    return parser.parse_args(argv)


def normalize_event_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return EVENT_ALIASES.get(normalized, normalized)


def iter_payload_candidates(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []

    candidates = [payload]
    for key in ("payload", "data", "params"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    return candidates


def extract_event_name(payload: object) -> str | None:
    for candidate in iter_payload_candidates(payload):
        for key in EVENT_KEYS:
            value = candidate.get(key)
            if isinstance(value, str):
                return normalize_event_name(value)

        method = candidate.get("method")
        if isinstance(method, str):
            return normalize_event_name(method)

    return None


def extract_input_messages(payload: object) -> list[str]:
    for candidate in iter_payload_candidates(payload):
        for key in INPUT_MESSAGE_KEYS:
            messages = candidate.get(key)
            if isinstance(messages, list):
                return [message for message in messages if isinstance(message, str)]
    return []


def is_legacy_after_agent_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(key in payload for key in LEGACY_KEYS)


def suppression_reason_for_payload(payload: object) -> str | None:
    messages = extract_input_messages(payload)
    if not messages:
        return None

    first_message = messages[0].lstrip().lower()
    if any(first_message.startswith(prefix) for prefix in INTERNAL_PROMPT_PREFIXES):
        return "internal-prompt"
    return None


def event_matches_payload(payload: object, allowed_events: set[str]) -> bool:
    event_name = extract_event_name(payload)
    if event_name:
        return event_name in allowed_events
    return is_legacy_after_agent_payload(payload)


def should_play_for_payload(payload: object, allowed_events: set[str]) -> bool:
    if suppression_reason_for_payload(payload) is not None:
        return False
    return event_matches_payload(payload, allowed_events)


def should_play_for_invocation(
    raw_payload: bytes,
    payload: object | None,
    allowed_events: set[str],
) -> bool:
    # Codex Computer Use currently invokes a preserved notify command without
    # forwarding the JSON payload. The invocation itself still occurs at turn
    # completion, so an empty payload is treated as a completion notification.
    if not raw_payload.strip():
        return True
    return should_play_for_payload(payload, allowed_events)


def decode_payload(raw: bytes) -> object | None:
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_forward_and_payload(
    payload_json: str | None,
    forward: list[str],
    stdin: object,
) -> tuple[bytes, object | None, list[str]]:
    if payload_json is not None:
        raw = payload_json.encode("utf-8")
        return raw, decode_payload(raw), normalize_forward_command(forward)

    if forward and forward[0] != "--":
        candidate = forward[0]
        raw = candidate.encode("utf-8")
        payload = decode_payload(raw)
        if payload is not None:
            return raw, payload, normalize_forward_command(forward[1:])

    normalized_forward = normalize_forward_command(forward)
    if normalized_forward:
        # Codex appends its JSON payload after every configured notify token.
        # When an existing notifier is preserved after `--`, the payload is
        # therefore the final token rather than the first positional token.
        candidate = normalized_forward[-1]
        raw = candidate.encode("utf-8")
        payload = decode_payload(raw)
        if payload is not None:
            return raw, payload, normalized_forward[:-1]

    raw = stdin.buffer.read()
    return raw, decode_payload(raw), normalized_forward


def normalize_forward_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def parse_forward_command_json(raw: str | None) -> list[str]:
    if raw is None:
        return []
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("forward command must be a JSON array of strings")
    return value


def play_sound(player: str, sound_path: Path) -> int:
    try:
        result = subprocess.run(
            [player, str(sound_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode
    except OSError:
        return 127


def run_forward_command(
    command: list[str],
    raw_payload: bytes,
    timeout_seconds: float = DEFAULT_FORWARD_TIMEOUT_SECONDS,
) -> int:
    command = normalize_forward_command(command)
    if not command:
        return 0
    forwarded_command = list(command)
    if raw_payload:
        forwarded_command.append(raw_payload.decode("utf-8", errors="replace"))
    try:
        result = subprocess.run(
            forwarded_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=max(timeout_seconds, 0.1),
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 127


def effective_event_name(payload: object) -> str | None:
    event_name = extract_event_name(payload)
    if event_name:
        return event_name
    if is_legacy_after_agent_payload(payload):
        return "agent-turn-complete"
    return None


def payload_state(raw_payload: bytes, payload: object | None) -> str:
    if not raw_payload.strip():
        return "empty"
    if payload is None:
        return "invalid-json"
    return "json"


def payload_preview(raw_payload: bytes) -> str:
    if not raw_payload:
        return ""
    text = raw_payload.decode("utf-8", errors="replace")
    return text[:MAX_PREVIEW_CHARS]


def write_log(log_path: Path, entry: dict[str, object]) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except OSError:
        # Logging is best-effort; notification flow should not fail because of it.
        return


def claim_play_slot(
    state_path: Path,
    window_ms: int,
    now: float | None = None,
) -> bool:
    """Return True once per short notification burst across processes."""
    # The system Python 3.9 shipped with some macOS installations exposes a
    # process-relative monotonic clock. This state is shared across processes,
    # so use wall-clock time to keep values comparable between invocations.
    current = time.time() if now is None else now
    window_seconds = max(window_ms, 0) / 1000
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw_previous = handle.read().strip()
            try:
                previous = float(raw_previous)
            except ValueError:
                previous = float("-inf")
            if current - previous < window_seconds:
                return False
            handle.seek(0)
            handle.truncate()
            handle.write(f"{current:.9f}\n")
            handle.flush()
            return True
    except OSError:
        # A dedupe-state failure must not suppress the requested notification.
        return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sound_path = Path(args.sound_path).expanduser()
    log_path = Path(args.log_path).expanduser()
    dedupe_path = Path(args.dedupe_path).expanduser()
    allowed_events = {
        normalize_event_name(event) for event in (args.events or list(DEFAULT_EVENTS))
    }
    allowed_events.discard(None)
    raw_payload, payload, forward_command = extract_forward_and_payload(
        payload_json=args.payload_json,
        forward=args.forward,
        stdin=sys.stdin,
    )
    configured_forward = parse_forward_command_json(args.forward_command_json)
    if configured_forward:
        forward_command = configured_forward
    empty_payload = not raw_payload.strip()
    event_name = effective_event_name(payload)
    if event_name is None and empty_payload:
        event_name = "agent-turn-complete"
    suppressed_reason = suppression_reason_for_payload(payload)
    matched = should_play_for_invocation(raw_payload, payload, allowed_events)
    deduplicated = False

    if not sound_path.exists():
        write_log(
            log_path,
            {
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": "missing-sound",
                "sound_path": str(sound_path),
                "event": event_name,
                "matched": matched,
                "deduplicated": deduplicated,
                "suppressed_reason": suppressed_reason,
                "payload_state": payload_state(raw_payload, payload),
                "payload_preview": payload_preview(raw_payload)
                if args.log_payload_preview
                else None,
            },
        )
        print(f"sound file not found: {sound_path}", file=sys.stderr)
        return 1

    play_exit_code = 0
    forward_exit_code = 0

    if matched:
        if claim_play_slot(dedupe_path, args.dedupe_window_ms):
            play_exit_code = play_sound(args.player, sound_path)
        else:
            deduplicated = True
    forward_exit_code = run_forward_command(
        forward_command,
        raw_payload,
        timeout_seconds=args.forward_timeout,
    )
    exit_code = play_exit_code or forward_exit_code

    write_log(
        log_path,
        {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "ok" if exit_code == 0 else "error",
            "event": event_name,
            "matched": matched,
            "deduplicated": deduplicated,
            "suppressed_reason": suppressed_reason,
            "allowed_events": sorted(allowed_events),
            "sound_path": str(sound_path),
            "player": args.player,
            "play_exit_code": play_exit_code,
            "forward_exit_code": forward_exit_code,
            "payload_state": payload_state(raw_payload, payload),
            "payload_preview": payload_preview(raw_payload)
            if args.log_payload_preview
            else None,
        },
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
