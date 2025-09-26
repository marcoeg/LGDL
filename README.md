# LGDL MVP (v0.1)

Language-Game Definition Language (LGDL) lets you describe conversational "games"—sets of moves, triggers, and actions—that can be parsed, compiled to an intermediate representation, and executed at runtime. This repository provides a complete MVP implementation:

- **Grammar & Parser** – authoritative Lark grammar (`lgdl/spec/grammar_v0_1.lark`) and transformer producing typed AST dataclasses.
- **IR Compiler** – deterministic AST-to-IR conversion (`lgdl/parser/ir.py`) with regex-backed triggers and confidence thresholds.
- **Runtime** – FastAPI `/move` endpoint orchestrating matching, policy checks, capability shims, and response generation.
- **Tooling** – CLI (`lgdl`) for validation/compilation, example medical scheduling game, golden dialog tests, and pytest coverage.

>  The runtime preloads a single game manifest (`examples/medical/game.lgdl`) at startup. All `/move` requests run against that compiled game. Serving multiple games concurrently would require additional routing (e.g., a `game_id`) or separate processes.

> The MVP grammar is a subset of the expanded specification in [`lgdl/spec/full_grammar_v1_0.ebnf`](lgdl/spec/full_grammar_v1_0.ebnf); the full grammar adds participants, vocabulary, context guards, learning rules, and richer templates while remaining additive over the baseline.
---

## Repository Layout

```
lgdl/
  spec/            # Grammar definitions (.lark /.ebnf)
  parser/          # AST nodes, parser, IR compiler
  runtime/         # FastAPI API, matcher, policy, capability shim
  cli/             # Click-based `lgdl` CLI
examples/medical/  # Sample game + golden dialogs + capability contract
scripts/           # Golden runner utilities
tests/             # Pytest coverage for parser/runtime
```

---

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (used for environment management and execution)
- Optional: `OPENAI_API_KEY` for embedding-based matching (falls back to token overlap otherwise)

---

## Setup

```bash
# create project-local virtualenv
uv venv .venv

# install baseline runtime dependencies
uv sync

# optional extras
uv sync --extra openai      # enable OpenAI HTTP client for embeddings
uv sync --extra dev         # add pytest, requests, PyYAML, ruff, etc.
```

`uv run …` automatically activates the virtualenv, so no manual `source .venv/bin/activate` is needed.

---

## CLI Usage

Validate and compile LGDL files via the packaged CLI entrypoint:

```bash
uv run lgdl validate examples/medical/game.lgdl
uv run lgdl compile  examples/medical/game.lgdl -o out.ir.json
```

The compiled IR contains regex triggers, confidence thresholds, and block/action metadata consumed by the runtime.

---

## Running the API

```bash
# optional: expose embedding key to enable cosine similarity scoring
export OPENAI_API_KEY=sk-...

# launch FastAPI runtime on http://127.0.0.1:8000
uv run uvicorn lgdl.runtime.api:app --reload --port 8000
```

Example request/response:

```bash
curl -s \
  -X POST http://127.0.0.1:8000/move \
  -H 'content-type: application/json' \
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
  "response": "I can check availability for Smith. Availability for Smith: Tue 10:00, Wed 14:00",
  "action": "check_availability",
  "manifest_id": "...",
  "latency_ms": 2.37,
  "firewall_triggered": false
}
```

---

## Tests & Goldens

```bash
# unit tests (pytest)
uv run pytest -q

# golden dialog runner (requires API running separately)
uv run python scripts/goldens.py --api http://127.0.0.1:8000/move -v
uv run python scripts/goldens.py --file examples/medical/golden_dialogs.yaml -v

# end-to-end convenience script: spins up API, runs goldens, shuts down
uv run bash scripts/run_goldens.sh
```

The golden dialogs in `examples/medical/golden_dialogs.yaml` assert move selection, confidence thresholds, actions, and response substrings for representative scenarios (confident match, negotiation, boundary confidence, capability denial).

---

## Optional Embedding Support

When `OPENAI_API_KEY` is provided and the `openai` extra is installed, `lgdl.runtime.matcher.TwoStageMatcher` uses cosine similarity between cached embeddings to influence scoring (`strict` triggers still short-circuit to high confidence). Without the key, the matcher falls back to deterministic token overlap.

---

## Contributing

- Keep `lgdl/spec/grammar_v0_1.lark` as the source of truth for grammar updates and ensure `lgdl/spec/grammar_v0_1.ebnf` stays aligned.

- Maintain backwards-compatible AST dataclasses where possible and extend tests/goldens when behaviour changes.
- Use `uv sync --extra dev` + `uv run pytest -q` before opening a PR.

---

## License

MIT © 2025 Graziano Labs Corp.
