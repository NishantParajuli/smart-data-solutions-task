from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, evidence, health, query
from app.config import get_settings
from app.db import Database
from app.generation.provider import build_provider
from app.ingestion.renderer import EvidenceRenderer
from app.repository import DocumentRepository
from app.retrieval.embeddings import FastEmbedEncoder
from app.retrieval.qdrant_store import QdrantStore
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.service import RetrievalService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(settings)
    repository = DocumentRepository(database)
    encoder = FastEmbedEncoder(settings.dense_model, settings.sparse_model)
    store = QdrantStore(settings, encoder)
    reranker = CrossEncoderReranker(settings.reranker_model) if settings.reranker_model else None
    app.state.settings = settings
    app.state.database = database
    app.state.repository = repository
    app.state.store = store
    app.state.retrieval = RetrievalService(settings, store, repository, reranker)
    app.state.provider = build_provider(settings)
    app.state.renderer = EvidenceRenderer(settings.artifacts_dir)
    yield
    await store.close()
    await database.close()


app = FastAPI(title="Apple Filing Evidence API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(evidence.router)
