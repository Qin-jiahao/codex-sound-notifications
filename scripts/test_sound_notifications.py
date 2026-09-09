#!/usr/bin/env python3
"""Tests for Codex sound notification helper scripts."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

if sys.platform != "darwin":
    raise unittest.SkipTest("macOS backend tests require macOS (fcntl and afplay)")

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import codex_sound_notify as notify_mod  # noqa: E402
import manage_sound_notifications as manage_mod  # noqa: E402
import setup_sound_notifications as setup_mod  # noqa: E402


class SetupSoundNotificationsTests(unittest.TestCase):
    def test_parse_args_defaults_to_celebration_sound(self) -> None:
        args = setup_mod.parse_args([])
        self.assertEqual(args.sound_file, "celebration.wav")

    def test_find_sound_member_ignores_macos_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "sounds.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("__MACOSX/SND03_industrial/._notification.wav", b"junk")
                archive.writestr("SND03_industrial/.DS_Store", b"junk")
                archive.writestr("SND03_industrial/notification.wav", b"ok")

            with zipfile.ZipFile(zip_path) as archive:
                member = setup_mod.find_sound_member(archive.namelist(), "notification.wav")

        self.assertEqual(member, "SND03_industrial/notification.wav")

    def test_update_config_replaces_existing_notify_by_default(self) -> None:
        original = '\n'.join(
            [
                'model = "gpt-5.4"',
                'notify = ["terminal-notifier", "-message", "done"]',
                "",
                "[tui]",
                'notifications = ["approval-requested"]',
                "",
            ]
        )
        notifier = Path("/Users/test/.codex/skills/codex-sound-notifications/scripts/codex_sound_notify.py")
        sound = Path("/Users/test/.codex/sounds/notification.wav")

        updated = setup_mod.update_config_text(
            original_text=original,
            notifier_path=notifier,
            sound_path=sound,
            event_name="agent-turn-complete",
        )

        self.assertIn('notify = ["python3", "/Users/test/.codex/skills/codex-sound-notifications/scripts/codex_sound_notify.py"', updated)
        self.assertNotIn("terminal-notifier", updated)
        self.assertIn('notifications = ["approval-requested"]', updated)

    def test_update_config_can_preserve_existing_notify_explicitly(self) -> None:
        original = 'notify = ["terminal-notifier", "-message", "done"]\n'
        notifier = Path("/Users/test/.codex/skills/codex-sound-notifications/scripts/codex_sound_notify.py")
        sound = Path("/Users/test/.codex/sounds/notification.wav")

        updated = setup_mod.update_config_text(
            original_text=original,
            notifier_path=notifier,
            sound_path=sound,
            event_name="agent-turn-complete",
            preserve_existing_notify=True,
        )

        self.assertIn('"--forward-command-json"', updated)
        self.assertIn("terminal-notifier", updated)

    def test_update_config_does_not_add_tui_notifications(self) -> None:
        original = ""
        notifier = Path("/Users/test/.codex/skills/codex-sound-notifications/scripts/codex_sound_notify.py")
        sound = Path("/Users/test/.codex/sounds/notification.wav")

        updated = setup_mod.update_config_text(
            original_text=original,
            notifier_path=notifier,
            sound_path=sound,
            event_name="agent-turn-complete",
        )

        self.assertNotIn("[tui]", updated)
        self.assertNotIn("notifications =", updated)

    def test_update_config_does_not_wrap_renamed_notifier(self) -> None:
        original = (
            'notify = ["python3", "/Users/test/.codex/skills/setup-sound-notifications/scripts/codex_sound_notify.py", "--sound-path", "/Users/test/.codex/skills/setup-sound-notifications/assets/sounds/notification.wav", "--event", "agent-turn-complete"]\n'
        )
        notifier = Path("/Users/test/.codex/skills/codex-sound-notifications/scripts/codex_sound_notify.py")
        sound = Path("/Users/test/.codex/skills/codex-sound-notifications/assets/sounds/celebration.wav")

        updated = setup_mod.update_config_text(
            original_text=original,
            notifier_path=notifier,
            sound_path=sound,
            event_name="agent-turn-complete",
        )

        self.assertIn(str(notifier), updated)
        self.assertNotIn('"--forward-command-json"', updated)

    def test_install_end_to_end_with_temp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "SND03_industrial.zip"
            bundled_dir = tmp / "bundled"
            config_path = tmp / "config.toml"
            sound_dir = tmp / "sounds"

            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("SND03_industrial/notification.wav", b"wave")

            result = setup_mod.install(
                sound_file="notification.wav",
                sound_dir=sound_dir,
                config_path=config_path,
                event_name="agent-turn-complete",
                zip_path=zip_path,
                bundled_sounds_dir=bundled_dir,
            )

            self.assertEqual(
                result["sound_path"],
                str((bundled_dir / "notification.wav").resolve()),
            )
            self.assertEqual(result["selected_sound"], "notification.wav")
            self.assertTrue((bundled_dir / "notification.wav").exists())
            self.assertFalse(sound_dir.exists())
            config_text = config_path.read_text()
            self.assertIn('notify = ["python3"', config_text)
            self.assertIn('/tmp', config_text)  # temp path should be rendered
            self.assertNotIn("notifications =", config_text)

    def test_install_uses_bundled_sounds_when_zip_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bundled_dir = tmp / "bundled"
            config_path = tmp / "config.toml"
            sound_dir = tmp / "sounds"
            bundled_dir.mkdir()
            (bundled_dir / "celebration.wav").write_bytes(b"wave")

            result = setup_mod.install(
                sound_file="celebration.wav",
                sound_dir=sound_dir,
                config_path=config_path,
                event_name="agent-turn-complete",
                bundled_sounds_dir=bundled_dir,
            )

            self.assertEqual(
                result["sound_path"],
                str((bundled_dir / "celebration.wav").resolve()),
            )
            self.assertEqual(result["selected_sound"], "celebration.wav")
            self.assertTrue((bundled_dir / "celebration.wav").exists())
            self.assertFalse(sound_dir.exists())

    def test_install_imports_zip_into_bundled_sounds_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bundled_dir = tmp / "bundled"
            bundled_dir.mkdir()
            zip_path = tmp / "SND01_sine.zip"
            sound_dir = tmp / "sounds"
            config_path = tmp / "config.toml"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("SND01_sine/button.wav", b"new-button")

            setup_mod.install(
                sound_file="button.wav",
                sound_dir=sound_dir,
                config_path=config_path,
                event_name="agent-turn-complete",
                zip_path=zip_path,
                bundled_sounds_dir=bundled_dir,
            )

            self.assertEqual((bundled_dir / "button.wav").read_bytes(), b"new-button")
            self.assertFalse(sound_dir.exists())

    def test_list_bundled_sounds_returns_sorted_wavs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bundled_dir = Path(tmpdir)
            (bundled_dir / "b.wav").write_bytes(b"b")
            (bundled_dir / "a.wav").write_bytes(b"a")
            (bundled_dir / "note.txt").write_text("x")

            sounds = setup_mod.list_bundled_sounds(bundled_dir)

        self.assertEqual(sounds, ["a.wav", "b.wav"])

    def test_read_current_sound_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                'notify = ["python3", "/tmp/codex_sound_notify.py", "--sound-path", "/Users/test/.codex/sounds/celebration.wav", "--event", "agent-turn-complete"]\n'
            )

            current_sound = setup_mod.read_current_sound_from_config(config_path)

        self.assertEqual(current_sound, "celebration.wav")

    def test_read_current_sound_from_config_uses_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sound_dir = Path(tmpdir) / "sounds"
            sound_dir.mkdir()
            (sound_dir / "current-sound.txt").write_text("button.wav\n", encoding="utf-8")
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                f'notify = ["python3", "/tmp/codex_sound_notify.py", "--sound-path", "{sound_dir / "current.wav"}", "--event", "agent-turn-complete"]\n'
            )

            current_sound = setup_mod.read_current_sound_from_config(config_path)

        self.assertEqual(current_sound, "button.wav")


class CodexSoundNotifyTests(unittest.TestCase):
    def test_extract_event_name_supports_known_shapes(self) -> None:
        payload = {"payload": {"event_name": "agent-turn-complete"}}
        self.assertEqual(
            notify_mod.extract_event_name(payload),
            "agent-turn-complete",
        )

    def test_should_play_for_legacy_payload(self) -> None:
        payload = {"thread-id": "thread-1", "turn-id": "turn-1"}
        self.assertTrue(
            notify_mod.should_play_for_payload(payload, {"agent-turn-complete"})
        )

    def test_should_skip_non_completion_event(self) -> None:
        payload = {"event": "approval-requested"}
        self.assertFalse(
            notify_mod.should_play_for_payload(payload, {"agent-turn-complete"})
        )

    def test_should_skip_internal_prompt_payload(self) -> None:
        payload = {
            "type": "agent-turn-complete",
            "input-messages": ["You are a title generator for Codex Desktop."],
        }
        self.assertFalse(
            notify_mod.should_play_for_payload(payload, {"agent-turn-complete"})
        )
        self.assertEqual(
            notify_mod.suppression_reason_for_payload(payload),
            "internal-prompt",
        )

    def test_should_play_for_normal_user_message(self) -> None:
        payload = {
            "type": "agent-turn-complete",
            "input-messages": [" ping\n"],
        }
        self.assertTrue(
            notify_mod.should_play_for_payload(payload, {"agent-turn-complete"})
        )
        self.assertIsNone(notify_mod.suppression_reason_for_payload(payload))

    def test_should_play_for_empty_forwarded_invocation(self) -> None:
        self.assertTrue(
            notify_mod.should_play_for_invocation(
                b"",
                None,
                {"agent-turn-complete"},
            )
        )

    def test_claim_play_slot_suppresses_short_duplicate_burst(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "last-play"

            first = notify_mod.claim_play_slot(state_path, 250, now=10.0)
            duplicate = notify_mod.claim_play_slot(state_path, 250, now=10.1)
            later = notify_mod.claim_play_slot(state_path, 250, now=10.3)

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertTrue(later)

    def test_effective_event_name_maps_legacy_payload(self) -> None:
        payload = {"thread-id": "thread-1", "turn-id": "turn-1"}
        self.assertEqual(
            notify_mod.effective_event_name(payload),
            "agent-turn-complete",
        )

    def test_write_log_appends_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "sound-notify.log"
            notify_mod.write_log(
                log_path,
                {"status": "ok", "event": "agent-turn-complete"},
            )

            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(
            json.loads(lines[0]),
            {"status": "ok", "event": "agent-turn-complete"},
        )

    def test_extract_forward_and_payload_reads_json_argument(self) -> None:
        stdin = type("FakeStdin", (), {"buffer": type("FakeBuffer", (), {"read": lambda self: b""})()})()
        raw, payload, forward = notify_mod.extract_forward_and_payload(
            payload_json=None,
            forward=['{"type":"agent-turn-complete"}', "echo", "done"],
            stdin=stdin,
        )

        self.assertEqual(raw, b'{"type":"agent-turn-complete"}')
        self.assertEqual(payload, {"type": "agent-turn-complete"})
        self.assertEqual(forward, ["echo", "done"])

    def test_extract_forward_and_payload_reads_trailing_json_after_forward(self) -> None:
        stdin = type("FakeStdin", (), {"buffer": type("FakeBuffer", (), {"read": lambda self: b""})()})()
        raw, payload, forward = notify_mod.extract_forward_and_payload(
            payload_json=None,
            forward=["--", "helper", "turn-ended", '{"type":"agent-turn-complete"}'],
            stdin=stdin,
        )

        self.assertEqual(raw, b'{"type":"agent-turn-complete"}')
        self.assertEqual(payload, {"type": "agent-turn-complete"})
        self.assertEqual(forward, ["helper", "turn-ended"])

    def test_run_forward_command_appends_payload_argument(self) -> None:
        completed = mock.Mock(returncode=0)
        with mock.patch.object(notify_mod.subprocess, "run", return_value=completed) as run:
            exit_code = notify_mod.run_forward_command(
                ["helper", "turn-ended"],
                b'{"type":"agent-turn-complete"}',
            )

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(
            ["helper", "turn-ended", '{"type":"agent-turn-complete"}'],
            stdin=notify_mod.subprocess.DEVNULL,
            stdout=notify_mod.subprocess.DEVNULL,
            stderr=notify_mod.subprocess.DEVNULL,
            check=False,
            timeout=notify_mod.DEFAULT_FORWARD_TIMEOUT_SECONDS,
        )

    def test_run_forward_command_returns_timeout_status(self) -> None:
        with mock.patch.object(
            notify_mod.subprocess,
            "run",
            side_effect=notify_mod.subprocess.TimeoutExpired("helper", 0.1),
        ):
            exit_code = notify_mod.run_forward_command(
                ["helper"],
                b"",
                timeout_seconds=0.1,
            )

        self.assertEqual(exit_code, 124)

    def test_parse_forward_command_json(self) -> None:
        command = notify_mod.parse_forward_command_json('["helper","turn-ended"]')
        self.assertEqual(command, ["helper", "turn-ended"])


class ManageSoundNotificationsTests(unittest.TestCase):
    def test_default_update_repository_targets_maintained_fork(self) -> None:
        self.assertEqual(
            manage_mod.DEFAULT_REPO,
            "Qin-jiahao/codex-sound-notifications",
        )

    def test_parse_github_repo_slug_supports_common_forms(self) -> None:
        self.assertEqual(
            manage_mod.parse_github_repo_slug(
                "https://github.com/zty42/codex-sound-notifications.git"
            ),
            "zty42/codex-sound-notifications",
        )
        self.assertEqual(
            manage_mod.parse_github_repo_slug(
                "git@github.com:zty42/codex-sound-notifications.git"
            ),
            "zty42/codex-sound-notifications",
        )
        self.assertEqual(
            manage_mod.parse_github_repo_slug("zty42/codex-sound-notifications"),
            "zty42/codex-sound-notifications",
        )

    def test_resolve_selection_accepts_number(self) -> None:
        sound = manage_mod.resolve_selection("2", ["a.wav", "b.wav"])
        self.assertEqual(sound, "b.wav")

    def test_format_sound_list_marks_current(self) -> None:
        formatted = manage_mod.format_sound_list(
            ["a.wav", "b.wav"],
            "b.wav",
        )
        self.assertIn(" 1. a.wav", formatted)
        self.assertIn(" 2. b.wav (current)", formatted)

    def test_interactive_manage_previews_then_applies(self) -> None:
        stdin = mock.Mock()
        stdin.readline = mock.Mock(side_effect=["2\n", "y\n"])
        stdout = mock.Mock()
        preview_fn = mock.Mock(return_value=0)
        apply_fn = mock.Mock(
            return_value={"sound_path": "/Users/test/.codex/sounds/b.wav"}
        )

        with mock.patch("builtins.print") as print_mock:
            exit_code = manage_mod.interactive_manage(
                sounds=["a.wav", "b.wav"],
                current_sound="a.wav",
                player="true",
                sounds_dir=Path("/tmp/sounds"),
                config_path=Path("/tmp/config.toml"),
                sound_dir=Path("/tmp/out"),
                event_name="agent-turn-complete",
                stdin=stdin,
                stdout=stdout,
                preview_fn=preview_fn,
                apply_fn=apply_fn,
            )

        self.assertEqual(exit_code, 0)
        preview_fn.assert_called_once_with("b.wav", "true", Path("/tmp/sounds"))
        apply_fn.assert_called_once_with(
            "b.wav",
            Path("/tmp/config.toml"),
            Path("/tmp/out"),
            "agent-turn-complete",
        )
        print_mock.assert_any_call("Previewed b.wav.", file=stdout)

    def test_preview_sound_returns_127_when_player_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sounds_dir = Path(tmpdir)
            (sounds_dir / "a.wav").write_bytes(b"a")

            exit_code = manage_mod.preview_sound("a.wav", "missing-player", sounds_dir)

        self.assertEqual(exit_code, 127)

    def test_check_for_updates_uses_metadata_for_non_git_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manage_mod.write_update_state(
                root,
                repo="zty42/codex-sound-notifications",
                ref="main",
                commit="1111111",
            )

            with (
                mock.patch.object(manage_mod, "is_git_checkout", return_value=False),
                mock.patch.object(
                    manage_mod,
                    "fetch_remote_revision",
                    return_value={
                        "repo": "zty42/codex-sound-notifications",
                        "ref": "main",
                        "commit": "2222222",
                        "message": "new commit",
                        "url": "https://github.com/zty42/codex-sound-notifications/commit/2222222",
                    },
                ),
            ):
                result = manage_mod.check_for_updates(root=root)

        self.assertEqual(result["status"], "update-available")
        self.assertTrue(result["update_available"])
        self.assertEqual(result["local_commit"], "1111111")
        self.assertEqual(result["local_version_source"], "metadata")

    def test_check_for_updates_reports_unknown_local_version_for_non_git_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            with (
                mock.patch.object(manage_mod, "is_git_checkout", return_value=False),
                mock.patch.object(
                    manage_mod,
                    "fetch_remote_revision",
                    return_value={
                        "repo": "zty42/codex-sound-notifications",
                        "ref": "main",
                        "commit": "2222222",
                        "message": "new commit",
                        "url": "https://github.com/zty42/codex-sound-notifications/commit/2222222",
                    },
                ),
            ):
                result = manage_mod.check_for_updates(root=root)

        self.assertEqual(result["status"], "local-version-unknown")
        self.assertIsNone(result["update_available"])
        self.assertIsNone(result["local_commit"])

    def test_update_non_git_install_merges_archive_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "assets" / "sounds").mkdir(parents=True)
            (root / "assets" / "sounds" / "custom.wav").write_bytes(b"custom")

            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "codex-sound-notifications-main/SKILL.md",
                    "# skill\n",
                )
                bundle.writestr(
                    "codex-sound-notifications-main/README.md",
                    "updated\n",
                )
                bundle.writestr(
                    "codex-sound-notifications-main/assets/sounds/notification.wav",
                    b"upstream",
                )
                bundle.writestr(
                    "codex-sound-notifications-main/scripts/manage_sound_notifications.py",
                    "# updated\n",
                )

            with (
                mock.patch.object(manage_mod, "is_git_checkout", return_value=False),
                mock.patch.object(
                    manage_mod,
                    "check_for_updates",
                    return_value={
                        "status": "update-available",
                        "update_available": True,
                        "repo": "zty42/codex-sound-notifications",
                        "ref": "main",
                        "local_commit": None,
                        "local_commit_short": None,
                        "local_version_source": "unknown",
                        "remote_commit": "abcdef0123456789",
                        "remote_commit_short": "abcdef0",
                        "remote_message": "refresh",
                        "remote_url": "https://github.com/zty42/codex-sound-notifications/commit/abcdef0123456789",
                    },
                ),
                mock.patch.object(
                    manage_mod,
                    "download_repo_archive",
                    return_value=archive.getvalue(),
                ),
            ):
                result = manage_mod.update_non_git_install(root, None, None)
            self.assertTrue(result["updated"])
            self.assertEqual(result["strategy"], "archive")
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), "updated\n")
            self.assertEqual(
                (root / "assets" / "sounds" / "custom.wav").read_bytes(),
                b"custom",
            )
            self.assertEqual(
                manage_mod.read_update_state(root),
                {
                    "repo": "zty42/codex-sound-notifications",
                    "ref": "main",
                    "commit": "abcdef0123456789",
                },
            )

    def test_update_git_install_refuses_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                mock.patch.object(manage_mod, "git_current_commit", return_value="1111111"),
                mock.patch.object(manage_mod, "git_has_local_changes", return_value=True),
            ):
                with self.assertRaisesRegex(RuntimeError, "local changes"):
                    manage_mod.update_git_install(root, "main")

    def test_update_skill_uses_git_strategy_for_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                mock.patch.object(manage_mod, "is_git_checkout", return_value=True),
                mock.patch.object(manage_mod, "git_current_branch", return_value="main"),
                mock.patch.object(
                    manage_mod,
                    "update_git_install",
                    return_value={"updated": True, "strategy": "git"},
                ) as update_git_mock,
            ):
                result = manage_mod.update_skill(root=root)

        self.assertEqual(result, {"updated": True, "strategy": "git"})
        update_git_mock.assert_called_once_with(root, "main")

    def test_main_check_update_prints_json(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                manage_mod,
                "check_for_updates",
                return_value={"status": "up-to-date", "update_available": False},
            ),
            mock.patch("sys.stdout", stdout),
        ):
            exit_code = manage_mod.main(["--check-update"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {"status": "up-to-date", "update_available": False},
        )

    def test_main_update_respects_confirmation_prompt(self) -> None:
        stdout = io.StringIO()
        stdin = io.StringIO("n\n")
        with (
            mock.patch.object(manage_mod, "update_skill") as update_mock,
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stdin", stdin),
        ):
            exit_code = manage_mod.main(["--update"])

        self.assertEqual(exit_code, 0)
        update_mock.assert_not_called()
        self.assertIn("Cancelled.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
