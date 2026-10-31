from __future__ import annotations

import hashlib
from pathlib import Path
from threading import RLock

from core.chunking import chunk_text
from core.citations import verify_citations
from core.conversations import ConversationStore, require_scope
from core.embedder import LocalEmbedder
from core.facts import extract_facts
from core.fusion import reciprocal_rank_fusion
from core.ingestion import IngestionService
from core.llm_engine import OllamaEngine
from core.retriever import Retriever
from database.db_manager import DatabaseManager
from database.documents import DocumentRepository
from security.audit_logger import AuditLogger


class FinSentinelPipeline:
    def __init__(self, db_manager=None, ingestion_service=None, embedder=None,
                 vector_store=None, llm_engine=None, audit_logger=None, retriever=None):
        self.db = db_manager or DatabaseManager()
        self.documents = DocumentRepository(self.db)
        self.ingestion = ingestion_service or IngestionService()
        self.embedder = embedder or LocalEmbedder()
        if vector_store is None:
            from database.vector_store import ChromaDBVectorStore
            vector_store = ChromaDBVectorStore()
        self.vector_store = vector_store
        self.retriever = retriever or Retriever(self.embedder, self.vector_store)
        self.llm_engine = llm_engine or OllamaEngine()
        self.audit_logger = audit_logger or AuditLogger(self.db)
        self.conversations = ConversationStore()
        # One GPU operation at a time, including deletion and conversation reset.
        self.lock = RLock()

    def ingest_and_store(self, source_path, session_id, user_id=None):
        require_scope(user_id, session_id)
        with self.lock:
            processed = []
            files = self.ingestion.get_supported_files(source_path)
            if not files:
                raise ValueError("No supported documents found")
            for path in files:
                doc_id = None
                try:
                    with Path(path).open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    doc_id, indexed = self.documents.begin(user_id, Path(path).name, digest)
                    if indexed:
                        processed.append({"path": str(path), "status": "stored", "document_id": doc_id})
                        continue
                    self.documents.status(user_id, doc_id, "processing")
                    document = self.ingestion.ingest(path)[0]
                    if document.error or not document.text.strip():
                        raise ValueError(document.error or "Document contains no readable text")
                    metadata = []
                    for page in document.pages:
                        for index, chunk in enumerate(chunk_text(page.text)):
                            chunk_id = hashlib.sha256(f"{doc_id}:{page.page}:{index}:chunks-v1".encode()).hexdigest()
                            metadata.append({**chunk, "chunk_id": chunk_id, "document_id": doc_id,
                                             "session_id": session_id, "user_id": user_id,
                                             "file_name": Path(path).name, "page": page.page,
                                             "parser": page.parser, "content_hash": digest})
                    if not metadata:
                        raise ValueError("No readable chunks extracted")
                    embeddings = self.embedder.embed_texts([m["text"] for m in metadata])
                    self.vector_store.delete_by_filter({"session_id": session_id, "document_id": doc_id})
                    self.vector_store.add(embeddings, metadata)
                    self.documents.save_chunks(user_id, doc_id, metadata, extract_facts(document.pages))
                    self.documents.status(user_id, doc_id, "indexed")
                    processed.append({"path": str(path), "status": "stored", "document_id": doc_id})
                except Exception as exc:
                    if doc_id is not None:
                        self.documents.status(user_id, doc_id, "failed", type(exc).__name__)
                    processed.append({"path": str(path), "status": "error", "error": "Document processing failed"})
            stored = sum(p["status"] == "stored" for p in processed)
            return {"processed_count": len(files), "stored_count": stored, "success_count": stored,
                    "error_count": len(files) - stored, "failed_count": len(files) - stored,
                    "documents": processed}

    def query(self, question, session_id, user_id=None, top_k=20):
        require_scope(user_id, session_id)
        if not question.strip() or len(question) > 8000 or not 1 <= top_k <= 100:
            raise ValueError("Invalid question or retrieval limit")
        with self.lock:
            embedding = self.embedder.embed_query(question)
            results = self.vector_store.search(embedding, top_k=top_k,
                                               filter_dict={"session_id": session_id, "user_id": user_id})
            results = self.documents.authorized_chunks(user_id, results)
            lexical = self.documents.search(user_id, question, limit=top_k)
            results = reciprocal_rank_fusion(results, lexical, limit=40)
            results = self.retriever.rerank(question, results, top_n=10)
            response = self.llm_engine.generate(question, results, [],
                conversation_history=self.conversations.history(user_id, session_id)[-6:])
            if results and not verify_citations(response, results):
                response = "I could not produce a properly cited answer. Please inspect the source evidence."
            self.audit_logger.log_interaction(user_id, "query", question, response)
            self.conversations.append(user_id, session_id, question, response)
            return {"query": question, "response": response, "results": results}

    def reset_conversation(self, session_id, user_id):
        require_scope(user_id, session_id)
        with self.lock:
            self.conversations.reset(user_id, session_id)

    def delete_document(self, filename, user_id):
        session = f"user_{user_id}_default"
        require_scope(user_id, session)
        with self.lock:
            document = self.documents.get(user_id, filename)
            if document:
                self.documents.status(user_id, document["id"], "deleting")
            self.vector_store.delete_by_filter({"session_id": session, "file_name": filename})
            self.documents.delete(user_id, filename)
            self.conversations.reset(user_id, session)
