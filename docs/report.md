# RAG for Apple’s 2022 Q3 Form 10-Q

**Live demo:** [https://demo.nishantparajuli.com.np/](https://demo.nishantparajuli.com.np/)

## 1. Problem and requirements

The assignment is to conceptualize and implement a retrieval-augmented
generation system for one supplied Apple Form 10-Q. 

The repository uses Python, object-oriented services, FastAPI,
SQLAlchemy, MySQL, Qdrant, Docling, PyMuPDF, FastEmbed, React/Vite, Docker Compose,
Git, a focused test suite, and a small retrieval benchmark.

The observable contract is intentionally narrow. An operator ingests the fixed
PDF through a CLI. A user can list documents, submit a question, inspect an
answer or abstention, and open a PDF crop for cited evidence. No public upload,
reindex, administration, or browser-supplied model key endpoints are present.

## 2. Architecture

```text
PDF → Docling → canonical elements → MySQL
                         ↓
                  selected chunker
                         ↓
            dense + BM25 sparse vectors → Qdrant
                         ↓
       retrieval → RRF → parent expansion → evidence
                         ↓
     structured answer / abstention → citation allowlist
                         ↓
             FastAPI → React + PDF crop panel
```

MySQL owns canonical document meaning: document SHA, parser/chunker versions,
text/table/figure elements, physical page, section path, structured table data,
bounding box, and parent relationship. Qdrant owns a rebuildable search
projection. This separation makes evidence expansion and image rendering
possible without treating a vector payload as the primary document database.

The application default is parent-child chunking, hybrid dense+sparse retrieval,
Qdrant reciprocal-rank fusion, six returned parents, and no reranker. The project
may use Google/Gemma structured generation when configured; otherwise an
explicit extractive provider selects the best supported passage. All provider
credentials stay server-side.

Ingestion is idempotent. If SHA, parser version, and chunker
version match a ready document, the run is skipped. Otherwise the service parses
and stores canonical elements, deletes that document’s existing Qdrant points,
inserts the new dense and sparse vectors, and marks the document ready. A failure
marks it failed and a later operator run rebuilds it. There is no publication
generation protocol or state machine.

## 3. Document extraction

Docling is the primary parser because it exposes layout-aware text, table, and
picture items instead of flattening every page into a string. OCR is disabled:
the supplied PDF has a high-quality digital text layer, and OCR would add model
cost plus transcription opportunities without improving coverage.

Each canonical element receives a deterministic document-scoped ID and retains:

- physical PDF page and section path;
- text or Markdown content;
- table columns, period headers, and row dictionaries;
- nearby scale context such as “dollars in millions”;
- figure caption state and layout bounding box;
- a parent ID used for coherent evidence expansion.

Duplicate or empty table headers are made stable instead of dropped. Numeric
cell values remain in their source strings so commas, parentheses, currency
marks, and reported rounding are visible. A nearby scale line is
associated with a table but is not silently converted into inferred units.

Narrative parents are bounded by physical page and section. Text children point
to those parents, tables and figures are their own canonical parent. This avoids
joining unrelated pages and makes the evidence crop a meaningful region.

PyMuPDF opens the original stored PDF on demand. The renderer converts Docling’s
bottom-left coordinates when necessary, applies a small margin, and caches a PNG
whose filename includes a rendering fingerprint.

## 4. Chunking and retrieval

Four chunkers implement one small interface:

1. **Fixed** creates page-local 2,000-character windows with 100-character
   overlap. It is the transparent baseline.
2. **Document-aware** groups narrative by page and section, bounds it at about
   1,600 characters, and preserves small tables and figures atomically.
3. **Semantic** begins with the same structural groups. Only an oversized
   narrative group is split using adjacent dense-embedding distance; tables and
   figures remain structural.
4. **Parent-child** indexes roughly 650-character narrative children and one
   searchable fact string per table row. Results expand to the canonical
   narrative/table/figure parent in MySQL.

Every Qdrant point carries a deterministic chunk ID, document ID, parent ID,
page, section, element type, embedding text, evidence content, and small strategy
metadata. The validated default collection contained 532 points. Its schema had
a named 384-dimensional cosine `dense` vector and a named `sparse` vector.

FastEmbed supplies BGE-small dense embeddings and Qdrant/BM25 sparse embeddings.
For hybrid search, each retriever prefetches candidates under the same document
filter; Qdrant then performs reciprocal-rank fusion. Parent IDs are deduplicated
before MySQL expansion. The optional cross-encoder reranks only the candidate
set and is lazy-loaded.

The normal interface does not expose these strategies. They exist to support a
small offline comparison and to make the default an evidence-backed decision.

## 5. Tables, figures, citations, and calculations

Table-row children include the row label, all period/value pairs, and the nearby
scale line. Retrieval can therefore match “Services,” “June 25, 2022,” and
“19,604” together. Expansion returns the full table with structured rows,
columns, period headers, and the source crop. The live table query retrieved the
Services row and preserved 19,604, 17,486, the two quarter headers, and the
“dollars in millions” context.

Figures are retained as searchable caption/layout elements with bounding boxes.
This filing contains graphics and an Apple mark but not a rich chart set. The
system does not claim to understand uncaptioned pixels; a vision-language model
would be a future extension. The crop still lets a human inspect the region.

Generation has five explicit checks: parse one JSON object; reject malformed
output; keep only citation IDs in the retrieved evidence set; abstain when an
answer has no valid citation; and execute only typed calculations locally. The
no-key extractive fallback uses question/evidence overlap to choose a passage and
abstains when none of the question’s meaningful terms occur in evidence.

Calculation requests contain operation, two decimal operands, evidence ID,
metric, period, and unit. The calculator accepts percentage, absolute change,
and percentage change. Each operand’s numeric value must appear in its cited
retrieved evidence; division by zero and invalid decimals are rejected. Decimal
arithmetic and formatting are deterministic. The implementation deliberately
does not try to prove arbitrary generated prose through regex claim rules.

## 6. Evaluation

The evaluator is independent of the serving application. Eleven answerable,
source-verified questions cover tables, narrative, calculations, and
multi-evidence retrieval; one unanswerable question is retained for manual
abstention checks. Gold units are matched by physical page plus normalized
content anchors, allowing a fact repeated in both a note and MD&A to count as
valid evidence. Each profile uses an isolated Qdrant collection and is rebuilt
from the new canonical extraction.

| Profile | Hit@5 | Recall@5 | Complete@5 | MRR | Mean ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| A Fixed + dense | 0.636 | 0.591 | 0.545 | 0.576 | 11.8 |
| B Fixed + hybrid | 0.818 | 0.773 | 0.727 | 0.609 | 15.2 |
| C Document-aware + dense | 0.636 | 0.591 | 0.545 | 0.491 | 12.1 |
| D Document-aware + hybrid | 0.727 | 0.682 | 0.636 | 0.545 | 13.3 |
| E Semantic + dense | 0.636 | 0.591 | 0.545 | 0.495 | 11.9 |
| F Semantic + hybrid | 0.727 | 0.682 | 0.636 | 0.545 | 12.8 |
| G Parent-child + dense | 0.909 | 0.864 | 0.818 | 0.735 | 12.6 |
| **H Parent-child + hybrid** | **0.909** | **0.864** | **0.818** | **0.836** | **14.9** |
| I Parent-child + hybrid + reranker | 0.818 | 0.773 | 0.727 | 0.758 | 2546.4 |

Hybrid retrieval improved every comparable non-reranked dense profile. The
parent-child profiles had the best evidence coverage; hybrid raised MRR over
parent-child dense. The reranker reduced both MRR and coverage and added about
2. 5 seconds of mean latency. These are descriptive results for a
small, single-filing gold set—not a claim of statistical significance.

## 7. Selected design and tradeoffs

Profile H remains the application default. It combines the strongest measured
coverage with coherent parents, row-level table search, source images, and low
latency. Fixed hybrid was competitive, but a fixed hit can cut a table or return
an arbitrary window as evidence. Parent expansion is easier for a reviewer to
trust and for a candidate to explain.

The cross-encoder stays optional. Its latency and reduced top-five coverage are
not justified in this CPU demonstration. Semantic chunking also did not improve
over document-aware chunking here: most filing sections were already short,
strong structural units, so embedding-based breaks had little room to help.

The source implementation’s useful parser, renderer, chunking ideas, embedding
wrapper, Qdrant RRF path, parent expansion, frontend evidence pattern, and gold
questions informed this build. Configuration, database access, ingestion,
generation, calculator, routes, evaluator, UI logic, and documentation were
rewritten. Publication generations, deep protocols/factories, the large regex
grounding validator, public administration, extensive deployment tooling,
security/operations treatises, hundreds of tests, stale results, and the learning
handbook were dropped.

## 8. Limitations and next steps

The system has been exercised only on this born-digital Apple 10-Q. It does not
prove general filing-layout coverage, hosted LLM answer quality, public
availability, compliance, or production reliability. Figure retrieval preserves
regions but does not analyze pixels. The extractive fallback is auditable but
less fluent than a reviewed hosted model. A failed direct Qdrant replacement
requires another ingestion run.

Next steps should follow observed failures: expand the gold catalog where the
same fact has multiple valid filing locations; test another issuer and a scanned
filing; add a small vision captioner only if figure questions justify it; and
inspect parent-child misses before changing model size. The current per-question
JSONL outputs make that improvement loop concrete.

## 9. Reproduction

```bash
cp .env.example .env
make up
make migrate
make ingest

curl -s http://localhost:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"aapl-2022-q3", \
       "question":"What drove Services growth in Q3 2022?"}'

make test
make evaluate
python -m evaluation.summarize
make down
```
