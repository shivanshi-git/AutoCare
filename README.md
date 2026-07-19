# Maruti Suzuki Knowledge Assistant

Enterprise AI-powered knowledge management platform for Maruti Suzuki India Limited.

## Architecture

- **Frontend:** Vanilla JS with native Web Components, hand-rolled state store & router
- **Backend:** Python FastAPI (async), layered architecture (routers → services → repositories → adapters)
- **AI:** Azure OpenAI Service behind an `AIProvider` interface (Copilot Studio connector available)
- **RAG:** Hand-rolled pipeline — chunker, retriever, reranker, orchestrator (no LangChain)
- **Vector DB:** FAISS (local), behind a `VectorStore` interface
- **Database:** PostgreSQL 16 via SQLAlchemy + Alembic
- **Deployment:** Docker Compose (local dev), Kubernetes manifests (enterprise path)

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start all services
docker compose up --build

# 3. Access
#    Frontend: http://localhost:3000
#    API:      http://localhost:8000
#    Health:   http://localhost:8000/health
```

## Project Structure

```
backend/
  api/v1/            # REST API routers
  services/          # Business logic
  repositories/      # Data access
  adapters/          # External system adapters (AI, vector DB, storage)
  rag/               # RAG pipeline (chunker, retriever, reranker, orchestrator)
  documentpipeline/  # Document ingestion (parsers, PII scanner, classifier)
  core/              # Config, security, permissions, logging
  models/            # SQLAlchemy ORM models
  schemas/           # Pydantic DTOs
  tests/             # Test suite

frontend/
  modules/           # Feature modules (chat, dashboard, documents, etc.)
  shared/            # Shared framework (components, store, router, API client)
  assets/            # Static assets
```

## Build Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Foundation | ✅ | Scaffolding, design tokens, Docker |
| 1 — Identity | ⬜ | Auth, RBAC, Departments, Projects |
| 2 — Documents | ⬜ | Upload, parsers, PII, classification |
| 3 — RAG Core | ⬜ | Chunking, embeddings, FAISS, retrieval |
| 4 — AI + Chat | ⬜ | AI provider, Chat UI |
| 5 — Discovery | ⬜ | Search, Knowledge Graph |
| 6 — Operations | ⬜ | Notifications, Dashboard, Analytics |
| 7 — Governance | ⬜ | Admin, Audit, Feedback |
| 8 — Hardening | ⬜ | Integration, security, docs, deployment |

## License

Proprietary — Maruti Suzuki India Limited
