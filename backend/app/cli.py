from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.db import Database
from app.ingestion.chunkers import build_chunker
from app.ingestion.parser import DoclingParser
from app.ingestion.service import IngestionService
from app.models import Base
from app.repository import DocumentRepository
from app.retrieval.embeddings import FastEmbedEncoder
from app.retrieval.qdrant_store import QdrantStore


async def migrate() -> None:
    database = Database(get_settings())
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await database.close()
    print("MySQL schema is ready")


async def ingest(path: Path, force: bool) -> None:
    settings = get_settings()
    database = Database(settings)
    repository = DocumentRepository(database)
    encoder = FastEmbedEncoder(settings.dense_model, settings.sparse_model)
    store = QdrantStore(settings, encoder)
    service = IngestionService(
        DoclingParser(), build_chunker(settings.chunking_strategy), repository, store
    )
    try:
        result = await service.ingest(path, force)
        print(json.dumps(result, indent=2))
    finally:
        await store.close()
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apple filing RAG operator CLI")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("migrate")
    ingest_parser = subcommands.add_parser("ingest")
    ingest_parser.add_argument("pdf", type=Path)
    ingest_parser.add_argument("--force", action="store_true")
    evaluate_parser = subcommands.add_parser("evaluate")
    evaluate_parser.add_argument("--profile", choices=list("ABCDEFGHI"))
    evaluate_parser.add_argument("--document-id", default="aapl-2022-q3")
    args = parser.parse_args()
    if args.command == "migrate":
        asyncio.run(migrate())
    elif args.command == "ingest":
        asyncio.run(ingest(args.pdf, args.force))
    else:
        from evaluation.runner import run

        asyncio.run(run(args.profile, args.document_id))


if __name__ == "__main__":
    main()
