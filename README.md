# LGDL v1.0 Beta

Language-Game Definition Language (LGDL) lets you describe conversational "games"—sets of moves, triggers, and actions—that can be parsed, compiled to an intermediate representation, and executed at runtime.

**v1.0 Beta** adds critical **security**, **scalability**, **determinism**, and **multi-turn conversation** capabilities:

- 🔒 **Template Security** – AST-based validation preventing RCE (error taxonomy E001-E499)
- 🎮 **Multi-Game API** – Registry for concurrent games with `/games/{id}/move` endpoints
- 🎯 **Deterministic Embeddings** – SQLite cache with version locking for reproducible confidence scores
- 💬 **Multi-Turn Conversations** – State management with SQLite persistence, context enrichment, and <10ms read/write latency
- 📊 **196 Tests** – Comprehensive coverage including 36 state management tests

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

### Multi-Turn Conversation State (NEW - v1.0-beta)
- **Persistent Storage**: SQLite backend (`~/.lgdl/conversations.db`) with conversation and turn history
- **Context Enrichment**: Short utterances enhanced with conversation history (e.g., "my chest" → "pain in chest")
- **Performance**: <10ms read/write latency for ongoing conversations
- **Thread-Safe**: Concurrent conversation access with asyncio locks
- **Optional**: Disable with `LGDL_STATE_DISABLED=1` for stateless mode

### Tooling
- CLI (`lgdl`) for validation, compilation, and serving
- Example games: medical scheduling, simple greeting
- Golden dialog testing framework
- Comprehensive pytest coverage (196 tests)

---

## Repository Layout

```
lgdl/
  spec/            # Grammar definitions (.lark /.ebnf)
  parser/          # AST nodes, parser, IR compiler
  runtime/         # Multi-game registry, matcher, policy, capabilities
    templates.py   # Secure template renderer
    registry.py    # Game registry for multi-game support
    negotiation.py # Negotiation state management
    state.py       # Multi-turn conversation state manager (NEW v1.0-beta)
    context.py     # Context enrichment for short utterances (NEW v1.0-beta)
    storage/       # Persistent storage backends (NEW v1.0-beta)
      sqlite.py    # SQLite conversation storage
  cli/             # Click-based `lgdl` CLI with serve command
  errors.py        # Error taxonomy (E001-E499)
examples/medical/  # Sample game + golden dialogs + capability contract
scripts/           # Golden runner utilities
tests/             # 196 pytest tests covering all features
  test_state_manager.py   # 36 state management tests (NEW)
  test_context.py         # Context enrichment tests (NEW)
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
uv run lgdl serve --games medical:examples/medical/game.lgdl,greeting:examples/greeting/game.lgdl

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

**Note**: The `negotiation` field appears only when the negotiation loop runs (success or failure). If negotiation doesn't trigger (confidence already above threshold or no clarify action), this field is omitted from the response.

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
  greeting:examples/greeting/game.lgdl

# Custom port
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 8080

# Dev mode (hot reload)
uv run lgdl serve --games medical:examples/medical/game.lgdl --dev
```

---

## Tests & Quality

### Run All Tests
```bash
# All 196 tests (160 core + 36 state management)
uv run pytest -v

# Quick mode
uv run pytest -q

# Specific test suites
uv run pytest tests/test_templates.py -v       # Template security (63 tests)
uv run pytest tests/test_registry.py -v        # Multi-game API (18 tests)
uv run pytest tests/test_state_manager.py -v   # State management (36 tests)
uv run pytest tests/test_context.py -v         # Context enrichment (8 tests)

# Run with state management disabled (test backward compatibility)
LGDL_STATE_DISABLED=1 uv run pytest -v
```

### Golden Dialog Tests
```bash
# End-to-end: starts API, runs goldens, shuts down
uv run bash scripts/run_goldens.sh

# Manual - Test individual games (requires API running)
# Medical game (✅ 4/4 passing)
uv run python scripts/goldens.py \
  --api http://127.0.0.1:8000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml -v

# Greeting game (✅ 5/5 passing)
uv run python scripts/goldens.py \
  --api http://127.0.0.1:8000/games/greeting/move \
  --file examples/greeting/golden_dialogs.yaml -v

# Test all working games
for game in medical greeting; do
  uv run python scripts/goldens.py \
    --api http://127.0.0.1:8000/games/$game/move \
    --file examples/$game/golden_dialogs.yaml
done
```

### Test Coverage by Feature

