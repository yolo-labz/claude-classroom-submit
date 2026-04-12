# CLAUDE.md

Guidance for Claude Code sessions working on `claude-classroom-submit`. Drop-in context so a fresh Claude can pick up without re-reading the whole repository. Last updated 2026-04-08.

## What this is

A published (or soon-to-be) Claude Code plugin that autonomously submits files to Google Classroom assignments by going **straight to the Classroom REST API** instead of scripting the Drive Picker iframe (which is cross-origin to `classroom.google.com` and therefore unreachable from parent-page JavaScript).

- **Repo:** https://github.com/yolo-labz/claude-classroom-submit
- **Org:** `yolo-labz` (Pedro's GitHub org — note the **Z**, matching `claude-mac-chrome`)
- **Working dir:** `~/Documents/Code/Apple/claude-classroom-submit`
- **Current version:** v0.1.0 (pre-release)
- **Sibling plugin:** [claude-mac-chrome](https://github.com/yolo-labz/claude-mac-chrome) — used together for complete Classroom automation (chrome-mac-chrome drives the browser reliably across profiles, classroom-submit finishes the submission without touching the picker)

## Why it exists

The Google Classroom web submission flow is fundamentally unscriptable by browser automation on macOS because:

1. The **Drive Picker is a cross-origin iframe** at `drive.google.com/picker` — parent JS cannot reach into it (Same-Origin Policy).
2. Classroom's parent DOM enforces **Trusted Types**, so `innerHTML` / `execCommand('insertHTML')` injection is blocked.
3. AppleScript mouse `click at {x, y}` requires **Accessibility permission** granted to `osascript`, which is not granted by default and most users don't want to grant.
4. Synthetic `DragEvent`s are ignored by Drive's drop handler because `event.isTrusted === false`.
5. Classroom's `batchexecute` RPC IDs live in lazy-loaded JS bundles that rotate across deploys, so reverse-engineering the internal API is not stable.

The only stable path is the public Classroom REST API with an OAuth 2.0 bearer token. That's what this plugin does.

## Architecture in one paragraph

A single `classroom.py` (pure Python 3 stdlib — no `requests`, no `google-auth`, no `google-api-python-client`) implements the full OAuth 2.0 Installed App flow with a loopback redirect, caches the refresh token under `~/.config/claude-classroom-submit/tokens.json` (mode `0600`), and exposes a subcommand CLI (`auth`, `whoami`, `courses`, `assignments`, `find`, `submission`, `attach`, `turn-in`, `submit`, `submit-file`). A thin `classroom-lib.sh` wraps it for shell / Claude Code skill invocation. Three slash commands (`/classroom-auth`, `/classroom-find`, `/classroom-submit`) expose the common flows inside Claude Code. The `submit-file` command chains: rclone copy → `rclone lsjson --original` → find assignment → `modifyAttachments` → `turnIn`, atomically.

## Repository layout

```
claude-classroom-submit/
├── .claude-plugin/
│   └── plugin.json             # Claude Code plugin manifest
├── .gitignore
├── CHANGELOG.md
├── CLAUDE.md                   # this file
├── LICENSE                     # MIT
├── README.md
├── commands/                   # Slash commands (Claude Code)
│   ├── classroom-auth.md
│   ├── classroom-find.md
│   └── classroom-submit.md
├── docs/
│   └── google-cloud-setup.md   # One-time OAuth client setup walkthrough
├── scripts/
│   └── lint.sh                 # shellcheck + shfmt + python syntax + smoke test
└── skills/
    └── classroom-submit/
        ├── SKILL.md            # Skill definition (Claude reads this to auto-trigger)
        ├── classroom-lib.sh    # Bash CLI wrapper (shellcheck + shfmt clean)
        └── classroom.py        # All the logic — stdlib Python only
```

## Common commands

```bash
# Lint everything (shellcheck + shfmt + python -m py_compile + smoke test)
./scripts/lint.sh

# Run the CLI directly without going through the plugin system
./skills/classroom-submit/classroom-lib.sh whoami
./skills/classroom-submit/classroom-lib.sh courses --terse
./skills/classroom-submit/classroom-lib.sh find "Airbnb" --terse

# Submit a file (end-to-end)
./skills/classroom-submit/classroom-lib.sh submit-file ~/file.pdf --query "Airbnb"

# Inside Claude Code (plugin installed)
/claude-classroom-submit:classroom-auth
/claude-classroom-submit:classroom-find Airbnb
/claude-classroom-submit:classroom-submit ~/file.pdf Airbnb
```

There are no unit tests. `scripts/lint.sh`'s smoke test (calling `classroom-lib.sh help` and `python3 -m py_compile classroom.py`) is the contract. `shellcheck`, `shfmt`, and Python's own syntax checker must stay clean.

## Trust model

- The plugin talks to `googleapis.com` and `oauth2.googleapis.com` only. No telemetry, no central backend, no shared secrets.
- The OAuth client is created in *the user's own* Google Cloud project. The plugin ships without any credentials. A user who wants to use it runs through the setup once (~5 min), downloads their own `credentials.json`, and all tokens are tied to their own client.
- Refresh tokens live at `~/.config/claude-classroom-submit/tokens.json` with mode `0600`. Never leaves the machine.
- Scopes are intentionally minimal: `classroom.courses.readonly` + `classroom.coursework.me` (write to own submissions only). The plugin cannot touch other students' data, cannot grade, cannot comment, cannot send emails.

## Conventions

- **Shell style:** match `claude-mac-chrome`. `set -euo pipefail` at the top, function names prefixed `classroom_`, stable exit codes documented in README + SKILL, shellcheck + shfmt clean with no disables.
- **Python style:** stdlib only, type-hint public APIs, no decorators beyond stdlib, single file for the CLI, explicit error codes. Avoid cleverness — this has to be readable by someone debugging at 11 pm before a deadline.
- **Error messages:** actionable. Say what went wrong, say what to do about it. "Run `classroom auth` first" beats "Unauthorized".
- **Documentation:** SKILL.md is the canonical source for how to use the plugin from Claude Code; README is the canonical source for humans; docs/google-cloud-setup.md is the canonical source for one-time setup. Keep them in sync when adding commands.

## Extension roadmap (open questions)

- **Multi-file attach:** currently `submit-file` handles one file per call. Adding a `--files file1 file2 file3` flag would batch the upload + single `modifyAttachments` call.
- **Short-form link attachments:** Classroom supports link-only attachments via `modifyAttachments` with `{"addAttachments": [{"link": {"url": "..."}}]}`. Would let us submit a Drive preview URL without a file upload.
- **Discord / Slack notifications on successful submission** — probably not, keeps the plugin focused.
- **Teacher-side scopes:** no. This plugin is explicitly student-only. A separate sister plugin would be the right shape.
- **Token storage via the macOS Keychain instead of plaintext JSON:** worth considering for v0.2. `security add-generic-password` is the path, but it adds a shell-out that breaks the stdlib-only promise on Linux. Defer.

## Known failure modes

- **First run after 7 days of idle on an unpublished OAuth client:** refresh token expires, user sees `invalid_grant`. Fix: re-run `classroom-lib.sh auth`. Workaround: publish the OAuth consent screen.
- **Credentials JSON missing or wrong format:** the CLI distinguishes "file not found" from "missing client_id" and prints the right remediation. Test both paths before shipping.
- **Picker iframe tab left open in Chrome from prior automation attempts:** irrelevant — the plugin doesn't touch Chrome. But if the user is confused why nothing is happening visually, tell them this plugin never opens a browser.
- **Rclone mount stale after Chrome restart:** rclone's VFS cache can lag 5-15s on first write. The Python `upload_via_rclone` helper polls `rclone lsjson` for up to 20s before giving up.

## Release engineering — shared standards

Release-engineering standards are shared across all self-coded yolo-labz Claude Code
plugins. The canonical source of truth lives in the NixOS config repo:

- **Research:** `~/NixOS/meta/yolo-labz-release-engineering-research.md`
- **Rollout plan:** `~/NixOS/meta/yolo-labz-release-engineering-plan.md`
- **Enforced rule:** `plugin-release-engineering` in `~/NixOS/modules/home/claude-code.nix`
  — loaded globally into every Claude Code session via home-manager.

**Current state:** v0.1.0 unsigned tag, no CI, no `.github/` directory. Greenfield for
supply-chain work.

**Phase 2 rollout (see plan §6.3):**

1. Bootstrap `.github/` from scratch. Target files: `workflows/{ci,release,codeql,osv-scan,scorecard,sonar,reproducibility,shellcheck}.yml`, `dependabot.yml`, `scorecard-config.yml`, `actions-lock.md`.
2. Add `SECURITY.md`, `CODEOWNERS`, `CONTRIBUTING.md`. Enable Private Vulnerability Reporting.
3. Enable branch protection via Repository Ruleset from scratch (currently unprotected).
4. `pyproject.toml` with `hatchling` backend, `requires-python = ">=3.11"`, semver in both `plugin.json` and `pyproject.toml` — keep them locked.
5. Set up **PyPI Trusted Publishing** via `pypa/gh-action-pypi-publish@release/v1`. Configure pending publisher on PyPI first (manual step, not automatable).
6. Publish to PyPI anyway despite being zero-dep — trusted publishing + PEP 740 attestations are free benefits, and `uvx claude-classroom-submit` / `pipx install` becomes the user install path.
7. Re-cut as **`v0.1.1`** signed. **Do NOT re-tag v0.1.0** — `slsa-verifier` validates against the commit SHA at signing time, and re-tagging produces stale provenance.

**Python stdlib-specific guidance:**

- Build via `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) PYTHONHASHSEED=0 uv build`.
- CycloneDX + SPDX SBOMs will be minimal (one component — the package itself) but still meaningful: they cryptographically prove the zero-dep claim.
- OSV-Scanner will be a no-op pass (nothing to scan).
- `ruff` replaces flake8/black/isort; `pyright` over mypy. Install via `uvx`, not a dev dep.
- CodeQL Python uses `build-mode: none` with `security-extended` query suite.
- **CodeQL misses taint through `subprocess` shell-outs** — add a Semgrep rule for the `upload_via_rclone` helper: `python.lang.security.audit.dangerous-subprocess-use`. The argv list pattern is already correct; Semgrep enforces it going forward.
- `SECURITY.md` points at `/security/advisories/new` (GitHub Private Vulnerability Reporting). No PGP.

**Invariants:**

1. Never re-tag a release.
2. Never add a non-stdlib Python dep — the "stdlib-only" promise is load-bearing for trust, audit, and zero-install-friction. If a future feature needs a dep, it's a separate plugin.
3. OAuth `credentials.json` and `tokens.json` are user-private — never committed, never logged. The `.gitignore` rule must stay.
4. `shell=False` / argv-list for every `subprocess` call — never build shell strings from user input. `scripts/lint.sh` enforces via a grep.
5. PyPI trusted publisher binding is fragile — renaming `release.yml` or changing the GitHub environment name breaks the identity match. Update the pending publisher config on PyPI before renaming.
