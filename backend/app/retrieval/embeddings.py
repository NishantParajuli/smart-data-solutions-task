from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class FastEmbedEncoder:
    """Lazy local dense and BM25 sparse embeddings."""

    def __init__(self, dense_model: str, sparse_model: str) -> None:
        self.dense_model_name = dense_model
        self.sparse_model_name = sparse_model
        self._dense: object | None = None
        self._sparse_model: object | None = None
        self._lock = asyncio.Lock()

    async def _load(self) -> None:
        if self._dense is not None and self._sparse_model is not None:
            return
        async with self._lock:
            if self._dense is not None and self._sparse_model is not None:
                return

            def load() -> tuple[object, object]:
                from fastembed import SparseTextEmbedding, TextEmbedding

                return (
                    TextEmbedding(model_name=self.dense_model_name),
                    SparseTextEmbedding(model_name=self.sparse_model_name),
                )

            self._dense, self._sparse_model = await asyncio.to_thread(load)

    @staticmethod
    def _convert_sparse(value: object) -> SparseVector:
        return SparseVector(
            indices=value.indices.tolist(),
            values=value.values.tolist(),
        )

    async def encode_documents(
        self, texts: Sequence[str]
    ) -> tuple[list[list[float]], list[SparseVector]]:
        await self._load()

        def encode() -> tuple[list[list[float]], list[SparseVector]]:
            assert self._dense is not None and self._sparse_model is not None
            dense = [item.tolist() for item in self._dense.embed(list(texts))]  # type: ignore[attr-defined]
            sparse = [
                self._convert_sparse(item)
                for item in self._sparse_model.embed(list(texts))  # type: ignore[attr-defined]
            ]
            return dense, sparse

        return await asyncio.to_thread(encode)

    async def dense_query(self, text: str) -> list[float]:
        await self._load()
        assert self._dense is not None
        return await asyncio.to_thread(
            lambda: next(iter(self._dense.query_embed(text))).tolist()  # type: ignore[attr-defined]
        )

    async def sparse_query(self, text: str) -> SparseVector:
        await self._load()
        assert self._sparse_model is not None
        return await asyncio.to_thread(
            lambda: self._convert_sparse(
                next(iter(self._sparse_model.query_embed(text)))  # type: ignore[attr-defined]
            )
        )

    async def query(self, text: str) -> tuple[list[float], SparseVector]:
        dense, sparse = await asyncio.gather(self.dense_query(text), self.sparse_query(text))
        return dense, sparse
