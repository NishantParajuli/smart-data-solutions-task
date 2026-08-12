# Apple Filing Evidence

Apple Filing Evidence is a compact retrieval-augmented generation (RAG) system
for Apple's 2022 Q3 Form 10-Q. It answers questions about narrative text,
financial tables, and extracted figures while showing the filing evidence behind
every supported answer.

**Live demo:** [https://demo.nishantparajuli.com.np/](https://demo.nishantparajuli.com.np/)

(It is locally hosted so it maybe subject to powercuts and internet disruptions)

The repository is deliberately sized for review: the normal path is one parser,
four understandable chunking choices, one MySQL schema, one Qdrant adapter, four
API routes, and one focused web interface.

## Architecture

```text
Apple 10-Q PDF
      |
      v
Docling (OCR off) ----> PyMuPDF evidence crops
      |
      v
canonical text / table / figure elements
      |
      +----> MySQL (provenance and parents)
      |
      v
parent-child chunks (default)
      |
      v
FastEmbed dense + BM25 sparse vectors
      |
      v
Qdrant retrieval ----> reciprocal-rank fusion
      |
      v
parent expansion / citation allowlist
      |
      v
Gemma/Google JSON answer or extractive fallback
      |
      v
FastAPI ----> React evidence workspace
```

## Core decisions

- **Canonical extraction lives in MySQL.** Docling preserves physical PDF page,
  section path, content, table rows/columns and period headers, nearby scale text,
  figures, and bounding boxes. Vectors are a rebuildable projection.
- **OCR is disabled.** The supplied filing is born-digital; OCR would add cost and
  transcription risk without useful coverage.
- **Parent-child is the application default.** Small narrative and table-row
  children retrieve precisely. The canonical text/table/figure parent supplies
  coherent answer context and the citation crop.
- **Hybrid means real dense and sparse vectors.** FastEmbed produces both named
  vector types and Qdrant performs reciprocal-rank fusion. No embeddings are
  written to ad-hoc files.
- **Grounding is explicit.** The optional LLM must return JSON. Unknown citation
  IDs are removed, and an answer with no retrieved citation becomes an
  abstention.
- **Arithmetic stays local.** Typed calculation requests use an allowlist and
  `Decimal`; each operand must appear in its cited evidence.
- **Rebuilds are simple.** An unchanged SHA/parser/chunker combination is skipped.
  A changed document stores canonical elements, replaces its Qdrant points, then
  becomes ready.

## Quick start

Requirements: Docker with Compose and approximately 6 GB of free space for the
Docling and embedding images/models.

```bash
cp .env.example .env
make up
make migrate
make ingest
```

Open <http://localhost:8080>. The first build and ingestion download local
document and embedding models, so they take longer than later runs.

The stack contains:

- `mysql`: canonical document elements and provenance;
- `qdrant`: dense and sparse vectors;
- `api`: FastAPI plus the operator CLI;
- `web`: the built React application behind Nginx.

MySQL and Qdrant are private to the Compose network. Nginx exposes the web UI and
proxies `/api` and `/health` on port 8080.

## Ingest the filing

The supplied PDF is committed at
`data/documents/Apple_2022_Q3_10-Q.pdf` for a reproducible assessment demo.

```bash
docker compose exec api python -m app.cli ingest \
  /app/data/documents/Apple_2022_Q3_10-Q.pdf
```

Run `make ingest` for the same command. Add `--force` only when intentionally
rebuilding unchanged input.

## Query the API

Only four public endpoints exist:

```text
GET  /health
GET  /api/documents
POST /api/query
GET  /api/evidence/{evidence_id}/image
```

Example:

```bash
curl -s http://localhost:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "document_id": "aapl-2022-q3",
    "question": "What drove Services growth in the third quarter of 2022?"
  }'
```

The response contains the answer or explicit abstention, citation objects,
retrieved evidence, optional calculations, and compact stage timings.

## LLM configuration

The default `extractive` provider needs no secret and returns the highest-ranked
filing passage with its citation. To use the server-side Google provider:

```dotenv
LLM_PROVIDER=google
LLM_API_KEY=your-key-here
LLM_MODEL=gemma-4-31b-it
```

Restart the API after changing `.env`. Provider keys never pass through the
browser and `.env` is ignored by Git.

## Web interface

The interface presents the indexed filing status, four suggested questions, a
single question box, a grounded-answer or abstention card, deterministic
calculation details, and ranked citations. Selecting evidence opens a source
panel with the PyMuPDF crop; extracted text remains available if an image cannot
load. Retrieval timings are collapsed under a small debug disclosure.

## Development commands

```bash
make up        # build and start all four services
make migrate   # initialize the MySQL schema
make ingest    # parse and index the supplied filing
make test      # focused Python suite and production frontend build
make lint      # Python lint
make down      # stop services; named data volumes remain
```

For a host-side Python workflow:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,ingestion]'
PYTHONPATH=backend pytest -q
```

## Evaluation

An optional nine-profile retrieval benchmark comparing fixed, document-aware,
semantic, and parent-child chunking is available under `evaluation/`; its
detailed commands, gold evidence contract, per-question outputs, and result table
live in `evaluation/README.md`.
