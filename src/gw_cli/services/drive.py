"""Google Drive API client."""

import io
from pathlib import Path

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from ..utils import (
    MIME_FOLDER, EXPORT_MIME_MAP, _human_size, _short_id, resolve_id,
    FILE_FIELDS, LIST_FIELDS,
)


class DriveClient:
    def __init__(self, service):
        self.service = service
        self.files = service.files()
        self.permissions = service.permissions()

    def _resolve_id(self, short_or_full: str) -> str:
        return resolve_id(self.files, short_or_full)

    def ls(self, query: str | None = None, limit: int = 20) -> str:
        """List files, optionally filtered by search query."""
        q_parts = ["trashed = false"]
        if query:
            q_parts.append(f"name contains '{query}'")
        q = " and ".join(q_parts)

        resp = self.files.list(
            q=q,
            fields=f"files({LIST_FIELDS})",
            pageSize=limit,
            orderBy="modifiedTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files = resp.get("files", [])
        if not files:
            return "No files found."

        lines = ["| ID | Name | Type | Size | Modified | Shared |", "| --- | --- | --- | --- | --- | --- |"]
        for f in files:
            mime = f.get("mimeType", "")
            ftype = "folder" if mime == MIME_FOLDER else mime.split(".")[-1] if "google-apps" in mime else mime.split("/")[-1]
            size = _human_size(f.get("size"))
            modified = f.get("modifiedTime", "")[:10]
            shared = "yes" if f.get("shared") else ""
            name = f["name"]
            if len(name) > 40:
                name = name[:37] + "..."
            lines.append(f"| {_short_id(f['id'])} | {name} | {ftype} | {size} | {modified} | {shared} |")

        return "\n".join(lines)

    def info(self, file_id: str) -> str:
        """Get detailed file metadata."""
        fid = self._resolve_id(file_id)
        f = self.files.get(
            fileId=fid,
            fields=FILE_FIELDS,
            supportsAllDrives=True,
        ).execute()

        owners = ", ".join(o.get("displayName", o.get("emailAddress", "?")) for o in f.get("owners", []))
        mime = f.get("mimeType", "")
        ftype = "folder" if mime == MIME_FOLDER else mime

        lines = [
            f"**{f['name']}**",
            f"",
            f"- **ID**: {f['id']}",
            f"- **Short ID**: {_short_id(f['id'])}",
            f"- **Type**: {ftype}",
            f"- **Size**: {_human_size(f.get('size'))}",
            f"- **Modified**: {f.get('modifiedTime', 'unknown')}",
            f"- **Owner**: {owners}",
            f"- **Shared**: {'yes' if f.get('shared') else 'no'}",
            f"- **Trashed**: {'yes' if f.get('trashed') else 'no'}",
            f"- **Link**: {f.get('webViewLink', 'n/a')}",
        ]

        try:
            perms = self.permissions.list(
                fileId=fid,
                fields="permissions(id, emailAddress, role, type)",
                supportsAllDrives=True,
            ).execute()
            perm_list = perms.get("permissions", [])
            if perm_list:
                lines.append("")
                lines.append("**Permissions:**")
                for p in perm_list:
                    email = p.get("emailAddress", p.get("type", "?"))
                    lines.append(f"- {email}: {p['role']}")
        except Exception:
            pass

        return "\n".join(lines)

    def download(self, file_id: str, out_path: str | None = None) -> str:
        """Download a file."""
        fid = self._resolve_id(file_id)
        meta = self.files.get(fileId=fid, fields="name, mimeType, size", supportsAllDrives=True).execute()
        name = meta["name"]
        mime = meta.get("mimeType", "")

        if mime in EXPORT_MIME_MAP:
            export_mime, ext = EXPORT_MIME_MAP[mime]
            request = self.files.export_media(fileId=fid, mimeType=export_mime)
            if not out_path:
                out_path = name + ext
        else:
            request = self.files.get_media(fileId=fid)
            if not out_path:
                out_path = name

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        out = Path(out_path)
        out.write_bytes(buf.getvalue())
        return f"Downloaded: {out} ({_human_size(len(buf.getvalue()))})"

    def upload(self, path: str, folder_id: str | None = None) -> str:
        """Upload a file."""
        filepath = Path(path)
        if not filepath.exists():
            return f"Error: {path} not found"

        body = {"name": filepath.name}
        if folder_id:
            fid = self._resolve_id(folder_id)
            body["parents"] = [fid]

        media = MediaFileUpload(str(filepath), resumable=True)
        f = self.files.create(
            body=body,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        return f"Uploaded: {f['name']} (ID: {_short_id(f['id'])})\n{f.get('webViewLink', '')}"

    def mkdir(self, name: str, parent_id: str | None = None) -> str:
        """Create a folder."""
        body = {"name": name, "mimeType": MIME_FOLDER}
        if parent_id:
            pid = self._resolve_id(parent_id)
            body["parents"] = [pid]

        f = self.files.create(
            body=body,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        return f"Created folder: {f['name']} (ID: {_short_id(f['id'])})"

    def trash(self, file_id: str) -> str:
        """Move a file to trash."""
        fid = self._resolve_id(file_id)
        self.files.update(fileId=fid, body={"trashed": True}, supportsAllDrives=True).execute()
        return f"Trashed: {fid}"

    def untrash(self, file_id: str) -> str:
        """Restore a file from trash."""
        fid = self._resolve_id(file_id)
        self.files.update(fileId=fid, body={"trashed": False}, supportsAllDrives=True).execute()
        return f"Restored: {fid}"

    def share(self, file_id: str, email: str, role: str = "reader") -> str:
        """Share a file with an email."""
        fid = self._resolve_id(file_id)
        self.permissions.create(
            fileId=fid,
            body={"type": "user", "role": role, "emailAddress": email},
            supportsAllDrives=True,
            sendNotificationEmail=True,
        ).execute()
        return f"Shared with {email} as {role}"

    def unshare(self, file_id: str, email: str) -> str:
        """Remove sharing for an email."""
        fid = self._resolve_id(file_id)
        perms = self.permissions.list(
            fileId=fid,
            fields="permissions(id, emailAddress)",
            supportsAllDrives=True,
        ).execute()

        for p in perms.get("permissions", []):
            if p.get("emailAddress", "").lower() == email.lower():
                self.permissions.delete(
                    fileId=fid,
                    permissionId=p["id"],
                    supportsAllDrives=True,
                ).execute()
                return f"Removed access for {email}"

        return f"No permission found for {email}"
