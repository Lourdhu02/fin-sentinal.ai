import pytest

from security.files import contained_path, safe_filename


@pytest.mark.parametrize("name", ["../secret", "..\\secret", "C:secret", "CON.pdf", "a:stream", "..", "a.", ".key"])
def test_unsafe_names_rejected(name, tmp_path):
    with pytest.raises(ValueError):
        contained_path(tmp_path, name)


def test_unicode_filename_preserved(tmp_path):
    name = "Facture été 2026.pdf"
    assert safe_filename(name) == name
    assert contained_path(tmp_path, name).parent == tmp_path.resolve()
