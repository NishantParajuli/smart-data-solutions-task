from __future__ import annotations

import asyncio
from pathlib import Path

from app.ingestion.chunkers import Chunker
from app.ingestion.parser import DoclingParser, sha256_file
from app.repository import DocumentRepository
from app.retrieval.qdrant_store import QdrantStore


class IngestionService:
    def __init__(
        self,
        parser: DoclingParser,
        chunker: Chunker,
        repository: DocumentRepository,
        store: QdrantStore,
    ) -> None:
        self.parser = parser
        self.chunker = chunker
        self.repository = repository
        self.store = store

    async def ingest(self, path: Path, force: bool = False) -> dict[str, object]:
        path = await asyncio.to_thread(path.resolve)
        is_file = await asyncio.to_thread(path.is_file)
        if not is_file or path.suffix.lower() != ".pdf":
            raise ValueError(f"PDF does not exist: {path}")
        digest = sha256_file(path)
        existing = await self.repository.matching_ready_document(
            digest, self.parser.version, self.chunker.version
        )
        if existing and not force:
            return {"document_id": existing.id, "status": "skipped", "reason": "unchanged"}

        document = self.parser.parse(path)
        chunks = self.chunker.chunks(document)
        await self.repository.store_canonical(document, self.parser.version, self.chunker.version)
        try:
            count = await self.store.replace_document(document.id, chunks)
        except Exception:
            await self.repository.set_status(document.id, "failed")
            raise
        await self.repository.set_status(document.id, "ready")
        return {
            "document_id": document.id,
            "status": "ready",
            "elements": len(document.elements),
            "chunks": count,
            "sha256": document.sha256,
        }