| Feature | Tests | Files |
|---------|-------|-------|
| Template Security | 63 | `test_errors.py`, `test_templates.py` |
| Multi-Game API | 18 | `test_registry.py` |
| **State Management** | **36** | **`test_state_manager.py`** (NEW) |
| Embedding Cache | 14 | `test_embedding_cache.py` |
| **Context Enrichment** | **8** | **`test_context.py`** (NEW) |
| Negotiation | 13 | `test_negotiation.py` |
| Parser/Runtime | 44 | `test_conformance.py`, `test_runtime.py`, etc. |
| **Total** | **196** | |

### Multi-Turn Conversation Testing (NEW v1.0-beta)

Test real multi-turn conversations with the E2E test script:

```bash
# Start server on port 5555
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 5555

# Run multi-turn E2E test (in another terminal)
python test_multiturn_e2e.py
```

**Test validates**:
- 3-turn conversation flow
- State persistence in `~/.lgdl/conversations.db`
- Context enrichment for short utterances
- Turn history tracking

**Sample conversation**:
```
Turn 1: "I have severe chest pain"
  → Matched: cardiac_emergency (0.92 confidence)

Turn 2: "it started an hour ago"
  → Enriched to: "pain started an hour ago"
  → Matched: pain_assessment (0.75 confidence)

Turn 3: "yes it's getting worse"
  → Enriched with previous context
  → Matched: pain_assessment (0.75 confidence)
```

All 3 turns stored in database with conversation ID `test-e2e-{timestamp}`.

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
export LGDL_GAMES=medical:examples/medical/game.lgdl,greeting:examples/greeting/game.lgdl

# Dev mode (enables hot reload endpoint)
export LGDL_DEV_MODE=1
```

#### State Management Configuration (v1.0-beta)
```bash
# Disable state management (run in stateless mode like v1.0-alpha)
export LGDL_STATE_DISABLED=1

# State management is ENABLED by default
# - Conversations stored in ~/.lgdl/conversations.db
# - Turn history persisted across server restarts
# - Context enrichment for short utterances
# - <10ms read/write latency
```

---

## Operational

### Game Registry

The `GameRegistry` (introduced in v1.0-alpha-foundation) manages multiple games concurrently.

**Current Implementation**: In-memory only
- Games are registered at API startup via `LGDL_GAMES` env var or `--games` CLI flag
- Registry cleared on server restart
- No persistence between runs

**Planned** (future enhancement):
```bash
# JSON manifest for persistence
lgdl serve --registry data/registry.json

# SQLite registry for multi-instance coordination
lgdl serve --registry sqlite:///data/registry.db
```

**Registry Contents**:
- Game metadata (id, name, version, file_hash)
- Compiled IR (in-memory)
- Per-game runtime instances
- Last compiled timestamp

**Hot Reload** (dev mode only):
```bash
# Reload specific game from disk
curl -X POST http://127.0.0.1:8000/games/medical/reload
```

**File Hash Tracking**:
- SHA256 hash (first 8 chars) computed on registration
- Used for cache invalidation (planned)
- Visible in `GET /games` and `GET /games/{id}` responses

---

## Security

### Template Security (P0-1)

Templates are validated with AST whitelisting to prevent code injection:

**Allowed**:
- Variables: `{doctor}`, `{user_name}`
- **Nested lookups** (dictionary traversal): `{user.name}`, `{user.profile.age}`
- Fallbacks: `{doctor?any provider}`, `{user.name?Guest}`
- Arithmetic: `${age + 5}`, `${(a + b) * 2}`
- Operators: `+`, `-`, `*`, `/`, `//`, `%`, unary `-`

**Forbidden** (raises SecurityError):
- **Dotted paths in expressions**: `${user.name}` → E010 (use `{user.name}` instead)
- Exponentiation: `${2 ** 999}` → E010
- Function calls: `${len(x)}` → E010
- Attribute access: `${obj.__class__}` → E010
- Subscripts: `${data['key']}` → E010
- Comprehensions, lambdas, etc. → E010

**Key Distinction**:
- ✅ `{user.name}` - Dictionary traversal (safe, allowed)
- ❌ `${user.name}` - Python attribute access (unsafe, blocked)

**Limits**:
- Max expression length: 256 chars → E011
- Max magnitude: ±1e9 → E012

**Examples**:
```python
# Safe variable lookups with nesting
"{doctor}"           # Direct lookup
"{user.name}"        # Nested dictionary: context["user"]["name"]
"{user.name?Guest}"  # With fallback

# Safe arithmetic (variables only, no dots)
"${age + 5}"         # Works if context = {"age": 30}
"${(a + b) * 2}"     # Works if context = {"a": 5, "b": 10}

# Blocked for security
"${user.name}"       # ❌ Attribute access in expression
"${__import__('os')}" # ❌ Function call
"${2 ** 999}"        # ❌ CPU bomb risk
```

