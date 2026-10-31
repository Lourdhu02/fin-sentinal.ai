"""Tenant-scoped source of truth; vector indexes are rebuildable projections."""
import hashlib
import json
import re

from database.db_manager import DatabaseManager


class DocumentRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.db.connection.executescript("""
        CREATE TABLE IF NOT EXISTS documents_v1 (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            filename TEXT NOT NULL, content_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('processing','indexed','failed','deleting')),
            facts_json TEXT NOT NULL DEFAULT '{}', error TEXT,
            UNIQUE(user_id, filename)
        );
        CREATE INDEX IF NOT EXISTS documents_user ON documents_v1(user_id);
        CREATE TABLE IF NOT EXISTS chunks_v1 (
            id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents_v1(id) ON DELETE CASCADE,
            text TEXT NOT NULL, metadata_json TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, text);
        CREATE TRIGGER IF NOT EXISTS chunks_remove_fts AFTER DELETE ON chunks_v1 BEGIN
            DELETE FROM chunks_fts WHERE chunk_id=old.id;
        END;
        """)
        self.db.connection.commit()

    @staticmethod
    def scope(user_id):
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Authenticated user ID required")

    def begin(self, user_id, filename, digest):
        self.scope(user_id)
        doc_id = hashlib.sha256(f"{user_id}\0{filename}\0{digest}".encode()).hexdigest()
        existing = self.db.connection.execute(
            "SELECT * FROM documents_v1 WHERE user_id=? AND filename=?", (user_id, filename)
        ).fetchone()
        if existing:
            if existing["content_hash"] != digest:
                raise ValueError("Document name exists with different content; delete before replacing")
            return existing["id"], existing["status"] == "indexed"
        with self.db.connection:
            self.db.connection.execute(
                "INSERT INTO documents_v1(id,user_id,filename,content_hash,status) VALUES(?,?,?,?,'processing')",
                (doc_id, user_id, filename, digest),
            )
        return doc_id, False

    def get(self, user_id, filename):
        self.scope(user_id)
        row = self.db.connection.execute(
            "SELECT * FROM documents_v1 WHERE user_id=? AND filename=?", (user_id, filename)
        ).fetchone()
        return dict(row) if row else None

    def list(self, user_id):
        self.scope(user_id)
        return [dict(row) for row in self.db.connection.execute(
            "SELECT id,filename,status FROM documents_v1 WHERE user_id=? ORDER BY filename", (user_id,)
        )]

    def status(self, user_id, doc_id, status, error=None):
        self.scope(user_id)
        with self.db.connection:
            self.db.connection.execute(
                "UPDATE documents_v1 SET status=?,error=? WHERE id=? AND user_id=?", (status, error, doc_id, user_id)
            )

    def save_chunks(self, user_id, doc_id, chunks, facts):
        self.scope(user_id)
        with self.db.connection:
            owned = self.db.connection.execute("SELECT 1 FROM documents_v1 WHERE id=? AND user_id=?", (doc_id, user_id)).fetchone()
            if not owned:
                raise PermissionError("Document does not belong to user")
            self.db.connection.execute("DELETE FROM chunks_v1 WHERE document_id=?", (doc_id,))
            for chunk in chunks:
                self.db.connection.execute("INSERT INTO chunks_v1 VALUES(?,?,?,?)", (chunk["chunk_id"], doc_id, chunk["text"], json.dumps(chunk)))
                self.db.connection.execute("INSERT INTO chunks_fts VALUES(?,?)", (chunk["chunk_id"], chunk["text"]))
            self.db.connection.execute("UPDATE documents_v1 SET facts_json=? WHERE id=?", (json.dumps(facts), doc_id))

    def search(self, user_id, question, limit=30):
        self.scope(user_id)
        terms = re.findall(r"\w+", question, flags=re.UNICODE)[:32]
        if not terms:
            return []
        expression = " OR ".join('"' + term + '"' for term in terms)
        rows = self.db.connection.execute("""
            SELECT c.metadata_json FROM chunks_fts f
            JOIN chunks_v1 c ON c.id=f.chunk_id
            JOIN documents_v1 d ON d.id=c.document_id
            WHERE chunks_fts MATCH ? AND d.user_id=? AND d.status='indexed'
            ORDER BY bm25(chunks_fts) LIMIT ?
        """, (expression, user_id, max(1, min(limit, 100))))
        return [json.loads(row[0]) for row in rows]

    def delete(self, user_id, filename):
        self.scope(user_id)
        with self.db.connection:
            self.db.connection.execute("DELETE FROM documents_v1 WHERE user_id=? AND filename=?", (user_id, filename))
