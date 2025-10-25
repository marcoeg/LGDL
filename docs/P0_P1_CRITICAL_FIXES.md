# P0/P1 Critical Fixes - Implementation Plan

**Status:** Ready for Implementation
**Branch:** `feature/p0-p1-critical-fixes`
**Created:** 2025-10-25
**Estimated Effort:** 11-13 hours total

---

## Executive Summary

This document details the implementation of 4 critical fixes required before v1.0 grammar work:

- **P0-1:** Template arithmetic security (RCE vulnerability)
- **P0-2:** Multi-game API with registry (production scalability)
- **P1-1:** Negotiation state management (spec clarity for v1.0)
- **P1-2:** Embedding versioning/caching (test reproducibility)

All recommendations from architecture review incorporated:
- Stricter arithmetic constraints (magnitude clamps, length limits, explicit node bans)
- Better observability (healthz, metadata endpoints, deprecation headers, hot reload)
- "No information gain" stop condition for negotiation
- TF-IDF character bigrams for offline embeddings

---

## Implementation Structure: 2 PRs

### PR-1: P0 Fixes (Security & Scalability)
- **P0-1:** Template arithmetic security
- **P0-2:** Multi-game API with registry
- **Duration:** 4-6 hours
- **DoD:** All P0 tests pass, API serves 2+ games, templates secure

### PR-2: P1 Fixes (Determinism & Negotiation)
- **P1-2:** Embedding cache (simpler, do first)
- **P1-1:** Negotiation state management
- **Duration:** 5-7 hours
- **DoD:** Embeddings reproducible, negotiation with "no gain" stop works

---

# PR-1: P0 FIXES

## P0-1: Template Arithmetic Security

### Threat Model

**Vulnerability:** Future `${...}` arithmetic evaluation could enable:
- Remote code execution via `__import__`
- Denial of service via exponential calculations (`2**999999`)
- Data exfiltration via attribute access (`obj.__class__.__bases__`)

**Impact:** Critical - potential RCE in production deployments

### Security Constraints

```python
# Configuration
MAX_EXPR_LENGTH = 256          # Prevent complexity bombs
MAX_NUMERIC_VALUE = 1e9        # Prevent magnitude overflow
ALLOWED_OPS = ['+', '-', '*', '/', '//', '%']  # NO ** (exponentiation)
```

### Files Modified/Created

- **New:** `lgdl/errors.py` (error taxonomy, brought forward from Phase 5)
- **New:** `lgdl/runtime/templates.py`
- **Modify:** `lgdl/runtime/engine.py`
- **New:** `tests/test_errors.py`
- **New:** `tests/test_templates.py`

### Implementation

#### Error Taxonomy (`lgdl/errors.py`)

```python
"""
Error codes for LGDL system.

E001-E099: Syntax and template errors
E100-E199: Semantic and compile errors
E200-E299: Runtime and capability errors
E300-E399: Policy violations
E400-E499: Learning errors
"""

class LGDLError(Exception):
    """Base class for all LGDL errors."""

    def __init__(
        self,
        code: str,
        message: str,
        loc: tuple[int, int] | None = None,
        hint: str | None = None
    ):
        self.code = code
        self.message = message
        self.loc = loc  # (line, column) if available
        self.hint = hint  # Suggestion for fix
        super().__init__(f"[{code}] {message}")

class TemplateError(LGDLError):
    """Template rendering errors (E001-E099)."""
    pass

class SecurityError(TemplateError):
    """Security violations in templates (E010-E019)."""
    pass

class CompileError(LGDLError):
    """Compilation errors (E100-E199)."""
    pass

class RuntimeError(LGDLError):
    """Runtime execution errors (E200-E299)."""
    pass

class PolicyError(LGDLError):
    """Policy/capability violations (E300-E399)."""
    pass

# Specific error codes:
# E001: Invalid template syntax
# E010: Forbidden expression node (security)
# E011: Expression too complex (length limit)
# E012: Numeric value exceeds safe range
```

#### Template Renderer (`lgdl/runtime/templates.py`)

```python
"""
Secure template renderer with arithmetic evaluation.

Supports:
- {var} and {var.nested}: Direct variable lookup
- {var?fallback}: Variable with fallback value
- ${expr}: Arithmetic expressions (validated)

Security:
- Whitelist AST node validation
- Length and magnitude constraints
- No attribute access, subscripts, calls, or exponentiation
"""

import ast
import re
from typing import Any, Dict
from ..errors import TemplateError, SecurityError

# Security configuration
MAX_EXPR_LENGTH = 256
MAX_NUMERIC_VALUE = 1e9

class SafeArithmeticValidator(ast.NodeVisitor):
    """
    Whitelist validator for safe arithmetic expressions.

    ALLOWED: + - * / // %
    FORBIDDEN: ** (exponent), attribute access, subscripts, calls
    """

    ALLOWED_NODES = (
        ast.Expression,     # Top-level expression wrapper
        ast.Constant,       # Modern literal (Python 3.8+)
        ast.Num,           # Legacy numeric literal (compat)
        ast.BinOp,         # Binary operations
        ast.UnaryOp,       # Unary operations
        ast.Add,           # +
        ast.Sub,           # -
        ast.Mult,          # *
        ast.Div,           # /
        ast.FloorDiv,      # //
        ast.Mod,           # %
        ast.USub,          # Unary minus
        ast.UAdd,          # Unary plus
        ast.Name,          # Variable references
        ast.Load,          # Load context
    )

    FORBIDDEN_NODES = (
        ast.Pow,           # ** exponentiation (CPU bomb risk)
        ast.Attribute,     # obj.attr (dunder access risk)
        ast.Subscript,     # obj[key] (injection risk)
        ast.Call,          # func() (RCE risk)
        ast.Lambda,        # Lambda expressions
        ast.IfExp,         # Ternary conditionals
        ast.ListComp,      # List comprehensions
        ast.DictComp,      # Dict comprehensions
        ast.GeneratorExp,  # Generator expressions
        ast.Await,         # Async await
        ast.Yield,         # Generator yield
        ast.YieldFrom,     # Yield from
    )

    def visit(self, node):
        # Explicit forbidden check (clearer errors)
        if isinstance(node, self.FORBIDDEN_NODES):
            raise SecurityError(
                code="E010",
                message=f"Forbidden expression node: {type(node).__name__}",
                hint="Template arithmetic only supports: + - * / // % with variables and numbers"
            )

        # Whitelist check
        if not isinstance(node, self.ALLOWED_NODES):
            raise SecurityError(
                code="E010",
                message=f"Unsupported expression node: {type(node).__name__}",
                hint="Only basic arithmetic is allowed in templates"
            )

        self.generic_visit(node)


class TemplateRenderer:
    """Render templates with {var} and ${expr} substitutions."""

    def render(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render template with variable and arithmetic substitutions.

        Args:
            template: Template string with {var} and ${expr} placeholders
            context: Variable context dictionary

        Returns:
            Rendered string with substitutions applied

        Raises:
            TemplateError: On syntax errors or invalid expressions
            SecurityError: On security violations
        """
        # Simple variables: {doctor}, {context.locale}, {var?fallback}
        template = re.sub(
            r'\{([a-zA-Z_][a-zA-Z0-9_\.]*?)(\?([^\}]+))?\}',
            lambda m: self._resolve_var(m, context),
            template
        )

        # Arithmetic: ${doctor.age + 5}
        template = re.sub(
            r'\$\{([^\}]+)\}',
            lambda m: self._eval_arithmetic(m.group(1), context),
            template
        )

        return template

    def _resolve_var(self, match, context):
        """Resolve {var.path?fallback} references."""
        path = match.group(1)
        fallback = match.group(3) if match.group(2) else ""

        keys = path.split('.')
        val = context
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                val = getattr(val, key, None)
            if val is None:
                return fallback
        return str(val) if val is not None else fallback

    def _eval_arithmetic(self, expr: str, context: Dict[str, Any]) -> str:
        """
        Evaluate arithmetic expression with security constraints.

        Args:
            expr: Arithmetic expression string
            context: Variable context

        Returns:
            String representation of result

        Raises:
            SecurityError: If expression violates safety rules
            TemplateError: If expression is invalid
        """
        expr = expr.strip()

        # Length constraint
        if len(expr) > MAX_EXPR_LENGTH:
            raise SecurityError(
                code="E011",
                message=f"Expression too long: {len(expr)} > {MAX_EXPR_LENGTH} chars",
                hint="Break complex calculations into multiple steps"
            )

        try:
            # Parse and validate AST
            tree = ast.parse(expr, mode='eval')
            SafeArithmeticValidator().visit(tree)

            # Compile with no builtins
            code = compile(tree, '<template>', 'eval')
            result = eval(code, {"__builtins__": {}}, context)

            # Magnitude constraint
            if isinstance(result, (int, float)):
                if abs(result) > MAX_NUMERIC_VALUE:
                    raise SecurityError(
                        code="E012",
                        message=f"Result exceeds safe range: {result}",
                        hint=f"Results must be within ±{MAX_NUMERIC_VALUE}"
                    )

            return str(result)

        except SyntaxError as e:
            raise TemplateError(
                code="E001",
                message=f"Invalid arithmetic syntax: {expr}",
                loc=(e.lineno, e.offset) if hasattr(e, 'lineno') else None,
                hint="Check for mismatched parentheses or invalid operators"
            ) from e
        except LGDLError:
            raise  # Re-raise LGDL errors as-is
        except Exception as e:
            raise TemplateError(
                code="E001",
                message=f"Template evaluation failed: {e}",
                hint="Ensure all variables are defined in context"
            ) from e
```

