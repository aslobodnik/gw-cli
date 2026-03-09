# Google OAuth Setup

Google OAuth setup is cumbersome the first time. Budget 15-30 minutes.

## Step 1: Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown (top left) > "New Project"
3. Name it whatever you want (e.g., "gw-cli")
4. Click "Create"

## Step 2: Enable APIs

Each API must be enabled individually.

Go to [APIs & Services > Library](https://console.cloud.google.com/apis/library) and enable all of these:

- Gmail API
- Google Calendar API
- Google Drive API
- Google Docs API
- Google Sheets API
- Google Slides API

Click each one, click "Enable".

## Step 3: OAuth Consent Screen

Go to [APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent).

1. Select **External** user type (unless you have a Google Workspace org and want Internal)
2. Fill in the required fields:
   - App name: anything (e.g., "gw-cli")
   - User support email: your email
   - Developer contact email: your email
3. Click through to "Scopes" -- skip this for now, we'll handle scopes in the credentials
4. Click through to "Test users"

### The Test User Trap

**This is the biggest gotcha.** While your app is in "Testing" mode:

- Only emails listed as test users can authenticate
- **Refresh tokens expire after 7 days** -- you'll have to re-auth weekly
- You're limited to 100 test users

**Add your email(s) as test users** on the consent screen. Every Google account you want to use with `gw` must be listed here.

To stop the 7-day token expiry, publish your app (Step 5).

## Step 4: Create OAuth Credentials

Go to [APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials).

1. Click "Create Credentials" > "OAuth client ID"
2. Application type: **Desktop app**
3. Name: anything
4. Click "Create"
5. You'll see your **Client ID** and **Client Secret** -- you'll need these

## Step 5: Publish the App (Important)

If you skip this, your tokens expire every 7 days and you'll be re-authenticating constantly.

Go back to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent):

1. Click "Publish App"
2. Google will warn you about verification. **Ignore this for personal use.**
3. Click "Confirm"

Your app is now "In production" but unverified. This means:
- Tokens no longer expire after 7 days
- Anyone can auth (not just test users)
- Users see a "Google hasn't verified this app" warning during auth -- click "Advanced" > "Go to [app name] (unsafe)" to proceed
- Google may email you about verification. For personal use, this can be ignored.

**If you don't publish:** re-run `gw auth add` every 7 days when tokens expire.

## Step 6: Download Client Secrets

1. On the Credentials page, find your OAuth client ID
2. Click the download icon (or "Download JSON")
3. Save the file as `client_secrets.json` in one of:
   - `~/.google_workspace_mcp/credentials/client_secrets.json`
   - The `gw-cli` project root

## Step 7: First Auth

```bash
gw auth add you@gmail.com
```

This reads your `client_secrets.json`, opens a browser, and starts the OAuth flow. You'll see the "unverified app" warning. Click through it:
1. "Advanced"
2. "Go to gw-cli (unsafe)"
3. Grant all permissions
4. Done -- credentials saved to `~/.google_workspace_mcp/credentials/`

## Gotchas

**"Access blocked" error**: Your email isn't listed as a test user (if app is in testing mode). Add it on the consent screen.

**"Token has been expired or revoked"**: You're in testing mode and the 7-day token expired. Either publish the app or re-run `gw auth add`.

**"Error 403: access_denied"**: You didn't enable one of the APIs. Go back to Step 2.

**Missing scopes warning during auth**: The first account you add defines the scopes for all subsequent accounts. If you add a second account and see fewer permissions, remove and re-add the first account.

**Google Workspace (company) accounts**: Your org admin may block third-party OAuth apps. You'll get "access blocked by admin" -- talk to your IT team or use a personal account.

**Multiple accounts**: Each `gw auth add` stores credentials separately. Switch with `gw -a email@example.com`.
