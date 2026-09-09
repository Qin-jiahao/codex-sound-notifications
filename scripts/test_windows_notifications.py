"""Portable tests for Windows log processing and backend dispatch; no user setup."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest import mock
import windows_sound_notifications as win
import setup_sound_notifications as setup
import manage_sound_notifications as manage

META = {"type": "session_meta", "payload": {"source": "cli"}}
FINAL = {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer"}}


def line(item):
    return (json.dumps(item) + "\n").encode()


class MonitorTests(unittest.TestCase):
    def test_skips_history_and_emits_each_new_final_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "session.jsonl"
            path.write_bytes(line(META) + line(FINAL))
            tail = win.Tail(root)
            self.assertEqual(tail.scan(path), 0)
            with path.open("ab") as f:
                f.write(line(FINAL) + line(FINAL))
            self.assertEqual(tail.scan(path), 2)
            self.assertEqual(tail.scan(path), 0)

    def test_split_json_record_survives_next_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tail = win.Tail(root)
            path = root / "new.jsonl"
            encoded = line(FINAL)
            path.write_bytes(line(META) + encoded[:30])
            self.assertEqual(tail.scan(path), 0)
            with path.open("ab") as f:
                f.write(encoded[30:])
            self.assertEqual(tail.scan(path), 1)

    def test_both_subagent_metadata_formats_are_ignored(self):
        for payload in ({"thread_source": "subagent"}, {"source": {"subagent": {}}}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                tail = win.Tail(root)
                path = root / "child.jsonl"
                path.write_bytes(line({"type": "session_meta", "payload": payload}) + line(FINAL))
                self.assertEqual(tail.scan(path), 0)

    def test_commentary_and_malformed_lines_do_not_play(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tail = win.Tail(root)
            path = root / "new.jsonl"
            item = {"type": "response_item", "payload": {**FINAL["payload"], "phase": "commentary"}}
            path.write_bytes(line(META) + b'broken\nnull\n' + line(item) + line(FINAL))
            self.assertEqual(tail.scan(path), 1)

    def test_windows_install_dispatch_does_not_write_codex_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.toml"
            config.write_text('notify = ["existing"]\n')
            with mock.patch.object(setup.sys, "platform", "win32"), \
                 mock.patch.object(setup, "install_sound_file", return_value=Path("sound.wav")), \
                 mock.patch.object(win, "install", return_value={"backend": "windows"}) as install:
                result = setup.install("sound.wav", Path(temp), config, "agent-turn-complete")
            self.assertEqual(result["backend"], "windows")
            install.assert_called_once_with(Path("sound.wav"))
            self.assertEqual(config.read_text(), 'notify = ["existing"]\n')

    def test_windows_preview_uses_native_player(self):
        player = mock.Mock(SND_FILENAME=1, SND_NODEFAULT=2)
        with mock.patch.object(manage.sys, "platform", "win32"), mock.patch.dict("sys.modules", winsound=player):
            self.assertEqual(manage.preview_sound("a.wav", manage.DEFAULT_PLAYER, Path("sounds")), 0)
        player.PlaySound.assert_called_once_with(str(Path("sounds") / "a.wav"), 3)

    @unittest.skipUnless(sys.platform == "win32", "Windows setup contract")
    def test_install_records_selection_without_modifying_real_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with mock.patch.object(win, "HOME", home), \
                 mock.patch.object(win, "STATE", home / "settings.json"), \
                 mock.patch.object(win, "powershell") as ps, \
                 mock.patch.object(win.subprocess, "Popen") as popen:
                result = win.install(win.ROOT / "assets/sounds/celebration.wav",
                                     start=False, register_task=False)
                self.assertFalse(result["started"])
                self.assertFalse(result["register_task"])
                self.assertEqual(win.read_settings()["sound_path"], result["sound_path"])
                self.assertIn("Unregister-ScheduledTask", ps.call_args.args[0])
                popen.assert_not_called()
                launcher = (home / "codex-sound-notifications-launcher.vbs").read_text(encoding="utf-16")
                self.assertIn('--monitor', launcher)
                self.assertIn(', 0, False', launcher)


if __name__ == "__main__":
    unittest.main()
