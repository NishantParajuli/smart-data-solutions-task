from evaluation.metrics import (
    complete_evidence_at_k,
    hit_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_retrieval_metrics() -> None:
    retrieved = ["wrong", "a", "b"]
    relevant = {"a", "b"}
    assert hit_at_k(retrieved, relevant) == 1
    assert recall_at_k(retrieved, relevant) == 1
    assert complete_evidence_at_k(retrieved, relevant) == 1
    assert reciprocal_rank(retrieved, relevant) == 0.5
