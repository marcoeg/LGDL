# LGDL MVP – Design Document

## Overview

The **Language-Game Definition Language (LGDL)** MVP demonstrates how conversational patterns can be expressed as structured **games** and executed by a deterministic runtime that integrates with large language models (LLMs).

The MVP focuses on three goals:

1. **Parsing & Validation** — Accept LGDL grammar (`.lgdl`) and produce an intermediate representation (IR).
2. **Deterministic Matching** — Match user inputs against declared moves with a two-stage strategy: lexical → semantic.
3. **Runtime Execution** — Orchestrate conversations, enforce safety policies, and expose a simple FastAPI `/move` endpoint.

This MVP is not feature-complete, but it provides a **foundation** to evolve into the full LGDL vision (learning pipeline, studio authoring environment, compliance, etc.).

---

## Scope

* **In Scope**

  * Parser using Lark grammar (`grammar_v0_1.lark`).
  * AST transformer → IR compiler (`parser/ir.py`).
  * Two-stage matcher (`runtime/matcher.py`):

    * Stage 1: Regex / lexical.
    * Stage 2: Semantic similarity (OpenAI embeddings with offline fallback).
  * Runtime orchestrator (`runtime/engine.py`):

    * Executes moves.
    * Produces responses defined in `.lgdl`.
    * Applies policy guard + firewall.
  * REST API (`runtime/api.py`):

    * POST `/move`: `{conversation_id, user_id, input}` → structured response.
  * CLI (`cli/main.py`):

    * `validate` and `compile` commands.
  * Example game (`examples/medical/game.lgdl`) and golden tests.
  * Golden runner (`scripts/goldens.py`) for regression verification.

* **Out of Scope (Future Work)**

  * Studio web editor.
  * Propose-only learning pipeline.
  * Capability integration beyond mock contract.
  * Complex state persistence.
  * Compliance tagging.

---

## Architecture

### High-Level Flow

```
User Input
    ↓
  Firewall ── PolicyGuard
    ↓
 LGDLRuntime
    ↓
  Interpreter (AST → IR)
    ↓
 TwoStagePatternMatcher
    ├─ Lexical (regex / DFA)
    └─ Semantic (embeddings / fallback)
    ↓
 Selected Move
    ↓
 Response Generation
```

### Components

* **Grammar & Parser**

  * Grammar defined in `spec/grammar_v0_1.lark`.
  * Parser built with Lark (`parser/parser.py`).
  * Transformer builds a typed AST (`parser/ast.py`).

* **IR Compiler**

  * AST compiled to an efficient IR (`parser/ir.py`).
  * Each move stores regexes + embeddings + confidence thresholds.

* **Matcher**

  * `matcher.py`: orchestrates lexical + semantic checks.
  * Embeddings cached in memory to minimize API calls.
  * Fallback: simple token overlap if no `OPENAI_API_KEY`.

* **Runtime**

  * `engine.py`: `LGDLRuntime` handles execution of moves.
  * `policy.py`: ACL for capability calls.
  * `firewall.py`: prompt injection sanitization.
  * `capability.py`: mock MCP-style external capability.

* **API**

  * FastAPI app in `runtime/api.py`.
  * `/move` endpoint:

    * Input: JSON payload with `conversation_id`, `user_id`, `input`.
    * Output: structured JSON with `move_id`, `confidence`, `response`, etc.

* **CLI**

  * `lgdl validate file.lgdl` → parse & validate grammar.
  * `lgdl compile file.lgdl -o out.ir.json` → compile to IR.

* **Examples & Tests**

  * `examples/medical/game.lgdl` defines a simple appointment scheduling game.
  * `examples/medical/golden_dialogs.yaml` encodes test scenarios.
  * `scripts/goldens.py` runs YAML dialogs against runtime.
  * `tests/` contains parser and runtime unit tests.

---

## Key Design Decisions

1. **BNF → Lark**
   EBNF spec (`grammar_v0_1.ebnf`) is the human-readable contract. Lark grammar is executable for parsing.

2. **Two-Stage Matching**
   Lexical stage ensures deterministic fast rejects; semantic stage allows fuzziness with controlled cost.

3. **Embedding Cascade**

   * Default: OpenAI embeddings (cosine similarity).
   * Fallback: token overlap for offline runs.

4. **Confidence as First-Class**

   * Moves can require `high`, `medium`, `low`, or numeric thresholds.
   * Golden tests validate confidence boundaries.

5. **Safety Layer**

   * Firewall strips suspicious tokens.
   * Policy guard enforces capability ACLs.
   * No raw exceptions leak to clients.

6. **CI-friendly Goldens**
   Golden YAML defines expected outcomes; `scripts/goldens.py` exits non-zero on failures for easy CI integration.

---

## Example

### `game.lgdl`

```lgdl
game medical_scheduling {
  description: "Book medical appointments"

  capabilities {
    appointment_system: ["check_availability"]
  }

  moves {
    move appointment_request {
      when user says something like: ["I need to see Dr. Smith"]
      confidence: high
      when confident {
        respond with: "Checking availability for Dr. Smith..."
      }
    }
  }
}
```

### `golden_dialogs.yaml`

```yaml
game: medical_scheduling
version: 1.0.0
dialogs:
  - name: doctor_name_present
    turns:
      - input: "I need to see Dr. Smith"
        expect:
          move: appointment_request
          confidence: ">=0.8"
          response_contains: ["Checking availability"]
```

---

## Deployment

* Managed with `uv` (fast Python package manager).
* Dependencies declared in `pyproject.toml`.
* Run:

  ```bash
  uv sync --extra openai --extra dev
  uv run uvicorn lgdl.runtime.api:app --reload
  uv run bash scripts/run_goldens.sh
  ```

---

## Future Evolution

* **Learning Pipeline** — propose-only learning, shadow tests, human approval.
* **LGDL Studio** — web-based editor, visualization, compliance checks.
* **Advanced State** — ephemeral vs. persistent state across turns.
* **Capability Contracts** — full MCP/OpenAPI spec validation.
* **Compliance & Security** — automated PII tagging, redaction, retention rules.

---

## Success Criteria

* Parser validates `.lgdl` games with no syntax errors.
* Runtime executes moves with `<500ms` p95 latency.
* Golden dialogs pass end-to-end.
* Optional embedding mode works when `OPENAI_API_KEY` is present.
* CI pipeline can run parser, unit tests, and golden tests.

---
