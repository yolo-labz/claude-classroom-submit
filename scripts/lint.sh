#!/usr/bin/env bash
# lint.sh — shellcheck + shfmt + python syntax + smoke test for claude-classroom-submit
#
# Runs the following in order, failing fast on any issue:
#   1. shfmt -d on all shell scripts (formatting diff)
#   2. shellcheck on all shell scripts
#   3. python3 -m py_compile on classroom.py
#   4. Smoke test: classroom-lib.sh help (no setup needed, no API calls)
#
# If shfmt or shellcheck are missing, the script falls back to `nix run nixpkgs#<tool>`
# so Pedro's NixOS workstation can lint without polluting the global env.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# -----------------------------------------------------------------------------
# Tool discovery
# -----------------------------------------------------------------------------

_have() { command -v "$1" >/dev/null 2>&1; }

_run_shfmt() {
	if _have shfmt; then
		shfmt "$@"
	elif _have nix; then
		nix run nixpkgs#shfmt -- "$@"
	else
		echo "error: neither shfmt nor nix is available" >&2
		return 2
	fi
}

_run_shellcheck() {
	if _have shellcheck; then
		shellcheck "$@"
	elif _have nix; then
		nix run nixpkgs#shellcheck -- "$@"
	else
		echo "error: neither shellcheck nor nix is available" >&2
		return 2
	fi
}

_run_python() {
	if _have python3; then
		python3 "$@"
	elif _have python; then
		python "$@"
	else
		echo "error: no python3 in PATH" >&2
		return 2
	fi
}

# -----------------------------------------------------------------------------
# File discovery
# -----------------------------------------------------------------------------

mapfile -t SHELL_FILES < <(
	find . \
		\( -name ".git" -o -name "node_modules" -o -name "__pycache__" \) -prune -o \
		\( -name "*.sh" -o -name "*.bash" \) -type f -print \
		| sort
)

mapfile -t PY_FILES < <(
	find . \
		\( -name ".git" -o -name "__pycache__" -o -name "*.egg-info" \) -prune -o \
		-name "*.py" -type f -print \
		| sort
)

# -----------------------------------------------------------------------------
# Step 1: shfmt -d
# -----------------------------------------------------------------------------

printf '\n===[ shfmt -d ]===\n'
if [[ ${#SHELL_FILES[@]} -eq 0 ]]; then
	echo "  (no shell files)"
else
	_run_shfmt -d -i 0 -ci -bn "${SHELL_FILES[@]}"
	echo "  ✓ shfmt clean (${#SHELL_FILES[@]} files)"
fi

# -----------------------------------------------------------------------------
# Step 2: shellcheck
# -----------------------------------------------------------------------------

printf '\n===[ shellcheck ]===\n'
if [[ ${#SHELL_FILES[@]} -eq 0 ]]; then
	echo "  (no shell files)"
else
	_run_shellcheck -x -o all -e SC2250,SC2312,SC2310 "${SHELL_FILES[@]}"
	echo "  ✓ shellcheck clean (${#SHELL_FILES[@]} files)"
fi

# -----------------------------------------------------------------------------
# Step 3: python syntax
# -----------------------------------------------------------------------------

printf '\n===[ python -m py_compile ]===\n'
if [[ ${#PY_FILES[@]} -eq 0 ]]; then
	echo "  (no python files)"
else
	for f in "${PY_FILES[@]}"; do
		_run_python -m py_compile "$f"
	done
	echo "  ✓ python syntax clean (${#PY_FILES[@]} files)"
fi

# -----------------------------------------------------------------------------
# Step 4: smoke test
# -----------------------------------------------------------------------------

printf '\n===[ smoke test ]===\n'
LIB="$ROOT/skills/classroom-submit/classroom-lib.sh"
if [[ ! -x "$LIB" ]]; then
	chmod +x "$LIB"
fi

# `help` and `config-dir` don't require setup or network — safe smoke tests
"$LIB" help >/dev/null
"$LIB" config-dir >/dev/null
echo "  ✓ classroom-lib.sh responds to help + config-dir"

# `classroom.py --help` should also work without any setup
_run_python "$ROOT/skills/classroom-submit/classroom.py" --help >/dev/null
echo "  ✓ classroom.py --help parses OK"

printf '\n✅ All lint checks passed.\n'
