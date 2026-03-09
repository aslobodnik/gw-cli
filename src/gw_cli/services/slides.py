"""Google Slides API client."""

import uuid

from ..utils import MIME_SLIDES, _short_id, resolve_id


class SlidesClient:
    def __init__(self, slides_service, drive_service):
        self.slides = slides_service
        self.files = drive_service.files()

    def _resolve_id(self, short_or_full: str) -> str:
        return resolve_id(self.files, short_or_full)

    def create(self, title: str) -> str:
        """Create a blank Google Slides presentation."""
        f = self.files.create(
            body={"name": title, "mimeType": MIME_SLIDES},
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return f"Created presentation: {f['name']} (ID: {_short_id(f['id'])})\n{f.get('webViewLink', '')}"

    def read(self, file_id: str) -> str:
        """Read text content from all slides."""
        fid = self._resolve_id(file_id)
        pres = self.slides.presentations().get(presentationId=fid).execute()
        slides = pres.get("slides", [])
        if not slides:
            return "Empty presentation (no slides)."
        lines = []
        for i, slide in enumerate(slides, 1):
            lines.append(f"## Slide {i}")
            for element in slide.get("pageElements", []):
                shape = element.get("shape")
                if not shape:
                    continue
                text_elements = shape.get("text", {}).get("textElements", [])
                for te in text_elements:
                    run = te.get("textRun")
                    if run:
                        lines.append(run.get("content", "").rstrip())
            lines.append("")
        return "\n".join(lines).rstrip()

    def add_slide(self, file_id: str, title: str, body: str | None = None) -> str:
        """Add a new slide with title and optional body text."""
        fid = self._resolve_id(file_id)

        slide_id = f"slide_{uuid.uuid4().hex[:8]}"
        title_id = f"title_{uuid.uuid4().hex[:8]}"
        body_id = f"body_{uuid.uuid4().hex[:8]}"

        requests = [
            {
                "createSlide": {
                    "objectId": slide_id,
                    "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                    "placeholderIdMappings": [
                        {
                            "layoutPlaceholder": {"type": "TITLE"},
                            "objectId": title_id,
                        },
                        {
                            "layoutPlaceholder": {"type": "BODY", "index": 0},
                            "objectId": body_id,
                        },
                    ],
                }
            },
            {
                "insertText": {
                    "objectId": title_id,
                    "text": title,
                }
            },
        ]
        if body:
            requests.append(
                {
                    "insertText": {
                        "objectId": body_id,
                        "text": body,
                    }
                }
            )

        self.slides.presentations().batchUpdate(
            presentationId=fid, body={"requests": requests}
        ).execute()
        return f"Added slide '{title}' to presentation {_short_id(fid)}"
