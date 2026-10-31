"""Portable filename and resolved-path checks for untrusted document names."""
import re
from pathlib import Path, PureWindowsPath


RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise ValueError("Invalid filename")
    if "/" in filename or "\\" in filename or PureWindowsPath(filename).drive:
        raise ValueError("Path components are not allowed")
    if len(filename) > 180 or filename != filename.strip().rstrip("."):
        raise ValueError("Invalid filename length or trailing characters")
    if re.search(r'[\x00-\x1f<>:"|?*]', filename):
        raise ValueError("Invalid filename characters")
    if filename.split(".", 1)[0].upper() in RESERVED or filename.startswith("."):
        raise ValueError("Reserved filename")
    return filename


def contained_path(directory: Path, filename: str) -> Path:
    safe_filename(filename)
    root = directory.resolve()
    target = root / filename
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError("Document path escapes storage directory")
    return target
