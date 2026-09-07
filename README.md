[English](./README.md) | [简体中文](./README-CN.md)

# Codex Sound Notifications

Play a local sound whenever Codex finishes a turn on macOS.

The skill uses Codex's official user-level `notify` setting. Once configured, it applies to new and existing Codex tasks that load the same `~/.codex/config.toml`. It includes bundled sounds, an interactive sound picker, update tools, privacy-conscious logs, and regression tests.

> This repository is a maintained derivative of [zty42/codex-sound-notifications](https://github.com/zty42/codex-sound-notifications), originally created by zty42 and distributed under the MIT License. This fork keeps that attribution and focuses on reliable Codex Desktop behavior found through real-world testing.

## What this fork improves

- Handles the JSON payload that Codex appends to the `notify` command
- Uses a direct `notify` command by default to avoid recursive wrappers and hanging helper processes
- Supports an optional existing-notifier forwarding mode with a five-second timeout
- Accepts empty completion callbacks used by some Codex Desktop integrations
- Prevents duplicate sounds across short-lived notifier processes
- Works with the system Python 3.9 included on older macOS installations
- Does not record prompt or response text in logs unless explicitly enabled
- Includes 39 local regression tests

## Requirements

- macOS
- Codex Desktop or Codex CLI with `notify` support
- Python 3.9 or later
- `afplay`, included with macOS
- Write access to `~/.codex/config.toml`

## Install

Clone the skill into the user-level Codex skills directory:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/Qin-jiahao/codex-sound-notifications.git \
  ~/.codex/skills/codex-sound-notifications
cd ~/.codex/skills/codex-sound-notifications
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav
```

Then quit Codex completely and reopen it. Existing app processes may keep the previous configuration in memory until restart.

You can also ask Codex to install the skill:

```text
$skill-installer install https://github.com/Qin-jiahao/codex-sound-notifications
```

The skill installer copies the files but does not enable the completion callback. Run the setup command once after installation.

## Verify the setup

Preview the selected sound:

```bash
python3 scripts/manage_sound_notifications.py --preview celebration.wav
```

Check that the user-level configuration contains a top-level `notify` entry:

```bash
grep '^notify =' ~/.codex/config.toml
```

Send a normal message in Codex after restarting the app. The sound should play when the reply finishes.

## Manage sounds

Start the interactive picker:

```bash
python3 scripts/manage_sound_notifications.py
```

Useful non-interactive commands:

```bash
python3 scripts/manage_sound_notifications.py --list
python3 scripts/manage_sound_notifications.py --preview button.wav
python3 scripts/manage_sound_notifications.py --apply button.wav --yes
python3 scripts/manage_sound_notifications.py --check-update
python3 scripts/manage_sound_notifications.py --update
```

You can invoke the same workflow from a Codex conversation:

```text
$codex-sound-notifications list sounds
$codex-sound-notifications preview celebration.wav
$codex-sound-notifications switch to button.wav
$codex-sound-notifications check for updates
```

## Existing `notify` configurations

The default setup replaces the current top-level `notify` value. This is the most reliable mode for Codex Desktop and is the mode tested on the machine where the compatibility fixes were developed.

If another tool already depends on `notify`, you can preserve and call it after sound playback:

```bash
python3 scripts/setup_sound_notifications.py \
  --sound-file celebration.wav \
  --preserve-existing-notify
```

Preservation mode serializes the previous command as JSON, forwards the Codex payload as its final argument, and stops waiting after five seconds. The existing program must accept Codex's payload as a command-line argument. Wrappers that expect standard input or that rewrite `notify` themselves may remain incompatible.

## Import a local sound

The setup script can import one WAV file from a local zip archive into `assets/sounds/`:

```bash
python3 scripts/setup_sound_notifications.py \
  --zip-path /path/to/sounds.zip \
  --sound-file custom.wav
```

Only local files are imported. The script ignores common macOS metadata entries in zip archives.

## Logs and privacy

The runtime writes diagnostic metadata to `/tmp/codex-sound-notify.log`.

The log records timestamps, event matching, playback status, and exit codes. Prompt and response content is omitted by default. The runtime option `--log-payload-preview` enables a 200-character payload preview for temporary debugging; this may contain conversation text.

```bash
tail -n 20 /tmp/codex-sound-notify.log
```

## Troubleshooting

### Preview works, but completed replies stay silent

1. Quit every running Codex window and reopen the app.
2. Confirm that `notify` is at the top level of `~/.codex/config.toml`, before any `[section]` header.
3. Run the setup command again without `--preserve-existing-notify`.
4. Check `/tmp/codex-sound-notify.log` for a new entry after a reply completes.

### The sound plays only once

Update to the current version and run the setup command again. An earlier implementation used a process-relative monotonic clock for cross-process duplicate suppression. The current version uses a comparable wall-clock timestamp.

### A reply produces two sounds

Check whether another notification layer is also playing audio. Codex `notify`, terminal notifications, and `[tui].notifications` are separate mechanisms. This skill configures only `notify` and suppresses duplicate invocations received within 250 milliseconds.

### Setup reports a `tomllib` import error

That error comes from an older version. This fork uses only Python standard-library features available in Python 3.9.

### Update fails

A Git checkout is updated with a fast-forward-only pull and will refuse to overwrite local changes. Archive-based installations use GitHub's repository endpoints and keep additional local sound files.

## Tests

```bash
python3 scripts/test_sound_notifications.py
```

The suite covers configuration replacement and preservation, payload parsing, completion filtering, duplicate suppression, sound import, interactive management, and update behavior.

## Project layout

```text
codex-sound-notifications/
├── SKILL.md
├── agents/openai.yaml
├── assets/sounds/*.wav
└── scripts/
    ├── codex_sound_notify.py
    ├── manage_sound_notifications.py
    ├── setup_sound_notifications.py
    └── test_sound_notifications.py
```

## Scope and limitations

- The current playback implementation supports macOS because it uses `afplay`.
- Each local machine or remote Codex host needs its own user-level configuration.
- Codex must reload `~/.codex/config.toml` after setup; a full app restart is the safest method.
- The skill is not a native Codex settings panel or slash command.
- Preserving arbitrary third-party notifier wrappers cannot be guaranteed.

## Credits and license

The original project and code are credited to [zty42](https://github.com/zty42). This fork retains the upstream MIT license and documents its changes in [CHANGELOG.md](./CHANGELOG.md).

The bundled WAV files were inherited unchanged from the upstream project. Its README credits [SND](https://snd.dev/) as their source. See [ASSETS.md](./ASSETS.md) for provenance details. This fork does not make an additional ownership claim over third-party sound assets.

## References

- [Codex Configuration Reference](https://developers.openai.com/codex/config-reference)
- [Codex Hooks](https://developers.openai.com/codex/hooks)
- [Original repository](https://github.com/zty42/codex-sound-notifications)
