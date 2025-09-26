# AGENTS.md

**Purpose:** Operating instructions for a code agent working in this repository.
**Project:** LGDL MVP — parser (Lark) → IR → runtime with FastAPI `/move`, optional OpenAI embedding matcher.

---

## Repo Map (important files)

```
lgdl/
  spec/
    grammar_v0_1.lark         # Lark grammar (authoritative for MVP)
    grammar_v0_1.ebnf         # EBNF reference (human-readable)
  parser/
    ast.py                    # Typed AST dataclasses
    parser.py                 # Lark parser + Transformer → AST
    ir.py                     # AST → IR compiler
  runtime/
    api.py                    # FastAPI app exposing POST /move
    engine.py                 # LGDLRuntime orchestration
    matcher.py                # Two-stage matcher (OpenAI embeddings + fallback)
    firewall.py               # Prompt-injection sanitation
    policy.py                 # Capability allowlist
    capability.py             # Example MCP-like capability client
  cli/
    main.py                   # `lgdl` CLI: validate/compile
examples/
  medical/
    game.lgdl                 # Sample LGDL game
    golden_dialogs.yaml       # Golden test spec
    capability_contract.json  # Example capability schema
tests/
  test_conformance.py
  test_runtime.py
docs/
  DESIGN.md
  MVP_TASKS.md
pyproject.toml                # uv-compatible project definition
README.md
```

---

## Environment & Dependencies (use `uv`)

Agents should prefer `uv` for setup and execution.

### Create & sync env

```bash
uv venv .venv
uv sync                 # runtime deps
# Optionally include embeddings + dev tools:
uv sync --extra openai --extra dev
```

### Run commands (no manual activation needed)

```bash
# Start API (FastAPI/uvicorn)
uv run uvicorn lgdl.runtime.api:app --reload --port 8000

# CLI
uv run lgdl validate examples/medical/game.lgdl
uv run lgdl compile  examples/medical/game.lgdl -o out.ir.json

# Tests
uv run pytest -q
```

### OpenAI embeddings (optional, recommended)

```bash
export OPENAI_API_KEY=sk-...  # required to use embeddings
uv sync --extra openai        # ensures httpx client is present
```

If `OPENAI_API_KEY` is absent, the matcher falls back to token-overlap scoring; tests still pass.

---

## HTTP API (for integration tests)

* **Endpoint:** `POST /move`
* **Request:**

```json
{
  "conversation_id": "c1",
  "user_id": "u1",
  "input": "I need to see Dr. Smith",
  "context": {}
}
```

* **Response (example):**

```json
{
  "move_id": "appointment_request",
  "confidence": 0.87,
  "response": "Availability for Smith: Tue 10:00, Wed 14:00",
  "action": "check_availability",
  "manifest_id": "uuid",
  "latency_ms": 123,
  "firewall_triggered": false
}
```

---

## Golden Dialog Runner (shell+python) — `scripts/run_goldens.sh`

Create this script (the repo may already include it; if not, add it):

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure env is ready
uv venv "$ROOT_DIR/.venv" >/dev/null 2>&1 || true
source "$ROOT_DIR/.venv/bin/activate"
uv sync

# Start API
uv run uvicorn lgdl.runtime.api:app --port 8000 --reload &
API_PID=$!
sleep 2

# Run goldens (inline python uses requests + PyYAML; installed via dev extra)
uv run python - <<'EOF'
import yaml, requests, sys
g = yaml.safe_load(open("examples/medical/golden_dialogs.yaml"))
failures = 0
for d in g["dialogs"]:
    for t in d["turns"]:
        r = requests.post("http://localhost:8000/move", json={
            "conversation_id":"c1","user_id":"u1","input":t["input"]
        })
        if r.status_code != 200:
            print(f"[FAIL] {d['name']}: HTTP {r.status_code}")
            failures += 1
            continue
        data = r.json()
        exp = t["expect"]
        ok = True
        if "move" in exp and data["move_id"] != exp["move"]:
            print(f"[FAIL] {d['name']}: move {data['move_id']} != {exp['move']}")
            ok = False
        if "confidence" in exp:
            op, thr = exp["confidence"][:2], float(exp["confidence"][2:])
            if op == ">=" and data["confidence"] < thr: ok = False
            if op == "<=" and data["confidence"] > thr: ok = False
            if not ok:
                print(f"[FAIL] {d['name']}: confidence {data['confidence']} vs {exp['confidence']}")
        if "response_contains" in exp:
            for s in exp["response_contains"]:
                if s.lower() not in data["response"].lower():
                    print(f"[FAIL] {d['name']}: missing '{s}' in response")
                    ok = False
        print(f"[{'OK' if ok else 'FAIL'}] {d['name']}")
        if not ok: failures += 1
