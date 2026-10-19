"""
Nexis AI - ChromaDB Local Vector Store & Embeddings Pipeline
Provides isolated per-session vector indices, local ONNX all-MiniLM-L6-v2 embeddings,
and cosine similarity retrieval.
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("NexisCRAG.VectorStore")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Persistent DB storage location
CHROMA_DATA_DIR = os.getenv("CHROMA_PERSIST_DIR", os.path.join(os.getcwd(), "data", "chroma"))
os.makedirs(CHROMA_DATA_DIR, exist_ok=True)


class VectorStoreManager:
    """
    Manages local ChromaDB collections with strict session-level isolation
    and local sentence-transformers (all-MiniLM-L6-v2) embeddings.
    """

    def __init__(self, persist_dir: str = CHROMA_DATA_DIR):
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        # ChromaDB DefaultEmbeddingFunction loads all-MiniLM-L6-v2 ONNX locally
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        logger.info(f"Initialized ChromaDB Persistent Vector Store at '{self.persist_dir}'")

    def _sanitize_collection_name(self, session_id: str) -> str:
        """
        Chroma collection names must be 3-63 chars, start/end with alphanumeric,
        and only contain alphanumeric, underscores, or hyphens.
        """
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id.strip())
        if not clean or len(clean) < 3:
            clean = f"sess_{clean}"
        if len(clean) > 60:
            clean = clean[:60]
        # Ensure starts with alphanumeric
        if not clean[0].isalnum():
            clean = f"s_{clean}"
        return f"rag_{clean}"[:63]

    def get_or_create_collection(self, session_id: str):
        """Retrieves or creates an isolated ChromaDB collection for the given session."""
        coll_name = self._sanitize_collection_name(session_id)
        return self.client.get_or_create_collection(
            name=coll_name,
            embedding_function=self.embedding_fn,
            metadata={"session_id": session_id, "hnsw:space": "cosine"}
        )

    def add_chunks(self, session_id: str, chunks: List[Dict[str, Any]]) -> int:
        """
        Embeds and stores chunks into the session's isolated Chroma collection.
        """
        if not chunks:
            return 0

        collection = self.get_or_create_collection(session_id)
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for c in chunks:
            chunk_id = c["chunk_id"]
            text = c["text"]
            meta = c.get("metadata", {})
            # Ensure session_id is tagged in metadata
            meta["session_id"] = session_id

            # Clean metadata values to primitive types for Chroma
            cleaned_meta = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    cleaned_meta[k] = v
                else:
                    cleaned_meta[k] = str(v)

            ids.append(chunk_id)
            documents.append(text)
            metadatas.append(cleaned_meta)

        # Batch upsert into Chroma
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

        logger.info(f"Indexed {len(ids)} chunks into session collection '{collection.name}'")
        return len(ids)

    def query(self, session_id: str, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs cosine similarity search against the session's document vectors.
        Returns top candidate chunks with content, metadata, and relevance distance.
        """
        try:
            coll_name = self._sanitize_collection_name(session_id)
            # Check if collection exists
            existing_colls = [c.name for c in self.client.list_collections()]
            if coll_name not in existing_colls:
                return []

            collection = self.client.get_collection(
                name=coll_name,
                embedding_function=self.embedding_fn
            )
            count = collection.count()
            if count == 0:
                return []

            actual_k = min(top_k, count)
            results = collection.query(
                query_texts=[query_text],
                n_results=actual_k,
                include=["documents", "metadatas", "distances"]
            )

            matched_chunks: List[Dict[str, Any]] = []
            if results and results.get("documents") and len(results["documents"]) > 0:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [None] * len(docs)

                for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
                    # Cosine similarity score = 1.0 - distance
                    similarity = max(0.0, 1.0 - float(dist)) if dist is not None else 1.0
                    matched_chunks.append({
                        "chunk_id": doc_id,
                        "content": doc,
                        "metadata": meta,
                        "distance": float(dist) if dist is not None else 0.0,
                        "similarity": round(similarity, 4)
                    })

            return matched_chunks

        except Exception as exc:
            logger.warning(f"Error querying Chroma vector store for session '{session_id}': {exc}")
            return []

    def has_documents(self, session_id: str) -> bool:
        """Checks if the given session has any indexed documents."""
        try:
            coll_name = self._sanitize_collection_name(session_id)
            existing_colls = [c.name for c in self.client.list_collections()]
            if coll_name not in existing_colls:
                return False
            collection = self.client.get_collection(
                name=coll_name,
                embedding_function=self.embedding_fn
            )
            return collection.count() > 0
        except Exception:
            return False

    def list_documents(self, session_id: str) -> List[str]:
        """Lists distinct source files indexed in the given session."""
        try:
            coll_name = self._sanitize_collection_name(session_id)
            existing_colls = [c.name for c in self.client.list_collections()]
            if coll_name not in existing_colls:
                return []
            collection = self.client.get_collection(
                name=coll_name,
                embedding_function=self.embedding_fn
            )
            records = collection.get(include=["metadatas"])
            metas = records.get("metadatas", []) or []
            files = list({m.get("source_file") for m in metas if m and m.get("source_file")})
            return sorted(files)
        except Exception:
            return []

    def get_all_chunks(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all chunks stored in the session's collection.
        Used for BM25 sparse index compilation.
        """
        try:
            coll_name = self._sanitize_collection_name(session_id)
            existing_colls = [c.name for c in self.client.list_collections()]
            if coll_name not in existing_colls:
                return []
            collection = self.client.get_collection(
                name=coll_name,
                embedding_function=self.embedding_fn
            )
            count = collection.count()
            if count == 0:
                return []
            records = collection.get(include=["documents", "metadatas"])
            docs = records.get("documents", []) or []
            metas = records.get("metadatas", []) or []
            ids = records.get("ids", []) or []

            all_chunks = []
            for c_id, doc, meta in zip(ids, docs, metas):
                all_chunks.append({
                    "chunk_id": c_id,
                    "content": doc,
                    "metadata": meta or {}
                })
            return all_chunks
        except Exception as exc:
            logger.warning(f"Error fetching all chunks for session '{session_id}': {exc}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Deletes collection and embeddings for a session."""
        try:
            coll_name = self._sanitize_collection_name(session_id)
            self.client.delete_collection(name=coll_name)
            return True
        except Exception:
            return False


# Global singleton instance
vector_store = VectorStoreManager()
