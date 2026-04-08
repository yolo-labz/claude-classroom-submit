#!/usr/bin/env bash
# setup-wizard.sh — guided Google Cloud OAuth setup for claude-classroom-submit
#
# Walks the user through the one-time manual steps that can't be automated
# (Google Cloud project creation + OAuth client download), then hands off to
# classroom-lib.sh auth for the fully automated rest of the flow.
#
# Each step:
#   1. Explains what to do in one sentence
#   2. Opens the relevant Google Cloud Console URL
#   3. Waits for the user to confirm (ENTER)
#   4. Validates state where possible before moving on
#
# Safe to re-run — idempotent. If credentials.json already exists, the wizard
# skips to the auth step. If tokens.json already exists and works, it short-
# circuits entirely and reports success.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/skills/classroom-submit/classroom-lib.sh"
CONFIG_DIR="${CLASSROOM_SUBMIT_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/claude-classroom-submit}"
CREDS="$CONFIG_DIR/credentials.json"
TOKENS="$CONFIG_DIR/tokens.json"

# Colors (only if stdout is a TTY)
if [[ -t 1 ]]; then
	BOLD=$'\033[1m'
	DIM=$'\033[2m'
	GREEN=$'\033[32m'
	YELLOW=$'\033[33m'
	BLUE=$'\033[34m'
	RESET=$'\033[0m'
else
	BOLD="" DIM="" GREEN="" YELLOW="" BLUE="" RESET=""
fi

_open_url() {
	local url="$1"
	if command -v open >/dev/null 2>&1; then
		open "$url"
	elif command -v xdg-open >/dev/null 2>&1; then
		xdg-open "$url"
	fi
	printf '%s  → %s%s\n' "$DIM" "$url" "$RESET"
}

_wait_enter() {
	printf '%s%s%s ' "$BLUE" "[press ENTER when done]" "$RESET"
	read -r _
}

_step() {
	printf '\n%s%s Step %s %s%s\n' "$BOLD" "$GREEN" "$1" "$2" "$RESET"
}

_info() {
	printf '%s  %s%s\n' "$DIM" "$1" "$RESET"
}

_warn() {
	printf '%s  ⚠ %s%s\n' "$YELLOW" "$1" "$RESET"
}

# ---------------------------------------------------------------------------
# Pre-flight: already done?
# ---------------------------------------------------------------------------

printf '%s=== claude-classroom-submit setup wizard ===%s\n' "$BOLD" "$RESET"
printf '\nConfig dir: %s\n' "$CONFIG_DIR"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR" 2>/dev/null || true

