"""Shared utilities for gw-cli."""

MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_DOC = "application/vnd.google-apps.document"
MIME_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_SLIDES = "application/vnd.google-apps.presentation"

FILE_FIELDS = "id, name, mimeType, size, modifiedTime, owners, shared, webViewLink, parents, trashed"
LIST_FIELDS = "id, name, mimeType, size, modifiedTime, shared"

MIME_DRAWING = "application/vnd.google-apps.drawing"

EXPORT_MIME_MAP = {
    MIME_DOC: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    MIME_SHEET: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    MIME_SLIDES: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    MIME_DRAWING: ("application/pdf", ".pdf"),
}


def _human_size(size_bytes: int | None) -> str:
    """Format byte size to human-readable string."""
    if size_bytes is None:
        return "-"
    size = int(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _short_id(file_id: str, length: int = 10) -> str:
    """Return last N chars of an ID for display."""
    return file_id[-length:]


def resolve_id(files_resource, short_or_full: str) -> str:
    """Resolve a short ID (last 10 chars) to full ID via paginated search."""
    if len(short_or_full) > 15:
        return short_or_full

    for q in ("trashed = false", "trashed = true"):
        page_token = None
        while True:
            resp = files_resource.list(
                q=q,
                fields="nextPageToken, files(id, name)",
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                if f["id"].endswith(short_or_full):
                    return f["id"]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    raise ValueError(f"No file found matching short ID: {short_or_full}")
