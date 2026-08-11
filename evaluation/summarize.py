import json
from pathlib import Path


def main() -> None:
    rows = [
        json.loads(path.read_text())
        for path in sorted(Path("evaluation/results").glob("*/summary.json"))
    ]
    headers = ["Profile", "Hit@5", "Recall@5", "Complete@5", "MRR", "Latency ms"]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        print(
            f"| {row['profile']}. {row['name']} | {row['hit_at_5']:.3f} | "
            f"{row['recall_at_5']:.3f} | {row['complete_evidence_at_5']:.3f} | "
            f"{row['reciprocal_rank']:.3f} | {row['mean_retrieval_latency_ms']:.1f} |"
        )


if __name__ == "__main__":
    main()
