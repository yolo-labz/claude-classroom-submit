---
name: classroom-submit
description: Autonomously submit files to Google Classroom assignments end-to-end, bypassing the cross-origin Drive Picker iframe that blocks browser automation. Uploads the file to the user's Google Drive via rclone, finds the target assignment (by query or explicit IDs), attaches the Drive file, and turns in the submission — all via the Classroom REST API using OAuth 2.0. Use when asked to "submit to Classroom", "upload this to Atividade X", "entregar", "turn in on Classroom", or any variant of actually finalizing a Classroom submission from a local file.
allowed-tools:
  - Bash
  - Read
---

# Google Classroom Autonomous Submission (macOS)

The Google Classroom web client uses a **cross-origin Drive Picker iframe** (`drive.google.com/picker` embedded in `classroom.google.com`) for file attachments. This iframe is unreachable from parent-page JavaScript (Trusted Types + cross-origin boundary), and AppleScript mouse clicks require Accessibility permission that is typically not granted to `osascript`. Result: **no amount of JS/keystroke injection can click "Entregar" reliably**.

This skill sidesteps the entire picker UI by going **straight to the Classroom REST API**, which accepts a Drive file ID and an assignment ID and performs the attach + turn-in atomically.

## When to use

Trigger this skill when the user wants any of:

