#!/usr/bin/env python3
"""Interactively list, preview, apply, and update bundled Codex sounds."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Sequence, TextIO
import zipfile

import setup_sound_notifications as setup_mod

DEFAULT_PLAYER = "afplay"
DEFAULT_REPO = "Qin-jiahao/codex-sound-notifications"
DEFAULT_REF = "main"
DEFAULT_TIMEOUT_SECONDS = 20.0
UPDATE_STATE_FILENAME = ".codex-sound-notifications-upstream.json"
HTTP_USER_AGENT = "codex-sound-notifications"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List bundled sounds and exit")
    parser.add_argument("--preview", metavar="SOUND", help="Preview one bundled sound and exit")
    parser.add_argument("--apply", metavar="SOUND", help="Apply one bundled sound and exit")
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check whether the skill has upstream updates and exit",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update the skill from its upstream repository",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation when used with --apply or --update",
    )
    parser.add_argument(
        "--player",
        default=DEFAULT_PLAYER,
        help=f"Audio player used for preview (default: {DEFAULT_PLAYER})",
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
        default=setup_mod.DEFAULT_EVENT,
        help=f"Notification event to enable (default: {setup_mod.DEFAULT_EVENT})",
    )
    parser.add_argument(
        "--repo",
        help=(
            "GitHub repo in owner/repo format for non-git installs "
            f"(default: {DEFAULT_REPO})"
        ),
    )
    parser.add_argument(
        "--ref",
        help=(
            "Git branch or ref to track for updates "
            f"(default: current branch for git installs, {DEFAULT_REF} otherwise)"
        ),
    )
    return parser.parse_args(argv)


def resolve_selection(choice: str, sounds: Sequence[str]) -> str:
    normalized = choice.strip()
    if not normalized:
        raise ValueError("empty selection")
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(sounds):
            return sounds[index - 1]
        raise ValueError(f"selection {index} is out of range")
    target = normalized.lower()
    for sound in sounds:
        if sound.lower() == target:
            return sound
    raise ValueError(f"unknown sound: {choice}")


def format_sound_list(sounds: Sequence[str], current_sound: str | None) -> str:
    lines = []
    for index, sound in enumerate(sounds, start=1):
        marker = " (current)" if current_sound == sound else ""
        lines.append(f"{index:>2}. {sound}{marker}")
    return "\n".join(lines)


def preview_sound(sound_name: str, player: str, sounds_dir: Path) -> int:
    sound_path = sounds_dir / sound_name
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


def short_commit(commit: str | None) -> str | None:
    if not commit:
        return None
    return commit[:7]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def update_state_path(root: Path) -> Path:
    return root / UPDATE_STATE_FILENAME


def parse_github_repo_slug(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if "://" not in raw and raw.count("/") == 1 and ":" not in raw:
        owner, repo = raw.split("/", 1)
        repo = repo.removesuffix(".git")
        if owner and repo:
            return f"{owner}/{repo}"
        return None
    if raw.startswith("git@github.com:"):
        path = raw.removeprefix("git@github.com:")
    else:
        parsed = urllib.parse.urlparse(raw)
        if parsed.netloc.lower() != "github.com":
            return None
        path = parsed.path.lstrip("/")
    parts = [part for part in path.removesuffix(".git").split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def read_update_state(root: Path) -> dict[str, str] | None:
    state_path = update_state_path(root)
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    repo = payload.get("repo")
    ref = payload.get("ref")
    commit = payload.get("commit")
    if not all(isinstance(value, str) and value for value in (repo, ref, commit)):
        return None
    return {"repo": repo, "ref": ref, "commit": commit}


def write_update_state(root: Path, *, repo: str, ref: str, commit: str) -> Path:
    state_path = update_state_path(root)
    state_path.write_text(
        json.dumps({"repo": repo, "ref": ref, "commit": commit}, indent=2) + "\n",
        encoding="utf-8",
    )
    return state_path


def run_git(args: Sequence[str], *, root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def is_git_checkout(root: Path) -> bool:
    try:
        return run_git(["rev-parse", "--is-inside-work-tree"], root=root) == "true"
    except RuntimeError:
        return False


def git_current_commit(root: Path) -> str | None:
    try:
        return run_git(["rev-parse", "HEAD"], root=root)
    except RuntimeError:
        return None


def git_current_branch(root: Path) -> str | None:
    try:
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root=root)
    except RuntimeError:
        return None
    if not branch or branch == "HEAD":
        return None
    return branch


def git_remote_url(root: Path) -> str | None:
    try:
        return run_git(["remote", "get-url", "origin"], root=root)
    except RuntimeError:
        return None


def git_has_local_changes(root: Path) -> bool:
    return bool(run_git(["status", "--porcelain"], root=root))


def git_fetch_remote_revision(root: Path, ref: str) -> dict[str, str]:
    run_git(["fetch", "origin", ref], root=root)
    commit = run_git(["rev-parse", "FETCH_HEAD"], root=root)
    message = run_git(["log", "-1", "--pretty=%s", "FETCH_HEAD"], root=root)
    return {"commit": commit, "message": message}


def json_request(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": HTTP_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected JSON payload from upstream")
    return payload


def bytes_request(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def fetch_remote_revision(repo: str, ref: str) -> dict[str, str]:
    encoded_ref = urllib.parse.quote(ref, safe="")
    payload = json_request(
        f"https://api.github.com/repos/{repo}/commits/{encoded_ref}"
    )
    commit = payload.get("sha")
    commit_info = payload.get("commit")
    message = ""
    if isinstance(commit_info, dict):
        raw_message = commit_info.get("message")
        if isinstance(raw_message, str):
            message = raw_message.splitlines()[0]
    html_url = payload.get("html_url")
    if not isinstance(commit, str) or not commit:
        raise RuntimeError("upstream response did not include a commit sha")
    if not isinstance(html_url, str) or not html_url:
        html_url = f"https://github.com/{repo}/commit/{commit}"
    return {
        "repo": repo,
        "ref": ref,
        "commit": commit,
        "message": message,
        "url": html_url,
    }


def download_repo_archive(repo: str, ref: str) -> bytes:
    owner, name = repo.split("/", 1)
    encoded_ref = urllib.parse.quote(ref, safe="")
    return bytes_request(f"https://codeload.github.com/{owner}/{name}/zip/{encoded_ref}")


def safe_extract_zip(zip_file: zipfile.ZipFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for info in zip_file.infolist():
        target = (destination / info.filename).resolve()
        if target == destination_root or destination_root in target.parents:
            continue
        raise RuntimeError("archive contains files outside the destination")
    zip_file.extractall(destination)


def extract_repo_archive(payload: bytes, destination: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        safe_extract_zip(archive, destination)
        top_levels = {Path(name).parts[0] for name in archive.namelist() if name}
    if len(top_levels) != 1:
        raise RuntimeError("unexpected archive layout")
    extracted_root = destination / next(iter(top_levels))
    if not (extracted_root / "SKILL.md").exists():
        raise RuntimeError("downloaded archive does not look like a skill")
    return extracted_root


def merge_repo_tree(source_root: Path, destination_root: Path) -> int:
    copied_files = 0
    for source_path in sorted(source_root.rglob("*")):
        relative_path = source_path.relative_to(source_root)
        if relative_path.parts and relative_path.parts[0] in {".git", "__pycache__"}:
            continue
        if relative_path.name == UPDATE_STATE_FILENAME:
            continue
        destination_path = destination_root / relative_path
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied_files += 1
    return copied_files


def resolve_non_git_upstream(root: Path, repo: str | None, ref: str | None) -> tuple[str, str]:
    state = read_update_state(root)
    resolved_repo = repo or (state["repo"] if state else None) or DEFAULT_REPO
    resolved_ref = ref or (state["ref"] if state else None) or DEFAULT_REF
    return resolved_repo, resolved_ref


def local_revision_from_state(root: Path, repo: str, ref: str) -> tuple[str | None, str]:
    state = read_update_state(root)
    if not state:
        return None, "unknown"
    if state["repo"] != repo or state["ref"] != ref:
        return None, "unknown"
    return state["commit"], "metadata"


def check_for_updates(
    *,
    root: Path,
    repo: str | None = None,
    ref: str | None = None,
) -> dict[str, object]:
    if is_git_checkout(root):
        resolved_ref = ref or git_current_branch(root) or DEFAULT_REF
        local_commit = git_current_commit(root)
        remote_url = git_remote_url(root)
        remote = git_fetch_remote_revision(root, resolved_ref)
        resolved_repo = repo or parse_github_repo_slug(remote_url) or DEFAULT_REPO
        update_available = local_commit != remote["commit"]
        return {
            "status": "update-available" if update_available else "up-to-date",
            "update_available": update_available,
            "repo": resolved_repo,
            "ref": resolved_ref,
            "local_commit": local_commit,
            "local_commit_short": short_commit(local_commit),
            "local_version_source": "git",
            "remote_commit": remote["commit"],
            "remote_commit_short": short_commit(remote["commit"]),
            "remote_message": remote["message"],
            "remote_url": remote_url or f"https://github.com/{resolved_repo}.git",
        }

    resolved_repo, resolved_ref = resolve_non_git_upstream(root, repo, ref)
    remote = fetch_remote_revision(resolved_repo, resolved_ref)
    local_commit, local_source = local_revision_from_state(root, resolved_repo, resolved_ref)
    if not local_commit:
        status = "local-version-unknown"
        update_available: bool | None = None
    else:
        update_available = local_commit != remote["commit"]
        status = "update-available" if update_available else "up-to-date"
    return {
        "status": status,
        "update_available": update_available,
        "repo": resolved_repo,
        "ref": resolved_ref,
        "local_commit": local_commit,
        "local_commit_short": short_commit(local_commit),
        "local_version_source": local_source,
        "remote_commit": remote["commit"],
        "remote_commit_short": short_commit(remote["commit"]),
        "remote_message": remote["message"],
        "remote_url": remote["url"],
    }


def update_git_install(root: Path, ref: str) -> dict[str, object]:
    local_commit = git_current_commit(root)
    if git_has_local_changes(root):
        raise RuntimeError(
            "git checkout has local changes; commit or stash them before updating"
        )
    remote_url = git_remote_url(root)
    remote = git_fetch_remote_revision(root, ref)
    if local_commit == remote["commit"]:
        return {
            "updated": False,
            "strategy": "git",
            "repo": parse_github_repo_slug(remote_url) or DEFAULT_REPO,
            "ref": ref,
            "local_commit_before": local_commit,
            "local_commit_after": local_commit,
            "remote_commit": remote["commit"],
            "remote_commit_short": short_commit(remote["commit"]),
            "remote_message": remote["message"],
        }
    run_git(["pull", "--ff-only", "origin", ref], root=root)
    updated_commit = git_current_commit(root)
    return {
        "updated": updated_commit != local_commit,
        "strategy": "git",
        "repo": parse_github_repo_slug(remote_url) or DEFAULT_REPO,
        "ref": ref,
        "local_commit_before": local_commit,
        "local_commit_after": updated_commit,
        "remote_commit": remote["commit"],
        "remote_commit_short": short_commit(remote["commit"]),
        "remote_message": remote["message"],
    }


def update_non_git_install(root: Path, repo: str | None, ref: str | None) -> dict[str, object]:
    status = check_for_updates(root=root, repo=repo, ref=ref)
    resolved_repo = str(status["repo"])
    resolved_ref = str(status["ref"])
    remote_commit = str(status["remote_commit"])
    if status["update_available"] is False:
        return {
            "updated": False,
            "strategy": "archive",
            **status,
        }
    payload = download_repo_archive(resolved_repo, resolved_ref)
    with tempfile.TemporaryDirectory(prefix="codex-sound-notifications-update-") as tmpdir:
        extracted_root = extract_repo_archive(payload, Path(tmpdir))
        copied_files = merge_repo_tree(extracted_root, root)
    state_path = write_update_state(
        root,
        repo=resolved_repo,
        ref=resolved_ref,
        commit=remote_commit,
    )
    return {
        "updated": True,
        "strategy": "archive",
        **status,
        "local_commit_after": remote_commit,
        "local_commit_after_short": short_commit(remote_commit),
        "files_copied": copied_files,
        "state_path": str(state_path),
    }


def update_skill(
    *,
    root: Path,
    repo: str | None = None,
    ref: str | None = None,
) -> dict[str, object]:
    if is_git_checkout(root):
        resolved_ref = ref or git_current_branch(root) or DEFAULT_REF
        return update_git_install(root, resolved_ref)
    return update_non_git_install(root, repo, ref)


def apply_sound(
    sound_name: str,
    config_path: Path,
    sound_dir: Path,
    event_name: str,
) -> dict[str, str]:
    return setup_mod.install(
        sound_file=sound_name,
        sound_dir=sound_dir,
        config_path=config_path,
        event_name=event_name,
    )


def interactive_manage(
    *,
    sounds: Sequence[str],
    current_sound: str | None,
    player: str,
    sounds_dir: Path,
    config_path: Path,
    sound_dir: Path,
    event_name: str,
    stdin: TextIO,
    stdout: TextIO,
    preview_fn: Callable[[str, str, Path], int] = preview_sound,
    apply_fn: Callable[[str, Path, Path, str], dict[str, str]] = apply_sound,
) -> int:
    if not sounds:
        print("No bundled sounds found.", file=stdout)
        return 1

    while True:
        print("Bundled sounds:", file=stdout)
        print(format_sound_list(sounds, current_sound), file=stdout)
        print("Select a sound by number or filename, or q to quit:", file=stdout)
        choice = stdin.readline()
        if not choice:
            return 1
        choice = choice.strip()
        if choice.lower() in {"q", "quit", "exit"}:
            return 0

        try:
            selected = resolve_selection(choice, sounds)
        except ValueError as exc:
            print(str(exc), file=stdout)
            continue

        preview_exit = preview_fn(selected, player, sounds_dir)
        if preview_exit == 0:
            print(f"Previewed {selected}.", file=stdout)
        else:
            print(f"Preview failed for {selected} (exit {preview_exit}).", file=stdout)

        while True:
            print("Apply this sound? [y]es / [n]o / [p]review / [q]uit", file=stdout)
            action = stdin.readline()
            if not action:
                return 1
            action = action.strip().lower()
            if action in {"q", "quit", "exit"}:
                return 0
            if action in {"n", "no"}:
                break
            if action in {"p", "preview"}:
                preview_exit = preview_fn(selected, player, sounds_dir)
                if preview_exit == 0:
                    print(f"Previewed {selected}.", file=stdout)
                else:
                    print(f"Preview failed for {selected} (exit {preview_exit}).", file=stdout)
                continue
            if action in {"y", "yes"}:
                result = apply_fn(selected, config_path, sound_dir, event_name)
                print(json.dumps(result, indent=2), file=stdout)
                return 0
            print("Please enter y, n, p, or q.", file=stdout)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = skill_root()
    sounds_dir = setup_mod.BUNDLED_SOUNDS_DIR
    sounds = setup_mod.list_bundled_sounds(sounds_dir)
    config_path = setup_mod.expand_path(args.config_path)
    sound_dir = setup_mod.expand_path(args.sound_dir)
    current_sound = setup_mod.read_current_sound_from_config(config_path)

    if args.list:
        if not sounds:
            print("No bundled sounds found.")
            return 1
        print(format_sound_list(sounds, current_sound))
        return 0

    if args.preview:
        try:
            sound_name = resolve_selection(args.preview, sounds)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return preview_sound(sound_name, args.player, sounds_dir)

    if args.apply:
        try:
            sound_name = resolve_selection(args.apply, sounds)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not args.yes:
            print(f"Apply {sound_name}? [y/N]")
            answer = sys.stdin.readline().strip().lower()
            if answer not in {"y", "yes"}:
                print("Cancelled.")
                return 0
        result = apply_sound(sound_name, config_path, sound_dir, args.event)
        print(json.dumps(result, indent=2))
        return 0

    if args.check_update:
        result = check_for_updates(root=root, repo=args.repo, ref=args.ref)
        print(json.dumps(result, indent=2))
        return 0

    if args.update:
        if not args.yes:
            print("Update this skill from its upstream repository? [y/N]")
            answer = sys.stdin.readline().strip().lower()
            if answer not in {"y", "yes"}:
                print("Cancelled.")
                return 0
        result = update_skill(root=root, repo=args.repo, ref=args.ref)
        print(json.dumps(result, indent=2))
        return 0

    return interactive_manage(
        sounds=sounds,
        current_sound=current_sound,
        player=args.player,
        sounds_dir=sounds_dir,
        config_path=config_path,
        sound_dir=sound_dir,
        event_name=args.event,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
