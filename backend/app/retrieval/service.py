from __future__ import annotations

import time

from app.config import Settings
from app.repository import DocumentRepository
from app.retrieval.qdrant_store import QdrantStore
from app.retrieval.reranker import CrossEncoderReranker
from app.schemas import Evidence, RetrievedChunk


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        store: QdrantStore,
        repository: DocumentRepository,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.repository = repository
        self.reranker = reranker

    async def retrieve(
        self, question: str, document_id: str, top_k: int | None = None
    ) -> tuple[list[RetrievedChunk], list[Evidence], dict[str, int]]:
        requested = top_k or self.settings.retrieval_top_k
        started = time.perf_counter()
        candidates = await self.store.search(
            question, document_id, max(requested, self.settings.retrieval_prefetch_k)
        )
        retrieval_ms = round((time.perf_counter() - started) * 1000)
        rerank_ms = 0
        if self.reranker:
            rerank_started = time.perf_counter()
            candidates = await self.reranker.rerank(question, candidates, requested)
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000)
        selected = self._deduplicate(candidates, requested)
        expansion_started = time.perf_counter()
        evidence = self._fit_budget(await self.repository.expand(selected))
        expansion_ms = round((time.perf_counter() - expansion_started) * 1000)
        return (
            selected,
            evidence,
            {
                "retrieval": retrieval_ms,
                "rerank": rerank_ms,
                "parent_expansion": expansion_ms,
            },
        )

    @staticmethod
    def _deduplicate(candidates: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        result: list[RetrievedChunk] = []
        seen: set[str] = set()
        for item in candidates:
            key = (
                item.chunk.id
                if item.chunk.metadata.get("evidence_mode") == "direct"
                else item.chunk.parent_id
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            if len(result) == top_k:
                break
        return result

    def _fit_budget(self, evidence: list[Evidence]) -> list[Evidence]:
        remaining = self.settings.max_context_characters
        result: list[Evidence] = []
        for item in evidence:
            if remaining <= 0:
                break
            if len(item.content) > remaining:
                item = item.model_copy(
                    update={"content": item.content[:remaining] + "\n[truncated]"}
                )
            result.append(item)
            remaining -= len(item.content)
        return result