#### Engine Integration (`lgdl/runtime/engine.py`)

```python
# In LGDLRuntime.__init__:
from .templates import TemplateRenderer

class LGDLRuntime:
    def __init__(self, compiled):
        self.compiled = compiled
        self.matcher = TwoStageMatcher()
        self.policy = PolicyGuard(...)
        self.cap = CapabilityClient(...)
        self.templates = TemplateRenderer()  # NEW

# In _exec_action:
async def _exec_action(self, action, params):
    if action["type"] == "respond":
        text = action["data"].get("text", "")
        # OLD: _subst_template(text, params)
        # NEW:
        return self.templates.render(text, params), None, "ok"
    ...
```

### Test Specifications

#### Error Tests (`tests/test_errors.py`)

```python
import pytest
from lgdl.errors import TemplateError, SecurityError

def test_error_has_code():
    err = TemplateError("E001", "test message")
    assert err.code == "E001"
    assert "[E001]" in str(err)

def test_error_with_location():
    err = TemplateError("E001", "test", loc=(5, 10))
    assert err.loc == (5, 10)

def test_error_with_hint():
    err = TemplateError("E001", "test", hint="Try this instead")
    assert err.hint == "Try this instead"

def test_error_inheritance():
    err = SecurityError("E010", "security violation")
    assert isinstance(err, TemplateError)
    assert isinstance(err, LGDLError)
```

#### Template Tests (`tests/test_templates.py`)

```python
import pytest
from lgdl.runtime.templates import TemplateRenderer, MAX_NUMERIC_VALUE
from lgdl.errors import SecurityError, TemplateError

# Basic functionality tests
def test_simple_variable():
    r = TemplateRenderer()
    assert r.render("{name}", {"name": "Alice"}) == "Alice"

def test_nested_variable():
    r = TemplateRenderer()
    assert r.render("{user.age}", {"user": {"age": 30}}) == "30"

def test_fallback():
    r = TemplateRenderer()
    assert r.render("{missing?fallback}", {}) == "fallback"
    assert r.render("{missing}", {}) == ""

def test_arithmetic_basic():
    r = TemplateRenderer()
    assert r.render("${age + 5}", {"age": 30}) == "35"
    assert r.render("${x * 2}", {"x": 10}) == "20"
    assert r.render("${a - b}", {"a": 100, "b": 30}) == "70"
    assert r.render("${a / b}", {"a": 10, "b": 2}) == "5.0"
    assert r.render("${a // b}", {"a": 10, "b": 3}) == "3"
    assert r.render("${a % b}", {"a": 10, "b": 3}) == "1"

def test_arithmetic_complex():
    r = TemplateRenderer()
    assert r.render("${(x + y) * 2}", {"x": 3, "y": 7}) == "20"
    assert r.render("${a / b + c}", {"a": 10, "b": 2, "c": 3}) == "8.0"

# Security tests
def test_security_reject_exponentiation():
    """E010: Reject ** operator (CPU bomb risk)."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${2 ** 999999}", {})
    assert exc.value.code == "E010"
    assert "Pow" in exc.value.message

def test_security_reject_import():
    """E010: Reject __import__ call."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${__import__('os').system('ls')}", {})
    assert exc.value.code == "E010"
    assert "Call" in exc.value.message

def test_security_reject_attribute_access():
    """E010: Reject dunder attribute access."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${obj.__class__.__bases__}", {"obj": object()})
    assert exc.value.code == "E010"
    assert "Attribute" in exc.value.message

def test_security_reject_subscript():
    """E010: Reject subscript access."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${data['key']}", {"data": {"key": "val"}})
    assert exc.value.code == "E010"
    assert "Subscript" in exc.value.message

def test_security_reject_lambda():
    """E010: Reject lambda expressions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${(lambda x: x+1)(5)}", {})
    assert exc.value.code == "E010"
    assert "Lambda" in exc.value.message

def test_security_reject_comprehension():
    """E010: Reject list comprehensions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${[x for x in range(10)]}", {})
    assert exc.value.code == "E010"

def test_security_expression_too_long():
    """E011: Reject expressions exceeding max length."""
    r = TemplateRenderer()
    long_expr = "x + " * 100 + "1"  # >256 chars
    with pytest.raises(SecurityError) as exc:
        r.render(f"${{{long_expr}}}", {"x": 1})
    assert exc.value.code == "E011"
    assert "too long" in exc.value.message.lower()

def test_security_magnitude_overflow():
    """E012: Reject results exceeding safe numeric range."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${x * y}", {"x": 1e8, "y": 1e8})  # Result: 1e16 > 1e9
    assert exc.value.code == "E012"
    assert "exceeds safe range" in exc.value.message.lower()

def test_error_invalid_syntax():
    """E001: Syntax errors have proper error code."""
    r = TemplateRenderer()
    with pytest.raises(TemplateError) as exc:
        r.render("${(x + }", {"x": 1})  # Mismatched parens
    assert exc.value.code == "E001"
    assert exc.value.hint is not None

# Regression tests
def test_regression_existing_templates_work():
    """Ensure existing MVP templates still work."""
    r = TemplateRenderer()
    # From golden tests
    assert r.render("I can check availability for {doctor?any provider}.",
                    {"doctor": "Smith"}) == "I can check availability for Smith."
    assert r.render("I can check availability for {doctor?any provider}.",
                    {}) == "I can check availability for any provider."
```

