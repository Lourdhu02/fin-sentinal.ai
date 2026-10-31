import asyncio
from io import BytesIO

from starlette.datastructures import UploadFile
import pytest

from core.uploads import save_upload


def save(tmp_path, name, content, limit=100):
    return asyncio.run(save_upload(UploadFile(BytesIO(content), filename=name), tmp_path, limit))


def test_upload_limit_and_staging_cleanup(tmp_path):
    with pytest.raises(ValueError, match="size"):
        save(tmp_path, "a.txt", b"1234", limit=3)
    assert list(tmp_path.iterdir()) == []


def test_upload_does_not_overwrite(tmp_path):
    save(tmp_path, "a.txt", b"original")
    with pytest.raises(FileExistsError):
        save(tmp_path, "a.txt", b"replacement")
    assert (tmp_path / "a.txt").read_bytes() == b"original"


def test_fake_pdf_rejected(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        save(tmp_path, "a.pdf", b"not a pdf")
    assert list(tmp_path.iterdir()) == []
