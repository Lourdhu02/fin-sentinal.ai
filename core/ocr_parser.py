from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

from config import get_settings


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str
    parser: str


class OCRParser:
    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}

    def parse_path(self, file_path: str | Path) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._clean_text(self.parse_pdf(path))
        if suffix in self.IMAGE_SUFFIXES:
            return self._clean_text(self.parse_image(path))
        if suffix in self.TEXT_SUFFIXES:
            return self._clean_text(self.parse_text_file(path))
        raise ValueError(f"Unsupported file type: {path.suffix}")

    def parse_pdf(self, file_path: str | Path) -> str:
        return "\n".join(page.text for page in self.parse_pdf_pages(file_path))

    def parse_pdf_pages(self, file_path: str | Path) -> list[ParsedPage]:
        import pdfplumber

        pages: list[ParsedPage] = []
        with pdfplumber.open(str(file_path)) as pdf:
            if len(pdf.pages) > get_settings().max_pdf_pages:
                raise ValueError("PDF exceeds configured page limit")
            for number, page in enumerate(pdf.pages, 1):
                text = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
                parser = "pdfplumber"
                if not text.strip():
                    try:
                        import pytesseract
                        image = page.to_image(resolution=150).original
                        try:
                            text = pytesseract.image_to_string(image, timeout=30)
                        finally:
                            image.close()
                        parser = "tesseract"
                    except Exception as exc:
                        raise ValueError(f"Page {number} requires OCR; install and provision Tesseract") from exc
                cleaned = self._clean_text(text)
                if not cleaned:
                    raise ValueError(f"No readable text on PDF page {number}")
                pages.append(ParsedPage(number, cleaned, parser))
        if not pages:
            raise ValueError("PDF contains no pages")
        return pages

    def parse_image(self, file_path: str | Path) -> str:
        from PIL import Image, ImageOps
        import pytesseract

        with Image.open(file_path) as image:
            prepared = ImageOps.grayscale(image)
            return pytesseract.image_to_string(prepared, config="--psm 6", timeout=30)

    def parse_text_file(self, file_path: str | Path) -> str:
        return Path(file_path).read_text(encoding="utf-8", errors="ignore")

    def _clean_text(self, text: str) -> str:
        normalized = text.replace("\x0c", "\n").replace("\r", "\n")
        normalized = re.sub(r"[^\S\n]+", " ", normalized)
        normalized = re.sub(r"\n{2,}", "\n", normalized)
        lines = [line.strip() for line in normalized.splitlines()]
        return "\n".join(line for line in lines if line)
