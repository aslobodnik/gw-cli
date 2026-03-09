"""Unified Google Workspace CLI for Claude Code."""

import sys
import click
from googleapiclient.errors import HttpError

from .auth import get_service, list_accounts, DEFAULT_CREDENTIALS_DIR, DEFAULT_SCOPES
from .config import get_account, get_config, save_config, get_calendar_aliases
from .services.drive import DriveClient
from .services.docs import DocsClient
from .services.sheets import SheetsClient
from .services.slides import SlidesClient
from .services.calendar import CalendarClient
from .services.gmail import GmailClient


class GwGroup(click.Group):
    """Click group with global error handling."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except HttpError as e:
            click.echo(f"Google API error: {e.resp.status} {e._get_reason()}", err=True)
            sys.exit(1)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


# --- Helpers ---

def _account(ctx: click.Context) -> str:
    return get_account(ctx.obj.get("account"))


def _svc(ctx: click.Context, api: str):
    return get_service(api, _account(ctx))


def _drive_client(ctx: click.Context) -> DriveClient:
    return DriveClient(_svc(ctx, "drive"))


def _docs_client(ctx: click.Context) -> DocsClient:
    return DocsClient(_svc(ctx, "docs"), _svc(ctx, "drive"))


def _sheets_client(ctx: click.Context) -> SheetsClient:
    return SheetsClient(_svc(ctx, "sheets"), _svc(ctx, "drive"))


def _slides_client(ctx: click.Context) -> SlidesClient:
    return SlidesClient(_svc(ctx, "slides"), _svc(ctx, "drive"))


def _cal_client(ctx: click.Context) -> CalendarClient:
    tz_override = ctx.obj.get("tz_override") if ctx.obj else None
    return CalendarClient(_svc(ctx, "calendar"), _account(ctx), tz_override=tz_override)


def _gmail_client(ctx: click.Context) -> GmailClient:
    return GmailClient(_svc(ctx, "gmail"), _account(ctx))


# --- Main group ---

@click.group(cls=GwGroup)
@click.option("-a", "--account", help="Google account email or alias")
@click.pass_context
def main(ctx, account):
    """Unified Google Workspace CLI."""
    ctx.ensure_object(dict)
    ctx.obj["account"] = account


# ============================================================
# AUTH
# ============================================================

@main.group()
def auth():
    """Manage account credentials."""
    pass


@auth.command("add")
@click.argument("email")
@click.option("--port", "-p", default=0, help="Local server port for OAuth callback (0 = auto)")
def auth_add(email, port):
    """Add a new Google account via OAuth (re-authenticates if token is stale)."""
    import json
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .auth import load_credentials, save_credentials

    creds_dir = DEFAULT_CREDENTIALS_DIR
    token_file = creds_dir / f"{email}.json"

    if token_file.exists():
        # Verify credentials actually work by forcing a refresh
        try:
            creds = load_credentials(email)
            creds.refresh(Request())
            save_credentials(email, creds)
            click.echo(f"Credentials for {email} are still valid.")
            return
        except (RefreshError, FileNotFoundError, Exception):
            click.echo(f"Stale credentials for {email} — re-authenticating...")
            token_file.unlink()

    # Borrow client_id/secret from any existing account, or fall back to client_secrets.json
    existing = list(creds_dir.glob("*.json"))
    if existing:
        with open(existing[0]) as f:
            d = json.load(f)
        client_id = d["client_id"]
        client_secret = d["client_secret"]
        token_uri = d.get("token_uri", "https://oauth2.googleapis.com/token")
        scopes = d.get("scopes", DEFAULT_SCOPES)
    else:
        # Bootstrap: look for client_secrets.json from Google Cloud Console
        secrets_file = creds_dir / "client_secrets.json"
        if not secrets_file.exists():
            secrets_file = Path("client_secrets.json")
        if not secrets_file.exists():
            click.echo("No existing accounts found.")
            click.echo("Download your OAuth client_secrets.json from Google Cloud Console")
            click.echo("and place it in one of:")
            click.echo(f"  {creds_dir / 'client_secrets.json'}")
            click.echo(f"  ./client_secrets.json")
            click.echo("See GOOGLE_SETUP.md for details.")
            return
        with open(secrets_file) as f:
            secrets = json.load(f)
        installed = secrets.get("installed", secrets.get("web", {}))
        client_id = installed["client_id"]
        client_secret = installed["client_secret"]
        token_uri = installed.get("token_uri", "https://oauth2.googleapis.com/token")
        scopes = DEFAULT_SCOPES

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": token_uri,
            "redirect_uris": ["http://localhost"],
        }
    }

    click.echo(f"Opening browser for {email}...")
    click.echo(f"NOTE: {email} must be a test user in the Google Cloud Console OAuth consent screen.")
    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    creds = flow.run_local_server(port=port, prompt="consent", login_hint=email)
    save_credentials(email, creds)
    click.echo(f"Saved credentials for {email}")


@auth.command("list")
def auth_list():
    """List configured accounts."""
    creds_dir = DEFAULT_CREDENTIALS_DIR
    if not creds_dir.exists():
        click.echo("No credentials directory found.")
        return
    accounts = sorted(f.stem for f in creds_dir.glob("*.json"))
    if not accounts:
        click.echo("No accounts configured.")
        return
    cfg = get_config()
    default = cfg.get("default_account", "")
    for a in accounts:
        marker = " (default)" if a == default else ""
        click.echo(f"  {a}{marker}")


@auth.command("remove")
@click.argument("email")
def auth_remove(email):
    """Remove credentials for an account."""
    token_file = DEFAULT_CREDENTIALS_DIR / f"{email}.json"
    if not token_file.exists():
        click.echo(f"No credentials found for {email}")
        return
    token_file.unlink()
    click.echo(f"Removed credentials for {email}")


# ============================================================
# DRIVE
# ============================================================

@main.group()
@click.pass_context
def drive(ctx):
    """Google Drive operations."""
    pass


@drive.command()
@click.argument("query", required=False)
@click.option("--limit", "-l", default=20, help="Number of files to show")
@click.pass_context
def ls(ctx, query, limit):
    """List files (optional search query)."""
    click.echo(_drive_client(ctx).ls(query=query, limit=limit))


@drive.command()
@click.argument("file_id")
@click.pass_context
def info(ctx, file_id):
    """File metadata & sharing info."""
    click.echo(_drive_client(ctx).info(file_id))


@drive.command()
@click.argument("file_id")
@click.option("--out", "-o", help="Output file path")
@click.pass_context
def download(ctx, file_id, out):
    """Download a file."""
    click.echo(_drive_client(ctx).download(file_id, out_path=out))


@drive.command()
@click.argument("path")
@click.option("--folder", "-f", help="Parent folder ID")
@click.pass_context
def upload(ctx, path, folder):
    """Upload a file."""
    click.echo(_drive_client(ctx).upload(path, folder_id=folder))


@drive.command()
@click.argument("name")
@click.option("--parent", "-p", help="Parent folder ID")
@click.pass_context
def mkdir(ctx, name, parent):
    """Create a folder."""
    click.echo(_drive_client(ctx).mkdir(name, parent_id=parent))


@drive.command()
@click.argument("file_id")
@click.pass_context
def trash(ctx, file_id):
    """Move to trash."""
    click.echo(_drive_client(ctx).trash(file_id))


@drive.command()
@click.argument("file_id")
@click.pass_context
def untrash(ctx, file_id):
    """Restore from trash."""
    click.echo(_drive_client(ctx).untrash(file_id))


@drive.command()
@click.argument("file_id")
@click.argument("email")
@click.option("--role", "-r", default="reader", type=click.Choice(["reader", "writer", "commenter"]))
@click.pass_context
def share(ctx, file_id, email, role):
    """Share a file with someone."""
    click.echo(_drive_client(ctx).share(file_id, email, role=role))


@drive.command()
@click.argument("file_id")
@click.argument("email")
@click.pass_context
def unshare(ctx, file_id, email):
    """Remove access for someone."""
    click.echo(_drive_client(ctx).unshare(file_id, email))


# ============================================================
# DOC
# ============================================================

@main.group()
@click.pass_context
def doc(ctx):
    """Google Docs operations."""
    pass


@doc.command()
@click.argument("title")
@click.pass_context
def create(ctx, title):
    """Create a blank Google Doc."""
    click.echo(_docs_client(ctx).create(title))


@doc.command()
@click.argument("file_id")
@click.pass_context
def read(ctx, file_id):
    """Read a Google Doc as plain text."""
    click.echo(_docs_client(ctx).read(file_id))


@doc.command()
@click.argument("file_id")
@click.argument("text")
@click.pass_context
def append(ctx, file_id, text):
    """Append text to end of a Google Doc."""
    click.echo(_docs_client(ctx).append(file_id, text))


# ============================================================
# SHEET
# ============================================================

@main.group()
@click.pass_context
def sheet(ctx):
    """Google Sheets operations."""
    pass


@sheet.command("create")
@click.argument("title")
@click.pass_context
def sheet_create(ctx, title):
    """Create a blank Google Sheet."""
    click.echo(_sheets_client(ctx).create(title))


@sheet.command("read")
@click.argument("file_id")
@click.argument("range_", metavar="RANGE", default="Sheet1")
@click.pass_context
def sheet_read(ctx, file_id, range_):
    """Read cells from a Google Sheet (default range: Sheet1)."""
    click.echo(_sheets_client(ctx).read(file_id, range_=range_))


@sheet.command("write")
@click.argument("file_id")
@click.argument("range_", metavar="RANGE")
@click.argument("json_data", metavar="JSON")
@click.pass_context
def sheet_write(ctx, file_id, range_, json_data):
    """Write cells to a Google Sheet. JSON = [[row1...],[row2...]]."""
    click.echo(_sheets_client(ctx).write(file_id, range_=range_, values_json=json_data))


# ============================================================
# SLIDES
# ============================================================

@main.group()
@click.pass_context
def slides(ctx):
    """Google Slides operations."""
    pass


@slides.command("create")
@click.argument("title")
@click.pass_context
def slides_create(ctx, title):
    """Create a blank Google Slides presentation."""
    click.echo(_slides_client(ctx).create(title))


@slides.command("read")
@click.argument("file_id")
@click.pass_context
def slides_read(ctx, file_id):
    """Read text content from all slides."""
    click.echo(_slides_client(ctx).read(file_id))


@slides.command("add")
@click.argument("file_id")
@click.argument("title")
@click.argument("body", required=False)
@click.pass_context
def slides_add(ctx, file_id, title, body):
    """Add a new slide with title and optional body text."""
    click.echo(_slides_client(ctx).add_slide(file_id, title, body=body))


# ============================================================
# MAIL
# ============================================================

@main.group()
@click.pass_context
def mail(ctx):
    """Gmail operations."""
    pass


@mail.command()
@click.option("--limit", "-l", default=10, help="Number of messages to show")
@click.option("--unread", "-u", is_flag=True, help="Show only unread messages")
@click.option("--days", "-d", type=int, help="Only show messages from last N days")
@click.pass_context
def inbox(ctx, limit, unread, days):
    """List inbox messages."""
    query = f"in:inbox newer_than:{days}d" if days else "in:inbox"
    click.echo(_gmail_client(ctx).list_messages(limit=limit, unread_only=unread, query=query))


@mail.command("read")
@click.argument("msg_ids", nargs=-1, required=True)
@click.option("--peek", "-p", is_flag=True, help="Don't mark as read")
@click.option("--brief", "-b", is_flag=True, help="Truncate and clean up content")
@click.pass_context
def mail_read(ctx, msg_ids, peek, brief):
    """Read one or more messages."""
    click.echo(_gmail_client(ctx).read_messages(list(msg_ids), peek=peek, brief=brief))


@mail.command()
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Number of results")
@click.option("--all", "-a", "search_all", is_flag=True, help="Search all mail, not just inbox")
@click.option("--all-accounts", "-A", is_flag=True, help="Search across all configured accounts")
@click.pass_context
def search(ctx, query, limit, search_all, all_accounts):
    """Search messages (Gmail syntax). Defaults to inbox only."""
    if not search_all and "in:" not in query.lower():
        query = f"in:inbox {query}"

    if all_accounts:
        accounts = list_accounts()
        if not accounts:
            click.echo("No accounts configured.", err=True)
            return
        for acct in accounts:
            click.echo(f"--- {acct} ---")
            try:
                svc = get_service("gmail", acct)
                client = GmailClient(svc, acct)
                click.echo(client.search(query, limit=limit))
            except Exception as e:
                click.echo(f"  Error: {e}", err=True)
            click.echo()
    else:
        click.echo(_gmail_client(ctx).search(query, limit=limit))


@mail.command("download")
@click.argument("msg_id")
@click.option("--dest", "-d", default=".", help="Destination directory")
@click.pass_context
def mail_download(ctx, msg_id, dest):
    """Download attachments from a message."""
    click.echo(_gmail_client(ctx).download_attachments(msg_id, dest))


@mail.command("mark-read")
@click.argument("msg_id")
@click.pass_context
def mail_mark_read(ctx, msg_id):
    """Mark message as read."""
    click.echo(_gmail_client(ctx).mark_read(msg_id))


@mail.command("mark-unread")
@click.argument("msg_id")
@click.pass_context
def mail_mark_unread(ctx, msg_id):
    """Mark message as unread."""
    click.echo(_gmail_client(ctx).mark_unread(msg_id))


@mail.command()
@click.argument("msg_id")
@click.pass_context
def star(ctx, msg_id):
    """Star a message."""
    click.echo(_gmail_client(ctx).star(msg_id))


@mail.command()
@click.argument("msg_id")
@click.pass_context
def unstar(ctx, msg_id):
    """Unstar a message."""
    click.echo(_gmail_client(ctx).unstar(msg_id))


@mail.command()
@click.argument("msg_id")
@click.pass_context
def archive(ctx, msg_id):
    """Archive a message."""
    click.echo(_gmail_client(ctx).archive(msg_id))


@mail.command("trash")
@click.argument("msg_id")
@click.pass_context
def mail_trash(ctx, msg_id):
    """Move message to trash."""
    click.echo(_gmail_client(ctx).trash(msg_id))


@mail.command()
@click.argument("msg_id")
@click.option("--block", "-b", is_flag=True, help="Also block sender")
@click.pass_context
def spam(ctx, msg_id, block):
    """Report message as spam."""
    click.echo(_gmail_client(ctx).spam(msg_id, block=block))


@mail.command()
@click.argument("msg_id")
@click.pass_context
def block(ctx, msg_id):
    """Block sender of a message."""
    click.echo(_gmail_client(ctx).block(msg_id))


@mail.command()
@click.argument("to")
@click.argument("subject")
@click.argument("body")
@click.pass_context
def send(ctx, to, subject, body):
    """Send an email."""
    click.echo(_gmail_client(ctx).send(to, subject, body))


@mail.command()
@click.argument("msg_id")
@click.argument("body")
@click.pass_context
def reply(ctx, msg_id, body):
    """Reply to a message."""
    click.echo(_gmail_client(ctx).reply(msg_id, body))


@mail.command()
@click.pass_context
def labels(ctx):
    """List available labels."""
    click.echo(_gmail_client(ctx).labels())


@mail.command()
@click.argument("msg_id")
@click.argument("label_name")
@click.pass_context
def label(ctx, msg_id, label_name):
    """Add a label to a message."""
    click.echo(_gmail_client(ctx).label(msg_id, label_name))


@mail.command()
@click.argument("msg_id")
@click.argument("label_name")
@click.pass_context
def unlabel(ctx, msg_id, label_name):
    """Remove a label from a message."""
    click.echo(_gmail_client(ctx).unlabel(msg_id, label_name))


@mail.command()
@click.pass_context
def accounts(ctx):
    """List configured accounts."""
    cfg = get_config()
    default = cfg.get("default_account", "")
    aliases = cfg.get("aliases", {})

    from .auth import DEFAULT_CREDENTIALS_DIR as creds_dir

    click.echo("ACCOUNTS:")
    if creds_dir.exists():
        for f in creds_dir.glob("*.json"):
            account = f.stem
            marker = " (default)" if account == default else ""
            click.echo(f"  {account}{marker}")

    if aliases:
        click.echo("\nALIASES:")
        for name, email in aliases.items():
            click.echo(f"  {name} -> {email}")


# --- Mail config sub-subgroup ---

@mail.group("config")
def mail_config():
    """Manage configuration."""
    pass


@mail_config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value."""
    cfg = get_config()
    cfg[key] = value
    save_config(cfg)
    click.echo(f"Set {key} = {value}")


