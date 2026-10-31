from config import get_settings


def test_settings_use_isolated_directory(tmp_path):
    assert get_settings().data_dir == tmp_path
    assert get_settings().db_path == tmp_path / "test.db"
