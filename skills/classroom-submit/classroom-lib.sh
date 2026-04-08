#!/usr/bin/env bash
# classroom-lib.sh — thin CLI wrapper around classroom.py
#
# Provides a subcommand interface for the Google Classroom autonomous
# submission tool. All heavy lifting happens in classroom.py (pure Python
# stdlib, no dependencies). This script exists so that:
#
#   1. Claude Code skills can shell out to a plain executable without
#      worrying about which python is on PATH.
#   2. Shell-first users can source a consistent API:
#        source classroom-lib.sh
#        classroom_submit_file /path/to/file.pdf "Airbnb"
#   3. The plugin's slash commands can `${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh <cmd>`.
#
# Conventions (match claude-mac-chrome):
#   - shellcheck + shfmt clean
#   - stable exit codes matching classroom.py
#   - no hardcoded user paths outside defaults
#
# Usage:
#   classroom-lib.sh auth
#   classroom-lib.sh whoami
#   classroom-lib.sh courses [--terse]
#   classroom-lib.sh assignments <course_id> [--terse]
#   classroom-lib.sh find <query> [--terse]
#   classroom-lib.sh submission <course_id> <coursework_id>
#   classroom-lib.sh attach <course_id> <coursework_id> <drive_file_id>
#   classroom-lib.sh turn-in <course_id> <coursework_id>
#   classroom-lib.sh submit <course_id> <coursework_id> <drive_file_id>
#   classroom-lib.sh submit-file <path> [--query <q>] [--course <id>] [--coursework <id>] [--attach-only] [--dry-run]
#   classroom-lib.sh config-dir
#   classroom-lib.sh help

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_classroom_lib_dir() {
	local source="${BASH_SOURCE[0]}"
	while [[ -L "$source" ]]; do
		local dir
		dir="$(cd -P "$(dirname "$source")" && pwd)"
		source="$(readlink "$source")"
		[[ $source != /* ]] && source="$dir/$source"
	done
	cd -P "$(dirname "$source")" && pwd
}

CLASSROOM_LIB_DIR="$(_classroom_lib_dir)"
CLASSROOM_PY="${CLASSROOM_LIB_DIR}/classroom.py"

# ---------------------------------------------------------------------------
# Python discovery
# ---------------------------------------------------------------------------

_find_python() {
	if [[ -n "${CLASSROOM_SUBMIT_PYTHON:-}" ]] && command -v "$CLASSROOM_SUBMIT_PYTHON" >/dev/null 2>&1; then
		printf '%s\n' "$CLASSROOM_SUBMIT_PYTHON"
		return 0
	fi
	for candidate in python3 python; do
		if command -v "$candidate" >/dev/null 2>&1; then
			printf '%s\n' "$candidate"
			return 0
		fi
	done
	echo "error: no python3 found in PATH (override with CLASSROOM_SUBMIT_PYTHON)" >&2
	return 2
}

_run_py() {
	local py
	py="$(_find_python)"
	"$py" "$CLASSROOM_PY" "$@"
}

# ---------------------------------------------------------------------------
# Public API (sourced or called as subcommands)
# ---------------------------------------------------------------------------

classroom_auth() { _run_py auth "$@"; }
classroom_whoami() { _run_py whoami "$@"; }
classroom_courses() { _run_py courses "$@"; }
classroom_assignments() { _run_py assignments "$@"; }
classroom_find() { _run_py find "$@"; }
classroom_submission() { _run_py submission "$@"; }
classroom_attach() { _run_py attach "$@"; }
classroom_turn_in() { _run_py turn-in "$@"; }
classroom_submit() { _run_py submit "$@"; }
classroom_submit_file() { _run_py submit-file "$@"; }

# Convenience: resolve a one-argument invocation (file path + search query)
# to the one-shot submit-file call.
#
# Usage: classroom_submit_from_path /path/to/file.pdf "Airbnb"
classroom_submit_from_path() {
	local file="$1"
	local query="$2"
	_run_py submit-file "$file" --query "$query"
}

classroom_config_dir() {
	# Respect CLASSROOM_SUBMIT_CONFIG_DIR override, else XDG default.
	if [[ -n "${CLASSROOM_SUBMIT_CONFIG_DIR:-}" ]]; then
		printf '%s\n' "$CLASSROOM_SUBMIT_CONFIG_DIR"
	else
		printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/claude-classroom-submit"
	fi
}

classroom_help() {
	cat <<'HELP'
classroom-lib.sh — Google Classroom autonomous submission CLI

Setup (one-time):
  1. Create a Google Cloud project and enable the Classroom API
  2. Create an OAuth 2.0 Client ID (type: Desktop app)
  3. Download the JSON → ~/.config/claude-classroom-submit/credentials.json
  4. Run:  classroom-lib.sh auth
  See docs/google-cloud-setup.md for the full walkthrough.

Common workflows:

  # Verify setup
  classroom-lib.sh whoami

  # Find the assignment you want to submit to
  classroom-lib.sh find "Airbnb" --terse

  # One-shot submit: upload to Drive via rclone, find assignment, attach, turn in
  classroom-lib.sh submit-file ~/Desktop/atividade.pdf --query "Airbnb"

  # Step-by-step (you already have the Drive file ID)
  classroom-lib.sh attach <course_id> <coursework_id> <drive_file_id>
  classroom-lib.sh turn-in <course_id> <coursework_id>

Exit codes:
  0  success           3  API error
  1  generic error     4  not found
  2  setup required    5  already turned in
HELP
}

# ---------------------------------------------------------------------------
# Subcommand dispatch (only when executed, not sourced)
# ---------------------------------------------------------------------------

if [[ "${BASH_SOURCE[0]}" == "${0:-}" ]]; then
	if [[ $# -eq 0 ]]; then
		classroom_help
		exit 0
	fi

	cmd="$1"
	shift || true

	case "$cmd" in
		auth) classroom_auth "$@" ;;
		whoami) classroom_whoami "$@" ;;
		courses) classroom_courses "$@" ;;
		assignments) classroom_assignments "$@" ;;
		find) classroom_find "$@" ;;
		submission) classroom_submission "$@" ;;
		attach) classroom_attach "$@" ;;
		turn-in | turnin) classroom_turn_in "$@" ;;
		submit) classroom_submit "$@" ;;
		submit-file | submit_file) classroom_submit_file "$@" ;;
		config-dir) classroom_config_dir ;;
		help | -h | --help) classroom_help ;;
		*)
			echo "error: unknown command '$cmd'" >&2
			echo >&2
			classroom_help >&2
			exit 1
			;;
	esac
fi
