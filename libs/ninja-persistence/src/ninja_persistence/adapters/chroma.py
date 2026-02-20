"""Chroma vector adapter implementing the Repository protocol."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema


class ChromaVectorAdapter:
    """Chroma-backed vector store adapter.

    Implements the Repository protocol with native semantic search support.

    Requires the ``chromadb`` optional dependency:
        pip install ninja-persistence[chroma]
    """

    def __init__(self, entity: EntitySchema, client: Any = None) -> None:
        self._entity = entity
        self._client = client
        self._collection_name = entity.collection_name or entity.name.lower()

    def _get_collection(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "ChromaVectorAdapter requires a Chroma client instance. Pass it via the `client` constructor parameter."
            )
        return self._client.get_or_create_collection(name=self._collection_name)

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        coll = self._get_collection()
        result = coll.get(ids=[id])
        if not result["ids"]:
            return None
        doc: dict[str, Any] = {"id": id}
        if result.get("metadatas"):
            doc.update(result["metadatas"][0])
        if result.get("documents"):
            doc["document"] = result["documents"][0]
        return doc

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        coll = self._get_collection()
        kwargs: dict[str, Any] = {"limit": limit}
        if filters and "where" in filters:
            kwargs["where"] = filters["where"]
        result = coll.get(**kwargs)
        docs: list[dict[str, Any]] = []
        for i, doc_id in enumerate(result["ids"]):
            doc: dict[str, Any] = {"id": doc_id}
            if result.get("metadatas") and i < len(result["metadatas"]):
                doc.update(result["metadatas"][i])
            if result.get("documents") and i < len(result["documents"]):
                doc["document"] = result["documents"][i]
            docs.append(doc)
        return docs

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        coll = self._get_collection()
        doc_id = data.get("id", "")
        document = data.get("document", "")
        metadata = {k: v for k, v in data.items() if k not in ("id", "document", "embedding")}
        embedding = data.get("embedding")
        kwargs: dict[str, Any] = {
            "ids": [doc_id],
            "documents": [document],
        }
        if metadata:
            kwargs["metadatas"] = [metadata]
        if embedding:
            kwargs["embeddings"] = [embedding]
        coll.add(**kwargs)
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        coll = self._get_collection()
        kwargs: dict[str, Any] = {"ids": [id]}
        if "document" in patch:
            kwargs["documents"] = [patch["document"]]
        metadata = {k: v for k, v in patch.items() if k not in ("id", "document", "embedding")}
        if metadata:
            kwargs["metadatas"] = [metadata]
        if "embedding" in patch:
            kwargs["embeddings"] = [patch["embedding"]]
        coll.update(**kwargs)
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        coll = self._get_collection()
        coll.delete(ids=[id])
        return True

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        coll = self._get_collection()
        result = coll.query(query_texts=[query], n_results=limit)
        docs: list[dict[str, Any]] = []
        if result["ids"] and result["ids"][0]:
            for i, doc_id in enumerate(result["ids"][0]):
                doc: dict[str, Any] = {"id": doc_id}
                if result.get("metadatas") and result["metadatas"][0] and i < len(result["metadatas"][0]):
                    doc.update(result["metadatas"][0][i])
                if result.get("documents") and result["documents"][0] and i < len(result["documents"][0]):
                    doc["document"] = result["documents"][0][i]
                if result.get("distances") and result["distances"][0] and i < len(result["distances"][0]):
                    doc["_distance"] = result["distances"][0][i]
                docs.append(doc)
        return docs

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        coll = self._get_collection()
        coll.update(ids=[id], embeddings=[embedding])