---

## Embedding Cache

Embeddings are cached in `.embeddings_cache/` (SQLite) with versioning for reproducibility:

- **Cache key**: `(text_hash, model, version)`
- **Version lock**: Warns on model mismatch, doesn't cache mismatched versions
- **Offline fallback**: TF-IDF character bigrams (256-dim, deterministic)
- **Persistence**: Survives restarts, shared across instances

**Note**: `.embeddings_cache/` is gitignored. Delete it to force re-caching.

---

## Negotiation & Clarification

LGDL supports multi-round clarification when initial confidence is below threshold.

### How It Works

When a move matches with **confidence < threshold** and has an **uncertain block with clarify action**, the runtime enters a negotiation loop:

1. Ask clarification question
2. User responds
3. Update context with response
4. Re-match with enriched input
5. Check stop conditions

**Note**: After successful negotiation, execution continues with the **same move** (no global re-ranking). The enriched input is only used to re-evaluate confidence for the current move.

### Stop Conditions (Priority Order)

1. **Threshold met** (confidence ≥ threshold) → ✓ SUCCESS
2. **Max rounds** (default: 3) → ✗ FAILURE
3. **Stagnation** (2 consecutive Δconf < 0.05) → ✗ FAILURE

### Configuration

```bash
# Enable/disable negotiation (default: enabled)
export LGDL_NEGOTIATION=1

# Max clarification rounds (default: 3)
export LGDL_NEGOTIATION_MAX_ROUNDS=3

# Stagnation threshold (default: 0.05)
export LGDL_NEGOTIATION_EPSILON=0.05
```

### Error Codes

When things go wrong, you'll see these E200-E2xx errors:

- **E200**: Move has no clarify action in the uncertain block
  - *When you'll see it*: Negotiation requested but move definition lacks `if uncertain { ask for clarification: "..." }`

- **E201**: Negotiation max iterations exceeded (internal safety limit)
  - *When you'll see it*: Hard guard tripped — report as bug if encountered

- **E202**: User prompt callback not implemented (stub invoked)
  - *When you'll see it*: Server lacks prompt channel (OK in tests; mock `_prompt_user()`)

### Manifest Format

Successful or failed negotiation appears in turn manifests:

```json
{
  "move_id": "appointment_request",
  "confidence": 0.88,
  "negotiation": {
    "enabled": true,
    "rounds": [
      {
        "n": 1,
        "q": "Which doctor?",
        "a": "Dr. Smith",
        "before": 0.65,
        "after": 0.88,
        "delta": 0.23
      }
    ],
    "final_confidence": 0.88,
    "reason": "threshold_met"
  }
}
```

### Testing

Mock the `_prompt_user` callback in tests:

```python
with patch.object(runtime, '_prompt_user', return_value="Smith"):
    result = await runtime.process_turn(...)
```

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

## Multi-Turn Conversations (v1.0-beta)

### ✅ Conversation State Management

**Current behavior**: Conversations maintain persistent state with history, context, and turn tracking.

**Capabilities**:
- ✅ Multi-turn pattern matching with conversation memory
- ✅ Variable extraction from rich inputs (`{location}`, `{severity}`)
- ✅ **Context enrichment** for short utterances (e.g., "my chest" → "pain in chest")
- ✅ **Turn history** persisted in SQLite (`~/.lgdl/conversations.db`)
- ✅ **State persistence** survives server restarts
- ✅ **Sub-10ms latency** for read/write operations

**Example**:
```
System: "Where does it hurt?"
User: "My chest"
System: [Enriched to "pain in chest"] → Matches pain_assessment

System: "How severe is the pain?"
User: "It started an hour ago"
System: [Enriched with previous context] → Continues assessment
```

The system maintains conversation context and enriches short responses with relevant history.

**Database Schema**:
- `conversations` table: metadata, turn count, awaiting_response flag
- `turns` table: full turn history with timestamps, confidence scores
- `extracted_context` table: parameter tracking across turns

**Performance Benchmarks**:
```
Write turn:                3.09ms  ✅
Read from cache:           0.00ms  ✅
Read from database (cold): 0.76ms  ✅
```

### Future Enhancements (v2.0 Roadmap)

Advanced conversation features planned:
- **Explicit slot filling**: Define required information per move
- **Auto-prompting**: Automatically ask for missing required slots
- **Typed validation**: Validate responses against expected types
- **Conditional execution**: Only call capabilities when all required information collected

---

## Roadmap

