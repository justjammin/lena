# LENA

**LangGraph-powered, model-agnostic agent harness.**

LENA runs any AI model — GPT-5.5, Claude, Gemini, or local Ollama — through a single LangGraph state machine. Approximately 70% of the core logic was ported from a Claude Code plugin, so the orchestration patterns are battle-tested. Swap the model; the graph stays the same.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [Configuration](#configuration)
- [Supported Models](#supported-models)
- [Stack](#stack)
- [Mega Man UI](#mega-man-ui)
- [Development](#development)

---

## Architecture

### LangGraph State Machine

Every task flows through a `StateGraph` compiled from `lena/runtime/graph.py`:

```
session_init
    └── vector_recall
            └── router_node
                    ├── [orchestrate + parallel tasks] → branch_executor (×N, parallel fan-out)
                    │                                         └── merge_node → synthesizer
                    ├── [orchestrate, no tasks]        → bd_register → executor
                    └── [direct / fallback]            → executor
                                                               ├── [action == review] → generator → critic → gate ⟲
                                                               └── [default]          → synthesizer
                                                                                              └── consolidation_node → END
```

Parallel fan-out (up to 4 branches) uses LangGraph `Send` objects returned from the conditional edge function — each branch runs `branch_executor` independently and converges at `merge_node`.

### Routing

Routing is handled by `skills/lena/routing_score.py` — a **zero-LLM, deterministic heuristic scorer**. It scores a task across six categories (task shape, domain breadth, concreteness, risk, validation need, intent verbs) and produces:

| Field | Meaning |
|---|---|
| `routing` | `direct`, `orchestrate`, or fallback path |
| `confidence` | 0–100 percentage |
| `domains` | matched domain tags (frontend, backend, database, …) |
| `action` | `execute`, `execute_log`, `clarify_or_orchestrate`, or `force_orchestrate` |

The threshold is configured in `lena.config.yaml` (`routing.threshold`, default `70`). If the scorer exits non-zero, times out, or returns unparseable JSON, the router falls back to a safe default and lets the executor proceed.

### ModelAdapter Protocol

`lena/adapters/base.py` defines a `ModelAdapter` Protocol:

```python
class ModelAdapter(Protocol):
    name: str
    last_usage: dict[str, int]

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        **kwargs,
    ) -> str: ...
```

Concrete adapters (`anthropic.py`, `openai.py`, `gemini.py`, `ollama.py`) are selected at runtime by pattern-matching the model string against `lena.config.yaml`. Every adapter is wrapped in `MetricsAdapter` to track token usage.

### 3-Layer Memory

| Layer | Backend | Purpose |
|---|---|---|
| Working memory | mem0 OSS + pgvector | Per-session episodic recall (`vector_recall` node) |
| Temporal knowledge graph | Zep OSS + Postgres | Long-term entity and fact timeline |
| Team moat | pgvector (`lena_team_memory` table) | Shared organizational memory, 768-dim `nomic-embed-text` embeddings |

### Event Bus

`lena/events.py` exports a module-level `bus: LenaEventBus` — a thread-safe async pub/sub queue. Both UIs subscribe to it and render live updates. Events include `NODE_ENTER`, `NODE_EXIT`, `TASK_COMPLETE`, `TASK_ERROR`, `TOKEN_USAGE`, `ROUTING_DECISION`, and `FEEDBACK_LOOP`.

---

## Prerequisites

- Python **3.11** or later
- **Docker Compose** (runs Postgres/pgvector, Redis, Zep, Langfuse)
- **Ollama** with `nomic-embed-text` pulled (used for embeddings by mem0 and the team moat)
- An **OpenAI API key** (the only paid external dependency; required only when using `gpt-*`, `o1-*`, or `o3-*` models)

---

## Installation

### 1. Clone and install

```bash
git clone https://github.com/your-org/lena.git
cd lena
pip install -e .
```

### 2. Pull the embedding model

```bash
ollama pull nomic-embed-text
```

### 3. Set environment variables

Copy the table in the [Environment Variables](#environment-variables) section into a `.env` file or your shell profile.

### 4. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **Postgres 16 + pgvector** on `localhost:5432` (creates `lena`, `zep`, and `langfuse` databases automatically)
- **Redis 7** on `localhost:6379`
- **Zep** on `localhost:8000`
- **Langfuse** (web + worker) on `localhost:3000`

### 5. Run database migrations

```bash
psql postgresql://lena:$LENA_DB_PASSWORD@localhost:5432/lena \
  -f lena/db/migrations/001_init.sql \
  -f lena/db/migrations/002_team_moat_indexes.sql \
  -f lena/db/migrations/003_hnsw_migration.sql
```

---

## Environment Variables

All variables are required unless noted otherwise.

| Variable | Used by | Notes |
|---|---|---|
| `LENA_DB_PASSWORD` | Postgres, Zep, Langfuse | Password for the `lena` Postgres user |
| `ZEP_AUTH_SECRET` | docker-compose (Zep container) | Secret used internally by the Zep service |
| `ZEP_API_KEY` | `lena.config.yaml` (Zep client) | API key the LENA runtime uses to call Zep |
| `LANGFUSE_NEXTAUTH_SECRET` | docker-compose (Langfuse web) | Required to boot the Langfuse container |
| `LANGFUSE_SALT` | docker-compose (Langfuse web + worker) | Required to boot the Langfuse container |
| `LANGFUSE_PUBLIC_KEY` | `lena.config.yaml` | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | `lena.config.yaml` | Langfuse project secret key |
| `OPENAI_API_KEY` | OpenAI SDK (standard env lookup) | Required only when using `gpt-*`, `o1-*`, or `o3-*` models |

Optional Langfuse bootstrap variables (`LANGFUSE_NEXTAUTH_URL`, `LANGFUSE_INIT_ORG_*`, `LANGFUSE_INIT_PROJECT_*`, `LANGFUSE_INIT_USER_*`) are accepted by docker-compose but not required for LENA to function.

---

## Usage

### CLI — run a task

```bash
lena run --task "Refactor the auth module to use JWT refresh tokens"
```

Read from stdin:

```bash
echo "Explain the team moat schema" | lena run
```

Override the model for a single run:

```bash
# Free — local Ollama
lena run --task "Review this PR" --model ollama/llama3

# Paid — OpenAI
lena run --task "Build a REST endpoint for user registration" --model gpt-5.5
```

Point to an alternate config file:

```bash
lena run --task "..." --config /path/to/custom.yaml
```

### TUI — Mega Man terminal UI

```bash
lena tui
```

Launches a Textual terminal app with NES-palette health bars, a live event log, and routing display. See [Mega Man UI](#mega-man-ui) for the full widget map.

### Web UI — pixel-art browser dashboard

```bash
lena serve
# Open http://localhost:8080
```

Custom host/port:

```bash
lena serve --host 0.0.0.0 --port 9090
```

The web UI connects to LENA over WebSocket (`/ws`) and renders the same event stream as the TUI.

---

## Configuration

`lena.config.yaml` at the repository root controls all runtime behavior.

```yaml
models:
  default: gpt-5.5      # used when --model is not passed
  fast: claude-haiku-4-5
  local: ollama/llama3

adapters:
  - pattern: "claude-*"
    adapter: anthropic
  - pattern: "gpt-*"
    adapter: openai
  - pattern: "o1-*"
    adapter: openai
  - pattern: "o3-*"
    adapter: openai
  - pattern: "gemini-*"
    adapter: gemini
  - pattern: "ollama/*"
    adapter: ollama
  - pattern: "llama*"
    adapter: ollama
  - pattern: "qwen*"
    adapter: ollama

routing:
  scorer_path: skills/lena/routing_score.py
  threshold: 70          # minimum confidence % for direct routing

memory:
  backend: mem0
  mem0:
    embedder:
      provider: ollama
      config:
        model: nomic-embed-text
        ollama_base_url: "http://localhost:11434"
    vector_store:
      provider: pgvector
      config:
        host: localhost
        port: 5432
        dbname: lena
        user: lena
        password: "${LENA_DB_PASSWORD}"
        collection_name: mem0_memories
        embedding_model_dims: 768
  zep:
    base_url: "http://localhost:8000"
    api_key: "${ZEP_API_KEY}"

observability:
  langfuse:
    host: "http://localhost:3000"
    public_key: "${LANGFUSE_PUBLIC_KEY}"
    secret_key: "${LANGFUSE_SECRET_KEY}"
  otel_endpoint: "http://localhost:3000/api/public/otel"

registry:
  manifest_path: agents.manifest.yaml

team_moat:
  enabled: true
  team_id: "default"
  top_k: 5

embeddings:
  provider: ollama
  model: nomic-embed-text
  base_url: "http://localhost:11434"
```

Pattern matching in `adapters` uses Python `fnmatch`. The first matching pattern wins. To add a new model family, append an entry — no code changes needed.

---

## Supported Models

| Model pattern | Adapter | Cost | Cache behavior |
|---|---|---|---|
| `gpt-*`, `o1-*`, `o3-*` | OpenAI | Paid | Automatic prefix caching (SDK reads `cached_tokens` from usage details) |
| `claude-*` | Anthropic | Paid | Explicit `cache_breakpoints` passed to the API |
| `gemini-*` | Gemini | Paid | `cachedContents` API |
| `ollama/*`, `llama*`, `qwen*` | Ollama | Free (local) | No caching |

The default model (`gpt-5.5`) is the only paid dependency for a standard run. Switch to `--model ollama/llama3` for a fully free local session.

---

## Stack

All components self-host via Docker Compose. The only external paid service is the OpenAI API.

| Component | Purpose | Local endpoint |
|---|---|---|
| LangGraph 0.2 | State machine / agent orchestration | — |
| mem0 OSS | Working memory with pgvector backend | — |
| Zep OSS | Temporal knowledge graph | `localhost:8000` |
| pgvector (Postgres 16) | Team moat + mem0 vector store (768-dim) | `localhost:5432` |
| Redis 7 | Langfuse internal queue | `localhost:6379` |
| Langfuse 2 (self-hosted) | LLM observability and tracing | `localhost:3000` |
| Ollama | Local inference + `nomic-embed-text` embeddings | `localhost:11434` |

---

## Mega Man UI

Both UIs share the same NES-inspired color palette and widget semantics. The palette (`#000000` background, `#0080c8` blue, `#c82000` red, `#f8b800` yellow, `#00c8c8` cyan, `#00a800` green, `#f87858` orange) is applied identically in both the Textual CSS and the web stylesheet.

### TUI (`lena tui`)

Built with [Textual](https://textual.textualize.io/). Runs entirely in the terminal.

| Widget | Maps to |
|---|---|
| **BOSS HP** bar | Task progress — drains to 0 on `TASK_COMPLETE` |
| **WEAPON** bar | Displayed but not updated by the event stream in the TUI |
| **LIFE** bar | Context window fill — drains as token usage rises (`TOKEN_USAGE` event) |
| **E-TANKS** `[⬛⬛⬛]` | Retry budget — one block consumed per `TASK_ERROR` (max 3) |
| **AGENT** label | Name of the currently executing graph node |
| **ROUTE** display | Routing decision: path, suggested role, and confidence % |
| **Event log** | Last 8 events, scrolling |

### Web UI (`lena serve`)

Built with FastAPI + WebSocket. The single-page app at `/` connects to `/ws` on load and auto-reconnects with exponential backoff (1 s initial, 30 s maximum).

| Widget | Maps to |
|---|---|
| **BOSS HP** bar | Task progress — drains to 0 on `TASK_COMPLETE` |
| **WEAPON** bar | Inverse of token usage (rises as context fills) |
| **LIFE** bar | Context window remaining |
| **E-TANKS** `[⬛⬛⬛]` | Retry budget — one block consumed per `TASK_ERROR` |
| **AGENT** label | Name of the currently executing graph node |
| **ROUTING** panel | Routing decision: path, suggested role, and confidence % |
| **EVENT LOG** | Last 20 events with timestamps and color-coded rows |
| **STAGE CLEAR** overlay | Full-screen flash on `TASK_COMPLETE` or `BD_CLOSE` |

---

## Development

### Install with test dependencies

```bash
pip install -e ".[test]"
```

### Run tests

```bash
# All unit tests
pytest

# Exclude integration tests that require a live Postgres connection
pytest -m "not integration"
```

Integration tests are marked with `@pytest.mark.integration`. The marker is declared in `pyproject.toml` under `[tool.pytest.ini_options]`.

### Score the router locally

The routing scorer can be called directly for debugging or threshold tuning:

```bash
python skills/lena/routing_score.py --task "Add JWT refresh tokens to the auth service" --verbose
python skills/lena/routing_score.py --task "Deploy to production and run database migrations" --json
```

### Agent manifest

`agents.manifest.yaml` maps domains to specialist agent definitions. Each entry specifies a name, tool list, and model. Most agents default to `gpt-5.5`; the `technical-writer` agent defaults to `ollama/llama3`.

---

## License

See `LICENSE` for terms.