### Definition of Done (P0-1)

- ✅ Arithmetic operations: `+ - * / // %` allowed
- ✅ Exponentiation `**` rejected with E010
- ✅ Max expression length: 256 chars (E011)
- ✅ Magnitude clamp: ±1e9 (E012)
- ✅ Uses `ast.Constant` (Python 3.8+) with `ast.Num` fallback
- ✅ Explicitly bans: `ast.Attribute`, `ast.Subscript`, `ast.Call`, `ast.Lambda`, `ast.IfExp`, comprehensions
- ✅ All errors have typed codes (E001, E010, E011, E012)
- ✅ Tests cover: dunder access, import, subscript, lambda, comprehension, length, magnitude
- ✅ `{var}` and `{var?fallback}` still work (regression test)
- ✅ Golden tests pass with new renderer

---

## P0-2: Multi-Game API & Registry

### Problem Statement

**Current state:** `api.py:25` hardcodes `examples/medical/game.lgdl`

**Impact:**
- Cannot A/B test game variants
- No multi-tenant support
- No game versioning
- Cannot serve different games to different users

### Solution Architecture

```
GameRegistry
  ├─ register(game_id, path, version) → compile & store
  ├─ get_runtime(game_id) → LGDLRuntime instance
  ├─ get_metadata(game_id) → {id, name, version, file_hash}
  └─ list_games() → [{...}, {...}]

API Endpoints
  ├─ GET /healthz → {status, games_loaded, games: [...]}
  ├─ GET /games → {games: [{id, name, version, file_hash}, ...]}
  ├─ GET /games/{id} → {id, name, version, path, file_hash}
  ├─ POST /games/{id}/move → MoveResponse
  └─ POST /move (deprecated) → routes to default game
```

### Files Modified/Created

- **New:** `lgdl/runtime/registry.py`
- **Modify:** `lgdl/runtime/api.py`
- **Modify:** `lgdl/cli/main.py`
- **New:** `tests/test_registry.py`

### Implementation

#### Game Registry (`lgdl/runtime/registry.py`)

```python
"""
Game registry for multi-game API support.

Manages loading, compilation, and routing to multiple LGDL games.
"""

import hashlib
from pathlib import Path
from typing import Dict
from ..parser.parser import parse_lgdl
from ..parser.ir import compile_game
from .engine import LGDLRuntime
from ..errors import CompileError


class GameRegistry:
    """Registry for multiple compiled games with metadata."""

    def __init__(self):
        self.games: Dict[str, dict] = {}
        self.runtimes: Dict[str, LGDLRuntime] = {}

    def register(self, game_id: str, path: str, version: str = "0.1"):
        """
        Load and compile a game.

        Args:
            game_id: Unique identifier for this game
            path: Path to .lgdl file
            version: Grammar version (default: "0.1")

        Raises:
            ValueError: If game_id already registered
            FileNotFoundError: If path doesn't exist
            CompileError: If game fails to compile
        """
        if game_id in self.games:
            raise ValueError(f"Game '{game_id}' already registered")

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Game file not found: {path}")

        # Compute file hash for cache invalidation
        content = path_obj.read_text()
        file_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

        # Parse and compile
        game_ast = parse_lgdl(path)
        compiled = compile_game(game_ast)

        self.games[game_id] = {
            "path": str(path_obj.absolute()),
            "version": version,
            "compiled": compiled,
            "name": compiled["name"],
            "file_hash": file_hash,
            "last_compiled": path_obj.stat().st_mtime
        }
        self.runtimes[game_id] = LGDLRuntime(compiled=compiled)

    def get_runtime(self, game_id: str) -> LGDLRuntime:
        """
        Get runtime for a specific game.

        Args:
            game_id: Game identifier

        Returns:
            LGDLRuntime instance for this game

        Raises:
            KeyError: If game not found
        """
        if game_id not in self.runtimes:
            available = list(self.runtimes.keys())
            raise KeyError(
                f"Game '{game_id}' not found. Available: {available}"
            )
        return self.runtimes[game_id]

    def get_metadata(self, game_id: str) -> dict:
        """
        Get metadata for a specific game.

        Args:
            game_id: Game identifier

        Returns:
            Dictionary with game metadata

        Raises:
            KeyError: If game not found
        """
        if game_id not in self.games:
            raise KeyError(f"Game '{game_id}' not found")
        meta = self.games[game_id]
        return {
            "id": game_id,
            "name": meta["name"],
            "version": meta["version"],
            "path": meta["path"],
            "file_hash": meta["file_hash"]
        }

    def list_games(self) -> list[dict]:
        """List all registered games with metadata."""
        return [self.get_metadata(gid) for gid in self.games.keys()]

    def reload(self, game_id: str):
        """
        Reload a game from disk (for hot reload in dev mode).

        Args:
            game_id: Game to reload

        Raises:
            KeyError: If game not registered
            CompileError: If reload fails
        """
        if game_id not in self.games:
            raise KeyError(f"Game '{game_id}' not found")

        meta = self.games[game_id]
        path = meta["path"]
        version = meta["version"]

        # Re-register (will overwrite)
        del self.games[game_id]
        del self.runtimes[game_id]
        self.register(game_id, path, version)
```

#### API Enhancements (`lgdl/runtime/api.py`)

