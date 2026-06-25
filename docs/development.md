# Development Guide

## Local setup (no Docker)

```bash
# 1. Install Ollama
# https://ollama.ai — follow platform instructions

# 2. Pull required models
ollama pull llama3.2
ollama pull nomic-embed-text

# 3. Clone and set up Python environment
git clone ...
cd lumen
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
```

Edit `.env` for local development:
```bash
OLLAMA_BASE_URL=http://localhost:11434
SQLITE_URL=sqlite+aiosqlite:///./data/lumen.db
CHROMA_PERSIST_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
```

```bash
# 5. Create data directories
mkdir -p data/uploads data/chroma

# 6. Run
python -m app.main
```

Open http://localhost:8080

## Project structure recap

```
app/
├── main.py        — entry point, wires FastAPI + NiceGUI
├── config.py      — all settings from env vars
├── schemas.py     — Pydantic models
├── models.py      — SQLAlchemy ORM
├── database.py    — engine + session factory
├── deps.py        — FastAPI dependency injectors
├── startup.py     — startup sequence
├── services/      — business logic (no HTTP, no UI)
├── api/           — FastAPI route handlers
└── ui/            — NiceGUI pages and components
```

## API documentation

FastAPI auto-generates interactive docs at:
- **Swagger UI**: http://localhost:8080/api/docs
- **ReDoc**: http://localhost:8080/api/redoc

## Adding a new document format

1. Add a parser function in `app/services/document_parser.py`
2. Register it in `_PARSERS` dict at the bottom of that file
3. Add the extension to `ALLOWED_EXTENSIONS` in `app/api/documents.py`
4. Add the library to `requirements.txt`

## Changing the RAG prompt

Edit `SYSTEM_PROMPT` in `app/services/rag.py`.

**Important:** the citation regex in `rag.query()` expects exactly:
```
[Source: <document name>, Page <number>]
```
If you change the citation format in the prompt, update `_CITATION_RE` to match.

## Changing chunk size

1. Update `CHUNK_SIZE` and `CHUNK_OVERLAP` in `.env` (or from the Settings page)
2. Re-index all documents — the Settings page has a "Re-index All" button,
   or call `POST /api/documents/{id}/reindex` for each document.

Existing chunks in ChromaDB were created with the old size and will persist
until re-indexed. Mixing chunk sizes in one collection is harmless but
may produce inconsistent retrieval quality.

## NiceGUI notes

- Each browser tab gets its own local variable scope within `@ui.page` functions.
  Use `nonlocal` to mutate state from inner async functions.
- `@ui.refreshable` wraps a component so it can be re-rendered with `.refresh()`.
- `ui.timer(interval, callback)` runs a callback on a recurring interval.
  Set `active=False` to start stopped; set `timer.active = True/False` at runtime.
- `ui.navigate.to("/path")` navigates without a full page reload.
- ChromaDB calls are synchronous — wrap in `asyncio.to_thread()` in async code.

## Docker rebuild after code changes

```bash
docker compose build app
docker compose up -d app
```

Ollama data is in a named volume and is not affected by rebuilds.

## Resetting all data

```bash
docker compose down
rm -rf data/uploads/* data/chroma/* data/lumen.db data/settings.json
docker compose up -d
```