sys.exit(1 if failures else 0)
EOF

kill $API_PID
```

Run:

```bash
chmod +x scripts/run_goldens.sh
uv run bash scripts/run_goldens.sh
```

> Dependencies: `requests` and `PyYAML` are included in the `dev` extra of `pyproject.toml`. Use `uv sync --extra dev` if missing.

---

## Agent Tasks (natural language → concrete actions)

* **“Parse and compile the example game”**

  ```bash
  uv run lgdl validate examples/medical/game.lgdl
  uv run lgdl compile  examples/medical/game.lgdl -o out.ir.json
  ```

* **“Start the API and hit it”**

  ```bash
  uv run uvicorn lgdl.runtime.api:app --reload --port 8000
  curl -s -X POST localhost:8000/move -H 'content-type: application/json' \
    -d '{"conversation_id":"c1","user_id":"u1","input":"I need to see Dr. Smith"}' | jq
  ```

* **“Run tests”**

  ```bash
  uv run pytest -q
  ```

* **“Run golden dialogs end-to-end”**

  ```bash
  uv run bash scripts/run_goldens.sh
  ```

* **“Enable embeddings (OpenAI)”**

  ```bash
  export OPENAI_API_KEY=sk-...
  uv sync --extra openai
  uv run pytest -q
  ```

* **“Add a new move and test it”**

  1. Edit `examples/medical/game.lgdl` — add a `move` with `when … says … like: [...]`
  2. Update `examples/medical/golden_dialogs.yaml` with a new dialog
  3. `uv run lgdl validate examples/medical/game.lgdl`
  4. `uv run bash scripts/run_goldens.sh`

---

## Coding Conventions & Guardrails (for agents)

* **Grammar source of truth:** `lgdl/spec/grammar_v0_1.lark`. If you alter it, **update tests** and regenerate any doc snippets in `grammar_v0_1.ebnf`.
* **AST invariants:** Keep `ast.py` fields backward compatible where possible (additive changes preferred).
* **IR compiler:** `ir.py` should remain deterministic and side-effect free. Regexes are case-insensitive and expand `{var}` capture groups.
* **Matcher rules:**

  * `strict` requires lexical match (regex) to score.
  * `fuzzy` emphasizes semantic similarity (embeddings when available, otherwise token overlap).
  * Other modifiers are carried through but may be no-ops in MVP.
* **Security:** Never return raw exceptions to clients. `firewall.sanitize` must run on all inputs.
* **Capabilities:** Enforce via `policy.PolicyGuard`. Add new capabilities with contracts before invocation.
* **Performance:** Avoid expensive calls in hot paths; the embedding client caches pattern vectors.
* **Tests:** Keep `tests/` green. If changing behavior, update goldens.

---

## Common Environment Variables

* `OPENAI_API_KEY` — enables embedding-based similarity (`matcher.py`); fallback is automatic if absent.
* `PORT` (optional) — if you customize server port.

---

## Minimal Agent Checklist

1. Sync env with `uv` (and `openai` extra if API key present).
2. Validate/compile the sample game.
3. Start API, exercise `/move`.
4. Run goldens.
5. Run `pytest`.
6. For changes: update grammar/AST/IR coherently, add tests, keep security checks.

---

If you (the agent) need to introduce new scripts, prefer placing them in `scripts/` and wiring them via `uv run …`.
