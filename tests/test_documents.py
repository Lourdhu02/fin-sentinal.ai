from database.db_manager import DatabaseManager
from database.documents import DocumentRepository


def test_document_index_is_tenant_scoped_and_idempotent():
    db = DatabaseManager()
    alice = db.create_user("alice", "hash").id
    bob = db.create_user("bob", "hash").id
    repo = DocumentRepository(db)
    doc, done = repo.begin(alice, "a.txt", "abc")
    assert not done
    repo.save_chunks(alice, doc, [{"chunk_id": "chunk1", "text": "invoice ZX900", "file_name": "a.txt"}], {})
    repo.status(alice, doc, "indexed")
    assert repo.begin(alice, "a.txt", "abc") == (doc, True)
    assert repo.search(bob, "ZX900") == []
    assert repo.search(alice, "ZX900")[0]["chunk_id"] == "chunk1"
    repo.delete(bob, "a.txt")
    assert repo.get(alice, "a.txt")
    repo.delete(alice, "a.txt")
    assert repo.search(alice, "ZX900") == []