if [[ -f "$TOKENS" ]]; then
	if "$LIB" whoami >/dev/null 2>&1; then
		email=$("$LIB" whoami 2>/dev/null | grep -oE '"email"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | cut -d'"' -f4)
		printf '\n%s✓ Already authenticated as %s%s\n' "$GREEN" "${email:-(unknown)}" "$RESET"
		printf 'Run %s%s courses --terse%s to list your courses.\n' "$BOLD" "$LIB" "$RESET"
		exit 0
	fi
	_warn "tokens.json exists but auth check failed — continuing to re-auth"
fi

# ---------------------------------------------------------------------------
# Step 1 — Create Google Cloud project
# ---------------------------------------------------------------------------

if [[ ! -f "$CREDS" ]]; then
	_step 1 "Create (or select) a Google Cloud project"
	cat <<'TEXT'

  Opening Google Cloud Console project creator. Create a new project named
  "claude-classroom" (or any name), or pick an existing one. Make sure you are
  signed in with the SAME Google account you use for Google Classroom (e.g.
  your @cin.ufpe.br account, not a personal Gmail).
TEXT
	_open_url "https://console.cloud.google.com/projectcreate"
	_wait_enter

	# -----------------------------------------------------------------------
	# Step 2 — Enable Classroom API
	# -----------------------------------------------------------------------
	_step 2 "Enable the Google Classroom API"
	cat <<'TEXT'

  Opening the Classroom API enablement page. Verify the correct project is
  selected at the top, then click "Enable". Wait for the status to change to
  "API enabled".
TEXT
	_open_url "https://console.cloud.google.com/apis/library/classroom.googleapis.com"
	_wait_enter

	# -----------------------------------------------------------------------
	# Step 3 — Configure OAuth consent screen
	# -----------------------------------------------------------------------
	_step 3 "Configure the OAuth consent screen"
	cat <<'TEXT'

  Opening the OAuth consent screen configuration. Choose:

    - User type:            External
    - App name:             claude-classroom-submit
    - User support email:   your own email
    - Developer email:      your own email

  Then on the Scopes step, click "Add or Remove Scopes" and add all three:

    https://www.googleapis.com/auth/classroom.courses.readonly
    https://www.googleapis.com/auth/classroom.coursework.me
    https://www.googleapis.com/auth/userinfo.email

  On the Test Users step, add your own email (the one you'll authenticate
  as in step 5). Skip the verification and publishing sections.
TEXT
	_open_url "https://console.cloud.google.com/apis/credentials/consent"
	_wait_enter

	# -----------------------------------------------------------------------
	# Step 4 — Create the OAuth client ID
	# -----------------------------------------------------------------------
	_step 4 "Create the OAuth 2.0 Client ID (Desktop app)"
	cat <<'TEXT'

  Opening the credentials page. Click:

    + Create Credentials → OAuth client ID
    Application type:  Desktop app
    Name:              classroom-submit-cli

  When the "OAuth client created" dialog appears, click
  "DOWNLOAD JSON". Save the file anywhere — we'll move it in a moment.
TEXT
	_open_url "https://console.cloud.google.com/apis/credentials"
	printf '\n  %sWaiting for you to download the credentials JSON…%s\n' "$DIM" "$RESET"
	_wait_enter

	# -----------------------------------------------------------------------
	# Locate and install credentials.json
	# -----------------------------------------------------------------------
	_step 5 "Install the downloaded credentials file"
	printf '\n  Searching for client_secret*.json in %s/Downloads…\n' "$HOME"

	FOUND=""
	if [[ -d "$HOME/Downloads" ]]; then
		# Pick the most recent match
		mapfile -t matches < <(
			find "$HOME/Downloads" -maxdepth 1 -type f -name 'client_secret*.json' -print 2>/dev/null \
				| sort
		)
		if ((${#matches[@]} > 0)); then
			# Sort by mtime descending, pick newest
			FOUND=$(
				for m in "${matches[@]}"; do
					stat -f '%m %N' "$m" 2>/dev/null || stat -c '%Y %n' "$m" 2>/dev/null
				done | sort -rn | head -1 | cut -d' ' -f2-
			)
		fi
	fi

	if [[ -n "$FOUND" && -f "$FOUND" ]]; then
		printf '  %s✓%s Found: %s\n' "$GREEN" "$RESET" "$FOUND"
		printf '  Moving to %s\n' "$CREDS"
		mv "$FOUND" "$CREDS"
		chmod 600 "$CREDS"
	else
		printf '  %sCould not auto-detect credentials file.%s\n' "$YELLOW" "$RESET"
		printf '  Please enter the full path to the downloaded JSON file:\n  '
		read -r user_path
		user_path="${user_path/#\~/$HOME}"
		if [[ ! -f "$user_path" ]]; then
			printf '\n  %s✗%s File not found: %s\n' "$YELLOW" "$RESET" "$user_path" >&2
			exit 1
		fi
		cp "$user_path" "$CREDS"
		chmod 600 "$CREDS"
		printf '  %s✓%s Installed to %s\n' "$GREEN" "$RESET" "$CREDS"
	fi
fi

# ---------------------------------------------------------------------------
# Step 6 — Run the OAuth flow
# ---------------------------------------------------------------------------
_step 6 "Run the Google OAuth consent flow"
cat <<'TEXT'

  A browser tab will open to the Google consent screen. Pick the SAME
  Google account you added as a test user, grant the three scopes, and
  wait for the "✓ Authorization received" page.

  IMPORTANT: you will see a warning about "Google hasn't verified this app".
  That is expected — you are the developer. Click "Advanced" → "Go to
  claude-classroom-submit (unsafe)" → "Continue".

TEXT
_wait_enter

if "$LIB" auth; then
	printf '\n%s✓ Setup complete.%s\n' "$GREEN" "$RESET"
	printf 'Try: %s%s courses --terse%s\n' "$BOLD" "$LIB" "$RESET"
else
	printf '\n%s✗ Auth flow failed.%s See error above. You can re-run this wizard safely.\n' "$YELLOW" "$RESET" >&2
	exit 1
fi
