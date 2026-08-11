import asyncio
from collections.abc import Sequence

from app.schemas import RetrievedChunk


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None

    async def rerank(
        self, question: str, candidates: Sequence[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = await asyncio.to_thread(CrossEncoder, self.model_name)
        scores = await asyncio.to_thread(
            self._model.predict,  # type: ignore[attr-defined]
            [(question, item.chunk.text) for item in candidates],
        )
        ranked = sorted(
            zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return [
            item.model_copy(update={"score": float(score), "rank": rank})
            for rank, (item, score) in enumerate(ranked[:top_k], 1)
        ]