```python
"""
FastAPI runtime for LGDL games.

Multi-game support with registry, health checks, and metadata endpoints.
"""

from fastapi import FastAPI, HTTPException, Path as PathParam
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
import time, uuid, os
from pathlib import Path
from .registry import GameRegistry

app = FastAPI(title="LGDL Runtime", version="0.2")

# Global registry
REGISTRY = GameRegistry()
DEV_MODE = os.getenv("LGDL_DEV_MODE", "0") == "1"


@app.on_event("startup")
async def load_games():
    """Load games specified in LGDL_GAMES env var or default."""
    games_spec = os.getenv("LGDL_GAMES")
    if games_spec:
        # Format: "medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl"
        for pair in games_spec.split(","):
            game_id, path = pair.split(":")
            REGISTRY.register(game_id.strip(), path.strip(), version="0.1")
    else:
        # Default: load medical example
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        REGISTRY.register(
            "medical_scheduling",
            str(examples_dir / "medical" / "game.lgdl"),
            version="0.1"
        )


@app.get("/healthz")
async def healthz():
    """
    Health check endpoint with registry status.

    Returns:
        Status info: healthy status, game count, loaded game IDs
    """
    return {
        "status": "healthy",
        "games_loaded": len(REGISTRY.list_games()),
        "games": [g["id"] for g in REGISTRY.list_games()]
    }


@app.get("/games")
async def list_games():
    """
    List all available games with metadata.

    Returns:
        List of games with id, name, version, file_hash
    """
    return {"games": REGISTRY.list_games()}


@app.get("/games/{game_id}")
async def get_game_metadata(game_id: str = PathParam(...)):
    """
    Get metadata for a specific game.

    Args:
        game_id: Game identifier

    Returns:
        Game metadata including path and file hash

    Raises:
        404: If game not found
    """
    try:
        return REGISTRY.get_metadata(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/games/{game_id}/move", response_model=MoveResponse)
async def move(
    game_id: str = PathParam(..., description="Game identifier"),
    req: MoveRequest
):
    """
    Execute a move in a specific game.

    Args:
        game_id: Game identifier
        req: Move request with conversation_id, user_id, input

    Returns:
        Move response with move_id, confidence, response, action, etc.

    Raises:
        404: If game not found
        500: On runtime error
    """
    try:
        runtime = REGISTRY.get_runtime(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e))

    t0 = time.perf_counter()
    result = await runtime.process_turn(
        req.conversation_id, req.user_id, req.input, req.context or {}
    )

    if not result:
        raise HTTPException(500, "Runtime error")

    latency = round((time.perf_counter() - t0) * 1000, 2)

    return MoveResponse(
        move_id=result["move_id"],
        confidence=result["confidence"],
        response=result["response"],
        action=result.get("action"),
        manifest_id=result.get("manifest_id", str(uuid.uuid4())),
        latency_ms=latency,
        firewall_triggered=result.get("firewall_triggered", False),
    )


@app.post("/move", response_model=MoveResponse, deprecated=True)
async def move_legacy(req: MoveRequest):
    """
    Legacy endpoint (routes to default game).

    DEPRECATED: Use /games/{game_id}/move instead.

    Returns:
        Same as /games/{game_id}/move
    """
    return await move("medical_scheduling", req)


# Deprecation header middleware
class DeprecationHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path == "/move":
            response.headers["X-Deprecation-Warning"] = (
                "Use /games/{game_id}/move instead. "
                "This endpoint will be removed in v2.0."
            )
        return response


app.add_middleware(DeprecationHeaderMiddleware)


# Hot reload endpoint (dev mode only)
if DEV_MODE:
    @app.post("/games/{game_id}/reload")
    async def reload_game(game_id: str):
        """
        Reload game from disk (dev mode only).

        Args:
            game_id: Game to reload

        Returns:
            Status message

        Raises:
            404: If game not found
            500: If reload fails
        """
        try:
            REGISTRY.reload(game_id)
            return {"status": "reloaded", "game_id": game_id}
        except KeyError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(500, f"Reload failed: {e}")
```

#### CLI Enhancement (`lgdl/cli/main.py`)

```python
@cli.command()
@click.option(
    "--games",
    required=True,
    help="Comma-separated game_id:path pairs (e.g., 'medical:examples/medical/game.lgdl')"
)
@click.option("--port", default=8000, help="Server port")
@click.option("--dev", is_flag=True, help="Enable dev mode (hot reload)")
def serve(games: str, port: int, dev: bool):
    """
    Start API server with multiple games.

    Example:

        lgdl serve --games medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl
    """
    import os, uvicorn
    from pathlib import Path

    # Validate game specs before starting server
    click.echo("Validating game files...")
    for pair in games.split(","):
        if ":" not in pair:
            click.echo(
                f"Error: Invalid format '{pair}'. Expected 'game_id:path'",
                err=True
            )
            raise click.Abort()

        game_id, path = pair.split(":", 1)
        path_obj = Path(path.strip())

        if not path_obj.exists():
            click.echo(f"Error: Game file not found: {path}", err=True)
            raise click.Abort()

        click.echo(f"✓ Validated: {game_id.strip()} -> {path_obj.absolute()}")

    # Set env vars for startup
    os.environ["LGDL_GAMES"] = games
    if dev:
        os.environ["LGDL_DEV_MODE"] = "1"
        click.echo("⚡ Dev mode enabled (hot reload available)")

    click.echo(f"\nStarting LGDL API server on port {port}...")
    click.echo(f"Health check: http://127.0.0.1:{port}/healthz")
    click.echo(f"Games list: http://127.0.0.1:{port}/games\n")

    from lgdl.runtime.api import app
    uvicorn.run(app, host="0.0.0.0", port=port, reload=dev)
```

### Test Specifications

#### Registry Tests (`tests/test_registry.py`)

```python
import pytest
from pathlib import Path
from lgdl.runtime.registry import GameRegistry
from lgdl.runtime.engine import LGDLRuntime


def test_register_game():
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    assert "test" in reg.games
    assert "test" in reg.runtimes


def test_duplicate_registration_fails():
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    with pytest.raises(ValueError, match="already registered"):
        reg.register("test", "examples/medical/game.lgdl")


def test_missing_file_raises():
    reg = GameRegistry()
    with pytest.raises(FileNotFoundError):
        reg.register("missing", "nonexistent.lgdl")


def test_get_runtime():
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    runtime = reg.get_runtime("test")
    assert isinstance(runtime, LGDLRuntime)


def test_get_runtime_not_found():
    reg = GameRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.get_runtime("nonexistent")


def test_get_metadata():
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    meta = reg.get_metadata("test")

    assert meta["id"] == "test"
    assert meta["name"] == "medical_scheduling"
    assert "file_hash" in meta
    assert len(meta["file_hash"]) == 8
    assert "path" in meta
    assert "version" in meta


def test_list_games():
    reg = GameRegistry()
    reg.register("game1", "examples/medical/game.lgdl")
    games = reg.list_games()

    assert len(games) == 1
    assert games[0]["id"] == "game1"
    assert all(key in games[0] for key in ["id", "name", "version", "file_hash"])


def test_list_games_multiple():
    reg = GameRegistry()
    reg.register("game1", "examples/medical/game.lgdl")
    reg.register("game2", "examples/medical/game.lgdl")  # Same file, different ID

    games = reg.list_games()
    assert len(games) == 2
    game_ids = [g["id"] for g in games]
    assert "game1" in game_ids
    assert "game2" in game_ids


# API Integration Tests

@pytest.mark.asyncio
async def test_api_healthz(test_client):
    """Test /healthz endpoint."""
    response = await test_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "games_loaded" in data
    assert "games" in data
    assert isinstance(data["games"], list)


@pytest.mark.asyncio
async def test_api_list_games(test_client):
    """Test GET /games endpoint."""
    response = await test_client.get("/games")
    assert response.status_code == 200
    games = response.json()["games"]
    assert len(games) >= 1
    assert all("id" in g and "name" in g and "file_hash" in g for g in games)


@pytest.mark.asyncio
async def test_api_get_game_metadata(test_client):
    """Test GET /games/{id} endpoint."""
    response = await test_client.get("/games/medical_scheduling")
    assert response.status_code == 200
    meta = response.json()
    assert meta["id"] == "medical_scheduling"
    assert meta["name"] == "medical_scheduling"
    assert "file_hash" in meta
    assert "path" in meta


@pytest.mark.asyncio
async def test_api_get_game_not_found(test_client):
    """Test GET /games/{id} with nonexistent game."""
    response = await test_client.get("/games/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_move_with_game_id(test_client):
    """Test POST /games/{id}/move endpoint."""
    response = await test_client.post(
        "/games/medical_scheduling/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["move_id"] == "appointment_request"
    assert data["confidence"] > 0.8


@pytest.mark.asyncio
async def test_api_move_game_not_found(test_client):
    """Test POST /games/{id}/move with nonexistent game."""
    response = await test_client.post(
        "/games/nonexistent/move",
        json={"conversation_id": "c1", "user_id": "u1", "input": "test"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_legacy_move_with_deprecation_header(test_client):
    """Test legacy /move endpoint has deprecation header."""
    response = await test_client.post(
        "/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )
    assert response.status_code == 200
    assert "X-Deprecation-Warning" in response.headers
    warning = response.headers["X-Deprecation-Warning"]
    assert "games" in warning.lower()
    assert "deprecated" in warning.lower() or "use" in warning.lower()
```

