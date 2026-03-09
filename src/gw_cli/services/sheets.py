"""Google Sheets API client."""

import json

from ..utils import MIME_SHEET, _short_id, resolve_id


class SheetsClient:
    def __init__(self, sheets_service, drive_service):
        self.sheets = sheets_service
        self.files = drive_service.files()

    def _resolve_id(self, short_or_full: str) -> str:
        return resolve_id(self.files, short_or_full)

    def create(self, title: str) -> str:
        """Create a blank Google Sheet."""
        f = self.files.create(
            body={"name": title, "mimeType": MIME_SHEET},
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return f"Created sheet: {f['name']} (ID: {_short_id(f['id'])})\n{f.get('webViewLink', '')}"

    def read(self, file_id: str, range_: str = "Sheet1") -> str:
        """Read cells from a Google Sheet, formatted as a markdown table."""
        fid = self._resolve_id(file_id)
        result = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=fid, range=range_)
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            return "Empty sheet (no data)."
        col_count = max(len(r) for r in rows)
        padded = [r + [""] * (col_count - len(r)) for r in rows]
        header = "| " + " | ".join(str(c) for c in padded[0]) + " |"
        sep = "| " + " | ".join("---" for _ in range(col_count)) + " |"
        lines = [header, sep]
        for row in padded[1:]:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines)

    def write(self, file_id: str, range_: str, values_json: str) -> str:
        """Write cells to a Google Sheet."""
        fid = self._resolve_id(file_id)
        values = json.loads(values_json)
        result = (
            self.sheets.spreadsheets()
            .values()
            .update(
                spreadsheetId=fid,
                range=range_,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )
        updated = result.get("updatedCells", 0)
        return f"Updated {updated} cells in {range_}"
