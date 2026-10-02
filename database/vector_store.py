import chromadb
from chromadb.config import Settings
from pathlib import Path
from typing import Any
import numpy as np

from config import get_settings

class ChromaDBVectorStore:
    def __init__(self, persist_dir: str | Path | None = None) -> None:
        self.settings = get_settings()
        self.persist_dir = str(persist_dir or self.settings.data_dir / "chroma")
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize persistent ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create the main collection
        self.collection = self.client.get_or_create_collection(
            name="finsentinel_docs",
            metadata={"hnsw:space": "l2"}
        )

    def add(self, embeddings: np.ndarray, metadatas: list[dict[str, Any]]) -> list[str]:
        if len(embeddings) == 0:
            return []
            
        import uuid
        ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
        
        # Chroma expects list of lists for embeddings
        embedding_list = embeddings.tolist()
        
        self.collection.add(
            embeddings=embedding_list,
            metadatas=metadatas,
            ids=ids
        )
        return ids

    def documents(self, filter_dict: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """All stored chunk metadata (with vector_id) matching the filter."""
        if self.collection.count() == 0:
            return []
        where_clause = None
        if filter_dict:
            items = list(filter_dict.items())
            where_clause = {items[0][0]: items[0][1]} if len(items) == 1 else {"$and": [{k: v} for k, v in items]}
        got = self.collection.get(where=where_clause, include=["metadatas"])
        return [{**dict(meta), "vector_id": vid} for vid, meta in zip(got["ids"], got["metadatas"])]

    def search(self, query_embedding: np.ndarray, top_k: int = 5, filter_dict: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []

        # Convert numpy array to list
        query_vector = query_embedding.tolist()
        if isinstance(query_vector[0], list):
            query_vector = query_vector[0] # Chroma wants a 1D list for a single query

        # Build ChromaDB filter
        where_clause = None
        if filter_dict:
            if len(filter_dict) == 1:
                k, v = list(filter_dict.items())[0]
                where_clause = {k: v}
            else:
                where_clause = {"$and": [{k: v} for k, v in filter_dict.items()]}

        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k, self.collection.count()),
                where=where_clause
            )
            
            formatted_results = []
            if results["metadatas"] and results["metadatas"][0]:
                for idx in range(len(results["metadatas"][0])):
                    item = dict(results["metadatas"][0][idx])
                    item["score"] = float(results["distances"][0][idx]) if results["distances"] else 0.0
                    item["vector_id"] = results["ids"][0][idx]
                    formatted_results.append(item)
                    
            return formatted_results
        except Exception as e:
            print(f"ChromaDB search error: {e}")
            return []

    def delete_by_filter(self, filter_dict: dict[str, Any]) -> None:
        where_clause = None
        if filter_dict:
            if len(filter_dict) == 1:
                k, v = list(filter_dict.items())[0]
                where_clause = {k: v}
            else:
                where_clause = {"$and": [{k: v} for k, v in filter_dict.items()]}
                
        if where_clause:
            self.collection.delete(where=where_clause)

    def save(self) -> None:
        # ChromaDB automatically persists when using PersistentClient
        pass

    def reset(self) -> None:
        try:
            self.client.delete_collection("finsentinel_docs")
            self.collection = self.client.get_or_create_collection("finsentinel_docs")
        except Exception:
            pass
