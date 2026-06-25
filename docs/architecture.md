# Lumen — Architecture

## Process model

Everything runs in a single Python process. NiceGUI mounts onto the FastAPI application via `ui.run_with(fastapi_app)` and shares the same uvicorn worker. There is no separate API server or frontend build step.

```
python -m app.main
└── uvicorn (started by NiceGUI)
    ├── FastAPI routes  →  /api/*
    └── NiceGUI routes  →  / /workspace /chat /settings
```

## Service communication

```
Browser ──WebSocket──► NiceGUI pages (Python)
                           │
                           ▼ direct function call (same process)
                       Services layer
                           │           │
                     ChromaDB      AsyncSessionLocal (SQLite)
                           │
                     ┌─────▼──────────────────────┐
                     │  Ollama  (Docker service)   │
                     │  http://ollama:11434         │
                     │  POST /api/embed             │
                     │  POST /api/chat              │
                     └────────────────────────────-┘
```

## Data flow

### Ingestion

```
1. User drops file in browser
2. NiceGUI upload_handler (workspace.py)
   → writes bytes to /data/uploads/{uuid}.{ext}
   → inserts Document row (status=pending)
   → asyncio.create_task(ingest_document(...))
3. Background task (ingestor.py)
   → status = ingesting
   → parse_document()     [asyncio.to_thread — blocking]
   → chunk_segments()     [pure Python, fast]
   → ollama_client.embed()  [async HTTP, slow]
   → vector_store.add_chunks()  [asyncio.to_thread — blocking]
   → status = ready
```

### Query

```
1. User types question, presses Send
2. NiceGUI chat.py _send()
   → rag.query(QueryRequest, db)
3. rag.py query()
   a. embed(question)                    → Ollama /api/embed
   b. vector_store.query(embedding, k)   → ChromaDB cosine search
   c. deduplicate by (doc_id, page_num)
   d. build context string with [Source: name, Page N] headers
   e. prepend chat history (last 10 messages)
   f. ollama_client.chat(messages)       → Ollama /api/chat
   g. regex-extract [Source: ...] citations from answer
   h. return QueryResponse{answer, citations}
4. chat.py saves messages to SQLite
5. NiceGUI renders answer + citation chips
```

## Storage layout

```
/data/
├── uploads/
│   └── {uuid}.{ext}          # raw uploaded files, never modified
├── chroma/
│   └── (ChromaDB internals)  # HNSW index, cosine space
└── lumen.db                  # SQLite: documents, chat_sessions, chat_messages
```

## ChromaDB schema

Single collection: `lumen_docs` (cosine similarity space)

Per-chunk metadata stored alongside each vector:
```json
{
  "document_id": "uuid",
  "document_name": "report.pdf",
  "page_number": 7,
  "chunk_index": 42
}
```

Query filtering: `where={"document_id": {"$in": [...]}}` for per-document scoping.

## SQLite schema

```sql
documents
  id TEXT PK, name, file_type, file_path, status, chunk_count, size_bytes,
  error_message, created_at, updated_at

chat_sessions
  id TEXT PK, title, created_at
  → one-to-many → chat_messages (cascade delete)

chat_messages
  id TEXT PK, session_id FK, role, content TEXT, citations_json TEXT, created_at
```

## Dependency layers (no circular imports)

```
Layer 0: config.py, schemas.py           (no internal imports)
Layer 1: models.py, database.py          (import Layer 0)
Layer 2: services/*                      (import Layers 0–1)
Layer 3: api/*                           (import Layers 0–2)
Layer 4: ui/*                            (import Layers 0–2 directly)
Layer 5: main.py, startup.py             (import all layers)
```

`ui/*` calls services directly (same process), not via HTTP. This avoids loopback overhead while keeping the API independently available for external tools.
