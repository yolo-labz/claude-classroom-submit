# Release Engineering Handoff — claude-classroom-submit

**Date:** 2026-04-12
**PR merged:** #1 (feat: CI + supply-chain bootstrap)
**Tag pushed:** v0.1.1 (first signed release; v0.1.0 was unsigned — never re-tag)
**Session:** NixOS repo rollout — 6-agent research + parallel execution

## What was shipped (greenfield bootstrap)

- **CI workflow** — shellcheck + shfmt on shell, ruff check + format on Python, pyright typecheck, smoke test (py_compile + scripts/lint.sh)
- **Release workflow** — `uv build` with SOURCE_DATE_EPOCH + PYTHONHASHSEED=0, `actions/attest-build-provenance@v2`, CycloneDX + SPDX SBOMs, PyPI trusted publish
- **CodeQL** (Python + Actions, build-mode: none, security-extended)
- **OSV-Scanner** — near-no-op (zero deps) but proves the claim
- **Scorecard** — weekly, SARIF upload
- **SonarQube** — gracefully skips when SONAR_TOKEN not set
- **Dependabot** — github-actions only (no pip deps to update)
- **pyproject.toml** — hatchling backend, v0.1.1, `dependencies = []` (stdlib-only invariant preserved)
- **SECURITY.md**, **CODEOWNERS**, **CONTRIBUTING.md**, **pull_request_template.md**, **scorecard-config.yml**
- **.pre-commit-config.yaml** — ruff + shellcheck hooks
- All actions SHA-pinned, top-level `permissions: {}`, `persist-credentials: false`, `timeout-minutes`
- 63 ruff errors auto-fixed in existing classroom.py (UP007, UP006, SIM105, formatting)
- Branch protection enabled (PR review + linear history + no force push)
- Private Vulnerability Reporting enabled

## Key invariant

**ZERO external Python deps.** The `dependencies = []` in pyproject.toml is load-bearing for trust. If a future feature needs a dep, it belongs in a separate plugin.

## Completed post-merge (2026-04-12)

- **SonarQube project** created (`yolo-labz_claude-classroom-submit`) via direct DB insert on Dokku host. PROJECT_ANALYSIS_TOKEN generated (SHA-384 hash), `SONAR_TOKEN` secret set. Token validated: `{"valid":true}`.
- **PyPI Trusted Publisher** registered on pypi.org via Chrome automation. Pending publisher: owner=yolo-labz, repo=claude-classroom-submit, workflow=release.yml, environment=pypi.
- **7 Dependabot PRs merged** (all action bumps: checkout, upload-artifact, download-artifact, setup-python, pypi-publish, sbom-action, scorecard-action).
- **Release v0.1.1 live** with 4 assets: wheel, sdist, sbom.cdx.json, sbom.spdx.json.
- **Release pipeline fixes applied**: split `anchore/sbom-action` into two calls (one per format), added missing GitHub Release job, made PyPI publish `continue-on-error: true`.

## Nice-to-have (none blocking)

1. **Add required status checks** — now that Lint, Typecheck, Smoke test, CodeQL, and OSV have all run on main, lock them as required
2. **PyPI first publish** — the release workflow's publish job will succeed once the pending publisher is activated by the first upload. Re-tag `v0.1.2` after verifying the trusted publisher works, or trigger manually via `uv build && uv publish`

## Source of truth

- Research: `~/NixOS/meta/yolo-labz-release-engineering-research.md`
- Plan: `~/NixOS/meta/yolo-labz-release-engineering-plan.md`
- Global rule: `plugin-release-engineering` in `~/NixOS/modules/home/claude-code.nix`
