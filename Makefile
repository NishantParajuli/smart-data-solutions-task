PDF := data/documents/Apple_2022_Q3_10-Q.pdf

.PHONY: up migrate ingest evaluate test lint down

up:
	docker compose up --build -d

migrate:
	docker compose exec api python -m app.cli migrate

ingest:
	docker compose exec api python -m app.cli ingest /app/$(PDF)

evaluate:
	docker compose exec api python -m app.cli evaluate

test:
	pytest -q
	npm --prefix frontend run build

lint:
	ruff check backend evaluation

down:
	docker compose down

