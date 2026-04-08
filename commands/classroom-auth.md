---
description: One-time OAuth 2.0 setup for Google Classroom. Opens a browser, asks Pedro to grant the `classroom.courses.readonly` + `classroom.coursework.me` scopes to the OAuth client whose `credentials.json` lives at `~/.config/claude-classroom-submit/credentials.json`, catches the redirect on localhost:8765, exchanges the code for an access+refresh token pair, and saves them to `~/.config/claude-classroom-submit/tokens.json`. Run this once; subsequent API calls auto-refresh the access token using the stored refresh token.
---

# /classroom-auth

Run the one-time Google OAuth consent flow for the classroom-submit plugin.

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/classroom-submit/classroom-lib.sh" auth
```

**Before running:** Confirm that `~/.config/claude-classroom-submit/credentials.json` exists. If not, walk the user through `docs/google-cloud-setup.md` first (create Google Cloud project → enable Classroom API → create Desktop OAuth client → download JSON → save as `credentials.json`).

**Expected flow:**

1. A browser tab opens to Google's consent screen
2. User picks the account they want to authenticate as (should be the same account enrolled in the target Classroom courses — e.g., `phsb@cin.ufpe.br` for UFPE students)
3. User clicks "Continue" / "Permitir" on the scope screen
4. Browser shows a plain HTML "✓ Authorization received" page served by the local callback server
5. Terminal prints `✓ Tokens saved to …/tokens.json` and the authenticated user's email

**If the browser doesn't open** (e.g., headless Claude Code session), the command prints the consent URL so the user can open it manually on any device logged into the same Google account, then paste the resulting redirect URL back.

**Common issues:**

- `credentials file not found` → run the Google Cloud setup first
- `OAuth error: access_denied` → user clicked "Cancel" on the consent screen, retry
- `port 8765 already in use` → another Python process is holding the port; set `CLASSROOM_SUBMIT_OAUTH_PORT=8766` and retry
- Opens consent screen in the wrong Google account → open a private/incognito window, paste the consent URL, and sign in with the correct account before granting
