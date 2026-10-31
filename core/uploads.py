from pathlib import Path
import tempfile

from security.files import contained_path


ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".json", ".xml", ".md"}


def validate_content(path: Path, suffix: str):
    with path.open("rb") as stream:
        prefix = stream.read(1024)
    if not prefix:
        raise ValueError("Empty upload")
    signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
    if suffix in signatures:
        if not prefix.startswith(signatures[suffix]):
            raise ValueError("Content does not match file extension")
    elif b"\x00" in prefix:
        raise ValueError("Binary content is not allowed for text uploads")
    else:
        prefix.decode("utf-8", errors="strict")


async def save_upload(upload, directory: Path, max_bytes: int) -> Path:
    target = contained_path(directory, upload.filename or "")
    suffix = target.suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("Unsupported file type")
    directory.mkdir(parents=True, exist_ok=True)
    # Staging is in the same directory so link publication is atomic and exclusive.
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".upload-", delete=False) as stream:
        staging = Path(stream.name)
        try:
            count = 0
            while chunk := await upload.read(64 * 1024):
                count += len(chunk)
                if count > max_bytes:
                    raise ValueError("Upload exceeds configured size limit")
                stream.write(chunk)
        except BaseException:
            stream.close()
            staging.unlink(missing_ok=True)
            raise
    try:
        validate_content(staging, suffix)
        import os
        os.link(staging, target)
        return target
    finally:
        staging.unlink(missing_ok=True)
