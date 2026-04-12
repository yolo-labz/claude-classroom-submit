# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

Please use **GitHub Private Vulnerability Reporting**:
https://github.com/yolo-labz/claude-classroom-submit/security/advisories/new

Solo maintainer; best-effort SLA: acknowledge within 5 business days,
patch or mitigation within 30 days for High/Critical.

**Do NOT open public issues for vulnerabilities.**

## Supply Chain Verification

All releases are published via PyPI Trusted Publishing with PEP 740 digital
attestations and SLSA build provenance. Verify downloaded artifacts with:

```bash
gh attestation verify ./claude_classroom_submit-*.whl \
  --repo yolo-labz/claude-classroom-submit \
  --signer-workflow yolo-labz/claude-classroom-submit/.github/workflows/release.yml
```

## Trust Model

- **Zero external dependencies** — stdlib Python only. The CycloneDX SBOM
  shipped with each release cryptographically proves this claim.
- OAuth credentials and tokens are user-private (never committed, never logged).
- The plugin communicates only with `googleapis.com` and `oauth2.googleapis.com`.
  No telemetry, no central backend, no shared secrets.
