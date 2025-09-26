Here’s a drop-in **`docs/MVP_TASKS.md`** you can place in the repo. It’s organized as actionable checklists with acceptance criteria, ownership hints, and dependencies. You can copy/paste as-is.

---

# MVP_TASKS.md

**Project:** LGDL MVP
**Goal:** Parser → IR → Runtime with `/move`, golden tests, and optional OpenAI embeddings.
**Owner(s):** @tech-lead, @backend, @ml, @devops, @fe (where applicable)

---

## 0) Ground Rules (Definition of Done)

* ✅ Code builds with `uv sync` (optionally `--extra openai --extra dev`).
* ✅ `uv run pytest -q` passes locally and in CI.
* ✅ Golden suite passes via `uv run python scripts/goldens.py`.
* ✅ No secrets committed; `.env`/keys are injected via env vars.
* ✅ API errors are sanitized (no stack traces in responses).
* ✅ Lint (optional) is clean or warnings are justified.

---

## 1) Grammar & Parser

### 1.1 Lark Grammar (authoritative)

* [x] Add/verify `lgdl/spec/grammar_v0_1.lark`
* [x] Keep `lgdl/spec/grammar_v0_1.ebnf` aligned with Lark
* **Acceptance:** `uv run lgdl validate examples/medical/game.lgdl` succeeds

### 1.2 Transformer → AST

* [x] Implement/verify `lgdl/parser/parser.py` (Transformer)
* [x] Typed dataclasses in `lgdl/parser/ast.py`
* **Acceptance:** AST contains `Game → Moves → Triggers/Blocks/Actions` with correct fields

### 1.3 Parser tests

* [x] `tests/test_conformance.py` covers: description, capabilities, triggers, modifiers, confidence, blocks
* **Acceptance:** `uv run pytest -q` passes

**Owner:** @backend
**Dependencies:** Lark grammar
**Estimated:** 1–2d

---

## 2) IR Compiler

### 2.1 AST → IR

* [x] Compile patterns to regex; capture `{var}` groups
* [x] Normalize confidence levels → numeric thresholds
* [x] Preserve blocks: `when`, `if_chain`
* **Acceptance:** `uv run lgdl compile examples/medical/game.lgdl -o out.ir.json` produces stable IR

### 2.2 IR tests

* [x] Verify thresholds, regexes, block shapes
* **Acceptance:** `tests/test_conformance.py` passes

**Owner:** @backend
**Dependencies:** Parser
**Estimated:** 1d

---

## 3) Runtime

### 3.1 Matcher (Two-stage)

* [x] Lexical: regex gate & params extraction
* [x] Semantic: OpenAI embeddings cosine (fallback to token overlap)
* [x] Caching for pattern embeddings
* **Acceptance:** With and without `OPENAI_API_KEY`, golden tests pass

### 3.2 Safety & Policy

* [x] `runtime/firewall.py` sanitizes input
* [x] `runtime/policy.py` allowlists capability functions
* **Acceptance:** Malicious inputs don’t cause crashes or capability execution

### 3.3 Capability shim

* [x] `runtime/capability.py` validates payload against `examples/.../capability_contract.json`
* **Acceptance:** Capability returns mocked availability message

### 3.4 Orchestrator

* [x] `runtime/engine.py` selects best move, evaluates conditions, executes actions
* [x] Template substitution `{var}` and `{var?fallback}`
* **Acceptance:** Direct curl to `/move` produces expected responses

**Owner:** @backend, @ml
**Dependencies:** IR, cap contract
**Estimated:** 2–3d

---

## 4) API & CLI

### 4.1 FastAPI

* [x] `runtime/api.py` `POST /move` (returns `move_id`, `confidence`, `response`, `action`, `manifest_id`, `latency_ms`, `firewall_triggered`)
* [x] Use `time.perf_counter()` for latency
* **Acceptance:** `curl` request returns 200 with expected schema

### 4.2 CLI

* [x] `lgdl validate` / `lgdl compile`
* **Acceptance:** `uv run lgdl validate ...` & `uv run lgdl compile ...` work

**Owner:** @backend
**Dependencies:** Runtime
**Estimated:** 0.5–1d

---

## 5) Examples & Goldens

### 5.1 Example game

* [x] `examples/medical/game.lgdl` with at least 2 moves
* **Acceptance:** Validates/compiles cleanly

### 5.2 Golden dialogs

