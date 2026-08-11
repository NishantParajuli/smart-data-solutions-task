from collections.abc import Sequence


def hit_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return float(bool(set(retrieved[:k]) & relevant)) if relevant else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return len(set(retrieved[:k]) & relevant) / len(relevant) if relevant else 0.0


def complete_evidence_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return float(bool(relevant) and relevant.issubset(set(retrieved[:k])))


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    for rank, item in enumerate(retrieved, 1):
        if item in relevant:
            return 1 / rank
    return 0.0
