from types import SimpleNamespace

from app.retrieval.qdrant_store import QdrantStore


def test_qdrant_hybrid_result_conversion() -> None:
    payload = {
        "id": "507d0d8f-9cad-5a2c-b01f-82f41cf6bfca",
        "document_id": "doc",
        "parent_id": "parent",
        "page": 10,
        "section": ["Revenue"],
        "element_type": "table_row_child",
        "text": "Services 19,604",
        "evidence_content": "table",
        "metadata": {"evidence_mode": "parent"},
    }
    converted = QdrantStore.convert_points([SimpleNamespace(payload=payload, score=0.75)])
    assert converted[0].chunk.parent_id == "parent"
    assert converted[0].score == 0.75
    assert converted[0].rank == 1