* [x] `examples/medical/golden_dialogs.yaml` with:

  * [x] Positive match (doctor name)
  * [x] Negotiation/uncertain path
  * [x] Near-miss (boundary confidence)
  * [x] Unauthorized capability scenario
* **Acceptance:** All pass with `scripts/goldens.py`

### 5.3 Golden runner

* [x] `scripts/goldens.py` (points to `http://localhost:8000/move`)
* **Acceptance:** Non-zero exit on failure, verbose mode `-v` shows payloads

**Owner:** @backend, @ml
**Dependencies:** Runtime running
**Estimated:** 0.5–1d

---

## 6) Tooling & Packaging

### 6.1 `pyproject.toml` (uv-first)

* [x] Runtime deps in `[project.dependencies]`
* [x] `openai` extra: `httpx`
* [x] `dev` extra: `pytest`, `pytest-asyncio`, `requests`, `PyYAML`, `ruff`
* [x] `[project.scripts] lgdl = "lgdl.cli.main:cli"`
* **Acceptance:**

  * `uv sync` (base) works
  * `uv sync --extra openai --extra dev` works

### 6.2 Lint (optional)

* [x] `ruff` configured in `pyproject.toml`
* **Acceptance:** `uv run ruff check .` is clean or warnings justified

**Owner:** @devops
**Dependencies:** Project files present
**Estimated:** 0.5d

---

## 7) CI (optional but recommended)

* [ ] GitHub Actions workflow:

  * `uv sync --extra dev`
  * `uv run pytest -q`
  * Start API (background) + `uv run python scripts/goldens.py`
* **Acceptance:** CI must fail on any test/golden failure

**Owner:** @devops
**Dependencies:** Tests & runner
**Estimated:** 0.5–1d

---

## 8) Documentation

* [x] `README.md`: quickstart, API example, uv commands
* [x] `docs/DESIGN.md`: architecture & decisions (present)
* [x] `AGENTS.md`: instructions for code agents (present)
* **Acceptance:** New dev can set up, run tests, and understand structure in <30 minutes

**Owner:** @tech-lead
**Estimated:** 0.5d

---

## 9) Feature Enhancements (tracked)

* [x] **Task:** Precise latency telemetry in `/move`
  * **Acceptance:** `latency_ms` derived via `time.perf_counter()` with two-decimal rounding; responses never report `0` for non-zero work.
  * **Owner:** @backend
  * **Estimate:** 0.25d

* [x] **Task:** Expand booking patterns and enforce capability denial
  * **Acceptance:** `book_intent` move handles doctor phrasing variations and goldens validate denial messaging without capability execution.
  * **Owner:** @backend
  * **Estimate:** 0.5d

* [x] **Task:** Golden runner action assertions
  * **Acceptance:** `scripts/goldens.py` compares expected and actual `action` fields, failing on mismatch.
  * **Owner:** @backend
  * **Estimate:** 0.25d

---

## Stretch (Post-MVP)

* [ ] Add `scripts/goldens_junit.py` to emit JUnit XML for CI test reporting
* [ ] State backend (in-memory → Redis toggle) for persistent context
* [ ] Pattern coverage metrics: distribution of scores, hit rates
* [ ] More modifiers: `context-sensitive`, `learned` (implement semantics)
* [ ] Basic Studio (Monaco editor) prototype

---

## Milestones

### Day 7 (Parser + IR)

* ✅ Grammar, AST, IR compiler, basic tests pass

### Day 14 (Runtime)

* ✅ Two-stage matcher + runtime + `/move` stable
* ✅ Capability shim + policy + firewall

### Day 21 (Quality)

* ✅ Goldens + unit tests green
* ✅ Docs finalized; CI (if enabled) green

---

## Risks & Mitigations

* **Embedding latency/cost** → Cache embeddings; fallback to offline scorer.
* **Pattern over-match** → Prefer `strict` for critical flows; strengthen goldens.
* **Security regression** → Keep firewall patterns up-to-date; add negative tests.
* **Spec drift (Lark vs EBNF)** → Treat Lark as source of truth; regenerate EBNF on change.

---

## Quick Commands (for convenience)

```bash
# Setup
uv venv .venv
uv sync --extra openai --extra dev

# Run API
uv run uvicorn lgdl.runtime.api:app --reload --port 8000

# Validate & compile
uv run lgdl validate examples/medical/game.lgdl
uv run lgdl compile  examples/medical/game.lgdl -o out.ir.json

# Unit tests
uv run pytest -q

# Goldens (runtime must be running)
uv run python scripts/goldens.py -v
```

---
