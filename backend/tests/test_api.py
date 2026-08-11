from types import SimpleNamespace

from app.api.query import router
from app.generation.provider import ExtractiveProvider
from app.schemas import Evidence
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeRepository:
    async def get_document(self, document_id: str) -> object:
        return SimpleNamespace(id=document_id, status="ready")


class FakeRetrieval:
    async def retrieve(self, question: str, document_id: str, top_k: int | None):
        item = Evidence(
            evidence_id="ev",
            child_id="child",
            document_id=document_id,
            page=4,
            section=["Statements"],
            element_type="table",
            content="Total net sales were 82,959.",
        )
        return [], [item], {"retrieval": 1, "rerank": 0, "parent_expansion": 0}


def test_query_api_smoke() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.repository = FakeRepository()
    app.state.retrieval = FakeRetrieval()
    app.state.provider = ExtractiveProvider()
    response = TestClient(app).post(
        "/api/query", json={"question": "What were total net sales?", "document_id": "doc"}
    )
    assert response.status_code == 200
    assert response.json()["citations"][0]["evidence_id"] == "ev"