### Golden Tests Update

Update `scripts/goldens.py` to support new endpoint:

```python
# Add --api-base flag
parser.add_argument(
    "--api",
    default="http://localhost:8000/games/medical_scheduling/move",
    help="Runtime /move endpoint (default uses new multi-game format)"
)
```

### Definition of Done (P0-2)

- ✅ Can register 2+ games concurrently
- ✅ `GET /healthz` returns game count and IDs
- ✅ `GET /games` lists all games with metadata (id, name, version, file_hash)
- ✅ `GET /games/{id}` returns specific game metadata
- ✅ `POST /games/{id}/move` routes correctly to game-specific runtime
- ✅ Legacy `/move` works with `X-Deprecation-Warning` header
- ✅ Hot reload endpoint (`POST /games/{id}/reload`) in dev mode only
- ✅ CLI validates game files exist before starting server
- ✅ CLI shows clear error if file missing or format invalid
- ✅ Golden tests updated to use `/games/{id}/move`
- ✅ No regressions in existing golden tests

---

# PR-2: P1 FIXES

## P1-2: Embedding Cache & Determinism (DO FIRST)

### Problem Statement

**Issue:** OpenAI embeddings are non-deterministic:
- Model updates change embeddings silently
- Cannot reproduce confidence scores from historical runs
- Golden tests flaky when embeddings change
- No audit trail for why confidence changed

**Impact:** Test instability, unpredictable behavior, difficult debugging

### Solution Architecture

```
EmbeddingClient
  ├─ Cache: SQLite database
  │   Key: (text_hash, model, version)
  │   Value: embedding vector (JSON)
  ├─ Version locking: Warn on model mismatch
  └─ Offline fallback: TF-IDF character bigrams

Cache Strategy:
1. Check cache (keyed by text + model + version)
2. If miss and online: fetch from OpenAI
3. Verify returned model matches expected
4. Store in cache
5. If offline: use deterministic TF-IDF fallback
```

### Files Modified/Created

- **Modify:** `lgdl/runtime/matcher.py` (embedding client section)
- **Modify:** `.gitignore` (add `.embeddings_cache/`)
- **New:** `tests/test_embedding_cache.py`

### Implementation

#### Embedding Client Enhancement (`lgdl/runtime/matcher.py`)

```python
# Replace existing EmbeddingClient class

import os, hashlib, json, sqlite3, warnings
from pathlib import Path
from typing import List, Dict
import numpy as np


class EmbeddingClient:
    """
    Embedding client with versioned caching and offline fallback.

    Features:
    - SQLite cache keyed by (text_hash, model, version)
    - Version lock warnings on model mismatch
    - Deterministic TF-IDF character bigram fallback
    """

    def __init__(self):
        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.version_lock = os.getenv("OPENAI_EMBEDDING_VERSION", "2025-01")
        self.cache_enabled = os.getenv("EMBEDDING_CACHE", "1") == "1"

        if self.cache_enabled:
            cache_dir = Path(".embeddings_cache")
            cache_dir.mkdir(exist_ok=True)
            self.cache_db = cache_dir / f"{self.model}_{self.version_lock}.db"
            self._init_cache_db()
        else:
            self.cache: Dict[str, List[float]] = {}

        self.enabled = bool(os.getenv("OPENAI_API_KEY"))
        if self.enabled:
            try:
                from openai import OpenAI
                self.client = OpenAI()
            except Exception:
                self.enabled = False

    def _init_cache_db(self):
        """Initialize SQLite cache with versioning."""
        conn = sqlite3.connect(self.cache_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                text_hash TEXT PRIMARY KEY,
                text TEXT,
                model TEXT,
                version TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def _key(self, text: str) -> str:
        """Generate cache key from text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> List[float]:
        """
        Get embedding for text with caching.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        text_hash = self._key(text)

        # Check cache
        if self.cache_enabled:
            cached = self._get_cached(text_hash)
            if cached:
                return cached
        elif text_hash in self.cache:
            return self.cache[text_hash]

        # Fallback to offline mode if no API key
        if not self.enabled:
            vec = self._offline_embedding(text)
            self._store_cache(text_hash, text, vec)
            return vec

        # Fetch from OpenAI
        try:
            res = self.client.embeddings.create(model=self.model, input=[text])
            vec = res.data[0].embedding

            # Version check (warn on mismatch)
            if hasattr(res, 'model'):
                returned_model = res.model
                if returned_model != self.model:
                    warnings.warn(
                        f"Embedding model mismatch: expected {self.model}, "
                        f"got {returned_model}. Confidence scores may not be "
                        f"reproducible. Consider setting OPENAI_EMBEDDING_MODEL={returned_model}",
                        UserWarning
                    )
                    # Fail closed: don't cache mismatched versions
                    return vec

            self._store_cache(text_hash, text, vec)
            return vec

        except Exception as e:
            # Fall back to offline
            warnings.warn(
                f"OpenAI embedding failed: {e}. Using offline fallback.",
                UserWarning
            )
            self.enabled = False
            return self.embed(text)

    def _get_cached(self, text_hash: str) -> List[float] | None:
        """Retrieve cached embedding if available."""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.execute(
            "SELECT embedding FROM embeddings "
            "WHERE text_hash = ? AND model = ? AND version = ?",
            (text_hash, self.model, self.version_lock)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return json.loads(row[0])
        return None

    def _store_cache(self, text_hash: str, text: str, vec: List[float]):
        """Store embedding in cache."""
        if self.cache_enabled:
            conn = sqlite3.connect(self.cache_db)
            conn.execute(
                "INSERT OR REPLACE INTO embeddings "
                "(text_hash, text, model, version, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                (text_hash, text, self.model, self.version_lock, json.dumps(vec))
            )
            conn.commit()
            conn.close()
        else:
            self.cache[text_hash] = vec

    def _offline_embedding(self, text: str) -> List[float]:
        """
        Deterministic offline embedding using TF-IDF-inspired character bigrams.

        Better than bag-of-letters because it captures local character patterns.

        Args:
            text: Text to embed

        Returns:
            Normalized embedding vector (256 dimensions)
        """
        # Use character bigrams as features (more expressive than single chars)
        bigrams = (
            [text[i:i+2] for i in range(len(text)-1)]
            if len(text) > 1
            else [text]
        )

        # Fixed vocabulary size for consistent dimensionality
        vocab_size = 256
        vec = np.zeros(vocab_size)

        # Hash each bigram to vocab index and increment
        for bigram in bigrams:
            idx = hash(bigram) % vocab_size
            vec[idx] += 1

        # L2 normalize
        norm = np.linalg.norm(vec) or 1.0
        vec = vec / norm

        return vec.tolist()
```

