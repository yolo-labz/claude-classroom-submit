# Changelog

All notable changes to `claude-classroom-submit` will be documented here.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/), versioning uses [SemVer](https://semver.org/).

## [0.1.0] — 2026-04-08

Initial release.

### Added
- **`classroom.py`** — pure Python stdlib CLI with 10 subcommands: `auth`, `whoami`, `courses`, `assignments`, `find`, `submission`, `attach`, `turn-in`, `submit`, `submit-file`.
- **OAuth 2.0 Installed App flow** with loopback redirect on `localhost:8765`, automatic access-token refresh on 401, refresh-token persistence at `~/.config/claude-classroom-submit/tokens.json` (mode `0600`).
- **Rclone-native upload path** — prefers local FUSE mount (instant `cp`) when available, falls back to `rclone copy`, polls `rclone lsjson --original` for up to 20s to resolve the Drive file ID.
- **Atomic `submit`** — combines `studentSubmissions.modifyAttachments` + `studentSubmissions.turnIn`, short-circuits if already `TURNED_IN` (exit code 5).
- **Natural-language assignment search** via `find <query>` that walks every active course and matches the query against both title and description (case-insensitive).
- **`classroom-lib.sh`** — shellcheck + shfmt clean bash wrapper, subcommand dispatch, matches `claude-mac-chrome` conventions.
- **Claude Code slash commands** — `/classroom-auth`, `/classroom-find`, `/classroom-submit`.
- **Skill definition** at `skills/classroom-submit/SKILL.md` so Claude auto-triggers this plugin whenever the user asks to submit to Classroom.
- **Full Google Cloud OAuth setup walkthrough** at `docs/google-cloud-setup.md` covering project creation, Classroom API enablement, consent screen, test users, Desktop client ID download, and auth flow execution.

### Known limitations
- Only student-side scopes (`classroom.coursework.me`) — teacher-side submission handling is out of scope.
- Single-file attachments per `submit-file` call. Batch attach is on the v0.2 roadmap.
- No macOS Keychain token storage yet — tokens live in plaintext JSON with mode `0600`.
- OAuth clients in "Testing" status expire refresh tokens after 7 days of idle. Workaround: publish the OAuth consent screen (requires Google verification for sensitive scopes).

[0.1.0]: https://github.com/yolo-labz/claude-classroom-submit/releases/tag/v0.1.0
