## macOS and Windows integration

- Add a separate Windows Python session monitor with native WAV playback, primary-session filtering and incomplete JSONL buffering.
- Share the sound library, preview and apply commands across both platforms; use celebration.wav by default.
- Preserve the macOS notify backend and keep Windows configuration independent of config.toml.
- Add per-user Windows logon startup, migration documentation, portable monitor tests and Windows/macOS CI.
- Credit YANG301 for the Windows session-monitor approach; retain original zty42 and audio provenance credits.

# Changelog

All notable project changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Changed setup to use a direct top-level `notify` command by default
- Made preservation of an existing notifier explicit through `--preserve-existing-notify`
- Changed non-git update checks to use `Qin-jiahao/codex-sound-notifications` as the default repository
- Stopped logging payload previews by default

### Fixed

- Parsed the JSON payload that Codex appends after configured notification arguments
- Prevented forwarded commands from waiting on standard input indefinitely
- Added a five-second timeout for forwarded notifier processes
- Added compatibility for empty completion callbacks produced by some Codex Desktop integrations
- Prevented recursive wrapping of existing copies of the notifier
- Replaced process-relative monotonic timestamps with wall-clock timestamps for cross-process duplicate suppression
- Removed the Python 3.11-only `tomllib` dependency so setup works with Python 3.9

### Added

- Added JSON-safe preservation of existing notifier commands
- Added opt-in `--log-payload-preview` diagnostics
- Added regression coverage for direct replacement, explicit preservation, trailing payload parsing, forwarded payloads, and duplicate suppression
- Added English and Chinese installation, privacy, compatibility, and troubleshooting documentation
- Added third-party asset provenance documentation

## [0.1.0] - 2026-03-20

### Added

- Initial release by zty42
- Bundled WAV sound assets for completion notifications
- Runtime notifier based on Codex `notify`
- Interactive sound management and update commands
- Installer and local test suite
- English and Chinese documentation
- MIT license

