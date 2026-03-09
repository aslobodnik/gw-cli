"""Gmail API operations."""

import base64
import html as html_lib
import os
import re
from email.mime.text import MIMEText
from datetime import datetime, timezone

from ..utils import _human_size

# Module-level cache: short_id (last 12 chars) -> full Gmail message ID.
# Populated by list_messages/search, consumed by _resolve_message_id.
# Persists across calls within the same process (same CLI invocation).
_id_cache: dict[str, str] = {}

# Max pages to scan in _resolve_message_id slow path (500 msgs/page).
_RESOLVE_MAX_PAGES = 5


def format_date(timestamp_ms: str) -> str:
    """Format email timestamp to relative or absolute date."""
    ts = int(timestamp_ms) / 1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    diff = now - dt

    if diff.days < 0:
        return dt.strftime("%b %d")
    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            mins = diff.seconds // 60
            return f"{mins}m ago" if mins > 0 else "now"
        return f"{hours}h ago"
    if diff.days == 1:
        return "yesterday"
    if diff.days < 7:
        return f"{diff.days}d ago"
    return dt.strftime("%b %d")


def get_header(headers: list, name: str) -> str:
    """Extract header value from message headers."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def truncate(s: str, length: int) -> str:
    """Truncate string to length."""
    return s[:length - 1] + "\u2026" if len(s) > length else s


def parse_email_address(addr: str) -> tuple[str, str]:
    """Parse 'Name <email>' into (name, email)."""
    match = re.match(r"^(.+?)\s*<(.+)>$", addr)
    if match:
        return match.group(1).strip().strip('"'), match.group(2)
    return "", addr


def format_from(addr: str, max_len: int = 20) -> str:
    """Format sender for display."""
    name, email = parse_email_address(addr)
    display = name if name else email.split("@")[0]
    return truncate(display, max_len)


class GmailClient:
    """Gmail API wrapper with concise output."""

    def __init__(self, service, account: str):
        self.service = service
        self.account = account

    def _batch_get(self, msg_ids: list[str], fmt: str = "full",
                   metadata_headers: list[str] | None = None) -> dict[str, dict]:
        """Batch-fetch messages by ID. Returns {msg_id: msg_data}."""
        result_map = {}

        def handle_response(request_id, response, exception):
            if exception is None:
                result_map[request_id] = response

        batch = self.service.new_batch_http_request(callback=handle_response)
        kwargs = {"format": fmt}
        if metadata_headers:
            kwargs["metadataHeaders"] = metadata_headers
        for mid in msg_ids:
            batch.add(
                self.service.users().messages().get(userId="me", id=mid, **kwargs),
                request_id=mid,
            )
        batch.execute()
        return result_map

    def list_messages(
        self,
        limit: int = 10,
        unread_only: bool = False,
        query: str | None = None,
    ) -> str:
        """List messages with concise output."""
        q = query or "in:inbox"
        if unread_only:
            q = f"is:unread {q}"

        result = self.service.users().messages().list(
            userId="me",
            q=q,
            maxResults=limit,
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return "No messages found."

        msg_ids = [m["id"] for m in messages]
        msg_data_map = self._batch_get(msg_ids, fmt="metadata",
                                       metadata_headers=["From", "Subject", "Date"])

        output_lines = []
        output_lines.append(f"{'ID':<12} {'FROM':<22} {'SUBJECT':<40} {'DATE':<10} FLAGS")
        output_lines.append("-" * 95)

        for msg in messages:
            msg_data = msg_data_map.get(msg["id"], {})
            headers = msg_data.get("payload", {}).get("headers", [])
            labels = msg_data.get("labelIds", [])

            from_addr = get_header(headers, "From")
            subject = get_header(headers, "Subject") or "(no subject)"
            date = format_date(msg_data.get("internalDate", "0"))

            flags = []
            if "UNREAD" in labels:
                flags.append("unread")
            if "STARRED" in labels:
                flags.append("starred")

            short_id = msg["id"][-12:]
            _id_cache[short_id] = msg["id"]

            output_lines.append(
                f"{short_id:<12} {format_from(from_addr):<22} {truncate(subject, 40):<40} {date:<10} {','.join(flags)}"
            )

        return "\n".join(output_lines)

    def read_messages(self, msg_ids: list[str], peek: bool = False, brief: bool = False) -> str:
        """Read one or more messages."""
        full_ids = [self._resolve_message_id(mid) for mid in msg_ids]

        msg_data_map = self._batch_get(full_ids)

        outputs = []
        for i, full_id in enumerate(full_ids):
            msg = msg_data_map.get(full_id)

            # Fallback: if batch missed this message, try a direct get
            if msg is None:
                try:
                    msg = self.service.users().messages().get(
                        userId="me",
                        id=full_id,
                        format="full",
                    ).execute()
                except Exception:
                    outputs.append(f"Error: could not fetch message '{msg_ids[i]}'. ID may be invalid or message was deleted.")
                    continue

            outputs.append(self._format_message(msg, brief=brief))

            if not peek:
                try:
                    self._modify_labels(full_id, remove=["UNREAD"])
                except Exception:
                    pass  # Don't crash read if mark-as-read fails

        return "\n\n---\n\n".join(outputs)

    def _format_message(self, msg: dict, brief: bool = False) -> str:
        """Format a message for display."""
        headers = msg.get("payload", {}).get("headers", [])

        from_addr = get_header(headers, "From")
        to_addr = get_header(headers, "To")
        cc_addr = get_header(headers, "Cc")
        subject = get_header(headers, "Subject") or "(no subject)"
        date = get_header(headers, "Date")

        body = self._extract_body(msg.get("payload", {}))
        if brief:
            body = self._clean_for_brief(body)

        attachment_parts = self._get_attachment_parts(msg.get("payload", {}))
        attachments = [f"{p['filename']} ({_human_size(p['size'])})" for p in attachment_parts]
        thread_id = msg.get("threadId")
        thread_count = self._get_thread_count(thread_id) if thread_id else 1
        msg_id = msg.get("id", "")[-12:]

        output = []
        output.append(f"FROM: {from_addr}")
        output.append(f"TO: {to_addr}")
        if cc_addr:
            output.append(f"CC: {cc_addr}")
        output.append(f"DATE: {date}")
        output.append(f"SUBJECT: {subject}")
        output.append("")
        output.append(body)

        if attachments:
            output.append("")
            output.append("--")
            output.append(f"ATTACHMENTS: {', '.join(attachments)}")

        if thread_count > 1:
            output.append(f"THREAD: {thread_count} messages")

        return "\n".join(output)

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from message payload."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for part in parts:
            if "parts" in part:
                body = self._extract_body(part)
                if body and body != "(no text content)":
                    return body

        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    return self._html_to_text(data)

        if mime_type == "text/html":
            data = payload.get("body", {}).get("data", "")
            if data:
                return self._html_to_text(data)

        return "(no text content)"

    def _html_to_text(self, data: str) -> str:
        """Convert base64 HTML to plain text."""
        raw_html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(br|p|div|tr|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = html_lib.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    def _clean_for_brief(self, text: str) -> str:
        """Clean up text for brief mode - remove tracking URLs, truncate."""
        text = re.sub(r"https?://[^\s]*(?:hubspot|click\.|track\.|gle/|/Ctc/|email\.|links\.)[^\s]*", "[link]", text)
        text = re.sub(r"https?://[^\s]{100,}", "[link]", text)
        text = re.sub(r"(\[link\]\s*)+", "[link] ", text)
        if len(text) > 1500:
            text = text[:1500] + "\n\n[truncated - use `gw mail read <id>` for full content]"
        return text.strip()

    def _get_attachment_parts(self, payload: dict) -> list[dict]:
        """Get attachment parts with metadata (recursive into nested multipart)."""
        parts_out = []
        for part in payload.get("parts", []):
            filename = part.get("filename")
            if filename:
                body = part.get("body", {})
                parts_out.append({
                    "filename": filename,
                    "size": body.get("size", 0),
                    "attachmentId": body.get("attachmentId"),
                    "data": body.get("data"),
                })
            # Recurse into nested multipart
            if part.get("parts"):
                parts_out.extend(self._get_attachment_parts(part))
        return parts_out

    def download_attachments(self, msg_id: str, dest_dir: str) -> str:
        """Download all attachments from a message to dest_dir."""
        full_id = self._resolve_message_id(msg_id)

        msg = self.service.users().messages().get(
            userId="me",
            id=full_id,
            format="full",
        ).execute()

        parts = self._get_attachment_parts(msg.get("payload", {}))
        if not parts:
            return f"No attachments found on message {msg_id}."

        os.makedirs(dest_dir, exist_ok=True)
        saved_count = 0
        lines = []

        for part in parts:
            filename = part["filename"]
            data = part.get("data")

            if not data and part.get("attachmentId"):
                att = self.service.users().messages().attachments().get(
                    userId="me",
                    messageId=full_id,
                    id=part["attachmentId"],
                ).execute()
                data = att.get("data", "")

            if not data:
                lines.append(f"  SKIP  {filename} (no data)")
                continue

            file_bytes = base64.urlsafe_b64decode(data)
            filepath = os.path.join(dest_dir, filename)

            # Avoid overwriting: append counter if file exists
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base}_{counter}{ext}"
                counter += 1

            with open(filepath, "wb") as f:
                f.write(file_bytes)
            saved_count += 1
            lines.append(f"  SAVED {filename} ({_human_size(len(file_bytes))}) -> {filepath}")

        return f"Downloaded {saved_count} attachment(s):\n" + "\n".join(lines)

    def _get_thread_count(self, thread_id: str) -> int:
        """Get number of messages in thread."""
        thread = self.service.users().threads().get(
            userId="me",
            id=thread_id,
            format="minimal",
        ).execute()
        return len(thread.get("messages", []))

    def _resolve_message_id(self, msg_id: str) -> str:
        """Resolve short ID (last 12 chars) to full message ID.

        Checks the module-level cache first (populated by search/list),
        then falls back to paginated scan (capped at _RESOLVE_MAX_PAGES).
        """
        if len(msg_id) > 12:
            return msg_id

        # Fast path: check cache from previous search/list calls
        if msg_id in _id_cache:
            return _id_cache[msg_id]

        # Slow path: paginate through messages list (bounded)
        page_token = None
        for _ in range(_RESOLVE_MAX_PAGES):
            result = self.service.users().messages().list(
                userId="me",
                maxResults=500,
                pageToken=page_token,
            ).execute()

            for msg in result.get("messages", []):
                short = msg["id"][-12:]
                _id_cache[short] = msg["id"]
                if short == msg_id:
                    return msg["id"]

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return msg_id

    def search(self, query: str, limit: int = 10) -> str:
        """Search messages."""
        return self.list_messages(limit=limit, query=query)

    def _modify_labels(
        self,
        full_id: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        """Modify labels on a message."""
        body = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        if body:
            self.service.users().messages().modify(
                userId="me", id=full_id, body=body
            ).execute()

    def mark_read(self, msg_id: str) -> str:
        """Mark message as read."""
        self._modify_labels(self._resolve_message_id(msg_id), remove=["UNREAD"])
        return f"Marked {msg_id} as read."

    def mark_unread(self, msg_id: str) -> str:
        """Mark message as unread."""
        self._modify_labels(self._resolve_message_id(msg_id), add=["UNREAD"])
        return f"Marked {msg_id} as unread."

    def star(self, msg_id: str) -> str:
        """Star a message."""
        self._modify_labels(self._resolve_message_id(msg_id), add=["STARRED"])
        return f"Starred {msg_id}."

    def unstar(self, msg_id: str) -> str:
        """Unstar a message."""
        self._modify_labels(self._resolve_message_id(msg_id), remove=["STARRED"])
        return f"Unstarred {msg_id}."

    def archive(self, msg_id: str) -> str:
        """Archive a message (remove from inbox)."""
        self._modify_labels(self._resolve_message_id(msg_id), remove=["INBOX"])
        return f"Archived {msg_id}."

    def trash(self, msg_id: str) -> str:
        """Move message to trash."""
        full_id = self._resolve_message_id(msg_id)
        self.service.users().messages().trash(
            userId="me",
            id=full_id,
        ).execute()
        return f"Moved {msg_id} to trash."

    def _get_sender_email(self, full_id: str) -> str:
        """Get sender email from a message."""
        msg = self.service.users().messages().get(
            userId="me",
            id=full_id,
            format="metadata",
            metadataHeaders=["From"],
        ).execute()
        from_addr = get_header(msg.get("payload", {}).get("headers", []), "From")
        _, sender_email = parse_email_address(from_addr)
        return sender_email

    def _create_block_filter(self, email: str) -> None:
        """Create filter to auto-delete future emails from sender."""
        self.service.users().settings().filters().create(
            userId="me",
            body={
                "criteria": {"from": email},
                "action": {"removeLabelIds": ["INBOX"]},
            },
        ).execute()

    def spam(self, msg_id: str, block: bool = False) -> str:
        """Report message as spam."""
        full_id = self._resolve_message_id(msg_id)
        sender_email = self._get_sender_email(full_id) if block else None

        self._modify_labels(full_id, add=["SPAM"], remove=["INBOX"])
        result = f"Reported {msg_id} as spam."

        if block and sender_email:
            self._create_block_filter(sender_email)
            result += f" Blocked {sender_email}."

        return result

    def block(self, msg_id: str) -> str:
        """Block sender of a message."""
        full_id = self._resolve_message_id(msg_id)
        sender_email = self._get_sender_email(full_id)
        self._create_block_filter(sender_email)
        return f"Blocked {sender_email}. Future emails will skip inbox."

    def send(self, to: str, subject: str, body: str) -> str:
        """Send an email."""
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = self.service.users().messages().send(
            userId="me",
            body={"raw": encoded},
        ).execute()

        return f"Sent email to {to}. Message ID: {result['id'][-12:]}"

    def reply(self, msg_id: str, body: str) -> str:
        """Reply to a message."""
        full_id = self._resolve_message_id(msg_id)

        orig = self.service.users().messages().get(
            userId="me",
            id=full_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID"],
        ).execute()

        headers = orig.get("payload", {}).get("headers", [])
        from_addr = get_header(headers, "From")
        subject = get_header(headers, "Subject")
        message_id = get_header(headers, "Message-ID")
        thread_id = orig.get("threadId")

        _, to_email = parse_email_address(from_addr)

        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        message = MIMEText(body)
        message["to"] = to_email
        message["subject"] = subject
        if message_id:
            message["In-Reply-To"] = message_id
            message["References"] = message_id

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = self.service.users().messages().send(
            userId="me",
            body={"raw": encoded, "threadId": thread_id},
        ).execute()

        return f"Replied to {to_email}. Message ID: {result['id'][-12:]}"

    def labels(self) -> str:
        """List all labels."""
        result = self.service.users().labels().list(userId="me").execute()
        labels = result.get("labels", [])

        output = ["LABELS:"]
        for label in sorted(labels, key=lambda x: x["name"]):
            label_type = label.get("type", "user")
            if label_type == "system":
                continue
            output.append(f"  {label['name']}")

        return "\n".join(output)

    def _get_label_id(self, label_name: str) -> str | None:
        """Get label ID from label name."""
        result = self.service.users().labels().list(userId="me").execute()
        for label in result.get("labels", []):
            if label["name"].lower() == label_name.lower():
                return label["id"]
        return None

    def label(self, msg_id: str, label_name: str) -> str:
        """Add a label to a message."""
        label_id = self._get_label_id(label_name)
        if not label_id:
            return f"Label '{label_name}' not found. Use `gw mail labels` to see available labels."

        self._modify_labels(self._resolve_message_id(msg_id), add=[label_id])
        return f"Added label '{label_name}' to {msg_id}."

    def unlabel(self, msg_id: str, label_name: str) -> str:
        """Remove a label from a message."""
        label_id = self._get_label_id(label_name)
        if not label_id:
            return f"Label '{label_name}' not found. Use `gw mail labels` to see available labels."

        self._modify_labels(self._resolve_message_id(msg_id), remove=[label_id])
        return f"Removed label '{label_name}' from {msg_id}."