### Completed (v1.0-beta)
- ✅ P0-1: Template Security with AST validation
- ✅ P0-2: Multi-Game API with Registry
- ✅ P1-2: Deterministic Embedding Cache
- ✅ **P1-1: Multi-Turn Conversation State Management** (NEW)
  - SQLite persistence with turn history
  - Context enrichment for short utterances
  - <10ms read/write latency
  - Thread-safe concurrent access
- ✅ Negotiation loops with confidence boosting

### Planned (v1.0-stable)
- Grammar v1.0: Capability await/timeout, context guards, learning hooks
- IR compiler updates
- Learning pipeline hooks
- Enhanced negotiation with backtracking

### Planned (v2.0)
- **Explicit slot filling**: Required/optional field definitions
- **Auto-prompting**: Automatic question generation for missing slots
- **Typed validation**: Range checks, enums, custom validators
- **Conditional capabilities**: Only execute when all requirements met
- **Conversation branching**: Multiple dialogue paths with state transitions

See [docs/P0_P1_CRITICAL_FIXES.md](docs/P0_P1_CRITICAL_FIXES.md) for implementation details.

---

## Examples

LGDL includes 5 example games showcasing different features:

### 1. Medical ER Triage (`examples/medical/`)
**Features**: Emergency room triage with multi-turn conversations, pattern matching, and capability integration
- Moves: pain_assessment, cardiac_emergency, respiratory_distress, trauma_intake, geriatric_fall, fever_assessment, appointment_request, book_intent
- Demonstrates: **Multi-turn state management**, confidence-based routing, variable extraction, context enrichment, external capability calls, safety-critical pattern matching
- Golden tests: 23 scenarios
- **NEW v1.0-beta**: Multi-turn conversations with context enrichment - can now process follow-up responses like "my chest" or "it started an hour ago" by enriching with conversation history
- See [`examples/medical/README.md`](examples/medical/README.md) for complete documentation including real multi-turn conversation examples

### 2. Greeting (`examples/greeting/`)
**Features**: Simple conversational interactions
- Moves: greeting, farewell, small_talk
- Demonstrates: Pattern matching, confidence levels, offer choices
- Golden tests: 5 scenarios

### 3. Online Shopping (`examples/shopping/`)
**Features**: E-commerce with price calculations
- Moves: product_search, price_inquiry, add_to_cart, apply_discount, checkout, compare_prices, bulk_order
- Demonstrates: Template arithmetic (`${price * quantity}`), nested context (`{user.cart.total}`), fallbacks (`{var?default}`)
- Golden tests: 12 scenarios
- Highlights:
  - Price calculations with discount arithmetic
  - Bulk order pricing with dynamic discounts
  - Cart total tracking across conversations

### 4. Customer Support (`examples/support/`)
**Features**: Multi-tier support with escalation
- Moves: issue_report, technical_issue, billing_question, reset_password, escalate_request, refund_request
- Demonstrates: Escalation flows, if/else chains, successful/failed conditions, strict pattern matching
- Golden tests: 18 scenarios
- Highlights:
  - Conditional escalation based on severity
  - Password reset with success/failure handling
  - Refund processing with fallback to human agent

### 5. Restaurant Booking (`examples/restaurant/`)
**Features**: Reservation system with dietary accommodations
- Moves: reservation, menu_inquiry, special_request, cancel_reservation, modify_reservation, group_booking
- Demonstrates: Fuzzy matching, context-sensitive patterns, learned patterns, time arithmetic
- Golden tests: 25 scenarios
- Highlights:
  - Table capacity calculation (`${party_size * 2}` seats)
  - Special dietary restrictions with allergen tracking
  - Large group handling with automatic private room escalation

### Running Examples

**Start server with all games**:
```bash
uv run lgdl serve --games \
  medical:examples/medical/game.lgdl,\
  greeting:examples/greeting/game.lgdl,\
  shopping:examples/shopping/game.lgdl,\
  support:examples/support/game.lgdl,\
  restaurant:examples/restaurant/game.lgdl
```

**Interactive chat** (requires running server):
```bash
# Chat with shopping assistant
uv run python scripts/chat.py --game shopping --api http://localhost:8000

# Chat with support bot
uv run python scripts/chat.py --game support --api http://localhost:8000

# Export conversation to JSON
uv run python scripts/chat.py --game restaurant --export my_convo.json
```

**Test with golden dialogs**:
```bash
# Test shopping game
uv run python scripts/goldens.py \
  --api http://localhost:8000/games/shopping/move \
  --file examples/shopping/golden_dialogs.yaml -v

# Test all examples
for game in shopping support restaurant; do
  uv run python scripts/goldens.py \
    --api http://localhost:8000/games/$game/move \
    --file examples/$game/golden_dialogs.yaml
done
```

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
