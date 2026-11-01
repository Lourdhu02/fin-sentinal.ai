import hashlib
import json
import os
from pathlib import Path
import tempfile


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_path(root: Path, relative: str) -> Path:
    if "\\" in relative or ":" in relative:
        raise ValueError("Source paths must be relative POSIX paths")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Source escapes corpus directory")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Source is missing or escapes corpus directory")
    return resolved


def write_json(path: Path, value):
    """Publish a complete artifact exclusively; never overwrite earlier results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".evaluation-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
