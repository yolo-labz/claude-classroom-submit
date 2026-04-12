#!/usr/bin/env python3
"""
claude-classroom-submit — autonomous Google Classroom submission CLI.

Pure Python 3 (stdlib only) — no google-api-python-client, no google-auth.
Speaks the Classroom REST API directly with OAuth 2.0 Installed App flow.

Commands:
    auth                                         One-time OAuth grant (opens browser)
    whoami                                       Test auth — print current user email
    courses                                      List enrolled courses (JSON)
    assignments <course_id>                      List coursework in a course (JSON)
    find <query>                                 Search all courses for coursework matching query
    submission <course_id> <coursework_id>       Get my submission status (JSON)
    attach <course_id> <coursework_id> <drive_id>   Attach a Drive file (does NOT turn in)
    turn-in <course_id> <coursework_id>          Turn in the submission
    submit <course_id> <coursework_id> <drive_id>   Attach + turn in (atomic)
    submit-file <path> [--query <text>] [--course <id>] [--coursework <id>]
                                                 Copy file to rclone Drive remote, find assignment,
                                                 attach + turn in in one shot.

Exit codes:
    0  success
    1  generic error
    2  setup error (run `auth` first, or credentials.json missing)
    3  Classroom API error (4xx/5xx)
    4  not found (course/coursework/submission)
    5  already turned in

Config locations (XDG):
    $XDG_CONFIG_HOME/claude-classroom-submit/credentials.json   OAuth client (user provides)
    $XDG_CONFIG_HOME/claude-classroom-submit/tokens.json        Refresh + access tokens (auto-managed, mode 600)
    $XDG_CONFIG_HOME/claude-classroom-submit/config.json        Optional: rclone_remote, rclone_mount_path

Environment overrides:
    CLASSROOM_SUBMIT_CONFIG_DIR       Override default config dir
    CLASSROOM_SUBMIT_RCLONE_REMOTE    Override rclone remote (default: gdrive-uni:Classroom-Submissions-2026.1)
    CLASSROOM_SUBMIT_RCLONE_MOUNT     Override local mount path for rclone remote
    CLASSROOM_SUBMIT_OAUTH_PORT       Override loopback OAuth callback port (default: 8765)
"""

import argparse
import contextlib
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me",
]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://classroom.googleapis.com/v1"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

DEFAULT_OAUTH_PORT = 8765
DEFAULT_RCLONE_REMOTE = "gdrive-uni:Classroom-Submissions-2026.1"
DEFAULT_RCLONE_MOUNT = "/Users/notroot/GoogleDrive-Uni/Classroom-Submissions-2026.1"

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------


def config_dir() -> str:
    override = os.environ.get("CLASSROOM_SUBMIT_CONFIG_DIR")
    if override:
        return override
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(xdg, "claude-classroom-submit")


def credentials_path() -> str:
    return os.path.join(config_dir(), "credentials.json")


def tokens_path() -> str:
    return os.path.join(config_dir(), "tokens.json")


def user_config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load_user_config() -> dict[str, Any]:
    path = user_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def rclone_remote() -> str:
    return (
        os.environ.get("CLASSROOM_SUBMIT_RCLONE_REMOTE")
        or load_user_config().get("rclone_remote")
        or DEFAULT_RCLONE_REMOTE
    )