- "submit this file to Classroom", "entregar no Classroom", "upload this to Atividade X"
- "turn in my submission for [assignment name]"
- "attach [file] to [course] assignment and mark as done"
- Batch-submitting multiple deliverables at once
- Finding the `courseId`/`courseWorkId` for a given assignment (the CLI's `find` subcommand searches by title)

Do **not** use this skill for:
- Browsing or viewing Classroom content (use `chrome-multi-profile` or the browser)
- Assignments that require text/link attachments only (the CLI currently handles Drive file attachments)
- Commenting on assignments

## One-time setup (required)

The plugin cannot work until the user creates an OAuth 2.0 client in their own Google Cloud project and grants Classroom API access. This is a ~5-minute manual step. See `docs/google-cloud-setup.md` for the complete walkthrough. Summary:

1. Google Cloud Console → new project → **Enable Classroom API**
2. APIs & Services → Credentials → **Create OAuth 2.0 Client ID** → type: **Desktop app**
3. Download JSON → save as `~/.config/claude-classroom-submit/credentials.json`
4. Run: `${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh auth`
5. Browser opens → grant `classroom.courses.readonly` + `classroom.coursework.me` → refresh token saved to `~/.config/claude-classroom-submit/tokens.json`

After step 5, all future submissions are autonomous until the refresh token is revoked.

## CLI reference

Always invoke via:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh" <command> [args...]
```

### Discovery
```bash
classroom-lib.sh whoami                         # verify auth, print email
classroom-lib.sh courses --terse                # list active courses (ID<tab>name)
classroom-lib.sh assignments <course_id> --terse # list coursework in a course
classroom-lib.sh find "Airbnb" --terse          # search all courses for a match
```

`find` is the workhorse: given a query string, it walks every active course and returns any coursework whose title or description contains the query (case-insensitive). Output fields: `course_id`, `course_name`, `coursework_id`, `title`, `due_date`, `due_time`, `state`, `alternate_link`, `work_type`.

### Submission (one-shot)

```bash
classroom-lib.sh submit-file ~/path/to/file.pdf --query "Airbnb"
```

This single command:
1. Copies the file to the rclone Drive remote (default: `gdrive-uni:Classroom-Submissions-2026.1`)
2. Polls until the Drive file ID is available (up to 20s)
3. Searches for the assignment matching `--query`
4. Fails if the query matches zero or multiple assignments (ambiguous)
5. Calls `studentSubmissions.modifyAttachments` to attach the Drive file
6. Calls `studentSubmissions.turnIn` to finalize
7. Prints the submission record as JSON

If you already know the exact IDs, skip the search:

```bash
classroom-lib.sh submit-file ~/file.pdf --course ODUxMzc0 --coursework Nzk3MDIx
```

Use `--attach-only` to attach without turning in (draft mode). Use `--dry-run` to resolve the assignment without touching Drive or the API.

### Step-by-step (when you already have a Drive file ID)

```bash
classroom-lib.sh submit <course_id> <coursework_id> <drive_file_id>
```

This is the atomic "attach + turn in" without any rclone upload. Use when the file already lives in Drive (e.g., previously uploaded, or exists from another source).

### Granular operations

```bash
classroom-lib.sh submission <course_id> <coursework_id>   # get submission state
classroom-lib.sh attach <c> <cw> <drive_id>               # attach only, no turn-in
classroom-lib.sh turn-in <course_id> <coursework_id>      # turn in existing attachments
```

## Exit codes (stable contract)

| Code | Meaning                           | When                                     |
|------|-----------------------------------|------------------------------------------|
| 0    | success                           | submit + turn-in confirmed               |
| 1    | generic error                     | malformed args, local FS issue           |
| 2    | setup required                    | credentials.json or tokens.json missing  |
| 3    | Classroom API error (4xx/5xx)     | invalid IDs, scope denied, quota         |
| 4    | not found                         | course/coursework/submission not found   |
| 5    | already turned in                 | `turn-in` called on TURNED_IN submission |

## Common failure modes and recovery

**`error: credentials file not found`** — user skipped the Google Cloud setup. Point them at `docs/google-cloud-setup.md`.

**`error: No tokens found. Run 'classroom auth' first.`** — self-explanatory; run `classroom-lib.sh auth`.

**`HTTP 401 Unauthorized` after long idle** — refresh token was revoked (user changed password, revoked access at myaccount.google.com, or exceeded 6-month inactivity on unverified OAuth clients). Re-run `classroom-lib.sh auth`.

**`HTTP 403 insufficient_scope`** — credentials were created with wrong scopes. Revoke access at https://myaccount.google.com/permissions and re-run `auth`.

**`Query 'X' matched N assignments`** — be more specific in `--query`, or pass `--course` and `--coursework` explicitly.

**`No student submission found`** — the user isn't enrolled in the course, or the assignment is in a draft state (not yet published), or the assignment uses an `assignedUserIds` list and the current user isn't on it.

**`rclone mount not found and rclone CLI not in PATH`** — rclone isn't installed or the mount isn't active. Either `brew install rclone` (or nix), or set `CLASSROOM_SUBMIT_RCLONE_MOUNT` to a different local directory that's synced to Drive.

## Environment overrides

| Variable                           | Default                                             | Purpose                                         |
|------------------------------------|-----------------------------------------------------|-------------------------------------------------|
| `CLASSROOM_SUBMIT_CONFIG_DIR`      | `$XDG_CONFIG_HOME/claude-classroom-submit`          | Where `credentials.json` and `tokens.json` live |
| `CLASSROOM_SUBMIT_RCLONE_REMOTE`   | `gdrive-uni:Classroom-Submissions-2026.1`           | Rclone remote:path target for uploads           |
| `CLASSROOM_SUBMIT_RCLONE_MOUNT`    | `/Users/notroot/GoogleDrive-Uni/Classroom-Submissions-2026.1` | Local FUSE mount path for fast `cp`-based upload |
| `CLASSROOM_SUBMIT_OAUTH_PORT`      | `8765`                                              | Loopback port for OAuth callback                |
| `CLASSROOM_SUBMIT_PYTHON`          | (auto-detect)                                       | Override which python interpreter to use        |

A `config.json` at `${CLASSROOM_SUBMIT_CONFIG_DIR}/config.json` can set `rclone_remote` and `rclone_mount_path` persistently without env vars.

## Scopes and privacy

The plugin requests only two Classroom scopes:

- `https://www.googleapis.com/auth/classroom.courses.readonly` — list courses the user is enrolled in
- `https://www.googleapis.com/auth/classroom.coursework.me` — list, modify, and turn in the user's own coursework submissions

It does **not** request access to other students' data, teacher-side data, grade books, or course rosters. The user's refresh token lives locally at `~/.config/claude-classroom-submit/tokens.json` with mode `0600` and never leaves the machine. No telemetry, no remote logging.

## Design notes

- **Pure Python 3 stdlib** — no `google-auth`, no `requests`, no `google-api-python-client`. This keeps the plugin reproducible on NixOS and trivially portable.
- **OAuth 2.0 Installed App flow** with a loopback redirect (`http://localhost:8765`) and `prompt=consent` to guarantee a refresh token on every run.
- **Automatic access-token refresh** on 401 — the Python layer refreshes once and retries, so callers don't need to think about token lifetime.
- **Rclone-first upload** — the skill prefers the local FUSE mount (instant `cp`) when available, falls back to `rclone copy` to a remote, polls `rclone lsjson --original` for up to 20s to get the Drive file ID. No Drive API write scope needed; the Classroom API trusts that the authenticated user has access to the file.
- **Atomic `submit`** combines `modifyAttachments` + `turnIn` and short-circuits if the submission is already `TURNED_IN` (exit code 5) to prevent double-submissions.

## Quick troubleshooting script

```bash
LIB="${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh"
"$LIB" whoami || echo "setup problem — run '$LIB auth'"
"$LIB" courses --terse | head -5
"$LIB" find "Airbnb" --terse
```
