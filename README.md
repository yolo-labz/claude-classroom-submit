# claude-classroom-submit

**Autonomously submit files to Google Classroom assignments from Claude Code** — bypass the cross-origin Drive Picker iframe that makes browser automation impossible, and go straight to the Classroom REST API.

[![claude-code-plugin](https://img.shields.io/badge/claude--code-plugin-8a2be2)](https://docs.claude.com/en/docs/claude-code/plugins)
[![python](https://img.shields.io/badge/python-3.8%2B-3776ab)](https://www.python.org/)
[![stdlib-only](https://img.shields.io/badge/dependencies-stdlib--only-success)](skills/classroom-submit/classroom.py)
[![license-MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Google Classroom's web client uses a **Drive Picker iframe** (hosted at `drive.google.com/picker`) for file attachments. That iframe is cross-origin to `classroom.google.com`, so:

- Parent-page JavaScript can't reach into it (Same-Origin Policy)
- `Trusted Types` blocks `innerHTML` injection
- AppleScript mouse clicks require macOS Accessibility permission that `osascript` typically lacks
- Synthetic `DragEvent`s are rejected because `event.isTrusted === false`
- `document.execCommand('insertHTML')` throws "This document requires TrustedHTML assignment"

As a result, any Claude Code workflow that tries to **actually finish a Classroom submission** gets stuck at the picker. You can write the deliverable, compile the PDF, stage the Drive file, open the tab, even arm the picker — but you can't click the file inside the picker iframe, and you can't click "Entregar".

This plugin solves that by never touching the picker at all.

## The solution

Instead of scripting the UI, `claude-classroom-submit` speaks the [Google Classroom REST API](https://developers.google.com/classroom/reference/rest) directly:

1. **Upload** the file to the user's Google Drive via rclone (FUSE mount preferred, `rclone copy` as fallback).
2. **Discover** the Drive file ID from `rclone lsjson --original`.
3. **Find** the target assignment via `courses.courseWork.list` + title substring match.
4. **Attach** via `courses.courseWork.studentSubmissions.modifyAttachments` with `{"addAttachments": [{"driveFile": {"id": <id>}}]}`.
5. **Turn in** via `courses.courseWork.studentSubmissions.turnIn`.

All five steps run in a single `classroom-lib.sh submit-file` call, take ~10 seconds end-to-end, and never open a browser.

## Features

- **Zero third-party Python dependencies** — 600 lines of pure stdlib (`urllib`, `http.server`, `json`, `subprocess`). No `google-auth`, no `requests`, no `google-api-python-client`. Reproducible on NixOS, Alpine, whatever.
- **OAuth 2.0 Installed App flow** with loopback redirect (`http://localhost:8765`) and automatic access-token refresh.
- **Minimal scopes** — only `classroom.courses.readonly` + `classroom.coursework.me`. The plugin cannot read other students' work, cannot touch the grade book, cannot send messages.
- **Atomic submit** — `modifyAttachments` + `turnIn` in one call, with a hard check for `TURNED_IN` state to prevent double-submissions.
- **Natural-language query search** — `find "Airbnb"` walks every active course and returns every assignment whose title or description contains "Airbnb". No need to memorize course IDs.
- **Rclone-native** — reuses the user's existing rclone Drive remote (default: `gdrive-uni:Classroom-Submissions-2026.1`), prefers the local FUSE mount for instant uploads.
- **Claude Code plugin** — integrates as a skill + three slash commands (`/classroom-auth`, `/classroom-find`, `/classroom-submit`), auto-triggers when the user asks to submit to Classroom.
- **shellcheck + shfmt clean**, matches the conventions of [claude-mac-chrome](https://github.com/yolo-labz/claude-mac-chrome).

## Installation

### As a Claude Code plugin

```bash
# In Claude Code, run:
/plugin install https://github.com/yolo-labz/claude-classroom-submit
```

Or install locally for development:

```bash
git clone https://github.com/yolo-labz/claude-classroom-submit ~/Documents/Code/Apple/claude-classroom-submit
# Register as a local plugin via Claude Code's plugin.json:
#   "~/Documents/Code/Apple/claude-classroom-submit"
```

### As a standalone CLI

```bash
alias classroom='~/Documents/Code/Apple/claude-classroom-submit/skills/classroom-submit/classroom-lib.sh'
classroom help
```

## Setup (one-time)

Before first use, create a Google Cloud project and an OAuth 2.0 Desktop client. Full walkthrough: [`docs/google-cloud-setup.md`](docs/google-cloud-setup.md). Summary:

1. <https://console.cloud.google.com/projectcreate> → new project
2. Enable Classroom API: <https://console.cloud.google.com/apis/library/classroom.googleapis.com>
3. Configure OAuth consent screen (External, add your email as a test user, add 3 scopes)
4. Create OAuth client → Desktop app → download JSON
5. Save as `~/.config/claude-classroom-submit/credentials.json`
6. `classroom-lib.sh auth` — opens browser, grants consent, saves tokens

After step 6, every subsequent call is autonomous.

## Usage

### Find an assignment

```bash
classroom-lib.sh find "Airbnb" --terse
# ODUxMzc0NzU3ODU3  Nzk3MDIxMjk3MjU4  2026-04-07  AD432 - Estratégia...  Atividade 2 - O caso da empresa Airbnb
```

### Submit a file (one shot)

```bash
classroom-lib.sh submit-file ~/Documents/atividade2-airbnb.pdf --query "Airbnb"
```

Output:

```json
{
  "submission_id": "Cg4I6P_…",
  "course_id": "ODUxMzc0NzU3ODU3",
  "coursework_id": "Nzk3MDIxMjk3MjU4",
  "drive_file_id": "1Pg_YdVT-NRmiKoAacz1Sf21XJ-MX4vRJ",
  "state": "TURNED_IN",
  "title": "Atividade 2 - O caso da empresa Airbnb",
  "file": "atividade2-airbnb.pdf"
}
```

### Submit with explicit IDs (skip search)

```bash
classroom-lib.sh submit-file ~/file.pdf --course ODUxMzc0NzU3ODU3 --coursework Nzk3MDIxMjk3MjU4
```

### Attach without turning in (draft mode)

```bash
classroom-lib.sh submit-file ~/file.pdf --query "Airbnb" --attach-only
```

### Step-by-step (file already in Drive)

```bash
# You have the Drive file ID from rclone lsjson or elsewhere
classroom-lib.sh submit <course_id> <coursework_id> <drive_file_id>
```

### From inside Claude Code

The plugin registers three slash commands:

- `/claude-classroom-submit:classroom-auth` — one-time OAuth
- `/claude-classroom-submit:classroom-find <query>` — search assignments
- `/claude-classroom-submit:classroom-submit <file-path> <query>` — atomic submit

When the user asks Claude to "submit X to Classroom", Claude auto-discovers this plugin via the `classroom-submit` skill and runs the right command without requiring the user to invoke the slash command manually.

## Exit codes (stable contract)

| Code | Meaning                           |
|------|-----------------------------------|
| `0`  | success                           |
| `1`  | generic error                     |
| `2`  | setup required (credentials/auth) |
| `3`  | Classroom API error (4xx/5xx)     |
| `4`  | not found                         |
| `5`  | already turned in                 |

## Environment overrides

| Variable                           | Default                                                       |
|------------------------------------|---------------------------------------------------------------|
| `CLASSROOM_SUBMIT_CONFIG_DIR`      | `$XDG_CONFIG_HOME/claude-classroom-submit`                    |
| `CLASSROOM_SUBMIT_RCLONE_REMOTE`   | `gdrive-uni:Classroom-Submissions-2026.1`                     |
| `CLASSROOM_SUBMIT_RCLONE_MOUNT`    | `/Users/notroot/GoogleDrive-Uni/Classroom-Submissions-2026.1` |
| `CLASSROOM_SUBMIT_OAUTH_PORT`      | `8765`                                                        |
| `CLASSROOM_SUBMIT_PYTHON`          | (auto-detect `python3` / `python`)                            |

Persistent overrides live in `~/.config/claude-classroom-submit/config.json`:

```json
{
  "rclone_remote": "gdrive-work:ClassroomDropbox",
  "rclone_mount_path": "/Users/you/GDriveWork/ClassroomDropbox"
}
```

## Security

- **Local tokens only** — `tokens.json` lives at `~/.config/claude-classroom-submit/tokens.json` with mode `0600`. Never leaves the machine.
- **No telemetry** — the plugin makes HTTPS calls only to `googleapis.com` and `oauth2.googleapis.com`. No other network I/O.
- **Minimal scopes** — the plugin cannot list teacher-side data, cannot see other students' submissions, cannot modify grades, cannot comment, cannot send email. If you don't trust it, read `skills/classroom-submit/classroom.py` — it's a single file, stdlib-only.
- **Own your OAuth client** — credentials.json is *your* OAuth 2.0 client, created in *your* Google Cloud project, consented by *you*. The plugin has no central backend, no shared secrets.

To uninstall fully:

```bash
rm -rf ~/.config/claude-classroom-submit
# Then revoke at https://myaccount.google.com/permissions
```

## FAQ

**Why rclone instead of the Drive REST API?** Rclone is already how Pedro (the author) manages his uni Google Drive as a FUSE mount. Using it means a file copy is a plain `cp`, no extra Drive upload scope is needed, and the existing mount infrastructure is reused. The Classroom API accepts any Drive file ID the authenticated user has access to.

**Does this work on Linux?** Yes, almost everything is portable. The default rclone mount path is macOS-specific; override it via `CLASSROOM_SUBMIT_RCLONE_MOUNT`. The Python code has no macOS-specific bits.

**Does this work for teacher accounts?** No — the plugin only uses the `.me` variant of the coursework scope, which is for students submitting their own work. Teacher-side operations (grading, listing all students' submissions) need different scopes and a different plugin.

**Can I attach multiple files at once?** Not in a single CLI call yet. Run `submit-file --attach-only` for each file, then `turn-in` once at the end.

**Can I submit to an assignment that doesn't have `ASSIGNMENT` type (e.g., questions)?** Probably not — the API only exposes `modifyAttachments` for assignment-type coursework. Open an issue with the exact `workType` and I'll look into it.

**Why not publish the OAuth client so users don't need Google Cloud setup?** Publishing requires Google verification, which for sensitive scopes (`classroom.coursework.me`) means a security review, a YouTube demo video, privacy policy hosting, and an annual audit. For a student tool that needs to stay trustworthy, it is cleaner for each user to own their own OAuth client. The 5-minute setup is a one-time cost.

## Related projects

- [claude-mac-chrome](https://github.com/yolo-labz/claude-mac-chrome) — sibling plugin for deterministic multi-profile Chrome automation on macOS. This plugin's conventions (shellcheck-clean shell wrapper, subcommand dispatch, SKILL.md frontmatter) match `claude-mac-chrome`'s, and the two are designed to be used together.

## License

MIT — see [LICENSE](LICENSE).

## Author

Pedro Henrique Souza Balbino — [@phsb5321](https://github.com/phsb5321)
