---
description: Atomically submit a local file to a Google Classroom assignment. Uploads the file to the configured rclone Drive remote (default `gdrive-uni:Classroom-Submissions-2026.1`), discovers the Drive file ID, resolves the target assignment by query string, attaches the Drive file via `studentSubmissions.modifyAttachments`, and finalizes with `studentSubmissions.turnIn`. Pass the file path and a query substring that uniquely matches the assignment title. If the query matches multiple assignments, the command fails with the list of candidates so the user can disambiguate.
argument-hint: <file-path> <query>
---

# /classroom-submit

Submit a file to a Classroom assignment in one shot.

```bash
args="$ARGUMENTS"
if [ -z "$args" ]; then
  cat <<'USAGE'
Usage: /classroom-submit <file-path> <query>

Examples:
  /classroom-submit ~/Desktop/atividade2-airbnb.pdf Airbnb
  /classroom-submit "~/Docs/APS leite.pdf" "cooperativa"
  /classroom-submit ~/report.docx "Engenharia Social"

The query is a case-insensitive substring of the assignment title.
If multiple assignments match, the command fails with the list so
you can refine the query.
USAGE
  exit 0
fi

# Parse: first token is the file path (quoted support), rest is the query.
# This is a lightweight tokenizer that respects the first quoted argument.
eval "set -- $args"
file_path="$1"; shift
query="$*"

if [ -z "$query" ]; then
  echo "error: a search query is required (second argument)" >&2
  exit 1
fi

if [ ! -f "$file_path" ]; then
  echo "error: file not found: $file_path" >&2
  exit 1
fi

"${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh" submit-file "$file_path" --query "$query"
```

**Expected output** (JSON):

```json
{
  "submission_id": "Cg4I...",
  "course_id": "ODUxMzc0NzU3ODU3",
  "coursework_id": "Nzk3MDIxMjk3MjU4",
  "drive_file_id": "1Pg_YdVT-NRmiKoAacz1Sf21XJ-MX4vRJ",
  "state": "TURNED_IN",
  "title": "Atividade 2 - O caso da empresa Airbnb",
  "file": "atividade2-airbnb.pdf"
}
```

**If the command fails:**

- `exit 2` — setup incomplete, run `/classroom-auth` first
- `exit 3` — Classroom API error (the JSON body is printed to stderr with details)
- `exit 4` — query matched zero or multiple assignments; refine the query or use `--course` / `--coursework` directly via `classroom-lib.sh submit-file …`
- `exit 5` — assignment is already `TURNED_IN`; unsubmit in the Classroom UI first if you want to re-attach

**For attach-only (no turn-in)** — useful when you want to preview the attachment in the UI before finalizing:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh" submit-file <path> --query "<q>" --attach-only
```