#### .gitignore Update

```bash
# Add to .gitignore
.embeddings_cache/
```

### Test Specifications

```python
# tests/test_embedding_cache.py

import os, sqlite3, tempfile
import pytest
from pathlib import Path
from lgdl.runtime.matcher import EmbeddingClient


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment for testing."""
    monkeypatch.setenv("EMBEDDING_CACHE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    # Cleanup is automatic with monkeypatch


def test_cache_persistence(clean_env):
    """Embeddings cached and retrieved correctly."""
    client = EmbeddingClient()
    vec1 = client.embed("test phrase")
    vec2 = client.embed("test phrase")
    assert vec1 == vec2  # Same from cache


def test_offline_deterministic(clean_env):
    """Offline embeddings are deterministic across instances."""
    client1 = EmbeddingClient()
    client2 = EmbeddingClient()

    vec1 = client1.embed("hello world")
    vec2 = client2.embed("hello world")

    assert vec1 == vec2
    assert len(vec1) == 256  # Expected dimensionality


def test_offline_different_texts(clean_env):
    """Different texts produce different embeddings."""
    client = EmbeddingClient()

    vec_hello = client.embed("hello world")
    vec_goodbye = client.embed("goodbye world")

    assert vec_hello != vec_goodbye


def test_offline_similarity_properties(clean_env):
    """Offline embeddings have reasonable similarity properties."""
    from lgdl.runtime.matcher import cosine

    client = EmbeddingClient()

    vec_hello1 = client.embed("hello world")
    vec_hello2 = client.embed("hello world")
    vec_goodbye = client.embed("goodbye world")

    # Same text should be identical
    sim_same = cosine(vec_hello1, vec_hello2)
    assert sim_same == 1.0

    # Different texts should have lower similarity
    sim_diff = cosine(vec_hello1, vec_goodbye)
    assert sim_diff < 1.0


def test_cache_versioning(clean_env):
    """Cache keys include model and version."""
    client = EmbeddingClient()
    vec = client.embed("test")

    conn = sqlite3.connect(client.cache_db)
    cursor = conn.execute(
        "SELECT model, version FROM embeddings WHERE text = ?",
        ("test",)
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == client.model
    assert row[1] == client.version_lock


def test_cache_db_created(clean_env):
    """Cache database file is created."""
    client = EmbeddingClient()
    assert client.cache_db.exists()
    assert client.cache_db.suffix == ".db"


def test_cache_survives_restart(clean_env):
    """Cache persists across client instances."""
    client1 = EmbeddingClient()
    vec1 = client1.embed("persistence test")

    # Create new client (simulates restart)
    client2 = EmbeddingClient()
    vec2 = client2.embed("persistence test")

    assert vec1 == vec2


def test_cache_disabled(clean_env, monkeypatch):
    """In-memory cache works when SQLite cache disabled."""
    monkeypatch.setenv("EMBEDDING_CACHE", "0")

    client = EmbeddingClient()
    vec1 = client.embed("test")
    vec2 = client.embed("test")

    assert vec1 == vec2
    assert not hasattr(client, 'cache_db')


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
def test_version_mismatch_warning(monkeypatch):
    """Warn when API returns different model version."""
    # This test requires mocking OpenAI API response
    # Skipping implementation for now, but structure:
    # 1. Mock openai.OpenAI().embeddings.create()
    # 2. Return response with mismatched model name
    # 3. Assert warnings.warn() called with version mismatch message
    pass


def test_embedding_normalization(clean_env):
    """Offline embeddings are L2 normalized."""
    import numpy as np

    client = EmbeddingClient()
    vec = client.embed("normalization test")

    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-6  # Should be ~1.0
```

### Golden Tests Configuration

Update `scripts/run_goldens.sh`:

```bash
# Add before running tests
export EMBEDDING_CACHE=1
export OPENAI_EMBEDDING_VERSION="2025-01"
```

### Definition of Done (P1-2)

