# Google Cloud OAuth setup (one-time, ~5 minutes)

The `claude-classroom-submit` plugin talks directly to the Google Classroom REST API, which requires an OAuth 2.0 client. Because the plugin ships as open source without a shared backend, every user creates their own OAuth client in their own Google Cloud project. This keeps your refresh token scoped to a client *you* control, and means there is no central credential that Google can revoke on everyone at once.

The whole process is free, stays inside the Google Cloud free tier forever, and has to be done exactly once per machine.

---

## Step 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/projectcreate>
2. Sign in with the **same Google account you use for Classroom** (e.g., `phsb@cin.ufpe.br` for UFPE students, not a personal Gmail).
3. Project name: anything memorable — `claude-classroom` is fine. Leave the organization as "No organization" unless your institution forces a specific one.
4. Click **Create**. Wait ~10 seconds for the project to provision.
5. Make sure the project selector at the top-left of the console shows your new project.

## Step 2. Enable the Classroom API

1. Go to <https://console.cloud.google.com/apis/library/classroom.googleapis.com>
2. Verify the correct project is selected at the top.
3. Click **Enable**. Wait a few seconds until the status changes to "API enabled".

You do **not** need to enable the Drive API — the plugin uses rclone for uploads and never calls the Drive REST API directly.

## Step 3. Configure the OAuth consent screen

Before you can create an OAuth client, Google makes you fill out the consent screen.

1. Go to <https://console.cloud.google.com/apis/credentials/consent>
2. User type: **External** (unless your university/employer gave you a Google Workspace with internal-only access). Click **Create**.
3. App information:
   - **App name:** `claude-classroom-submit` (or anything — only you will see this)
   - **User support email:** your own email
   - **Developer contact information:** your own email
4. Click **Save and Continue**.
5. Scopes: click **Add or Remove Scopes**, then manually add (paste in the filter box):
   - `https://www.googleapis.com/auth/classroom.courses.readonly`
   - `https://www.googleapis.com/auth/classroom.coursework.me`
   - `https://www.googleapis.com/auth/userinfo.email`
   Tick all three and click **Update**, then **Save and Continue**.
6. Test users: click **Add Users**, paste the email of the Google account you use for Classroom (the same one from step 1). Click **Add**, then **Save and Continue**.
7. Summary: click **Back to Dashboard**.

> **Note on "Test users":** Until you publish the OAuth app (which requires a Google review for apps requesting sensitive scopes), only the test-user emails you added here can sign in. For personal use, just add your own email and ignore the publishing flow.

## Step 4. Create the OAuth 2.0 Client ID

1. Go to <https://console.cloud.google.com/apis/credentials>
2. Click **+ Create Credentials** → **OAuth client ID**.
3. Application type: **Desktop app**.
4. Name: `classroom-submit-cli` (any name).
5. Click **Create**.
6. A dialog appears with your Client ID and Client Secret. Click **Download JSON** — this is the file the plugin needs.
7. Save the downloaded file to:
   ```
   ~/.config/claude-classroom-submit/credentials.json
   ```
   Create the parent directory if it doesn't exist:
   ```bash
   mkdir -p ~/.config/claude-classroom-submit
   mv ~/Downloads/client_secret_*.json ~/.config/claude-classroom-submit/credentials.json
   chmod 600 ~/.config/claude-classroom-submit/credentials.json
   ```

## Step 5. Run the auth flow

From a terminal on the same machine:

```bash
~/Documents/Code/Apple/claude-classroom-submit/skills/classroom-submit/classroom-lib.sh auth
```

Or, if the plugin is installed in Claude Code:

```
/claude-classroom-submit:classroom-auth
```

The command will:

1. Open your default browser to the Google consent screen.
2. Ask you to pick a Google account — **pick the account you added as a test user in step 3**.
3. Show a warning banner about "Google hasn't verified this app" — this is expected for apps in "Testing" state. Click **Advanced** → **Go to claude-classroom-submit (unsafe)** → **Continue**. You are the developer of this app and you trust it.
4. Show the scope consent screen listing the three scopes from step 3. Click **Continue**.
5. Redirect your browser to `http://localhost:8765/?code=...` which the plugin's loopback server catches.
6. The browser tab shows "✓ Authorization received".
7. The terminal prints:
   ```
   ✓ Tokens saved to /Users/you/.config/claude-classroom-submit/tokens.json
     Authenticated as: your.email@cin.ufpe.br
   ```

You are done. The plugin now has a refresh token that will keep working indefinitely (typically 6+ months between re-auths, longer once you publish the app).

## Step 6. Verify the setup

```bash
classroom-lib.sh whoami                       # should print your email
classroom-lib.sh courses --terse | head -5    # should list your courses
classroom-lib.sh find "test"                  # should return JSON (possibly empty array)
```

All three commands should succeed with exit code 0. If any of them fails, see the Troubleshooting section below.

---

## Troubleshooting

### `port 8765 already in use`

Another process is holding the loopback port. Either kill it, or pick a different port:

```bash
export CLASSROOM_SUBMIT_OAUTH_PORT=8766
classroom-lib.sh auth
```

If you change the port, you also need to update the OAuth client in Google Cloud Console: Credentials → click your client → **Authorized redirect URIs** → add `http://localhost:8766`. Desktop-type clients allow any `http://localhost:<port>` by default, but some Google Workspace tenants restrict this.

### `Error 400: redirect_uri_mismatch`

The OAuth client was created as a **Web application** instead of **Desktop app**. Delete it and recreate with the correct type, or add `http://localhost:8765` to the Authorized redirect URIs list on the existing client.

### `Error 403: access_denied`

Your Google account is not in the Test Users list for the OAuth consent screen. Go back to step 3 and add your email under Test users.

### `Error 403: insufficient_scope` on API calls

The OAuth client was created before you added the scopes to the consent screen, so the existing refresh token is missing scopes. Fix:

1. Revoke the app at <https://myaccount.google.com/permissions>
2. Delete `~/.config/claude-classroom-submit/tokens.json`
3. Re-run `classroom-lib.sh auth`

### Refresh token expired / revoked after long idle

OAuth clients in "Testing" status (not published) have refresh tokens that expire after 7 days of inactivity. If you go more than a week without running the plugin, you may see `invalid_grant` errors. Fix: re-run `classroom-lib.sh auth`. For long-term use without re-auth, publish the OAuth consent screen (click "Publish App" on the consent screen page) — this requires Google verification for apps using sensitive scopes, but Classroom scopes are typically approved within a few days for individual developers.

### Wrong Google account authenticated

If Chrome signed you in with the wrong account during consent, the tokens are tied to the wrong account. Delete tokens.json and re-auth from an incognito window:

```bash
rm ~/.config/claude-classroom-submit/tokens.json
classroom-lib.sh auth
```

In the browser, before clicking the consent URL, open an incognito window, sign into the correct Google account, then paste the URL from the terminal.

---

## What gets stored locally

After setup, your config directory contains:

```
~/.config/claude-classroom-submit/
├── credentials.json      # client_id + client_secret from Google Cloud (mode 600)
├── tokens.json           # access_token + refresh_token + expiry (mode 600)
└── config.json           # optional user overrides (rclone remote, mount path)
```

Neither file leaves your machine. There is no telemetry, no remote logging, no central server. The plugin's Python code is ~600 lines of stdlib-only Python and can be audited in `skills/classroom-submit/classroom.py`.

To fully uninstall: `rm -rf ~/.config/claude-classroom-submit` and revoke the app at <https://myaccount.google.com/permissions>.
