"""Application settings loaded from environment variables (12-factor)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NextBot AI"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Demo mode — everything runs without paid credentials
    demo_mode: bool = True
    ai_provider: Literal["mock", "openai"] = "mock"
    payment_provider: Literal["mock", "razorpay", "stripe"] = "mock"
    shipping_provider: Literal["mock", "shiprocket"] = "mock"
    whatsapp_enabled: bool = False
    email_enabled: bool = False
    seed_on_startup: bool = True

    # Databases
    database_url: str = "postgresql+asyncpg://nextbot:nextbot@localhost:5432/nextbot"
    redis_url: str | None = None
    mongo_url: str | None = None
    mongo_db: str = "nextbot"
    db_echo: bool = False

    # Search
    search_backend: Literal["database", "opensearch"] = "database"
    opensearch_url: str | None = None

    # Messaging
    event_bus: Literal["memory", "kafka"] = "memory"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_prefix: str = "nextbot"
    outbox_poll_interval_s: float = 1.0

    # n8n workflow automation (optional). When set, every domain event is forwarded to this n8n webhook.
    n8n_webhook_url: str | None = None
    n8n_webhook_token: str = "nextbot-n8n-demo-token"  # sent as X-NextBot-Token; checked by the n8n workflow
    n8n_signing_secret: str = "nextbot-n8n-demo-signing-secret"  # HMAC-SHA256 of the body -> X-NextBot-Signature
    n8n_editor_url: str = "http://localhost:5678"  # link shown to admins (browser-facing)

    # Security
    jwt_secret: str = Field(default="change-me-in-production-use-32+chars", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 120
    chat_rate_limit_per_minute: int = 30
    webhook_secret: str = "demo-webhook-secret"
    mcp_allowed_hosts: list[str] = ["127.0.0.1:*", "localhost:*", "backend:*"]  # MCP DNS-rebinding protection

    # AI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Any OpenAI-compatible API. Gemini: https://generativelanguage.googleapis.com/v1beta/openai/ (key from AI Studio)
    openai_base_url: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384
    agent_max_iterations: int = 6
    agent_timeout_s: float = 15.0
    # Admin AI Research assistant (OpenAI Responses API + web search). Admin-only; mock answer without a key.
    openai_research_model: str | None = None  # defaults to openai_model; must be a model that supports web search
    research_rate_limit_per_minute: int = 10
    research_daily_limit: int = 200  # per admin, protects the OpenAI bill

    # RAG
    rag_chunk_size: int = 600
    rag_chunk_overlap: int = 80
    rag_top_k: int = 4
    rag_min_score: float = 0.10  # tuned for the hashing embedder; use ~0.30 with OpenAI embeddings

    # Business policy
    return_window_days: int = 10
    refund_approval_threshold: float = 10000.0
    cancellation_approval_threshold: float = 50000.0
    inventory_adjustment_approval_units: int = 500
    low_stock_threshold: int = 5
    fraud_review_score: int = 60
    max_payment_failures: int = 3

    # External providers (adapters raise ExternalServiceNotConfigured when missing)
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    stripe_secret_key: str | None = None
    shiprocket_email: str | None = None
    shiprocket_password: str | None = None
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_verify_token: str = "nextbot-verify"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "NextBot AI <no-reply@nextbot.local>"

    # Observability
    otel_enabled: bool = False
    otel_exporter_endpoint: str | None = None

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
