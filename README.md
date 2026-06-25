# Lumen

**Local-first AI document intelligence for analyst teams.**

Lumen lets your team upload documents and ask questions in plain language. Every answer cites its source — document name and page number — so you can verify the AI's reasoning. All processing happens on your own infrastructure. No data leaves your network.

---

## Features

- **Document Q&A** — ask questions across your entire document library in natural language
- **Source citations** — every answer includes `[Source: filename, Page N]` references
- **Multi-format ingestion** — PDF, DOCX, PPTX, XLSX, TXT
- **Fully local** — LLM and embeddings run via Ollama; no API keys, no cloud calls
- **Persistent chat history** — sessions are saved with their full message history
- **Document scoping** — query all documents or filter to a specific subset
- **Model flexibility** — switch between any Ollama model from the Settings page
- **Docker/Podman ready** — one command to start the full stack

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Docker / Podman Compose                                 │
│                                                          │
│  ┌──────────────────────────────────┐  ┌─────────────┐  │
│  │  lumen_app  (port 8080)          │  │ lumen_ollama│  │
│  │                                  │  │ (port 11434)│  │
│  │  FastAPI  ──  REST API           │  │             │  │
│  │     +         /api/v1/*          │◄─►  LLM        │  │
│  │  NiceGUI  ──  Browser UI         │  │  Embeddings │  │
│  │               localhost:8080     │  │             │  │
│  │                                  │  └─────────────┘  │
│  │  ChromaDB  (embedded)            │                   │
│  │  SQLite    (metadata)            │                   │
│  └──────────────────────────────────┘                   │
│                   │                                      │
│            ./data/ (bind mount)                          │
│            ├── uploads/   raw files                      │
│            ├── chroma/    vector index                   │
│            └── lumen.db   metadata + chat history        │
└─────────────────────────────────────────────────────────┘
```

**RAG pipeline:**
```
Upload → Parse (PyMuPDF/docx/pptx/xlsx)
       → Chunk (sliding window, page-aware)
       → Embed (Ollama nomic-embed-text)
       → Store (ChromaDB)

Query  → Embed question
       → Retrieve top-K chunks (ChromaDB cosine similarity)
       → Build prompt with context + citations
       → Generate answer (Ollama LLM)
       → Return answer + parsed citations
```

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) or [Podman](https://podman.io/getting-started/installation) (v4+)
- `docker compose` or `podman compose` / `podman-compose`
- At least **8 GB RAM** for the default `llama3.2` model
- At least **10 GB disk** for model weights + your documents

---

## Quick Start

### Docker

```bash
git clone https://github.com/yourorg/lumen.git
cd lumen

# Copy environment config (edit if needed)
cp .env.example .env

# Create the data directory
mkdir -p data/uploads data/chroma

# Start the stack
docker compose up -d

# Follow startup logs (model pulls happen on first start — takes a few minutes)
docker compose logs -f app
```

Open **http://localhost:8080** when you see `Lumen is ready!` in the logs.

### Podman

```bash
cp .env.example .env
mkdir -p data/uploads data/chroma

# Using podman compose (Podman v4+)
podman compose up -d

# Or using podman-compose
podman-compose up -d
```

> **Podman rootless networking:** If containers can't reach each other by hostname,
> edit `.env` and set `OLLAMA_BASE_URL=http://localhost:11434`, then restart.

### GPU Acceleration (optional)

For significantly faster inference, uncomment the GPU section in `docker-compose.yml`.

**Docker + NVIDIA:**
```yaml
# In docker-compose.yml, under ollama service:
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

**Podman + NVIDIA:**
```bash
# Generate CDI config (one-time setup)
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# Then uncomment in docker-compose.yml:
# devices:
#   - nvidia.com/gpu=all
```

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_CHAT_MODEL` | `llama3.2` | LLM for Q&A generation |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `CHUNK_SIZE` | `512` | Characters per document chunk |
| `CHUNK_OVERLAP` | `64` | Overlap between chunks |
| `TOP_K` | `5` | Chunks retrieved per query |
| `MAX_CONTEXT_CHUNKS` | `8` | Max chunks sent to LLM |
| `NICEGUI_STORAGE_SECRET` | `change-me-...` | Cookie signing secret — **change this** |

Settings can also be changed at runtime from the **Settings** page in the UI.

### Choosing a model

| Model | RAM needed | Speed | Quality |
|---|---|---|---|
| `llama3.2` (3B) | ~4 GB | Fast | Good for simple Q&A |
| `mistral:7b` | ~6 GB | Medium | Good general purpose |
| `llama3.1:8b` | ~8 GB | Medium | Best default choice |
| `qwen2.5:14b` | ~14 GB | Slow | High quality, multilingual |

---

## Usage Guide

### 1. Upload Documents

Go to **Workspace** → drag and drop your files or click to browse.

Supported formats: PDF, DOCX, PPTX, XLSX, TXT (up to 100 MB each).

Documents are automatically ingested (parsed → chunked → embedded). Status shows:
- `pending` → queued
- `ingesting` → processing
- `ready` → available for Q&A
- `error` → hover for details

### 2. Ask Questions

Go to **Chat** → type your question.

- Use **All Documents** to search across everything
- Or select specific documents from the dropdown for targeted queries
- Each session is saved — revisit previous chats from the sidebar
- Citations appear below each AI answer — click to see the source text

### 3. Settings

Go to **Settings** to:
- Switch chat or embedding models
- Tune chunk size and retrieval depth
- Pull new models from Ollama's library
- Re-index all documents after changing chunk settings

---

## Development Setup

Running locally without Docker:

```bash
# Prerequisites: Python 3.12+, Ollama installed locally
# Install Ollama: https://ollama.ai

# Pull required models
ollama pull llama3.2
ollama pull nomic-embed-text

# Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure for local development
cp .env.example .env
# Edit .env: set OLLAMA_BASE_URL=http://localhost:11434
# Set SQLITE_URL=sqlite+aiosqlite:///./data/lumen.db
# Set CHROMA_PERSIST_DIR=./data/chroma
# Set UPLOAD_DIR=./data/uploads

mkdir -p data/uploads data/chroma

# Run the app
python -m app.main
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM & Embeddings | [Ollama](https://ollama.ai) |
| Vector store | [ChromaDB](https://trychroma.com) (embedded) |
| Metadata & chat history | SQLite via SQLAlchemy async |
| Backend API | FastAPI |
| Browser UI | NiceGUI (Python → Quasar/Vue) |
| PDF parsing | PyMuPDF |
| DOCX parsing | python-docx |
| PPTX parsing | python-pptx |
| XLSX parsing | openpyxl |
| HTTP client | httpx |
| Deployment | Docker Compose / Podman Compose |

---

## Roadmap

**v0.2 — Multi-user**
- User authentication (FastAPI Users + JWT)
- Per-user document workspaces
- Role-based access control

**v0.3 — Integrations**
- Watch folder for auto-ingestion
- SharePoint / network drive connector
- REST webhook on ingestion complete

**v0.4 — Analytics**
- Query audit log (who asked what, when)
- Usage dashboard
- Document coverage reporting

---

## License

MIT
