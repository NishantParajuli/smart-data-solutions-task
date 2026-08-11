from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Apple Filing Evidence"
    app_version: str = "0.1.0"
    database_url: str = "mysql+aiomysql://rag:rag@localhost:3306/rag"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "apple_parent_child_hybrid"
    dense_model: str = "BAAI/bge-small-en-v1.5"
    dense_dimension: int = 384
    sparse_model: str = "Qdrant/bm25"
    chunking_strategy: Literal["fixed", "document_aware", "semantic", "parent_child"] = (
        "parent_child"
    )
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    retrieval_prefetch_k: int = Field(default=24, ge=1, le=100)
    reranker_model: str | None = None
    llm_provider: Literal["google", "extractive"] = "extractive"
    llm_api_key: str | None = None
    llm_model: str = "gemma-4-31b-it"
    max_context_characters: int = 16_000
    documents_dir: Path = Path("data/documents")
    artifacts_dir: Path = Path("data/artifacts")
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
