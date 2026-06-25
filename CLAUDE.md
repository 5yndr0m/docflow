# Lumen — Developer Context for Claude

## What this project is

Lumen is a local-first AI document analyzer for business analyst teams. It ingests documents (PDF, DOCX, PPTX, XLSX, TXT), builds a vector index, and answers questions with source citations. Everything runs on-prem via Ollama — no cloud APIs.

## Stack summary

- **FastAPI + NiceGUI** — single process, single port (8080). NiceGUI mounts onto FastAPI via `ui.run_with(app)`.
- **Ollama** — local LLM and embedding model. Two Docker services: `lumen_app` and `lumen_ollama`.
- **ChromaDB** — embedded (no separate container). One global collection `lumen_docs`, documents filtered by `document_id` metadata.
- **SQLite** — async via SQLAlchemy + aiosqlite. Stores document metadata and chat history.
- **No LlamaIndex** — RAG is implemented manually in `app/services/rag.py`. Simpler to debug.

## Directory structure

```
app/
├── main.py          # Entry point: FastAPI + NiceGUI wired together
├── config.py        # Pydantic Settings — single source of truth
├── schemas.py       # All Pydantic request/response models
├── models.py        # SQLAlchemy ORM models (Document, ChatSession, ChatMessage)
├── database.py      # Async engine, session factory, init_db()
├── deps.py          # FastAPI dependency injectors
├── startup.py       # Startup sequence: DB init, Ollama health, model pulls
│
├── services/
│   ├── ollama_client.py   # HTTP wrapper for Ollama API (embed, chat, list, pull)
│   ├── vector_store.py    # ChromaDB wrapper (add, query, delete)
│   ├── document_parser.py # Per-format text extraction → [{text, page_number}]
│   ├── chunker.py         # Sliding window chunker → list[ChunkData]
│   ├── ingestor.py        # Orchestrates parse→chunk→embed→store as asyncio task
│   ├── rag.py             # Full RAG query pipeline with citation extraction
│   └── chat_history.py    # Chat session CRUD
│
├── api/
│   ├── router.py      # Combines all sub-routers under /api prefix
│   ├── documents.py   # /api/documents/* (upload, list, delete, reindex)
│   ├── chat.py        # /api/chat/* (sessions, messages, query)
│   └── settings.py    # /api/settings/* (get/set config, list Ollama models)
│
└── ui/
    ├── app_ui.py      # NiceGUI page registration + shared layout (header, sidebar)
    ├── pages/
    │   ├── workspace.py  # Document upload and management page
    │   ├── chat.py       # Q&A chat interface
    │   └── settings.py   # Model and RAG settings page
    └── components/
        ├── upload_card.py    # Drag-drop upload component
        ├── document_table.py # Document list with status badges
        ├── chat_bubble.py    # Message bubble with citation chips
        └── model_selector.py # Ollama model dropdown
```

## Import rules (strict layering — no circular imports)

```
config.py, schemas.py          (no internal imports)
    ↓
models.py, database.py         (import config, schemas)
    ↓
services/*                     (import models, database, config, schemas)
    ↓
api/*                          (import services, deps, schemas)
    ↓
ui/*                           (import services directly — same process)
    ↓
main.py                        (imports everything, wires it together)
```

Services are **singletons** at module level (`ollama_client = OllamaClient()`, `vector_store = VectorStore()`). Import the singleton, not the class.

## Key design decisions

**Ingestion as asyncio background task:** `asyncio.create_task(ingest_document(...))` is called after the document row is committed to the DB. The ingestor opens its own DB sessions (`AsyncSessionLocal()`). Status polling is done by the UI via GET `/api/documents/{id}`.

**ChromaDB is synchronous:** Wrap all ChromaDB calls in `asyncio.to_thread()` inside the ingestor and any async context.

**Document parsers are synchronous:** Same — wrap in `asyncio.to_thread()` in the ingestor.

**NiceGUI local variables are per-connection:** Each browser tab that loads a `@ui.page` function gets its own local variable scope. Use `nonlocal` to mutate them from inner async functions.

**Settings at runtime:** Mutable settings (chat model, chunk size, top-k) are stored in `/data/settings.json`. The `settings` object in `config.py` is mutated in-place by `PUT /api/settings/`. This is MVP simplicity — not process-safe for multi-worker deployments.

## Running locally (without Docker)

```bash
# Requires Ollama running at localhost:11434
cp .env.example .env
# Edit .env: set OLLAMA_BASE_URL=http://localhost:11434 and local paths

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Common tasks

**Add a new document format:**
1. Add parser in `app/services/document_parser.py`
2. Add extension to `ALLOWED_EXTENSIONS` in `app/api/documents.py`
3. Add the parsing library to `requirements.txt`

**Change the RAG prompt:**
Edit `SYSTEM_PROMPT` in `app/services/rag.py`. The citation format `[Source: <name>, Page <N>]` must be preserved — the regex in `rag.query()` depends on it.

**Add a new API endpoint:**
1. Add route in the appropriate `app/api/*.py` file
2. It's automatically included via `app/api/router.py`

**Add a new UI page:**
1. Create `app/ui/pages/newpage.py` with an `async def render()` function
2. Register it in `app/ui/app_ui.py` with `@ui.page('/newpage')`
3. Add a nav link in `render_sidebar()`

## Testing

Tests live in `tests/`. Run with:
```bash
pytest tests/ -v
```

Key areas to test:
- `test_parser.py` — each document format parser
- `test_chunker.py` — chunk boundary and page attribution logic
- `test_rag.py` — citation extraction regex
