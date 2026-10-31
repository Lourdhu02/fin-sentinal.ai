"""Paragraph-aware chunks with deterministic page-local offsets."""
import re


def chunk_text(text: str, size: int = 900, overlap: int = 120):
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Require 0 <= overlap < chunk size")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            breaks = list(re.finditer(r"\n\s*\n|\n|(?<=\.)\s", text[start:end]))
            if breaks and breaks[-1].end() > size // 2:
                end = start + breaks[-1].end()
        if text[start:end].strip():
            chunks.append({"text": text[start:end], "start_char": start, "end_char": end})
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
