# LGDL v1.0 Alpha Foundation

Language-Game Definition Language (LGDL) lets you describe conversational "games"—sets of moves, triggers, and actions—that can be parsed, compiled to an intermediate representation, and executed at runtime.

**v1.0 Alpha Foundation** adds critical **security**, **scalability**, and **determinism** improvements:

- 🔒 **Template Security** – AST-based validation preventing RCE (error taxonomy E001-E499)
- 🎮 **Multi-Game API** – Registry for concurrent games with `/games/{id}/move` endpoints
- 🎯 **Deterministic Embeddings** – SQLite cache with version locking for reproducible confidence scores
- 📊 **97+ Tests** – Comprehensive coverage (from 2 tests in MVP)

> **Migration from MVP v0.1**: See [CHANGELOG.md](CHANGELOG.md) for breaking changes and [docs/MIGRATION_MVP_TO_V1.md](docs/MIGRATION_MVP_TO_V1.md) for the full migration plan.

---

## Features

### Grammar & Parser
Authoritative Lark grammar (`lgdl/spec/grammar_v0_1.lark`) with typed AST dataclasses.

### IR Compiler
Deterministic AST-to-IR conversion (`lgdl/parser/ir.py`) with regex-backed triggers and confidence thresholds.

### Secure Template Engine (NEW)
- Supports `{var}`, `{var?fallback}`, `${arithmetic}` with AST validation
- Prevents code injection: no `**`, attribute access, subscripts, or function calls
- Constraints: 256 char max length, ±1e9 magnitude limit

### Multi-Game Runtime (NEW)
- **GameRegistry** managing multiple games concurrently
- **New endpoints**: `/healthz`, `/games`, `/games/{id}/move`
- **CLI**: `lgdl serve --games medical:examples/medical/game.lgdl`
- **Hot reload** in dev mode

### Deterministic Embeddings (NEW)
- SQLite cache with `(text_hash, model, version)` keys
- TF-IDF character bigram offline fallback (256-dim)
- Version lock warnings on model mismatch

### Tooling
- CLI (`lgdl`) for validation, compilation, and serving
- Example medical scheduling game
- Golden dialog testing framework
- Comprehensive pytest coverage

---

## Repository Layout

```
lgdl/
  spec/            # Grammar definitions (.lark /.ebnf)
  parser/          # AST nodes, parser, IR compiler
  runtime/         # Multi-game registry, matcher, policy, capabilities
    templates.py   # Secure template renderer
    registry.py    # Game registry for multi-game support
    negotiation.py # Negotiation state management (P1-1, WIP)
  cli/             # Click-based `lgdl` CLI with serve command
  errors.py        # Error taxonomy (E001-E499)
examples/medical/  # Sample game + golden dialogs + capability contract
scripts/           # Golden runner utilities
tests/             # 97+ pytest tests covering all features
docs/              # Migration guides, implementation plans
CHANGELOG.md       # Full version history
```

---

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (environment management and execution)
- Optional: `OPENAI_API_KEY` for embedding-based matching (falls back to offline TF-IDF)

---

## Quick Start

### Setup

```bash
# Create project-local virtualenv
uv venv .venv

# Install all dependencies including dev tools
uv sync --extra dev

# Optional: Enable OpenAI embeddings
uv sync --extra openai
export OPENAI_API_KEY=sk-...
```

### Run the Multi-Game API

```bash
# Start server with one game
uv run lgdl serve --games medical:examples/medical/game.lgdl

# Or with multiple games
uv run lgdl serve --games medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl

# Dev mode with hot reload
uv run lgdl serve --games medical:examples/medical/game.lgdl --dev
```

Server runs on http://127.0.0.1:8000

### API Examples

#### Health Check
```bash
curl http://127.0.0.1:8000/healthz
```

```json
{
  "status": "healthy",
  "games_loaded": 1,
  "games": ["medical"]
}
```

#### List Games
```bash
curl http://127.0.0.1:8000/games
```

```json
{
  "games": [
    {
      "id": "medical",
      "name": "medical_scheduling",
      "version": "0.1",
      "file_hash": "a1b2c3d4"
    }
  ]
}
```

#### Execute Move
```bash
curl -X POST http://127.0.0.1:8000/games/medical/move \
  -H 'Content-Type: application/json' \
  -d '{
    "conversation_id": "c1",
    "user_id": "u1",
    "input": "I need to see Dr. Smith"
  }'
```

```json
{
  "move_id": "appointment_request",
  "confidence": 0.92,
  "response": "I can check availability for Smith.",
  "action": "check_availability",
  "manifest_id": "...",
  "latency_ms": 2.37,
  "firewall_triggered": false
}
```

#### Legacy Endpoint (Deprecated)
```bash
# Still works but includes deprecation warning header
curl -X POST http://127.0.0.1:8000/move \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"c1","user_id":"u1","input":"test"}'
```

---

## CLI Usage

### Validate Game Files
```bash
uv run lgdl validate examples/medical/game.lgdl
```

### Compile to IR
```bash
uv run lgdl compile examples/medical/game.lgdl -o out.ir.json
```

### Serve Multi-Game API
```bash
# Basic usage
uv run lgdl serve --games medical:examples/medical/game.lgdl

# Multiple games
uv run lgdl serve --games \
  medical:examples/medical/game.lgdl,\
  er:examples/er_triage.lgdl

# Custom port
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 8080

# Dev mode (hot reload)
uv run lgdl serve --games medical:examples/medical/game.lgdl --dev
```

