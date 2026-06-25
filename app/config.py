from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "lumen_docs"

    # ── Database ──────────────────────────────────────────────────────────────
    SQLITE_URL: str = "sqlite+aiosqlite:///./data/lumen.db"

    # ── Storage ───────────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./data/uploads"

    # ── RAG parameters ────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K: int = 5
    MAX_CONTEXT_CHUNKS: int = 8

    # ── App server ────────────────────────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    NICEGUI_STORAGE_SECRET: str = "change-me-in-production"

    # ── Dev ───────────────────────────────────────────────────────────────────
    DEBUG: bool = False


settings = Settings()
