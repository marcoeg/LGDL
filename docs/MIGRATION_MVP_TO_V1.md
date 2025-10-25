# LGDL Migration Plan: MVP v0.1 → v1.0

**Status:** Planning Phase
**Created:** 2025-10-25
**MVP Tag:** `mvp-v0.1`
**Target:** Full `spec/full_grammar_v1_0.ebnf` implementation

---

## Executive Summary

This document outlines the migration path from the LGDL MVP (v0.1) to the full v1.0 specification. The plan addresses:

1. **Grammar parity** with `spec/full_grammar_v1_0.ebnf`
2. **Critical security and scalability issues** identified in MVP review
3. **Phased implementation** strategy to minimize risk
4. **Backward compatibility** considerations

**Estimated effort:** 40-60 hours of focused development work across 6 phases.

---

## Table of Contents

1. [Gap Analysis](#gap-analysis)
2. [Critical Issues (P0/P1)](#critical-issues-p0p1)
3. [Migration Strategy](#migration-strategy)
4. [Phase 0: Critical Fixes](#phase-0-critical-fixes-p0p1)
5. [Phase 1: Grammar & Parser](#phase-1-grammar--parser)
6. [Phase 2: IR & Matching](#phase-2-ir--matching)
7. [Phase 3: Engine Semantics](#phase-3-engine-semantics)
8. [Phase 4: Templates, Guards, Learning](#phase-4-templates-guards-learning)
9. [Phase 5: Tooling & CLI](#phase-5-tooling--cli)
10. [Phase 6: Testing & Documentation](#phase-6-testing--documentation)
11. [Risk Mitigation](#risk-mitigation)
12. [Success Criteria](#success-criteria)

---

## Gap Analysis

### What MVP v0.1 Has

✅ **Parser & Grammar**
- Lark-based parser (`spec/grammar_v0_1.lark`)
- Basic AST with `Game`, `Move`, `Trigger`, `Pattern`, `Action`
- IR compiler with regex patterns and confidence thresholds

✅ **Runtime**
- Two-stage matcher (lexical regex + semantic embeddings)
- FastAPI `/move` endpoint
- Policy guard (capability ACLs)
- Firewall (input sanitization)
- Basic confidence handling (`high`/`medium`/`low`)
- Template substitution (`{var}` and `{var?fallback}`)

✅ **Testing**
- Golden dialog tests (4 scenarios)
- Unit tests for parser and runtime
- CLI commands: `validate`, `compile`

### What v1.0 Needs (from `full_grammar_v1_0.ebnf`)

❌ **Not Implemented:**
- Pattern modifiers: `(strict)`, `(fuzzy)`, `(context-sensitive)`, `(learned)` - **PARTIALLY DONE** (strict/fuzzy exist, not others)
- Context guards: `requires context: user.age >= 18`
- Participants section with role-based actions
- Vocabulary section (synonym expansion)
- Negotiation loops: `negotiate ... until confident`
- Clarify with options: `clarify doctor with options: [...]`
- Capability `await` and `timeout` parameters
- Arithmetic templates: `${doctor.age + 5}`
- Learning section (propose-only pattern suggestions)
- If/else-if chains (MVP has partial support)
- Weighted confidence: `confidence: high weighted by user.trust_score`
- Special conditions: `successful`, `failed` (MVP has `confident`/`uncertain`)
- Rich error taxonomy with error codes
- Manifest/trace output for debugging

❌ **Architecture Gaps:**
- Single-game API (hardcoded path in `api.py:25`)
- No game registry for multi-tenancy
- Embedding versioning/reproducibility issues
- Template security vulnerability (arbitrary eval risk)
- Unclear negotiation state management

---

## Critical Issues (P0/P1)

### P0-1: Template Arithmetic Security Risk 🔴

**Problem:** Future `${...}` arithmetic evaluation could use `eval()`, enabling code injection.

**Example exploit:**
```lgdl
respond with: "${__import__('os').system('rm -rf /')}"
```

**Impact:** Remote code execution vulnerability.

**Fix:** Implement AST-based whitelist validator before v1.0 template work begins.

**Branch:** `feature/p0-p1-critical-fixes`
**Files:** New `runtime/templates.py`, tests
**Estimated:** 1-2 hours

---

### P0-2: Single-Game API Limitation 🔴

**Problem:** `api.py:25` hardcodes `examples/medical/game.lgdl`. Cannot serve multiple games.

**Impact:**
- No A/B testing of game variants
- No multi-tenant support
- No game versioning in production

**Fix:** Implement `GameRegistry` with `/games/{game_id}/move` routing.

**Branch:** `feature/p0-p1-critical-fixes`
**Files:** New `runtime/registry.py`, modify `api.py`, extend CLI
**Estimated:** 2-3 hours

---

### P1-1: Negotiation State Management Undefined ⚠️

**Problem:** v1.0 spec has `negotiate ... until confident` but no design for:
- How user responses update parameters
- How confidence is recalculated
- When to stop looping

**Impact:** Cannot implement negotiation without this design.

**Fix:** Define and implement `NegotiationLoop` class with clear state update strategy.

**Branch:** `feature/p0-p1-critical-fixes`
**Files:** New `runtime/negotiation.py`, tests, golden examples
**Estimated:** 3-4 hours

---

### P1-2: Embedding Non-Determinism ⚠️

**Problem:** OpenAI embeddings change when model updates → golden tests break.

**Impact:**
- Cannot reproduce confidence scores from 6 months ago
- CI flakiness
- No audit trail for why confidence changed

**Fix:** Implement versioned embedding cache (SQLite) with model version locking.

**Branch:** `feature/p0-p1-critical-fixes`
**Files:** Modify `runtime/matcher.py`, add `.embeddings_cache/`
**Estimated:** 1-2 hours

---

## Migration Strategy

### Principles

1. **No directory reshuffles:** Keep current structure, extend in-place
2. **Backward compatibility:** MVP games continue to work via `version="0.1"` flag
3. **Test-driven:** Each phase has DoD with passing tests
4. **Incremental:** Each phase ships independently
5. **Security-first:** Fix P0 issues before adding features

### Versioning Strategy

**Parser:**
```python
def parse_game(text: str, version: str = "0.1") -> Game:
    if version == "1.0":
        return Lark(open("spec/grammar_v1_0.lark")).parse(text)
    else:
        return Lark(open("spec/grammar_v0_1.lark")).parse(text)
```

**API:**
```python
# New multi-game endpoint
POST /games/{game_id}/move

# Legacy endpoint (backward compat)
POST /move  # routes to default game
```

**CLI:**
```bash
lgdl validate --version 1.0 game.lgdl
lgdl compile --version 1.0 game.lgdl -o out.ir
```

---

## Phase 0: Critical Fixes (P0/P1)

**Branch:** `feature/p0-p1-critical-fixes`
**Duration:** 7-11 hours
**Merge to:** `main` before starting Phase 1

### Tasks

#### 0.1 Template Security (P0-1)

**Files:**
- New: `lgdl/runtime/templates.py`
- Modify: `lgdl/runtime/engine.py`
- New: `tests/test_templates.py`

**Implementation:**
```python
class SafeArithmeticValidator(ast.NodeVisitor):
    ALLOWED_NODES = (ast.Expression, ast.Num, ast.BinOp, ast.Add, ...)
    def visit(self, node):
        if not isinstance(node, self.ALLOWED_NODES):
            raise SecurityError(f"Forbidden: {type(node).__name__}")
```

**DoD:**
- ✅ `{var}` and `{var?fallback}` still work
- ✅ Security tests block `__import__`, `__class__`, function calls
- ✅ Arithmetic expressions allowed: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- ✅ Golden tests pass with new renderer

---

#### 0.2 Multi-Game API (P0-2)

**Files:**
- New: `lgdl/runtime/registry.py`
- Modify: `lgdl/runtime/api.py`
- Modify: `lgdl/cli/main.py` (add `serve` command)
- New: `tests/test_registry.py`

**Implementation:**
```python
class GameRegistry:
    def register(self, game_id: str, path: str, version: str = "0.1"): ...
    def get_runtime(self, game_id: str) -> LGDLRuntime: ...

# API
@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest): ...

# CLI
@cli.command()
def serve(games: str, port: int):
    # games="medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl"
```

**DoD:**
- ✅ Can register 2+ games concurrently
- ✅ `/games` lists all games
- ✅ `/games/{game_id}/move` routes correctly
- ✅ Legacy `/move` still works (backward compat)
- ✅ Golden tests updated to use new endpoints

---

#### 0.3 Negotiation State Design (P1-1)

**Files:**
- New: `lgdl/runtime/negotiation.py`
- Modify: `lgdl/runtime/engine.py`
- New: `examples/medical/golden_dialogs_negotiation.yaml`
- New: `tests/test_negotiation.py`

**Strategy:**
```python
class NegotiationLoop:
    async def clarify_until_confident(self, move, initial_match, ...):
        """
        1. Present clarification question with options
        2. User responds with choice
        3. Update params dict: params[param_name] = user_choice
        4. Reconstruct enriched input: f"{original} {choice}"
        5. Re-run matcher on enriched input
        6. Check if confidence >= threshold
        7. Repeat up to max_rounds
        """
```

**DoD:**
- ✅ Negotiation updates params correctly
- ✅ Confidence recalculated after each round
- ✅ Golden test shows 2-round clarification → success
- ✅ Max rounds prevent infinite loops
- ✅ Result includes negotiation metadata in response

---

#### 0.4 Embedding Cache (P1-2)

**Files:**
- Modify: `lgdl/runtime/matcher.py`
- New: `.embeddings_cache/` (gitignored)
- New: `tests/test_embedding_cache.py`

**Implementation:**
```python
class EmbeddingClient:
    def __init__(self):
        self.model = "text-embedding-3-small"
        self.version_lock = "2025-01"
        self.cache_db = Path(f".embeddings_cache/{model}_{version}.db")
        # SQLite: (text_hash, model, version) -> embedding

    def embed(self, text: str) -> List[float]:
        # Check cache first
        # If OpenAI API returns different model version, warn
        # Fall back to deterministic bag-of-letters if offline
```

**DoD:**
- ✅ Embeddings persisted to SQLite
- ✅ Golden tests reproducible with `--use-embedding-cache`
- ✅ Version mismatch triggers warning
- ✅ Offline mode still works

---

## Phase 1: Grammar & Parser

**Branch:** `feature/v1-grammar-parser`
**Duration:** 4-6 hours
**Dependencies:** Phase 0 complete

### 1.1 Lark Grammar v1.0

**Files:**
- New: `spec/grammar_v1_0.lark` (translate from `full_grammar_v1_0.ebnf`)

**Additions:**
- Pattern modifiers: `(context-sensitive)`, `(learned)` (strict/fuzzy already exist)
- Context guards: `requires context: <condition>`
- Participants section
- Vocabulary section
- Multi-line strings (triple quotes)
- `else if` chains
- `negotiate` and `clarify` actions
- `await` and `timeout` in capability calls
- Arithmetic templates: `${expr}`
- Learning section

**DoD:**
- ✅ Lark parses v1.0 examples without conflicts
- ✅ Invalid v1.0 syntax rejected with clear errors

---

### 1.2 AST Extensions

**Files:**
- Modify: `parser/ast.py`
- Modify: `parser/parser.py` (transformer)

**New dataclasses:**
```python
@dataclass
class PatternModifier(Enum):
    STRICT = "strict"
    FUZZY = "fuzzy"
    LEARNED = "learned"
    CONTEXT_SENSITIVE = "context-sensitive"

@dataclass
class ContextGuard:
    expr: BoolExpr  # user.age >= 18 and context.locale matches /en/

@dataclass
class ConfidenceSpec:
    threshold: float | str  # numeric or 'low'/'medium'/'high'
    weighted_by: str | None

@dataclass
class Participant:
    name: str
    allowed_actions: list[str] | str  # ["ask", "respond"] or "anything"

@dataclass
class VocabularyEntry:
    canonical: str
    synonyms: list[str]

@dataclass
class LearningSection:
    rules: list[dict]  # Propose-only metadata

@dataclass
class Game:
    name: str
    extends: str | None
    participants: list[Participant]
    vocabulary: list[VocabularyEntry]
    capabilities: dict[str, list[str]]
    moves: list[Move]
    learning: LearningSection | None
```

**DoD:**
- ✅ Parser produces v1.0 AST for valid inputs
- ✅ 50+ conformance tests (valid + invalid fixtures)
- ✅ AST snapshot tests for regression

---

## Phase 2: IR & Matching

**Branch:** `feature/v1-ir-matching`
**Duration:** 3-4 hours
**Dependencies:** Phase 1

### 2.1 IR Compiler Upgrades

**Files:**
- Modify: `parser/ir.py`

**Extensions:**
```python
@dataclass
class IRPattern:
    raw: str
    modifiers: set[str]
    dfa: re.Pattern | None  # For strict patterns
    embedding_handle: str | None  # For fuzzy patterns

@dataclass
class CompiledConfidence:
    threshold: float
    band: str | None  # 'low'/'medium'/'high'
    weight_feature: str | None  # For weighted confidence

@dataclass
class IRMove:
    ...
    guards: list[CompiledGuard]
    confidence: CompiledConfidence
    when_blocks: list[IRWhenBlock]
    if_chain: IRIfChain | None
```

**DoD:**
- ✅ All v1.0 ASTs compile to IR
- ✅ Guards compiled to evaluable expressions
- ✅ Confidence bands → numeric thresholds
- ✅ Vocabulary synonyms expanded at compile time

---

### 2.2 Matcher Enhancements

**Files:**
- Modify: `runtime/matcher.py`

**Changes:**
- Add confidence band mapping (configurable):
  ```python
  BANDS = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 0.95}
  ```
- Weighted confidence:
  ```python
  def apply_weight(match_score: float, feature_value: float|None) -> float:
      if feature_value is None: return match_score
      alpha = 0.5
      return alpha * feature_value + (1 - alpha) * match_score
  ```
- Return provenance:
  ```python
  MatchResult(confidence: float, provenance: {
      "lexical_score": 0.75,
      "semantic_score": 0.85,
      "weight_feature": "user.trust_score",
      "weight_value": 0.9
  })
  ```

**DoD:**
- ✅ Confidence respects bands
- ✅ Weighted confidence works when feature present
- ✅ Provenance records all scoring components

---

## Phase 3: Engine Semantics

**Branch:** `feature/v1-engine-semantics`
**Duration:** 6-8 hours
**Dependencies:** Phase 2

### 3.1 Special Conditions & Branching

**Files:**
- Modify: `runtime/engine.py`

**Implementation:**
```python
def eval_condition(cond, confidence, threshold, last_action_status, context):
    if cond.special == "confident":
        return confidence >= threshold
    if cond.special == "uncertain":
        return confidence < threshold
    if cond.special == "successful":
        return last_action_status == "ok"
    if cond.special == "failed":
        return last_action_status == "err"
    # Handle compound: and/or/not
    # Handle comparisons: user.age >= 18
```

**DoD:**
- ✅ Guards evaluated before move selection
- ✅ Special conditions work correctly
- ✅ `if ... else if ... else` chains execute only one branch
- ✅ Golden tests validate branching logic

---

### 3.2 Capability Await/Timeout

**Files:**
- Modify: `runtime/capability.py`
- Modify: `runtime/engine.py`

**Implementation:**
```python
class CapabilityClient:
    async def call(self, service, func, params, await_flag, timeout_sec):
        if not await_flag:
            return self._sync_call(service, func, params)

        try:
            async with asyncio.timeout(timeout_sec):
                return await self._async_call(service, func, params)
        except asyncio.TimeoutError:
            raise CapabilityTimeout(f"{service}.{func} timeout")

# In engine:
async def _exec_action(self, action, params):
    if action["type"] == "capability":
        try:
            result = await self.cap.call(...)
            last_status = "ok"
        except CapabilityTimeout:
            last_status = "err"
```

**DoD:**
- ✅ `await timeout 3` enforced
- ✅ Timeout triggers `failed` condition
- ✅ Policy guard still enforced before call

---

## Phase 4: Templates, Guards, Learning

**Branch:** `feature/v1-templates-learning`
**Duration:** 5-7 hours
**Dependencies:** Phase 3, Phase 0.1 (template security)

### 4.1 Arithmetic Templates

**Files:**
- Modify: `runtime/engine.py` (use `runtime/templates.py` from Phase 0.1)

**Already implemented in Phase 0.1**, just needs integration.

**DoD:**
- ✅ `${doctor.age + 5}` works
- ✅ Security validator rejects unsafe expressions
- ✅ Clear error messages for bad arithmetic

---

### 4.2 Context Guards

**Files:**
- Modify: `runtime/engine.py`

**Implementation:**
```python
def eval_guard(guard: CompiledGuard, context: dict) -> bool:
    # Evaluate: user.age >= 18, context.locale matches /en/
    # Short-circuit evaluation for 'and'/'or'
    # Regex matching for 'matches' operator
```

**DoD:**
- ✅ Guards filter moves before matching
- ✅ Table-driven tests for all operators
- ✅ Bad expressions raise typed errors

---

### 4.3 Propose-Only Learning

**Files:**
- Modify: `runtime/engine.py`
- New: `scripts/pattern_proposals/` (output directory)

**Implementation:**
```python
def emit_proposal(self, turn_result, confidence_trail):
    if not os.getenv("LEARNING_PROPOSALS"):
        return

    proposal = {
        "timestamp": datetime.now().isoformat(),
        "input": turn_result["input"],
        "move": turn_result["move_id"],
        "confidence": turn_result["confidence"],
        "negotiation_rounds": turn_result.get("negotiation", {}).get("rounds", 0),
        "provenance": turn_result["provenance"],
        "success": turn_result["success"]
    }

    # Write to JSONL
    Path("scripts/pattern_proposals").mkdir(exist_ok=True)
    with open(f"scripts/pattern_proposals/{date.today()}.jsonl", "a") as f:
        f.write(json.dumps(proposal) + "\n")
```

**DoD:**
- ✅ Proposals written when `LEARNING_PROPOSALS=1`
- ✅ Schema validated in tests
- ✅ PII redaction applied (basic regex)

---

## Phase 5: Tooling & CLI

**Branch:** `feature/v1-tooling`
**Duration:** 4-5 hours
**Dependencies:** All previous phases

### 5.1 Error Taxonomy

**Files:**
- New: `lgdl/errors.py`
- Modify: All modules to use new error classes

**Implementation:**
```python
class LGDLError(Exception):
    def __init__(self, code: str, message: str, loc: tuple[int,int]|None=None):
        self.code = code
        self.message = message
        self.loc = loc

# Codes:
# E001-E099: Syntax errors
# E100-E199: Semantic/compile errors
# E200-E299: Runtime/capability errors
# E300-E399: Policy violations
# E400-E499: Learning errors
```

**DoD:**
- ✅ All errors have codes
- ✅ Tests assert error codes

---

### 5.2 Run Manifests & Trace

**Files:**
- Modify: `runtime/engine.py`
- Modify: `cli/main.py`

**Implementation:**
```python
# Engine emits manifest
{
  "turn_id": "...",
  "input": "...",
  "move_selected": "...",
  "confidence": 0.85,
  "provenance": {...},
  "branch_taken": "when confident",
  "actions": [...],
  "timing_ms": {"match": 12, "exec": 35, "total": 47}
}

# CLI command
$ lgdl trace --input "chest pain" game.lgdl --manifest out/trace.json
```

**DoD:**
- ✅ Manifest written to file
- ✅ All fields validated in tests

---

### 5.3 Lint Command

**Files:**
- New: `lgdl/cli/lint.py`
- Modify: `cli/main.py`

**Rules:**
- **unreachable-move**: Move never matched (dead code)
- **overlapping-triggers**: Two moves with identical strict patterns
- **missing-uncertainty-handling**: Move with confidence but no `when uncertain` block
- **over-broad-regex**: Pattern `.*` without anchors (warning)

**DoD:**
- ✅ Non-zero exit on error-severity
- ✅ Warnings show rule ID

---

## Phase 6: Testing & Documentation

**Branch:** `feature/v1-docs-tests`
**Duration:** 6-8 hours
**Dependencies:** All previous phases

### 6.1 Comprehensive Tests

**Files:**
- Extend: `tests/test_conformance.py` (50+ fixtures)
- Extend: `tests/test_runtime.py` (negotiation, await, templates, conditions)
- New: `examples/v1/er_triage.lgdl` (showcase v1.0 features)
- Extend: `examples/medical/golden_dialogs.yaml` (add negotiation scenarios)

**DoD:**
- ✅ All golden tests pass
- ✅ Coverage ≥ 85% (if enforced)

---

### 6.2 Documentation

**Files:**
- New: `docs/lgdl-spec-v1.0.md` (derive from EBNF + examples)
- New: `docs/authoring-guide.md` (moves, confidence, negotiation)
- New: `docs/capabilities.md` (await/timeout contracts)
- New: `docs/error-reference.md` (taxonomy + remedies)
- Update: `README.md` (v1.0 examples, CLI usage)

**DoD:**
- ✅ All features documented with examples
- ✅ Migration guide complete

---

## Risk Mitigation

### Risk 1: Breaking Changes

**Mitigation:**
- Keep v0.1 parser alongside v1.0
- Default to v0.1 initially, flip to v1.0 later
- Automated migration tool: `lgdl migrate --from 0.1 --to 1.0`

---

### Risk 2: Embedding API Changes

**Mitigation:**
- Phase 0.4 implements version locking
- Warnings on model mismatch
- Cached embeddings provide fallback

---

### Risk 3: Scope Creep

**Mitigation:**
- Defer vocabulary expansion to v1.1 if complex
- Defer participants enforcement to v1.1 if unclear
- Each phase has explicit DoD

---

### Risk 4: Test Flakiness

**Mitigation:**
- Embedding cache for deterministic tests
- Timeouts set conservatively
- Skip benchmarks in CI if env unstable

---

## Success Criteria

v1.0 is **complete** when:

✅ All phases 0-6 merged to `main`
✅ `spec/grammar_v1_0.lark` parses all v1.0 examples
✅ CLI: `lgdl validate --version 1.0 game.lgdl` works
✅ API: `/games/{game_id}/move` serves multiple games
✅ Golden tests: All scenarios pass (including negotiation)
✅ Security: Template eval passes penetration tests
✅ Docs: All features documented with examples
✅ Performance: p95 latency < 500ms (per MVP success criteria)
✅ CI: All tests pass on clean run

---

## Timeline Estimate

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 0 (P0/P1 fixes) | 7-11 hours | 11h |
| Phase 1 (Grammar/Parser) | 4-6 hours | 17h |
| Phase 2 (IR/Matching) | 3-4 hours | 21h |
| Phase 3 (Engine) | 6-8 hours | 29h |
| Phase 4 (Templates/Learning) | 5-7 hours | 36h |
| Phase 5 (Tooling) | 4-5 hours | 41h |
| Phase 6 (Tests/Docs) | 6-8 hours | 49h |
| **Total** | **35-49 hours** | |
| *Buffer (20%)* | *+7-10 hours* | |
| **Realistic Total** | **42-59 hours** | |

Assuming 10 hours/week → **4-6 weeks** calendar time.

---

## Deferred to v1.1

The following features from `full_grammar_v1_0.ebnf` are **explicitly deferred** to v1.1:

- **Vocabulary synonym expansion** (if pattern multiplication causes maintenance issues)
- **Participants runtime enforcement** (if semantics unclear after v1.0 testing)
- **Advanced learning strategies** (beyond propose-only JSONL)
- **Pattern coverage metrics** (analytics dashboard)

These can be added as additive features without breaking v1.0 compatibility.

---

## References

- **MVP Tag:** `mvp-v0.1`
- **Spec:** `spec/full_grammar_v1_0.ebnf`
- **Design Doc:** `docs/DESIGN.md`
- **Task Tracker:** `docs/MVP_TASKS.md`

---

**Last Updated:** 2025-10-25
**Status:** Ready for Phase 0 implementation
**Next Step:** Create `feature/p0-p1-critical-fixes` branch and begin P0-1 (template security)