- ✅ Embeddings persisted to SQLite
- ✅ Cache key: `(text_hash, model, version)`
- ✅ Warn on model mismatch (fail closed, don't cache)
- ✅ Offline deterministic fallback (TF-IDF character bigrams, 256 dims)
- ✅ Golden tests reproducible with `EMBEDDING_CACHE=1`
- ✅ Cache survives across test runs and client restarts
- ✅ `.gitignore` updated to exclude `.embeddings_cache/`
- ✅ Tests cover: persistence, determinism, versioning, offline similarity

---

## P1-1: Negotiation State Management (DO SECOND)

### Problem Statement

**Issue:** v1.0 spec has `negotiate ... until confident` but undefined:
- How user responses update parameters
- How confidence is recalculated
- When to stop looping (infinite loop risk)

**Impact:** Cannot implement negotiation features for v1.0

### Solution Architecture

```
NegotiationLoop
  ├─ State: {round, history: [(q,a),...], feature_deltas}
  ├─ Strategy:
  │   1. Ask clarification question
  │   2. User responds
  │   3. Update parameters dict
  │   4. Reconstruct enriched input
  │   5. Re-run matcher
  │   6. Check stop conditions
  └─ Stop conditions (IN ORDER):
      1. Confidence >= threshold (SUCCESS)
      2. Max rounds exceeded (FAILURE)
      3. No information gain: Δconf < ε for 2 consecutive rounds (FAILURE)
```

### Stop Condition Details

**Priority Order:**
1. **Threshold met** (confidence >= move.threshold) → SUCCESS
2. **Max rounds** (default: 3) → FAILURE: `max_rounds_exceeded`
3. **No gain** (Δconf < epsilon for 2 consecutive rounds) → FAILURE: `no_information_gain`

**Epsilon (ε):** Minimum confidence improvement per round (default: 0.05)

### Files Modified/Created

- **New:** `lgdl/runtime/negotiation.py`
- **Modify:** `lgdl/runtime/engine.py`
- **New:** `examples/medical/golden_dialogs_negotiation.yaml`
- **New:** `tests/test_negotiation.py`

### Implementation

#### Negotiation Module (`lgdl/runtime/negotiation.py`)

```python
"""
Negotiation loop for clarification-driven confidence improvement.

Implements iterative clarification with multiple stop conditions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class NegotiationRound:
    """Record of one negotiation round."""
    round_num: int
    question: str
    user_response: str
    updated_params: Dict[str, Any]
    confidence_before: float
    confidence_after: float
    feature_deltas: Dict[str, float] = field(default_factory=dict)


@dataclass
class NegotiationState:
    """Persistent state across negotiation rounds."""
    round: int = 0
    history: List[tuple[str, str]] = field(default_factory=list)  # [(Q, A), ...]
    feature_deltas: Dict[str, float] = field(default_factory=dict)


@dataclass
class NegotiationResult:
    """Final result of negotiation loop."""
    success: bool
    rounds: List[NegotiationRound]
    final_confidence: float
    final_params: Dict[str, Any]
    reason: str  # "threshold_met" | "max_rounds_exceeded" | "no_information_gain"


class NegotiationLoop:
    """
    Implements clarification loop with confidence re-evaluation.

    Stop conditions (checked in order):
    1. Confidence >= threshold → success
    2. Reached max_rounds → failure
    3. No information gain (Δconf < epsilon for 2 consecutive rounds) → failure
    """

    def __init__(self, max_rounds: int = 3, epsilon: float = 0.05):
        """
        Initialize negotiation loop.

        Args:
            max_rounds: Maximum clarification rounds (default: 3)
            epsilon: Minimum confidence gain per round (default: 0.05)
        """
        self.max_rounds = max_rounds
        self.epsilon = epsilon

    async def clarify_until_confident(
        self,
        move: dict,
        initial_input: str,
        initial_match: dict,
        matcher,
        compiled_game: dict,
        ask_user: Callable[[str, List[str]], str]
    ) -> NegotiationResult:
        """
        Execute negotiation loop.

        Args:
            move: Move IR with clarify action
            initial_input: Original user input
            initial_match: Initial match result
            matcher: TwoStageMatcher instance
            compiled_game: Compiled game IR
            ask_user: Async function to prompt user

        Returns:
            NegotiationResult with success status and metadata
        """
        state = NegotiationState()
        rounds = []
        params = initial_match["params"].copy()
        confidence = initial_match["score"]
        threshold = move["threshold"]

        no_gain_count = 0  # Track consecutive rounds with no gain

        for round_num in range(1, self.max_rounds + 1):
            state.round = round_num

            # Extract clarification action from move
            clarify_action = self._find_clarify_action(move)
            if not clarify_action:
                return NegotiationResult(
                    success=False, rounds=rounds,
                    final_confidence=confidence, final_params=params,
                    reason="no_clarify_action"
                )

            question = clarify_action.get("question", "Can you clarify?")
            options = clarify_action.get("options", [])
            param_name = clarify_action.get("param_name")

            # Ask user
            user_response = await ask_user(question, options)
            state.history.append((question, user_response))

            # Record confidence before update
            confidence_before = confidence

            # Update parameters
            if param_name:
                params[param_name] = user_response

            # Reconstruct enriched input
            enriched_input = self._enrich_input(initial_input, params)

            # Re-run matcher on enriched input
            new_match = matcher.match(enriched_input, compiled_game)
            confidence_after = new_match["score"]

            # Calculate feature deltas (if provenance available)
            feature_deltas = {}
            if "provenance" in new_match:
                # Extract feature contributions from provenance
                # This depends on matcher returning detailed provenance
                # For now, leave empty
                pass

            # Record round
            rounds.append(NegotiationRound(
                round_num=round_num,
                question=question,
                user_response=user_response,
                updated_params=params.copy(),
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                feature_deltas=feature_deltas
            ))

            confidence = confidence_after

            # STOP CONDITION 1: Threshold met
            if confidence >= threshold:
                return NegotiationResult(
                    success=True, rounds=rounds,
                    final_confidence=confidence, final_params=params,
                    reason="threshold_met"
                )

            # STOP CONDITION 3: No information gain
            delta = confidence_after - confidence_before
            if delta < self.epsilon:
                no_gain_count += 1
                if no_gain_count >= 2:
                    # Two consecutive rounds with no meaningful gain
                    return NegotiationResult(
                        success=False, rounds=rounds,
                        final_confidence=confidence, final_params=params,
                        reason="no_information_gain"
                    )
            else:
                no_gain_count = 0  # Reset if we had meaningful gain

        # STOP CONDITION 2: Max rounds exceeded
        return NegotiationResult(
            success=False, rounds=rounds,
            final_confidence=confidence, final_params=params,
            reason="max_rounds_exceeded"
        )

    def _find_clarify_action(self, move: dict) -> dict | None:
        """
        Extract clarify action from uncertain block.

        Args:
            move: Move IR

        Returns:
            Clarify action data dict or None
        """
        for block in move.get("blocks", []):
            if block.get("condition", {}).get("special") == "uncertain":
                for action in block.get("actions", []):
                    if action.get("type") in ("ask_clarification", "clarify"):
                        return action.get("data", {})
        return None

    def _enrich_input(self, original: str, params: Dict[str, Any]) -> str:
        """
        Reconstruct input with extracted parameters.

        Strategy: Append new information to original input.

        Example:
            original = "I need to see a doctor"
            params = {"doctor": "Smith"}
            enriched = "I need to see a doctor Smith"

        Args:
            original: Original user input
            params: Extracted/updated parameters

        Returns:
            Enriched input string
        """
        enriched = original
        for key, val in params.items():
            if val and str(val).lower() not in original.lower():
                enriched += f" {val}"
        return enriched
```

#### Engine Integration (`lgdl/runtime/engine.py`)

```python
# Add import
from .negotiation import NegotiationLoop, NegotiationResult

# In LGDLRuntime.__init__:
class LGDLRuntime:
    def __init__(self, compiled):
        self.compiled = compiled
        self.matcher = TwoStageMatcher()
        self.policy = PolicyGuard(...)
        self.cap = CapabilityClient(...)
        self.templates = TemplateRenderer()
        self.negotiation = NegotiationLoop(max_rounds=3, epsilon=0.05)  # NEW

    async def process_turn(self, conversation_id, user_id, text, context):
        cleaned, flagged = sanitize(text)
        match = self.matcher.match(cleaned, self.compiled)

        if not match["move"]:
            return {...}

        mv = match["move"]
        score = match["score"]
        threshold = mv["threshold"]

        # NEW: Negotiation if uncertain and has clarify action
        if score < threshold and self._has_clarify(mv):
            neg_result = await self.negotiation.clarify_until_confident(
                mv, cleaned, match, self.matcher, self.compiled,
                ask_user=lambda q, opts: self._prompt_user(conversation_id, q, opts)
            )

            # Log negotiation manifest (stdout)
            for round_data in neg_result.rounds:
                delta = round_data.confidence_after - round_data.confidence_before
                print(
                    f"[Negotiation Round {round_data.round_num}] "
                    f"Confidence: {round_data.confidence_before:.2f} → "
                    f"{round_data.confidence_after:.2f} (Δ {delta:+.2f})"
                )

            if neg_result.success:
                score = neg_result.final_confidence
                params = neg_result.final_params
                print(f"[Negotiation] Success: {neg_result.reason}")
            else:
                print(f"[Negotiation] Failed: {neg_result.reason}")
                return {
                    "move_id": mv["id"],
                    "confidence": score,
                    "response": (
                        f"I wasn't able to understand after "
                        f"{len(neg_result.rounds)} clarifications."
                    ),
                    "negotiation": {
                        "rounds": len(neg_result.rounds),
                        "reason": neg_result.reason,
                        "history": [
                            (r.question, r.user_response)
                            for r in neg_result.rounds
                        ]
                    },
                    "manifest_id": str(uuid.uuid4()),
                    "firewall_triggered": flagged
                }

        # Continue with normal execution...

    def _has_clarify(self, move: dict) -> bool:
        """Check if move has clarify action in uncertain block."""
        for block in move.get("blocks", []):
            if block.get("condition", {}).get("special") == "uncertain":
                for action in block.get("actions", []):
                    if action.get("type") in ("ask_clarification", "clarify"):
                        return True
        return False

    async def _prompt_user(self, conversation_id: str, question: str, options: List[str]) -> str:
        """
        Prompt user for clarification.

        In production, this would be async communication channel.
        For tests, can be mocked.
        """
        # Placeholder implementation
        # In real system, would send message and await response
        raise NotImplementedError("User prompting not implemented in MVP")
```

### Test Specifications

**(See docs/P0_P1_CRITICAL_FIXES.md section for complete test code - truncated here for brevity)**

Key tests:
- `test_negotiation_threshold_met` - Success case
- `test_negotiation_max_rounds` - Max rounds abort
- `test_negotiation_no_information_gain` - No gain abort after 2 rounds
- `test_negotiation_state_history` - History tracking

### Golden Test Example

```yaml
# examples/medical/golden_dialogs_negotiation.yaml (NEW FILE)
game: medical_scheduling
version: 0.1
dialogs:
  - name: two_round_clarification_success
    description: User provides missing info, confidence crosses threshold
    turns:
      - input: "I need to see a doctor"
        expect:
          move: appointment_request
          confidence: "<=0.70"
          # Triggers negotiation
      - input: "Dr. Smith"  # User's clarification response
        expect:
          move: appointment_request
          confidence: ">=0.80"
          response_contains: ["availability", "Smith"]
          negotiation:
            rounds: 1
            reason: "threshold_met"

  - name: max_rounds_abort
    description: User provides unhelpful responses, hits max rounds
    turns:
      - input: "I need something"
        expect:
          move: general_inquiry
          confidence: "<=0.40"
      - input: "I don't know"  # Round 1 - unhelpful
      - input: "Not sure"      # Round 2 - unhelpful
      - input: "Maybe?"        # Round 3 - unhelpful
        expect:
          negotiation:
            rounds: 3
            reason: "max_rounds_exceeded"
          response_contains: ["wasn't able to understand"]

  - name: no_gain_abort
    description: Confidence plateaus, stops after 2 no-gain rounds
    turns:
      - input: "book something"
        expect:
          confidence: "<=0.50"
      - input: "appointment"  # Small gain
      - input: "yes"          # No gain round 1
      - input: "uh huh"       # No gain round 2
        expect:
          negotiation:
            reason: "no_information_gain"
```

### Definition of Done (P1-1)

- ✅ Negotiation state object with round, history, feature_deltas
- ✅ Ordered stop rules:
  1. Confidence >= threshold (SUCCESS)
  2. Max rounds (default 3, FAILURE)
  3. No information gain (Δconf < epsilon for 2 consecutive rounds, FAILURE)
- ✅ Epsilon configurable (default 0.05)
- ✅ Structured result with rounds, Q/A history, reason
- ✅ Golden test: two-round success case
- ✅ Golden test: max-rounds abort case
- ✅ Test: no-information-gain abort case (2 consecutive low-delta rounds)
- ✅ Manifest lines printed to stdout during negotiation
- ✅ Negotiation metadata in API response
- ✅ No infinite loops (all paths terminate)

---

# Execution Checklist

## Sequencing (STRICT ORDER)

### Phase 1: PR-1 (P0 Fixes)

- [ ] **P0-1: Template Security**
  - [ ] Create `lgdl/errors.py` with error taxonomy
  - [ ] Create `lgdl/runtime/templates.py` with SafeArithmeticValidator
  - [ ] Modify `lgdl/runtime/engine.py` to use TemplateRenderer
  - [ ] Create `tests/test_errors.py`
  - [ ] Create `tests/test_templates.py`
  - [ ] All template tests pass
  - [ ] Golden tests pass (no regression)

- [ ] **P0-2: Multi-Game API**
  - [ ] Create `lgdl/runtime/registry.py` with GameRegistry
  - [ ] Modify `lgdl/runtime/api.py` (add endpoints, deprecation header)
  - [ ] Modify `lgdl/cli/main.py` (add `serve` command)
  - [ ] Create `tests/test_registry.py`
  - [ ] Update `scripts/goldens.py` for new endpoint
  - [ ] All registry/API tests pass
  - [ ] Golden tests pass with new `/games/{id}/move` endpoint

- [ ] **PR-1 Merge**
  - [ ] All tests green locally
  - [ ] Code review completed
  - [ ] Merge to `main`
  - [ ] Tag: `p0-fixes-complete`

### Phase 2: PR-2 (P1 Fixes)

- [ ] **P1-2: Embedding Cache** (DO FIRST)
  - [ ] Modify `lgdl/runtime/matcher.py` (EmbeddingClient with SQLite cache)
  - [ ] Update `.gitignore` (add `.embeddings_cache/`)
  - [ ] Create `tests/test_embedding_cache.py`
  - [ ] Update `scripts/run_goldens.sh` (add EMBEDDING_CACHE env)
  - [ ] All embedding cache tests pass
  - [ ] Golden tests reproducible with cache enabled

- [ ] **P1-1: Negotiation State** (DO SECOND)
  - [ ] Create `lgdl/runtime/negotiation.py` with NegotiationLoop
  - [ ] Modify `lgdl/runtime/engine.py` (integrate negotiation)
  - [ ] Create `examples/medical/golden_dialogs_negotiation.yaml`
  - [ ] Create `tests/test_negotiation.py`
  - [ ] All negotiation tests pass
  - [ ] Negotiation golden tests pass

- [ ] **PR-2 Merge**
  - [ ] All tests green locally
  - [ ] Code review completed
  - [ ] Merge to `main`
  - [ ] Tag: `p0-p1-fixes-complete`

### Phase 3: Documentation

- [ ] Update `docs/MIGRATION_MVP_TO_V1.md` with completed P0/P1
- [ ] Update `README.md` with new CLI commands and API endpoints
- [ ] Inline docstrings verified

---

# Timeline & Estimates

| Item | Estimated Time | Notes |
|------|---------------|-------|
| **P0-1: Template Security** | 1-2 hours | Error taxonomy + validator + tests |
| **P0-2: Multi-Game API** | 2-3 hours | Registry + endpoints + CLI + tests |
| **PR-1 Review/Merge** | 1 hour | Code review, merge conflicts |
| **P1-2: Embedding Cache** | 1-2 hours | SQLite cache + TF-IDF + tests |
| **P1-1: Negotiation** | 3-4 hours | Loop logic + integration + tests |
| **PR-2 Review/Merge** | 1 hour | Code review, golden test updates |
| **Documentation Updates** | 0.5 hours | README, migration doc updates |
| **Total** | **10.5-13.5 hours** | Includes review/merge time |

**Expected completion:** 2-3 focused work sessions

---

# References

- **Branch:** `feature/p0-p1-critical-fixes`
- **Migration Plan:** `docs/MIGRATION_MVP_TO_V1.md`
- **MVP Tag:** `mvp-v0.1`
- **Success Criteria:** All P0/P1 DoDs met, no golden test regressions

---

**Status:** Ready for Implementation
**Last Updated:** 2025-10-25
**Next Action:** Begin P0-1 (Template Security) implementation
