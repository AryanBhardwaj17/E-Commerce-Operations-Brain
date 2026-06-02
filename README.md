# E-Commerce Operations Brain

<div align="center">

**AI-Powered Multi-Agent System for E-Commerce Operations Intelligence**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-FF4B4B.svg)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[Features](#features) • [Architecture](#architecture) • [Quick Start](#quick-start) • [Deployment](#deployment)

</div>

---

## Overview

E-Commerce Operations Brain is a production-ready **multi-agent AI system** designed to provide store owners with intelligent operational insights through natural language queries. Built on LangGraph and FastAPI, it orchestrates specialized AI agents to investigate sales patterns, inventory issues, marketing performance, and customer support metrics.

### What It Does

Transform natural language questions into actionable intelligence:

- **"Why did sales drop on May 31st?"** → Root cause analysis with correlated events
- **"Show me daily sales for the last 30 days"** → Time-series analysis with trends
- **"Which products are close to stockout?"** → Inventory alerts with recommendations
- **"Compare this week vs last week revenue"** → Period-over-period analysis
- **"Should we discount or restock Product X?"** → Decision support with approval workflows

### Key Differentiators

- **Multi-Agent Orchestration** - Specialized agents (Sales, Inventory, Marketing, Support) collaborate on investigations  
- **Human-in-the-Loop** - Approval workflows for risky operations (discounts, restocking)  
- **Durable Execution** - Persistent state management with PostgreSQL + LangGraph checkpointing  
- **Date Range Intelligence** - Parse temporal queries with daily/weekly/monthly granularity  
- **Completeness Validation** - Track requested vs. addressed metrics for quality assurance  
- **Production-Ready** - Observability (LangSmith, OpenTelemetry), testing, type safety

---

## Features

### Intelligent Query Interpretation
- **Temporal Scope Parsing:** Understands "last 30 days", "this quarter", "May 1-15"
- **Multi-Granularity:** Daily, weekly, monthly time-series analysis
- **Metric Extraction:** Automatically identifies requested KPIs (revenue, conversion rate, AOV)
- **Comparison Detection:** Recognizes period-over-period, baseline comparisons

### Response Formats
- **Diagnosis:** Root cause analysis for anomalies
- **Summary:** Bullet-point executive summaries
- **Comparison:** Side-by-side metric comparisons
- **List:** Structured data tables

### Quality Assurance
- **Completeness Checks:** Validates all requested metrics were addressed
- **Data Gap Detection:** Explicitly flags missing data or unsupported metrics
- **Answer Quality Scoring:** Complete, Partial, or Insufficient ratings

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Store Owner Assistant (Chat Interface)                  │  │
│  │  • Query submission • Real-time status polling           │  │
│  │  • Approval UI • Local run history                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/SSE
┌────────────────────────────┴────────────────────────────────────┐
│                     BACKEND (FastAPI + LangGraph)               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ API Layer                                                  │ │
│  │ • POST /query • GET /runs/{id}/status                     │ │
│  │ • GET /runs/{id}/events • POST /approvals/{id}/respond   │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Execution Backend (In-Process / Queued Worker)            │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ LangGraph Multi-Agent Workflow                            │ │
│  │  ┌───────────┬────────────┬──────────┬─────────┬────────┐ │ │
│  │  │Guardrails │ Query      │ Memory   │Coordina-│Synthesis│ │
│  │  │  Check    │Interpreter │  Reader  │  tor    │ Agent  │ │ │
│  │  └───────────┴────────────┴──────────┴─────────┴────────┘ │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │  Specialist Agents (Parallel Execution)              │ │ │
│  │  │  • Sales Analyst    • Inventory Analyst              │ │ │
│  │  │  • Marketing Analyst • Support Analyst               │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Memory Systems                                            │ │
│  │ • KADB (Action Knowledge) • KEDB (Event Knowledge)       │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                    INFRASTRUCTURE                               │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐ │
│  │ PostgreSQL   │ ChromaDB     │ Runtime Store│ LangSmith    │ │
│  │ (Repository  │ (Vector      │ (File/Future │ (Observ-     │ │
│  │  + Checkpt)  │  Search)     │  Postgres)   │  ability)    │ │
│  └──────────────┴──────────────┴──────────────┴──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Workflow

```mermaid
graph LR
    A[User Query] --> B[Guardrails]
    B --> C[Query Interpreter]
    C --> D[Memory Reader]
    D --> E[Coordinator]
    E --> F1[Sales Analyst]
    E --> F2[Inventory Analyst]
    E --> F3[Marketing Analyst]
    E --> F4[Support Analyst]
    F1 --> G[Reflection Agent]
    F2 --> G
    F3 --> G
    F4 --> G
    G --> H[Synthesis Agent]
    H --> I{Actions Needed?}
    I -->|Yes| J[Action Executor + Approval]
    I -->|No| K[Final Report]
    J --> K
```

### Execution Modes

| Mode | Use Case | Description |
|------|----------|-------------|
| **In-Process** | Local Development | API process executes workflows synchronously |
| **Queued** | Production | API enqueues work; separate workers execute asynchronously |

---

## Quick Start

### Prerequisites

- **Python 3.11+** with `pip` or `uv`
- **Node.js 18+** with npm 11+
- **Docker & Docker Compose** (for containerized setup)
- **PostgreSQL 15+** (for repository backend + checkpointing)
- **ChromaDB** (for vector memory)
- **OpenAI/Azure OpenAI API Key** (or Ollama for local LLMs)

### Option 1: Local Development (Single Process)

#### 1. Clone & Install

```bash
# Clone repository
git clone <repository-url>
cd E-Commerce-Operations-Brain

# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Frontend setup
cd ../frontend
npm install
```

#### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials:
# - LLM_PROVIDER (azure/openai/ollama)
# - AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
# - LANGSMITH_API_KEY (optional)
# - DATABASE_URL
```

#### 3. Initialize Database

```bash
# Start PostgreSQL and ChromaDB (via Docker)
docker compose up -d postgres chromadb

# Seed application data
cd backend
python scripts/seed_postgres.py
python scripts/seed_kadb.py  # Action knowledge
python scripts/seed_kedb.py  # Event knowledge
```

#### 4. Run Services

```bash
# Terminal 1: Backend API
cd backend
make dev  # Runs uvicorn with reload

# Terminal 2: Frontend
cd frontend
npm run dev  # Starts Next.js on localhost:3000
```

#### 5. Access Application

Open **http://localhost:3000** and ask:

> "Show me daily sales for the last 30 days"

### Option 2: Docker Compose (Multi-Process)

```bash
# Copy environment file
cp .env.example .env
# Edit .env with your credentials

# Start all services
docker compose up --build

# Access at http://localhost:3000
```

**Services:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/docs` (OpenAPI)
- PostgreSQL: `localhost:5432`
- ChromaDB: `localhost:8001`

---

## Repository Structure

```
E-Commerce-Operations-Brain/
├── backend/                    # FastAPI + LangGraph backend
│   ├── src/
│   │   ├── agents/            # Multi-agent implementations
│   │   │   ├── coordinator.py        # Agent routing logic
│   │   │   ├── query_interpreter.py  # NL→structured query parsing
│   │   │   ├── sales_analyst.py      # Sales domain specialist
│   │   │   ├── inventory_analyst.py  # Inventory domain specialist
│   │   │   ├── marketing_analyst.py  # Marketing domain specialist
│   │   │   ├── support_analyst.py    # Support domain specialist
│   │   │   ├── reflection_agent.py   # Quality validation
│   │   │   └── synthesis_agent.py    # Report generation
│   │   ├── api/               # FastAPI routes & middleware
│   │   │   └── routes/
│   │   │       ├── query.py          # Main query endpoint
│   │   │       ├── actions.py        # Approval workflows
│   │   │       └── memory.py         # Memory retrieval
│   │   ├── core/              # Core business logic
│   │   │   ├── orchestrator.py       # LangGraph workflow
│   │   │   ├── state.py              # Workflow state model
│   │   │   ├── guardrails.py         # Query validation
│   │   │   ├── reflection.py         # Completeness checks
│   │   │   └── hitl.py               # Human-in-the-loop logic
│   │   ├── tools/             # Agent tools (function calling)
│   │   │   ├── sales_tools.py
│   │   │   ├── inventory_tools.py
│   │   │   └── action_tools.py
│   │   ├── memory/            # Vector memory (ChromaDB)
│   │   │   ├── kadb.py               # Action knowledge base
│   │   │   └── kedb.py               # Event knowledge base
│   │   ├── infrastructure/    # Data persistence
│   │   │   ├── repositories/         # Repository pattern
│   │   │   │   ├── postgres/        # Postgres implementations
│   │   │   │   └── mock/            # In-memory for testing
│   │   │   └── runtime_store.py      # Run state persistence
│   │   ├── execution/         # Execution backends
│   │   │   ├── query_runner.py       # In-process executor
│   │   │   └── worker.py             # Queued worker
│   │   ├── models/            # Pydantic schemas
│   │   ├── observability/     # Logging, tracing, metrics
│   │   └── bootstrap/         # Startup initialization
│   ├── tests/
│   │   ├── unit/              # Unit tests
│   │   ├── integration/       # Integration tests
│   │   └── eval/              # LLM evaluation tests
│   ├── scripts/               # Utility scripts (seeding, migration)
│   ├── pyproject.toml         # Python dependencies & config
│   ├── Makefile               # Development commands
│   └── Dockerfile             # Backend container
│
├── frontend/                   # Next.js monorepo
│   ├── apps/
│   │   └── store-owner-assistant/  # Chat UI application
│   │       ├── src/
│   │       │   ├── app/              # Next.js app router
│   │       │   ├── components/       # React components
│   │       │   ├── hooks/            # Custom React hooks
│   │       │   └── lib/              # Utilities
│   │       ├── package.json
│   │       └── next.config.js
│   ├── packages/
│   │   ├── api-client/        # Backend API client
│   │   └── ui/                # Shared UI components
│   ├── package.json           # Workspace root
│   └── Dockerfile             # Frontend container
│
├── docker/                     # Shared Docker assets
│   └── collector/             # OpenTelemetry collector config
├── .env.example               # Environment variables template
├── .gitignore
├── docker-compose.yml         # Multi-container orchestration
├── Makefile                   # Monorepo commands
└── README.md                  # This file
```

---

## Development

### Common Commands

#### Backend

```bash
cd backend

# Development
make dev              # Run FastAPI with hot reload
make dev-worker       # Run queued worker (queued mode)

# Testing
make test             # Run all tests
make test-unit        # Unit tests only
make test-integration # Integration tests only
make test-eval        # LLM evaluation tests (requires API key)

# Code Quality
make lint             # Run Ruff linter
make typecheck        # Run mypy type checker
make format           # Auto-format code

# Database
python scripts/seed_postgres.py  # Seed business data
python scripts/seed_kadb.py      # Seed action knowledge
python scripts/seed_kedb.py      # Seed event knowledge
```

#### Frontend

```bash
cd frontend

npm run dev           # Development server (port 3000)
npm run build         # Production build
npm run lint          # ESLint
npm run typecheck     # TypeScript type checking
```

#### Monorepo

```bash
# From repository root
make check            # Run all lints, typechecks, and builds
```

### Testing Strategy

| Test Type | Location | Purpose |
|-----------|----------|---------|
| **Unit** | `backend/tests/unit/` | Individual functions, agent logic |
| **Integration** | `backend/tests/integration/` | API endpoints, database interactions |
| **Evaluation** | `backend/tests/eval/` | LLM output quality (DeepEval) |

**Run specific test:**
```bash
pytest backend/tests/unit/test_query_runner_backends.py -v
```

**Coverage report:**
```bash
pytest --cov=src --cov-report=html backend/tests/
```

---

## Key Concepts

#### 1. Query Interpreter
Parses natural language into structured intents:
```python
query_intent = {
    "temporal_scope": {
        "start_date": "2026-05-12",
        "end_date": "2026-06-11",
        "granularity": "daily"
    },
    "requested_metrics": ["revenue", "conversion_rate"],
    "comparison_intent": {"type": "period_over_period"},
    "response_format": "summary"
}
```

#### 2. Human-in-the-Loop (HITL)
Before executing risky actions (discounts, restocking):
1. Agent proposes action
2. System creates approval request
3. Frontend displays approval UI
4. User approves/rejects
5. Action executor proceeds/cancels

#### 3. Durable State Management
- **Runtime Store:** File-based (transitional) for run state, approvals, events
- **Repository Backend:** PostgreSQL for business data (sales, inventory, etc.)
- **LangGraph Checkpointing:** PostgreSQL for workflow resumption

---

## Deployment

### Production Architecture

**Recommended Setup:**
```
┌─────────────┐      ┌─────────────┐
│  Frontend   │─────▶│  API (3x)   │
│  (Next.js)  │      │  (FastAPI)  │
└─────────────┘      └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  Workers    │
                     │  (LangGraph)│
                     └──────┬──────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
   │PostgreSQL│        │ChromaDB│        │ Runtime │
   │         │        │         │        │  Store  │
   └─────────┘        └─────────┘        └─────────┘
```

### Environment Configuration

**Critical Variables:**
```bash
# Execution mode
EXECUTION_BACKEND=queued  # Use 'queued' for production

# LLM Provider
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key

# Database
DATABASE_URL=postgresql://user:pass@host:5432/ops_brain
CHECKPOINT_BACKEND=auto  # Uses DATABASE_URL
REPOSITORY_BACKEND=postgres

# Observability
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317

# Security
API_KEY=generate-secure-key
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com
```

### Docker Compose Production

```yaml
# docker-compose.prod.yml
services:
  api:
    image: eob-backend:latest
    environment:
      EXECUTION_BACKEND: queued
    replicas: 3
    
  worker:
    image: eob-backend:latest
    command: eob-worker
    replicas: 2
    
  frontend:
    image: eob-frontend:latest
    environment:
      NEXT_PUBLIC_API_URL: https://api.your-domain.com
```

**Deploy:**
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Health Checks

- **API:** `GET /health` → `{"status": "healthy"}`
- **Worker:** Logs `Worker started` and polls runtime store
- **PostgreSQL:** `pg_isready`
- **ChromaDB:** `GET /api/v1/heartbeat`

### Monitoring

**LangSmith Dashboard:**
- Run traces with agent execution timelines
- Tool call success/failure rates
- Average query latency

**Custom Metrics:**
- Query throughput (queries/min)
- Average investigation time
- Approval response time
- Data gap frequency

---

## Testing & Validation

### Manual Test Queries

```bash
# After starting services, try these in the UI:

# 1. Date range query
"Show me daily sales for the last 30 days"

# 2. Diagnostic query
"Why did sales drop on May 31st?"

# 3. Inventory check
"Which products are close to stockout?"

# 4. Comparison query
"Compare this week vs last week revenue"

# 5. Action query (triggers approval)
"Should we discount Product X?"
```

### Automated Tests

```bash
# Backend unit tests (fast)
pytest backend/tests/unit/ -v

# Backend integration tests (requires DB)
pytest backend/tests/integration/ -v

# LLM evaluation tests (requires API key + credits)
pytest backend/tests/eval/ -v -m eval
```

### CI/CD Pipeline

`.github/workflows/ci.yml` runs:
1. Linting (Ruff, ESLint)
2. Type checking (mypy, TypeScript)
3. Unit tests
4. Integration tests (with PostgreSQL service)
5. Build verification (Docker images)

---

## Troubleshooting

### Common Issues

#### 1. "LLM API key not configured"
**Solution:** Check `.env` file has correct `AZURE_OPENAI_API_KEY` or `OPENAI_API_KEY`

#### 2. "Database connection failed"
**Solution:**
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Verify DATABASE_URL in .env
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

#### 3. "ChromaDB not available"
**Solution:**
```bash
# Start ChromaDB
docker compose up -d chromadb

# Verify connectivity
curl http://localhost:8001/api/v1/heartbeat
```

#### 4. "Worker not processing queries"
**Solution:**
- Ensure `EXECUTION_BACKEND=queued` in worker's environment
- Check worker logs: `docker compose logs worker`
- Verify shared `RUNTIME_STORE_DIR` is mounted

#### 5. "Frontend can't connect to API"
**Solution:**
- Check `NEXT_PUBLIC_API_URL` in frontend `.env`
- Verify CORS settings in backend: `CORS_ALLOWED_ORIGINS`
- Test API directly: `curl http://localhost:8000/health`

### Debug Mode

**Backend verbose logging:**
```bash
LOG_LEVEL=DEBUG make dev
```

**LangSmith tracing:**
```bash
LANGSMITH_TRACING=true LANGSMITH_PROJECT=debug-session make dev
```

---

## Contributing

### Development Workflow

1. **Fork & Clone**
```bash
git clone <your-fork-url>
cd E-Commerce-Operations-Brain
git checkout -b feature/your-feature
```

2. **Install Pre-Commit Hooks**
```bash
cd backend
pre-commit install
```

3. **Make Changes**
- Follow existing code style (Ruff for Python, ESLint for TypeScript)
- Add tests for new features
- Update documentation

4. **Test Locally**
```bash
make check  # Runs all lints, tests, builds
```

5. **Submit PR**
- Clear description of changes
- Link related issues
- Ensure CI passes

### Code Style

**Python (Backend):**
- Ruff formatting (line length: 100)
- Type hints on public functions
- Docstrings for agents and complex logic

**TypeScript (Frontend):**
- ESLint + Prettier
- Functional components with hooks
- Props interface definitions

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

**Technologies:**
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Multi-agent orchestration framework
- [FastAPI](https://fastapi.tiangolo.com) - High-performance Python web framework
- [Next.js](https://nextjs.org) - React framework for production
- [PostgreSQL](https://www.postgresql.org/) - Relational database
- [ChromaDB](https://www.trychroma.com/) - Vector database for semantic memory
- [LangSmith](https://www.langchain.com/langsmith) - LLM observability platform

---

## Support & Contact

**Issues & Bugs:** [GitHub Issues](https://github.com/your-org/ecommerce-ops-brain/issues)  
**Discussions:** [GitHub Discussions](https://github.com/your-org/ecommerce-ops-brain/discussions)  
**Documentation:** [Project Wiki](https://github.com/your-org/ecommerce-ops-brain/wiki)

---

<div align="center">

**Built for e-commerce operations teams**

[Back to Top](#e-commerce-operations-brain)

</div>
