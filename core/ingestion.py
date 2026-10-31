from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.ocr_parser import OCRParser, ParsedPage


@dataclass(slots=True)
class IngestedDocument:
    path: str
    file_type: str
    text: str
    error: str | None = None
    pages: list[ParsedPage] = field(default_factory=list)


class IngestionService:
    SUPPORTED_SUFFIXES = {
        ".pdf": "pdf",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".bmp": "image",
        ".tif": "image",
        ".tiff": "image",
        ".txt": "text",
        ".md": "text",
        ".csv": "text",
        ".json": "text",
        ".xml": "text",
        ".html": "text",
        ".htm": "text",
    }

    def __init__(self, parser: OCRParser | None = None) -> None:
        self.parser = parser or OCRParser()

    def ingest(self, source_path: str | Path) -> list[IngestedDocument]:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        return [self._ingest_file(fp) for fp in self.get_supported_files(path)]

    def ingest_text(self, source_path: str | Path) -> str:
        return "\n\n".join(d.text for d in self.ingest(source_path) if d.text)

    def detect_file_type(self, file_path: str | Path) -> str:
        return self.SUPPORTED_SUFFIXES.get(Path(file_path).suffix.lower(), "unknown")

    def get_supported_files(self, source_path: str | Path) -> list[Path]:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if path.is_file():
            return [path] if path.suffix.lower() in self.SUPPORTED_SUFFIXES else []
        # FIXED: respect ALL supported suffixes, not just pdf/png/jpg/jpeg
        return sorted(
            fp for fp in path.rglob("*")
            if fp.is_file() and fp.suffix.lower() in self.SUPPORTED_SUFFIXES
        )

    def _ingest_file(self, file_path: Path) -> IngestedDocument:
        file_type = self.detect_file_type(file_path)
        try:
            if file_type == "pdf":
                pages = self.parser.parse_pdf_pages(file_path)
                return IngestedDocument(path=str(file_path), file_type=file_type,
                                        text="\n\n".join(p.text for p in pages), pages=pages)
            text = self.parser.parse_path(file_path)
            if not text.strip():
                raise ValueError("Document contains no readable text")
            return IngestedDocument(path=str(file_path), file_type=file_type, text=text,
                                    pages=[ParsedPage(1, text, "tesseract" if file_type == "image" else "text")])
        except Exception as exc:
            return IngestedDocument(path=str(file_path), file_type=file_type, text="", error=str(exc))
