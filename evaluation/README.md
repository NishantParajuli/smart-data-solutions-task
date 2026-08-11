# Retrieval evaluation

This subsystem compares retrieval choices without adding experiment controls to
the normal application. The serving API does not import the evaluator.

## Gold set

`dataset.jsonl` contains a concise selection of source-verified questions from
the supplied filing: table lookup, narrative lookup, multi-evidence, calculation,
and one unanswerable prompt. `evidence_catalog.json` defines the expected physical
PDF page and content anchors. Generated chunk/evidence IDs are intentionally not
gold labels, so all chunking strategies are judged against the same source facts.

The unanswerable prompt is retained for manual abstention checks and excluded
from retrieval metrics because it has no relevant evidence set.

## Profiles

| ID | Chunking | Retrieval | Reranker |
|---|---|---|---|
| A | Fixed | Dense | No |
| B | Fixed | Hybrid | No |
| C | Document-aware | Dense | No |
| D | Document-aware | Hybrid | No |
| E | Semantic | Dense | No |
| F | Semantic | Hybrid | No |
| G | Parent-child | Dense | No |
| H | Parent-child | Hybrid | No |
| I | Parent-child | Hybrid | Cross-encoder |

Every profile uses its own Qdrant collection and deterministically replaces the
document points before querying. Hybrid profiles store/search real FastEmbed
dense and BM25 sparse vectors and use Qdrant RRF.

## Run

First start, migrate, and ingest the filing as described in the root README.

```bash
# all nine profiles
make evaluate

# one profile
docker compose exec api python -m app.cli evaluate --profile H

# render the compact Markdown result table
docker compose exec api python -m evaluation.summarize
```

Host-side equivalent (with MySQL and Qdrant URLs configured):

```bash
PYTHONPATH=backend python -m evaluation.runner --profile H
```

The reranker extra is needed only for profile I. The first semantic/reranker run
may download its local model.

## Outputs and metrics

Each `evaluation/results/<profile>/` directory contains:

- `results.jsonl`: question, expected and matched evidence units, ranked evidence,
  per-question metrics, and latency;
- `summary.json`: macro averages for the profile.

Reported metrics are intentionally small and inspectable:

- **Hit@5:** at least one required evidence unit appears in the first five;
- **evidence Recall@5:** fraction of all required units found in the first five;
- **Complete Evidence@5:** every required unit appears in the first five;
- **MRR:** reciprocal rank of the first relevant unit;
- **mean retrieval latency:** observed end-to-end retrieval and parent expansion.

## Current results

These results were generated from this repository's implementation after a fresh
Docling extraction and per-profile Qdrant rebuild. No source-repository result
files were reused.

| Profile | Hit@5 | Recall@5 | Complete@5 | MRR | Latency ms |
|---|---:|---:|---:|---:|---:|
| A. Fixed + dense | 0.636 | 0.591 | 0.545 | 0.576 | 11.8 |
| B. Fixed + hybrid | 0.818 | 0.773 | 0.727 | 0.609 | 15.2 |
| C. Document-aware + dense | 0.636 | 0.591 | 0.545 | 0.491 | 12.1 |
| D. Document-aware + hybrid | 0.727 | 0.682 | 0.636 | 0.545 | 13.3 |
| E. Semantic + dense | 0.636 | 0.591 | 0.545 | 0.495 | 11.9 |
| F. Semantic + hybrid | 0.727 | 0.682 | 0.636 | 0.545 | 12.8 |
| G. Parent-child + dense | 0.909 | 0.864 | 0.818 | 0.735 | 12.6 |
| H. Parent-child + hybrid | **0.909** | **0.864** | **0.818** | **0.836** | **14.9** |
| I. Parent-child + hybrid + reranker | 0.818 | 0.773 | 0.727 | 0.758 | 2546.4 |

Profile H is the application default. Profile I reduced both MRR and evidence
coverage while adding approximately 2.5 seconds of mean latency.
The per-question files show the remaining misses and should be read before
drawing conclusions from this deliberately small, single-document benchmark.
