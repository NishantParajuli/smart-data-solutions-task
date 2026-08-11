from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import yaml
from app.config import Settings
from app.db import Database
from app.ingestion.chunkers import build_chunker
from app.repository import DocumentRepository
from app.retrieval.embeddings import FastEmbedEncoder
from app.retrieval.qdrant_store import QdrantStore
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.service import RetrievalService

from evaluation.metrics import complete_evidence_at_k, hit_at_k, recall_at_k, reciprocal_rank

ROOT = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def evidence_matches(evidence: list[object], catalog: dict[str, Any]) -> list[list[str]]:
    matches_by_rank: list[list[str]] = []
    for item in evidence:
        content = normalize(getattr(item, "content", ""))
        page = getattr(item, "page", -1)
        matches: list[str] = []
        for key, target in catalog.items():
            pages = target.get("pages", [target.get("page")])
            if page not in pages:
                continue
            anchors = [normalize(anchor) for anchor in target["anchors"]]
            if all(anchor in content for anchor in anchors):
                matches.append(key)
        matches_by_rank.append(matches)
    return matches_by_rank


async def run_profile(profile_id: str, profile: dict[str, Any], document_id: str) -> dict[str, Any]:
    collection = f"evaluation_{profile_id.lower()}_{profile['chunker']}"
    settings = Settings(
        qdrant_collection=collection,
        retrieval_mode=profile["retrieval"],
        chunking_strategy=profile["chunker"],
        reranker_model=None,
    )
    database = Database(settings)
    repository = DocumentRepository(database)
    document = await repository.load_parsed(document_id)
    if document is None:
        await database.close()
        raise RuntimeError("Canonical document is missing; run the ingestion command first")
    encoder = FastEmbedEncoder(settings.dense_model, settings.sparse_model)
    store = QdrantStore(settings, encoder)
    chunker = build_chunker(profile["chunker"])
    await store.replace_document(document_id, chunker.chunks(document))
    reranker = (
        CrossEncoderReranker("cross-encoder/ms-marco-MiniLM-L-6-v2")
        if profile["reranker"]
        else None
    )
    service = RetrievalService(settings, store, repository, reranker)
    dataset = load_jsonl(ROOT / "dataset.jsonl")
    catalog = json.loads((ROOT / "evidence_catalog.json").read_text())
    rows: list[dict[str, Any]] = []
    for question in dataset:
        if not question["required_evidence"]:
            continue
        started = time.perf_counter()
        _, evidence, timings = await service.retrieve(question["question"], document_id, 5)
        latency = round((time.perf_counter() - started) * 1000, 2)
        relevant = set(question["required_evidence"])
        matches_by_rank = evidence_matches(evidence, catalog)
        matched = list(dict.fromkeys(key for matches in matches_by_rank for key in matches))
        ranked = [
            next((key for key in matches if key in relevant), f"unmatched-{rank}")
            for rank, matches in enumerate(matches_by_rank, 1)
        ]
        rows.append(
            {
                "id": question["id"],
                "question": question["question"],
                "category": question["category"],
                "expected": sorted(relevant),
                "matched": matched,
                "retrieved": [
                    {"id": item.evidence_id, "page": item.page, "score": item.score}
                    for item in evidence
                ],
                "hit_at_5": hit_at_k(ranked, relevant),
                "recall_at_5": recall_at_k(ranked, relevant),
                "complete_evidence_at_5": complete_evidence_at_k(ranked, relevant),
                "reciprocal_rank": reciprocal_rank(ranked, relevant),
                "latency_ms": latency,
                "timings_ms": timings,
            }
        )
    summary = {
        "profile": profile_id,
        "name": profile["name"],
        "questions": len(rows),
        **{
            metric: round(sum(row[metric] for row in rows) / len(rows), 4)
            for metric in (
                "hit_at_5",
                "recall_at_5",
                "complete_evidence_at_5",
                "reciprocal_rank",
            )
        },
        "mean_retrieval_latency_ms": round(sum(row["latency_ms"] for row in rows) / len(rows), 2),
    }
    destination = ROOT / "results" / profile_id.lower()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    await store.close()
    await database.close()
    return summary


async def run(
    selected: str | None = None, document_id: str = "aapl-2022-q3"
) -> list[dict[str, Any]]:
    profiles = yaml.safe_load((ROOT / "profiles.yaml").read_text())["profiles"]
    selected_profiles = {selected: profiles[selected]} if selected else profiles
    summaries = []
    for profile_id, profile in selected_profiles.items():
        summary = await run_profile(profile_id, profile, document_id)
        summaries.append(summary)
        print(json.dumps(summary))
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=list("ABCDEFGHI"))
    parser.add_argument("--document-id", default="aapl-2022-q3")
    args = parser.parse_args()
    asyncio.run(run(args.profile, args.document_id))


if __name__ == "__main__":
    main()
