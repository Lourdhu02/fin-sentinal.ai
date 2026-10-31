from database.db_manager import DatabaseManager


def test_separate_database_paths_do_not_share_connections(tmp_path):
    first = DatabaseManager(tmp_path / "first.db")
    second = DatabaseManager(tmp_path / "second.db")
    first.create_user("alice", "hash")
    assert second.get_user("alice") is None
    first.close()
    second.close()