---

## Tests & Quality

### Run All Tests
```bash
# All 97+ tests
uv run pytest -v

# Quick mode
uv run pytest -q

# Specific test files
uv run pytest tests/test_templates.py -v
uv run pytest tests/test_registry.py -v
```

### Golden Dialog Tests
```bash
# End-to-end: starts API, runs goldens, shuts down
uv run bash scripts/run_goldens.sh

# Manual (requires API running)
uv run python scripts/goldens.py --api http://127.0.0.1:8000/move -v
```

### Test Coverage by Feature

| Feature | Tests | Files |
|---------|-------|-------|
| Template Security | 63 | `test_errors.py`, `test_templates.py` |
| Multi-Game API | 18 | `test_registry.py` |
| Embedding Cache | 14 | `test_embedding_cache.py` |
| Parser/Runtime | 2 | `test_conformance.py`, `test_runtime.py` |
| **Total** | **97+** | |

---

## Configuration

### Environment Variables

#### Embedding Configuration
```bash
# Model selection (default: text-embedding-3-small)
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Version lock for reproducibility (default: 2025-01)
export OPENAI_EMBEDDING_VERSION=2025-01

# Enable/disable SQLite cache (default: 1)
export EMBEDDING_CACHE=1

# OpenAI API key (optional, uses offline fallback without it)
export OPENAI_API_KEY=sk-...
```

#### Server Configuration
```bash
# Multiple games (comma-separated game_id:path pairs)
export LGDL_GAMES=medical:examples/medical/game.lgdl,er:examples/er.lgdl

# Dev mode (enables hot reload endpoint)
export LGDL_DEV_MODE=1
```

---

## Security

### Template Security (P0-1)

Templates are validated with AST whitelisting to prevent code injection:

**Allowed**:
- Variables: `{doctor}`, `{user.name}`
- Fallbacks: `{doctor?any provider}`
- Arithmetic: `${age + 5}`, `${(a + b) * 2}`
- Operators: `+`, `-`, `*`, `/`, `//`, `%`, unary `-`

**Forbidden** (raises SecurityError):
- Exponentiation: `${2 ** 999}` → E010
- Function calls: `${len(x)}` → E010
- Attribute access: `${obj.__class__}` → E010
- Subscripts: `${data['key']}` → E010
- Comprehensions, lambdas, etc. → E010

**Limits**:
- Max expression length: 256 chars → E011
- Max magnitude: ±1e9 → E012

---

## Embedding Cache

Embeddings are cached in `.embeddings_cache/` (SQLite) with versioning for reproducibility:

- **Cache key**: `(text_hash, model, version)`
- **Version lock**: Warns on model mismatch, doesn't cache mismatched versions
- **Offline fallback**: TF-IDF character bigrams (256-dim, deterministic)
- **Persistence**: Survives restarts, shared across instances

**Note**: `.embeddings_cache/` is gitignored. Delete it to force re-caching.

---

## Migration from MVP v0.1

### Breaking Changes
None! Legacy `/move` endpoint still works (with deprecation warning).

### Recommended Updates

**Old API Usage**:
```bash
POST /move
```

**New API Usage**:
```bash
POST /games/{game_id}/move
```

**Old Server Start**:
```bash
uvicorn lgdl.runtime.api:app
```

**New Server Start**:
```bash
lgdl serve --games medical:examples/medical/game.lgdl
```

See [docs/MIGRATION_MVP_TO_V1.md](docs/MIGRATION_MVP_TO_V1.md) for full details.

---

## Roadmap

### Completed (v1.0-alpha-foundation)
- ✅ P0-1: Template Security with AST validation
- ✅ P0-2: Multi-Game API with Registry
- ✅ P1-2: Deterministic Embedding Cache

### In Progress
- 🚧 P1-1: Negotiation State Management (clarification loops)

### Planned (v1.0)
- Grammar v1.0: Capability await/timeout, context guards, learning hooks
- IR compiler updates
- Learning pipeline
- Full negotiation support

See [docs/P0_P1_CRITICAL_FIXES.md](docs/P0_P1_CRITICAL_FIXES.md) for implementation details.

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - Version history
- [docs/MIGRATION_MVP_TO_V1.md](docs/MIGRATION_MVP_TO_V1.md) - Migration guide
- [docs/P0_P1_CRITICAL_FIXES.md](docs/P0_P1_CRITICAL_FIXES.md) - Implementation guide
- [docs/DESIGN.md](docs/DESIGN.md) - Original MVP design
- [lgdl/spec/grammar_v0_1.lark](lgdl/spec/grammar_v0_1.lark) - Executable grammar
- [lgdl/spec/full_grammar_v1_0.ebnf](lgdl/spec/full_grammar_v1_0.ebnf) - v1.0 grammar spec

---

## Contributing

- Keep `lgdl/spec/grammar_v0_1.lark` as source of truth for grammar
- Maintain backward-compatible AST dataclasses where possible
- Add tests for new features (aim for >95% coverage)
- Run `uv run pytest -q` before committing
- Update CHANGELOG.md with notable changes

---

## License

MIT © 2025 Graziano Labs Corp.
