"""Google Docs API client."""

from ..utils import MIME_DOC, _short_id, resolve_id


class DocsClient:
    def __init__(self, docs_service, drive_service):
        self.docs = docs_service
        self.files = drive_service.files()

    def _resolve_id(self, short_or_full: str) -> str:
        return resolve_id(self.files, short_or_full)

    def create(self, title: str) -> str:
        """Create a blank Google Doc."""
        f = self.files.create(
            body={"name": title, "mimeType": MIME_DOC},
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return f"Created doc: {f['name']} (ID: {_short_id(f['id'])})\n{f.get('webViewLink', '')}"

    def read(self, file_id: str) -> str:
        """Read a Google Doc as plain text."""
        fid = self._resolve_id(file_id)
        doc = self.docs.documents().get(documentId=fid).execute()
        text = []
        for element in doc.get("body", {}).get("content", []):
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for elem in paragraph.get("elements", []):
                run = elem.get("textRun")
                if run:
                    text.append(run.get("content", ""))
        return "".join(text).rstrip()

    def append(self, file_id: str, text: str) -> str:
        """Append text to end of a Google Doc."""
        fid = self._resolve_id(file_id)
        doc = self.docs.documents().get(documentId=fid).execute()
        content = doc.get("body", {}).get("content", [])
        end_index = content[-1]["endIndex"] - 1 if content else 1
        self.docs.documents().batchUpdate(
            documentId=fid,
            body={
                "requests": [
                    {"insertText": {"location": {"index": end_index}, "text": text}}
                ]
            },
        ).execute()
        return f"Appended {len(text)} chars to doc {_short_id(fid)}"