def rclone_mount() -> str:
    return (
        os.environ.get("CLASSROOM_SUBMIT_RCLONE_MOUNT")
        or load_user_config().get("rclone_mount_path")
        or DEFAULT_RCLONE_MOUNT
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SetupError(Exception):
    """Raised when the plugin is not set up (credentials/tokens missing)."""


class APIError(Exception):
    """Raised on Classroom API errors."""

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class NotFoundError(Exception):
    """Raised when a requested course/coursework/submission cannot be found."""


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# OAuth client credentials
# ---------------------------------------------------------------------------


def load_credentials() -> dict[str, str]:
    path = credentials_path()
    if not os.path.exists(path):
        raise SetupError(
            f"Credentials file not found at {path}\n"
            "Download your OAuth 2.0 client credentials (Desktop app) from Google Cloud Console "
            "and save as credentials.json in that directory.\n"
            "See docs/google-cloud-setup.md in the plugin repository."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Google Cloud Console exports as {"installed": {...}} for Desktop type
    if "installed" in data:
        data = data["installed"]
    elif "web" in data:
        data = data["web"]
    required = ("client_id", "client_secret")
    for key in required:
        if key not in data:
            raise SetupError(f"credentials.json is missing field '{key}'")
    return {"client_id": data["client_id"], "client_secret": data["client_secret"]}


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------


def load_tokens() -> dict[str, Any] | None:
    path = tokens_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_tokens(tokens: dict[str, Any]) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    path = tokens_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def tokens_valid(tokens: dict[str, Any]) -> bool:
    expiry = tokens.get("expiry_epoch", 0)
    return bool(tokens.get("access_token")) and expiry > time.time() + 60


# ---------------------------------------------------------------------------
# HTTP helpers (urllib-based, no third-party deps)
# ---------------------------------------------------------------------------


def http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise APIError(f"HTTP {e.code} from {url}", status=e.code, body=body) from e


def http_request(
    method: str,
    url: str,
    access_token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise APIError(f"{method} {url} → HTTP {e.code}", status=e.code, body=raw) from e


# ---------------------------------------------------------------------------
# OAuth flow — Installed App with loopback redirect
# ---------------------------------------------------------------------------


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802 (required stdlib signature)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _OAuthCallbackHandler.code = (params.get("code") or [None])[0]
        _OAuthCallbackHandler.error = (params.get("error") or [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if _OAuthCallbackHandler.code:
            body = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>claude-classroom-submit</title>"
                "<style>body{font-family:system-ui;max-width:540px;margin:60px auto;padding:0 24px;}</style>"
                "</head><body><h1>✓ Authorization received</h1>"
                "<p>You can close this tab and return to your terminal.</p></body></html>"
            )
        else:
            body = (
                f"<!doctype html><html><body><h1>Authorization failed</h1>"
                f"<pre>{_OAuthCallbackHandler.error or 'no code received'}</pre></body></html>"
            )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
        return


def oauth_port() -> int:
    raw = os.environ.get("CLASSROOM_SUBMIT_OAUTH_PORT")
    if raw and raw.isdigit():
        return int(raw)
    return DEFAULT_OAUTH_PORT


def do_oauth_flow() -> dict[str, Any]:
    creds = load_credentials()
    port = oauth_port()
    redirect_uri = f"http://localhost:{port}"

    params = {
        "client_id": creds["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES + ["https://www.googleapis.com/auth/userinfo.email"]),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    consent_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"Opening browser for Google consent (scopes: {', '.join(SCOPES)})")
    print(f"If the browser does not open, visit this URL manually:\n\n  {consent_url}\n")

    # Start loopback server (single request)
    server = socketserver.TCPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = 300  # 5 minutes to complete consent

    def _serve() -> None:
        server.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    with contextlib.suppress(webbrowser.Error):
        webbrowser.open(consent_url)

    print(f"Waiting for callback on {redirect_uri} (timeout 5 min)…")
    thread.join(timeout=305)
    with contextlib.suppress(OSError):
        server.server_close()

    if _OAuthCallbackHandler.error:
        raise APIError(f"OAuth error: {_OAuthCallbackHandler.error}")
    if not _OAuthCallbackHandler.code:
        raise APIError("OAuth flow timed out before receiving code")

    # Exchange code for tokens
    token_response = http_post_form(
        TOKEN_URL,
        {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "code": _OAuthCallbackHandler.code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )

    # Persist
    tokens = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "token_type": token_response.get("token_type", "Bearer"),
        "scope": token_response.get("scope", ""),
        "expiry_epoch": int(time.time()) + int(token_response.get("expires_in", 3600)),
    }
    if not tokens["refresh_token"]:
        existing = load_tokens() or {}
        if existing.get("refresh_token"):
            tokens["refresh_token"] = existing["refresh_token"]
        else:
            raise APIError(
                "No refresh_token returned from Google. "
                "Revoke access at https://myaccount.google.com/permissions and retry."
            )
    save_tokens(tokens)
    return tokens


def refresh_access_token() -> dict[str, Any]:
    tokens = load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        raise SetupError("No tokens found. Run `classroom auth` first.")
    creds = load_credentials()

    resp = http_post_form(
        TOKEN_URL,
        {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        },
    )

    tokens["access_token"] = resp["access_token"]
    tokens["expiry_epoch"] = int(time.time()) + int(resp.get("expires_in", 3600))
    if "scope" in resp:
        tokens["scope"] = resp["scope"]
    save_tokens(tokens)
    return tokens


def get_access_token() -> str:
    tokens = load_tokens()
    if tokens and tokens_valid(tokens):
        return tokens["access_token"]
    tokens = refresh_access_token()
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Classroom API wrappers
# ---------------------------------------------------------------------------


def api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_access_token()
    url = path if path.startswith("http") else API_BASE + path
    try:
        return http_request(method, url, token, body)
    except APIError as e:
        if e.status == 401:
            # Refresh once and retry
            tokens = refresh_access_token()
            return http_request(method, url, tokens["access_token"], body)
        raise


def whoami() -> dict[str, Any]:
    token = get_access_token()
    return http_request("GET", USERINFO_URL, token)


def list_courses(active_only: bool = True) -> list[dict[str, Any]]:
    path = "/courses?pageSize=100"
    if active_only:
        path += "&courseStates=ACTIVE"
    out: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        full = path + (f"&pageToken={next_token}" if next_token else "")
        resp = api("GET", full)
        out.extend(resp.get("courses", []))
        next_token = resp.get("nextPageToken")
        if not next_token:
            break
    return out


def list_coursework(course_id: str) -> list[dict[str, Any]]:
    path = f"/courses/{course_id}/courseWork?pageSize=100"
    out: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        full = path + (f"&pageToken={next_token}" if next_token else "")
        resp = api("GET", full)
        out.extend(resp.get("courseWork", []))
        next_token = resp.get("nextPageToken")
        if not next_token:
            break
    return out


def list_submissions(course_id: str, coursework_id: str, user_id: str = "me") -> list[dict[str, Any]]:
    path = f"/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions?userId={user_id}&pageSize=20"
    resp = api("GET", path)
    return resp.get("studentSubmissions", [])


def get_my_submission(course_id: str, coursework_id: str) -> dict[str, Any]:
    subs = list_submissions(course_id, coursework_id, "me")
    if not subs:
        raise NotFoundError(
            f"No student submission found for course={course_id} coursework={coursework_id}. "
            "Are you enrolled in this course? Is the assignment currently assigned to you?"
        )
    return subs[0]


def attach_drive_file(course_id: str, coursework_id: str, submission_id: str, drive_file_id: str) -> dict[str, Any]:
    path = f"/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions/{submission_id}:modifyAttachments"
    body = {"addAttachments": [{"driveFile": {"id": drive_file_id}}]}
    return api("POST", path, body)


def turn_in_submission(course_id: str, coursework_id: str, submission_id: str) -> dict[str, Any]:
    path = f"/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions/{submission_id}:turnIn"
    return api("POST", path, {})


def submit(course_id: str, coursework_id: str, drive_file_id: str) -> dict[str, Any]:
    submission = get_my_submission(course_id, coursework_id)
    sub_id = submission["id"]
    state = submission.get("state", "")
    if state == "TURNED_IN":
        raise APIError("Submission is already TURNED_IN", status=409)
    attach_drive_file(course_id, coursework_id, sub_id, drive_file_id)
    result = turn_in_submission(course_id, coursework_id, sub_id)
    return {
        "submission_id": sub_id,
        "course_id": course_id,
        "coursework_id": coursework_id,
        "drive_file_id": drive_file_id,
        "state": "TURNED_IN",
        "api_response": result,
    }


def find_coursework(query: str) -> list[dict[str, Any]]:
    """Search all active courses for coursework whose title contains `query` (case-insensitive)."""
    query_lc = query.lower()
    out: list[dict[str, Any]] = []
    for course in list_courses(active_only=True):
        try:
            items = list_coursework(course["id"])
        except APIError:
            continue
        for cw in items:
            title = (cw.get("title") or "").lower()
            desc = (cw.get("description") or "").lower()
            if query_lc in title or query_lc in desc:
                out.append(
                    {
                        "course_id": course["id"],
                        "course_name": course.get("name", ""),
                        "coursework_id": cw["id"],
                        "title": cw.get("title", ""),
                        "due_date": cw.get("dueDate"),
                        "due_time": cw.get("dueTime"),
                        "state": cw.get("state"),
                        "alternate_link": cw.get("alternateLink"),
                        "work_type": cw.get("workType"),
                    }
                )
    return out


# ---------------------------------------------------------------------------
# Rclone helpers (for submit-file one-shot)
# ---------------------------------------------------------------------------


def rclone_available() -> bool:
    try:
        subprocess.run(["rclone", "version"], capture_output=True, check=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def rclone_lsjson(remote: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["rclone", "lsjson", "--original", remote],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def rclone_copy_to_remote(local_path: str, remote: str) -> None:
    subprocess.run(
        ["rclone", "copy", local_path, remote],
        check=True,
        timeout=300,
    )


def upload_via_rclone(file_path: str, remote: str | None = None) -> tuple[str, str]:
    """Upload `file_path` to `remote` and return (drive_file_id, file_name).

    Prefers the local FUSE mount if available (faster, no rclone copy),
    falls back to `rclone copy`.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    remote = remote or rclone_remote()
    basename = os.path.basename(file_path)

    mount = rclone_mount()
    if os.path.isdir(mount):
        # Mount is available — use plain cp
        dest = os.path.join(mount, basename)
        import shutil

        shutil.copy2(file_path, dest)
    else:
        if not rclone_available():
            raise RuntimeError(
                f"rclone mount not found at {mount} and rclone CLI not in PATH. "
                "Configure CLASSROOM_SUBMIT_RCLONE_MOUNT or install rclone."
            )
        rclone_copy_to_remote(file_path, remote)

    # Poll for Drive sync (up to 20s)
    deadline = time.time() + 20
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            files = rclone_lsjson(remote)
            for f in files:
                if f.get("Name") == basename and f.get("ID"):
                    return f["ID"], basename
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(2)
    if last_err:
        raise RuntimeError(f"Could not find file in Drive after upload: {last_err}")
    raise RuntimeError(f"File '{basename}' not visible in {remote} after 20s")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_auth(args: argparse.Namespace) -> int:
    try:
        tokens = do_oauth_flow()
        print(f"✓ Tokens saved to {tokens_path()}")
        print(f"  Access token expires at epoch {tokens['expiry_epoch']}")
        print(f"  Scopes granted: {tokens.get('scope', '(unknown)')}")
        # Sanity check
        info = whoami()
        print(f"  Authenticated as: {info.get('email', '(no email)')}")
        return 0
    except SetupError as e:
        die(str(e), code=2)
        return 2


def cmd_whoami(args: argparse.Namespace) -> int:
    info = whoami()
    print_json(info)
    return 0


def cmd_courses(args: argparse.Namespace) -> int:
    courses = list_courses(active_only=not args.all)
    if args.terse:
        for c in courses:
            print(f"{c['id']}\t{c.get('name', '')}")
    else:
        print_json(courses)
    return 0


def cmd_assignments(args: argparse.Namespace) -> int:
    items = list_coursework(args.course_id)
    if args.terse:
        for c in items:
            due = c.get("dueDate") or {}
            due_str = f"{due.get('year', '?'):04d}-{due.get('month', '?'):02d}-{due.get('day', '?'):02d}" if due else ""
            print(f"{c['id']}\t{due_str}\t{c.get('title', '')}")
    else:
        print_json(items)
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    matches = find_coursework(args.query)
    if not matches:
        die(f"No coursework found matching '{args.query}'", code=4)
    if args.terse:
        for m in matches:
            due = m.get("due_date") or {}
            due_str = (
                f"{due.get('year', '?'):04d}-{due.get('month', '?'):02d}-{due.get('day', '?'):02d}"
                if due
                else "     no due"
            )
            print(f"{m['course_id']}\t{m['coursework_id']}\t{due_str}\t{m['course_name'][:30]:30s}\t{m['title']}")
    else:
        print_json(matches)
    return 0


def cmd_submission(args: argparse.Namespace) -> int:
    sub = get_my_submission(args.course_id, args.coursework_id)
    print_json(sub)
    return 0


def cmd_attach(args: argparse.Namespace) -> int:
    sub = get_my_submission(args.course_id, args.coursework_id)
    result = attach_drive_file(args.course_id, args.coursework_id, sub["id"], args.drive_file_id)
    print_json({"submission_id": sub["id"], "result": result})
    return 0


def cmd_turn_in(args: argparse.Namespace) -> int:
    sub = get_my_submission(args.course_id, args.coursework_id)
    if sub.get("state") == "TURNED_IN":
        print_json({"submission_id": sub["id"], "state": "TURNED_IN", "note": "already turned in"})
        return 5
    result = turn_in_submission(args.course_id, args.coursework_id, sub["id"])
    print_json({"submission_id": sub["id"], "state": "TURNED_IN", "api_response": result})
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    result = submit(args.course_id, args.coursework_id, args.drive_file_id)
    print_json(result)
    return 0


def _resolve_assignment(query: str | None, course_id: str | None, coursework_id: str | None) -> tuple[str, str, str]:
    """Return (course_id, coursework_id, title)."""
    if course_id and coursework_id:
        return course_id, coursework_id, ""
    if not query:
        raise ValueError("Either --query or both --course and --coursework are required")
    matches = find_coursework(query)
    if not matches:
        raise NotFoundError(f"No coursework matching '{query}'")
    if len(matches) > 1:
        titles = [f"  - {m['title']} (course: {m['course_name']})" for m in matches]
        raise ValueError(f"Query '{query}' matched {len(matches)} assignments. Refine:\n" + "\n".join(titles))
    m = matches[0]
    return m["course_id"], m["coursework_id"], m["title"]


def cmd_submit_file(args: argparse.Namespace) -> int:
    file_path = os.path.abspath(args.file)
    if not os.path.exists(file_path):
        die(f"File not found: {file_path}", code=1)

    try:
        course_id, coursework_id, title = _resolve_assignment(args.query, args.course, args.coursework)
    except (NotFoundError, ValueError) as e:
        die(str(e), code=4)
        return 4

    if args.dry_run:
        print_json(
            {
                "dry_run": True,
                "file": file_path,
                "course_id": course_id,
                "coursework_id": coursework_id,
                "title": title,
                "rclone_remote": rclone_remote(),
            }
        )
        return 0

    print(f"→ Uploading {os.path.basename(file_path)} to {rclone_remote()}…", file=sys.stderr)
    drive_id, basename = upload_via_rclone(file_path, rclone_remote())
    print(f"  ✓ Drive file ID: {drive_id}", file=sys.stderr)

    if args.attach_only:
        sub = get_my_submission(course_id, coursework_id)
        result = attach_drive_file(course_id, coursework_id, sub["id"], drive_id)
        print_json(
            {
                "action": "attach",
                "file": basename,
                "drive_file_id": drive_id,
                "course_id": course_id,
                "coursework_id": coursework_id,
                "title": title,
                "submission_id": sub["id"],
                "result": result,
            }
        )
        return 0

    print(f"→ Attaching + turning in submission for: {title or coursework_id}", file=sys.stderr)
    result = submit(course_id, coursework_id, drive_id)
    result["title"] = title
    result["file"] = basename
    print_json(result)
    print(f"✓ Submitted {basename} → {title or coursework_id}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="classroom",
        description="Google Classroom autonomous submission CLI (stdlib-only).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="One-time OAuth setup (opens browser)")
    sub.add_parser("whoami", help="Print current user profile")

    p_courses = sub.add_parser("courses", help="List enrolled courses")
    p_courses.add_argument("--all", action="store_true", help="Include archived/non-active courses")
    p_courses.add_argument("--terse", action="store_true", help="ID<TAB>name plain format")

    p_assign = sub.add_parser("assignments", help="List coursework in a course")
    p_assign.add_argument("course_id")
    p_assign.add_argument("--terse", action="store_true")

    p_find = sub.add_parser("find", help="Search all active courses for coursework matching query")
    p_find.add_argument("query")
    p_find.add_argument("--terse", action="store_true")

    p_subm = sub.add_parser("submission", help="Get my submission for a coursework")
    p_subm.add_argument("course_id")
    p_subm.add_argument("coursework_id")

    p_attach = sub.add_parser("attach", help="Attach a Drive file (does NOT turn in)")
    p_attach.add_argument("course_id")
    p_attach.add_argument("coursework_id")
    p_attach.add_argument("drive_file_id")

    p_turn = sub.add_parser("turn-in", help="Turn in my submission")
    p_turn.add_argument("course_id")
    p_turn.add_argument("coursework_id")

    p_submit = sub.add_parser("submit", help="Attach Drive file + turn in (atomic)")
    p_submit.add_argument("course_id")
    p_submit.add_argument("coursework_id")
    p_submit.add_argument("drive_file_id")

    p_sf = sub.add_parser(
        "submit-file",
        help="Upload local file to Drive via rclone, find assignment, attach, turn in.",
    )
    p_sf.add_argument("file", help="Path to local file to submit")
    p_sf.add_argument("--query", "-q", help="Search coursework by title substring")
    p_sf.add_argument("--course", help="Course ID (skip search)")
    p_sf.add_argument("--coursework", help="Coursework ID (skip search)")
    p_sf.add_argument("--attach-only", action="store_true", help="Attach but don't turn in")
    p_sf.add_argument("--dry-run", action="store_true", help="Resolve assignment but don't upload or submit")

    return p


COMMANDS = {
    "auth": cmd_auth,
    "whoami": cmd_whoami,
    "courses": cmd_courses,
    "assignments": cmd_assignments,
    "find": cmd_find,
    "submission": cmd_submission,
    "attach": cmd_attach,
    "turn-in": cmd_turn_in,
    "submit": cmd_submit,
    "submit-file": cmd_submit_file,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = COMMANDS[args.command]
    try:
        return handler(args) or 0
    except SetupError as e:
        die(str(e), code=2)
        return 2
    except NotFoundError as e:
        die(str(e), code=4)
        return 4
    except APIError as e:
        msg = str(e)
        if e.body:
            msg += f"\nBody: {e.body[:500]}"
        die(msg, code=3)
        return 3
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