@mail_config.command("get")
@click.argument("key")
def config_get(key):
    """Get a config value."""
    cfg = get_config()
    click.echo(cfg.get(key, "(not set)"))


@mail_config.command("alias")
@click.argument("name")
@click.argument("email")
def config_alias(name, email):
    """Create an alias for an account."""
    cfg = get_config()
    if "aliases" not in cfg:
        cfg["aliases"] = {}
    cfg["aliases"][name] = email
    save_config(cfg)
    click.echo(f"Alias '{name}' -> {email}")


# ============================================================
# CAL
# ============================================================

@main.group()
@click.option("--tz", "tz_override", default=None, help="Timezone override (e.g. Asia/Kolkata)")
@click.pass_context
def cal(ctx, tz_override):
    """Google Calendar operations."""
    ctx.ensure_object(dict)
    ctx.obj["tz_override"] = tz_override


@cal.command()
@click.pass_context
def today(ctx):
    """Show today's events."""
    click.echo(_cal_client(ctx).today())


@cal.command()
@click.pass_context
def tomorrow(ctx):
    """Show tomorrow's events."""
    click.echo(_cal_client(ctx).tomorrow())


@cal.command()
@click.pass_context
def week(ctx):
    """Show next 7 days of events."""
    click.echo(_cal_client(ctx).week())


