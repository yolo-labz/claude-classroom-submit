# Contributing to claude-classroom-submit

Thanks for your interest! This is a solo-maintained project, but contributions
are welcome.

## Dev setup

```bash
# Clone
git clone https://github.com/yolo-labz/claude-classroom-submit.git
cd claude-classroom-submit

# Lint everything (requires shellcheck + shfmt + python3)
./scripts/lint.sh

# Optional: install pre-commit hooks
pip install pre-commit
pre-commit install
```

No Python dependencies to install — the project uses stdlib only.

## Lint and type-check

```bash
# Shell linting
shellcheck -x -o all -e SC2250,SC2312,SC2310 scripts/*.sh skills/classroom-submit/*.sh
shfmt -d -i 0 -ci -bn scripts/*.sh skills/classroom-submit/*.sh

# Python linting + formatting
uvx ruff check skills/ scripts/
uvx ruff format --check skills/ scripts/

# Type checking
uvx pyright skills/classroom-submit/classroom.py

# All-in-one
./scripts/lint.sh
```

## PR workflow

1. Fork and create a feature branch from `main`.
2. Make your changes with conventional commit messages (`feat:`, `fix:`, `chore:`, etc.).
3. Ensure `scripts/lint.sh` passes.
4. Open a PR against `main`.
5. Wait for CI checks to pass (lint, typecheck, smoke, CodeQL).

## Key invariants

- **Zero external Python dependencies.** The stdlib-only promise is load-bearing
  for trust, audit, and zero-install-friction. If a feature needs a dep, it
  belongs in a separate plugin.
- **`shell=False` / argv-list for every `subprocess` call.** Never build shell
  strings from user input.
- **OAuth credentials and tokens are never committed or logged.**

## Code style

- **Python:** ruff with line-length=120, target py311. Type-hint public APIs.
- **Shell:** `set -euo pipefail`, function names prefixed `classroom_`, shellcheck
  + shfmt clean.
- **Commits:** conventional commits, subject line under 72 chars.
