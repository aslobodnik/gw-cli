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
        doc = self.docs.documents().get(documentId=fid, includeTabsContent=True).execute()
        tabs = self._flatten_tabs(doc.get("tabs", []))
        if not tabs:
            return self._content_text(doc.get("body", {}).get("content", [])).rstrip()
        if len(tabs) == 1:
            return self._content_text(tabs[0][1]).rstrip()
        return "\n\n".join(
            f"=== Tab: {title} ===\n{self._content_text(content).rstrip()}" for title, content in tabs
        )

    def _flatten_tabs(self, tabs: list) -> list:
        """Tabs and nested child tabs, in order, as (title, content) pairs."""
        out = []
        for tab in tabs:
            content = tab.get("documentTab", {}).get("body", {}).get("content", [])
            out.append((tab.get("tabProperties", {}).get("title", ""), content))
            out += self._flatten_tabs(tab.get("childTabs", []))
        return out

    def _content_text(self, content: list) -> str:
        """Paragraphs as text, tables as pipe-delimited rows."""
        text = []
        for element in content:
            if "paragraph" in element:
                for elem in element["paragraph"].get("elements", []):
                    run = elem.get("textRun")
                    if run:
                        text.append(run.get("content", ""))
            elif "table" in element:
                for row in element["table"].get("tableRows", []):
                    cells = [
                        " / ".join(self._content_text(cell.get("content", [])).split("\n")).strip(" /")
                        for cell in row.get("tableCells", [])
                    ]
                    text.append("| " + " | ".join(cells) + " |\n")
                text.append("\n")
        return "".join(text)

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
