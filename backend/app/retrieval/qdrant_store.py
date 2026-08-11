from __future__ import annotations

from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.retrieval.embeddings import FastEmbedEncoder
from app.schemas import Chunk, RetrievedChunk


class QdrantStore:
    """Real Qdrant collection with dense, sparse, and server-side RRF search."""

    def __init__(self, settings: Settings, encoder: FastEmbedEncoder) -> None:
        self.settings = settings
        self.encoder = encoder
        self.client = AsyncQdrantClient(url=settings.qdrant_url, check_compatibility=False)

    @property
    def collection(self) -> str:
        return self.settings.qdrant_collection

    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.settings.dense_dimension, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        await self.client.create_payload_index(
            collection_name=self.collection,
            field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )

    @staticmethod
    def _filter(document_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
            ]
        )

    async def replace_document(self, document_id: str, chunks: Sequence[Chunk]) -> int:
        if not chunks:
            raise ValueError("Refusing to build an empty index")
        await self.ensure_collection()
        dense, sparse = await self.encoder.encode_documents([item.text for item in chunks])
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=self._filter(document_id)),
            wait=True,
        )
        for start in range(0, len(chunks), 64):
            points = [
                models.PointStruct(
                    id=chunks[index].id,
                    vector={
                        "dense": dense[index],
                        "sparse": models.SparseVector(
                            indices=sparse[index].indices, values=sparse[index].values
                        ),
                    },
                    payload=chunks[index].model_dump(mode="json"),
                )
                for index in range(start, min(start + 64, len(chunks)))
            ]
            await self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(chunks)

    async def search(
        self, question: str, document_id: str, top_k: int, mode: str | None = None
    ) -> list[RetrievedChunk]:
        mode = mode or self.settings.retrieval_mode
        query_filter = self._filter(document_id)
        if mode == "dense":
            response = await self.client.query_points(
                collection_name=self.collection,
                query=await self.encoder.dense_query(question),
                using="dense",
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        else:
            dense, sparse = await self.encoder.query(question)
            response = await self.client.query_points(
                collection_name=self.collection,
                prefetch=[
                    models.Prefetch(
                        query=dense,
                        using="dense",
                        filter=query_filter,
                        limit=self.settings.retrieval_prefetch_k,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                        using="sparse",
                        filter=query_filter,
                        limit=self.settings.retrieval_prefetch_k,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
        return self.convert_points(response.points)

    @staticmethod
    def convert_points(points: Sequence[object]) -> list[RetrievedChunk]:
        result: list[RetrievedChunk] = []
        for rank, point in enumerate(points, 1):
            payload = dict(getattr(point, "payload", {}) or {})
            result.append(
                RetrievedChunk(
                    chunk=Chunk.model_validate(payload),
                    score=float(getattr(point, "score", 0)),
                    rank=rank,
                )
            )
        return result

    async def healthy(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self.client.close()
