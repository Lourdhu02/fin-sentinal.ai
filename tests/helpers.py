import numpy as np


class Embedder:
    def embed_texts(self, texts):
        return np.ones((len(texts), 3), dtype=np.float32)

    def embed_query(self, text):
        return np.ones(3, dtype=np.float32)


class Vectors:
    def __init__(self):
        self.items = {}

    def add(self, embeddings, metadata):
        self.items.update({m["chunk_id"]: m for m in metadata})

    def delete_by_filter(self, filters):
        self.items = {k: v for k, v in self.items.items() if not all(v.get(f) == value for f, value in filters.items())}

    def search(self, embedding, top_k, filter_dict):
        # Deliberately unfiltered: SQL authorization must still prevent leakage.
        return list(self.items.values())[:top_k]


class Generator:
    def __init__(self):
        self.calls = []

    def generate(self, question, results, summaries, conversation_history):
        self.calls.append((question, results, conversation_history))
        return results[0]["text"] if results else "Insufficient evidence"


class Reranker:
    def rerank(self, question, results, top_n):
        return results[:top_n]