@cal.command("next")
@click.pass_context
def next_event(ctx):
    """Show next upcoming event."""
    click.echo(_cal_client(ctx).next_event())


@cal.command()
@click.argument("title")
@click.argument("time")
@click.option("-c", "--calendar", help="Calendar: ns, gmail, or ens")
@click.option("-l", "--location", help="Event location/address")
@click.option("-i", "--invite", multiple=True, help="Invite email address (repeatable)")
@click.option("--meet", is_flag=True, help="Add Google Meet link")
@click.pass_context
def add(ctx, title, time, calendar, location, invite, meet):
    """Add a new event."""
    attendees = list(invite) if invite else None
    click.echo(_cal_client(ctx).add_event(title, time, calendar_id=calendar, add_meet=meet, location=location, attendees=attendees))


@cal.command("delete")
@click.argument("event_id")
@click.option("-c", "--calendar", help="Calendar: ns, gmail, or ens")
@click.pass_context
def cal_delete(ctx, event_id, calendar):
    """Delete an event."""
    click.echo(_cal_client(ctx).delete_event(event_id, calendar_id=calendar))


@cal.command()
@click.pass_context
def invites(ctx):
    """Show pending invites."""
    click.echo(_cal_client(ctx).pending_invites())


@cal.command()
@click.pass_context
def calendars(ctx):
    """List accessible calendars."""
    aliases = get_calendar_aliases()
    client = _cal_client(ctx)
    cals = client._get_all_calendars()
    click.echo("Accessible calendars:")
    for c in cals:
        alias = next((k for k, v in aliases.items() if v == c), None)
        suffix = f" ({alias})" if alias else ""
        click.echo(f"  {c}{suffix}")


@cal.command()
@click.argument("event_id")
@click.option("-c", "--calendar", help="Calendar: ns, gmail, or ens")
@click.pass_context
def accept(ctx, event_id, calendar):
    """Accept an invite."""
    click.echo(_cal_client(ctx).respond_invite(event_id, "accepted", calendar_id=calendar))


@cal.command()
@click.argument("event_id")
@click.option("-c", "--calendar", help="Calendar: ns, gmail, or ens")
@click.pass_context
def decline(ctx, event_id, calendar):
    """Decline an invite."""
    click.echo(_cal_client(ctx).respond_invite(event_id, "declined", calendar_id=calendar))


if __name__ == "__main__":
    main()
