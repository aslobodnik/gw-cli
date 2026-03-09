"""Unified Google Workspace OAuth authentication."""

import json
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

DEFAULT_CREDENTIALS_DIR = Path.home() / ".google_workspace_mcp" / "credentials"

# API name -> (service_name, version)
_SERVICES = {
    "drive": ("drive", "v3"),
    "sheets": ("sheets", "v4"),
    "docs": ("docs", "v1"),
    "slides": ("slides", "v1"),
    "gmail": ("gmail", "v1"),
    "calendar": ("calendar", "v3"),
}


def load_credentials(account: str, credentials_dir: Path | None = None) -> Credentials:
    """Load OAuth credentials for an account."""
    creds_dir = credentials_dir or DEFAULT_CREDENTIALS_DIR
    token_file = creds_dir / f"{account}.json"

    if not token_file.exists():
        raise FileNotFoundError(f"No credentials found for {account} at {token_file}")

    with open(token_file) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            raise FileNotFoundError(
                f"Token expired/revoked for {account}. Fix: gw auth remove {account} && gw auth add {account}"
            )
        save_credentials(account, creds, creds_dir)

    return creds


def save_credentials(account: str, creds: Credentials, credentials_dir: Path | None = None):
    """Save credentials back to file."""
    creds_dir = credentials_dir or DEFAULT_CREDENTIALS_DIR
    token_file = creds_dir / f"{account}.json"

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

    with open(token_file, "w") as f:
        json.dump(token_data, f, indent=2)


def list_accounts(credentials_dir: Path | None = None) -> list[str]:
    """List all configured account emails."""
    creds_dir = credentials_dir or DEFAULT_CREDENTIALS_DIR
    if not creds_dir.exists():
        return []
    return sorted(f.stem for f in creds_dir.glob("*.json"))


def get_service(api: str, account: str, credentials_dir: Path | None = None):
    """Get an authenticated Google API service by name."""
    service_name, version = _SERVICES[api]
    creds = load_credentials(account, credentials_dir)
    return build(service_name, version, credentials=creds)
