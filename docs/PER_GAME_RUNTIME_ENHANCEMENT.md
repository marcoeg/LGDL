# Per-Game Runtime Enhancement Plan

**Status**: Proposed
**Priority**: P1-3 (Medium - Required for true multi-game capability support)
**Affects**: Multi-game API (P0-2), capability system
**Author**: Discovery from examples generation session
**Date**: 2025-10-30

---

## Executive Summary

The current multi-game API (P0-2) successfully routes requests to different games but shares a single `LGDLRuntime` instance with hardcoded medical game configuration. This prevents non-medical games from executing their capabilities, as all capability calls hit the medical game's `PolicyGuard` allowlist and `CapabilityClient`.

**Impact**: New games (shopping, support, restaurant) parse and route correctly but cannot execute capability actions, resulting in "Not allowed." appended to all responses.

**Solution**: Instantiate per-game runtime instances with game-specific policy guards and capability clients.

---

## Problem Statement

### Current Architecture

```
GameRegistry
├─ Stores: {game_id: compiled_IR}
├─ Routes: /games/{id}/move → LGDLRuntime
└─ Runtime: Single shared LGDLRuntime instance

LGDLRuntime (lgdl/runtime/engine.py:50-60)
├─ PolicyGuard(allowlist={"check_availability"})  # Hardcoded medical
├─ CapabilityClient("examples/medical/capability_contract.json")  # Hardcoded medical
└─ Used by ALL games
```

**Symptom**:
```bash
# Shopping game trying to call product_catalog.search_products
Response: "Great there! I'll search for laptops for you. Not allowed."
                                                           ^^^^^^^^^^^^
# PolicyGuard rejects because "search_products" not in {"check_availability"}
```

### Root Cause Analysis

**File**: `lgdl/runtime/engine.py`

```python
class LGDLRuntime:
    def __init__(self, compiled):
        self.compiled = compiled
        self.matcher = TwoStageMatcher()
        self.policy = PolicyGuard(allowlist={"check_availability"})  # ← HARDCODED
        self.cap = CapabilityClient(str(Path(__file__).resolve().parents[2] / "examples" / "medical" / "capability_contract.json"))  # ← HARDCODED
        # ...
```

**File**: `lgdl/runtime/api.py`

```python
# Global runtime instance per game
game_runtimes: Dict[str, LGDLRuntime] = {}

@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest):
    # ...
    if game_id not in game_runtimes:
        game_runtimes[game_id] = LGDLRuntime(compiled)  # ← Uses hardcoded constructor
```

**Issues**:
1. `PolicyGuard` allowlist is medical-specific
2. `CapabilityClient` points to medical contract JSON
3. No mechanism to pass game-specific config to `LGDLRuntime`

---

## Proposed Solution

### Architecture: Per-Game Runtime Instances

```
GameRegistry
├─ Stores: {game_id: GameEntry}
│   └─ GameEntry:
│       ├─ compiled_ir: dict
│       ├─ capability_contract_path: str
│       ├─ allowlist: Set[str]  (extracted from compiled IR)
│       └─ runtime: LGDLRuntime  (per-game instance)
│
└─ Routes: /games/{id}/move → GameEntry.runtime
```

**Key Changes**:
1. Extract allowlist from compiled IR (IR already knows capabilities)
2. Store capability contract path per game
3. Instantiate `LGDLRuntime` with game-specific config
4. One runtime instance per game (not shared)

### Data Flow

**Registration** (`lgdl serve --games shopping:examples/shopping/game.lgdl`):
```
1. Parse game.lgdl → AST
2. Compile AST → IR
3. Extract capabilities from IR:
   capabilities: {
     "product_catalog": ["search_products", "get_price"],
     "cart_system": ["add_item"]
   }
   → allowlist = {"search_products", "get_price", "add_item"}
4. Locate capability_contract.json (same dir as game.lgdl)
5. Create LGDLRuntime(compiled, allowlist, contract_path)
6. Store in registry
```

**Request** (`POST /games/shopping/move`):
```
1. Lookup: registry["shopping"] → GameEntry
2. Use: GameEntry.runtime.process_turn(...)
3. Runtime uses shopping's PolicyGuard and CapabilityClient
```

---

## Implementation Plan

### Phase 1: Extract Capability Metadata from IR

**File**: `lgdl/parser/ir.py`

Add helper to extract capabilities from compiled IR:

```python
def extract_capability_allowlist(compiled_ir: dict) -> Set[str]:
    """
    Extract all capability functions from compiled IR.

    Args:
        compiled_ir: Compiled game IR

    Returns:
        Set of allowed function names (e.g., {"search_products", "add_item"})
    """
    allowlist = set()

    # Iterate through all moves
    for move in compiled_ir.get("moves", []):
        for block in move.get("blocks", []):
            for action in block.get("actions", []):
                if action.get("type") == "capability":
                    call = action.get("data", {}).get("call", {})
                    function = call.get("function")
                    if function:
                        allowlist.add(function)

    return allowlist
```

**Test**:
```python
def test_extract_allowlist():
    compiled = compile_game(parse_lgdl("examples/shopping/game.lgdl"))
    allowlist = extract_capability_allowlist(compiled)
    assert "search_products" in allowlist
    assert "add_item" in allowlist
    assert "check_availability" not in allowlist  # medical only
```

---

### Phase 2: Refactor LGDLRuntime Constructor

**File**: `lgdl/runtime/engine.py`

**Before**:
```python
class LGDLRuntime:
    def __init__(self, compiled):
        self.compiled = compiled
        self.matcher = TwoStageMatcher()
        self.policy = PolicyGuard(allowlist={"check_availability"})
        self.cap = CapabilityClient("examples/medical/capability_contract.json")
```

**After**:
```python
class LGDLRuntime:
    def __init__(
        self,
        compiled: dict,
        allowlist: Optional[Set[str]] = None,
        capability_contract_path: Optional[str] = None
    ):
        """
        Initialize game runtime.

        Args:
            compiled: Compiled game IR
            allowlist: Allowed capability functions (if None, extract from IR)
            capability_contract_path: Path to capability contract JSON (if None, disable capabilities)
        """
        self.compiled = compiled
        self.matcher = TwoStageMatcher()

        # Auto-extract allowlist if not provided
        if allowlist is None:
            from ..parser.ir import extract_capability_allowlist
            allowlist = extract_capability_allowlist(compiled)

        self.policy = PolicyGuard(allowlist=allowlist)

        # Only create capability client if contract provided
        if capability_contract_path and Path(capability_contract_path).exists():
            self.cap = CapabilityClient(capability_contract_path)
        else:
            self.cap = None  # No-op capability client

        self.templates = TemplateRenderer()
        self.negotiation = NegotiationLoop(
            max_rounds=int(os.getenv("LGDL_NEGOTIATION_MAX_ROUNDS", "3")),
            epsilon=float(os.getenv("LGDL_NEGOTIATION_EPSILON", "0.05"))
        )
        self.negotiation_enabled = os.getenv("LGDL_NEGOTIATION", "1") == "1"
```

**Backward compatibility**: Existing code without allowlist/contract args auto-extracts from IR.

---

### Phase 3: Update GameRegistry

**File**: `lgdl/runtime/registry.py`

**Add to GameEntry dataclass**:
```python
@dataclass
class GameEntry:
    """Entry in game registry."""
    id: str
    name: str
    version: str
    file_path: str
    file_hash: str
    compiled: dict
    registered_at: float
    capability_contract_path: Optional[str] = None  # NEW
    runtime: Optional[Any] = None  # NEW: Per-game runtime instance
```

**Update register_game**:
```python
def register_game(self, game_id: str, file_path: str) -> GameEntry:
    """
    Register game and create per-game runtime.

    Args:
        game_id: Unique game identifier
        file_path: Path to .lgdl file

    Returns:
        GameEntry with initialized runtime
    """
    # Existing parsing/compilation
    game_ast = parse_lgdl(file_path)
    compiled = compile_game(game_ast)
    file_hash = self._compute_file_hash(file_path)

    # NEW: Locate capability contract
    game_dir = Path(file_path).parent
    contract_path = game_dir / "capability_contract.json"
    contract_path_str = str(contract_path) if contract_path.exists() else None

    # NEW: Extract allowlist from IR
    from ..parser.ir import extract_capability_allowlist
    allowlist = extract_capability_allowlist(compiled)

    # NEW: Create per-game runtime instance
    from .engine import LGDLRuntime
    runtime = LGDLRuntime(
        compiled=compiled,
        allowlist=allowlist,
        capability_contract_path=contract_path_str
    )

    entry = GameEntry(
        id=game_id,
        name=compiled.get("name", game_id),
        version=compiled.get("version", "unknown"),
        file_path=file_path,
        file_hash=file_hash,
        compiled=compiled,
        registered_at=time.time(),
        capability_contract_path=contract_path_str,
        runtime=runtime  # Store per-game runtime
    )

    self._games[game_id] = entry
    return entry
```

---

### Phase 4: Update API to Use Per-Game Runtimes

**File**: `lgdl/runtime/api.py`

**Before**:
```python
# Global shared runtime per game
game_runtimes: Dict[str, LGDLRuntime] = {}

@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest):
    entry = registry.get_game(game_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Game '{game_id}' not found")

    # Lazy-init shared runtime
    if game_id not in game_runtimes:
        game_runtimes[game_id] = LGDLRuntime(entry.compiled)

    runtime = game_runtimes[game_id]
```

**After**:
```python
@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest):
    entry = registry.get_game(game_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Game '{game_id}' not found")

    # Use per-game runtime from registry
    runtime = entry.runtime
    if not runtime:
        raise HTTPException(status_code=500, detail=f"Runtime not initialized for game '{game_id}'")
```

**Remove global `game_runtimes` dict** - no longer needed!

---

### Phase 5: Handle Capability Execution

**File**: `lgdl/runtime/engine.py`

**Update `_exec_action` to handle missing capability client**:

```python
async def _exec_action(self, action: Dict[str, Any], params: Dict[str, Any]):
    atype = action.get("type")
    data = action.get("data", {})
    status = "ok"

    # ... existing respond, offer_choices ...

    if atype == "capability":
        call = data.get("call", {})
        func = call.get("function")

        if not self.policy.allowed(func):
            return "Not allowed.", None, "err"

        # NEW: Check if capability client available
        if not self.cap:
            return f"Capability system not configured for this game.", None, "err"

        payload = {}
        for k in ("doctor", "date"):  # TODO: Make dynamic based on IR
            if k in params and params[k] is not None:
                payload[k] = params[k]

        res = await self.cap.execute(f'{call.get("service")}.{func}', payload)
        return res.get("message", ""), func, status
```

---

### Phase 6: Testing

**Unit Tests** (`tests/test_per_game_runtime.py`):

```python
def test_extract_capability_allowlist():
    """Extract allowlist from shopping game IR."""
    compiled = compile_game(parse_lgdl("examples/shopping/game.lgdl"))
    allowlist = extract_capability_allowlist(compiled)

    assert "search_products" in allowlist
    assert "add_item" in allowlist
    assert "process_payment" in allowlist
    assert "check_availability" not in allowlist  # medical only


def test_runtime_with_custom_allowlist():
    """LGDLRuntime accepts custom allowlist."""
    compiled = {"moves": []}
    allowlist = {"custom_function"}

    runtime = LGDLRuntime(compiled, allowlist=allowlist, capability_contract_path=None)

    assert runtime.policy.allowed("custom_function")
    assert not runtime.policy.allowed("check_availability")


def test_runtime_auto_extracts_allowlist():
    """LGDLRuntime auto-extracts allowlist when not provided."""
    compiled = compile_game(parse_lgdl("examples/shopping/game.lgdl"))
    runtime = LGDLRuntime(compiled)  # No allowlist arg

    assert runtime.policy.allowed("search_products")
    assert not runtime.policy.allowed("check_availability")


def test_registry_creates_per_game_runtimes():
    """GameRegistry creates separate runtime for each game."""
    registry = GameRegistry()

    medical = registry.register_game("medical", "examples/medical/game.lgdl")
    shopping = registry.register_game("shopping", "examples/shopping/game.lgdl")

    # Different runtime instances
    assert medical.runtime is not shopping.runtime

    # Medical runtime allows medical capabilities
    assert medical.runtime.policy.allowed("check_availability")
    assert not medical.runtime.policy.allowed("search_products")

    # Shopping runtime allows shopping capabilities
    assert shopping.runtime.policy.allowed("search_products")
    assert not shopping.runtime.policy.allowed("check_availability")
```

**Integration Tests** (`tests/test_multi_game_capabilities.py`):

```python
@pytest.mark.asyncio
async def test_shopping_game_capability_calls():
    """Shopping game can execute its own capabilities."""
    registry = GameRegistry()
    registry.register_game("shopping", "examples/shopping/game.lgdl")

    entry = registry.get_game("shopping")
    runtime = entry.runtime

    result = await runtime.process_turn(
        conversation_id="test",
        user_id="user1",
        text="looking for laptops",
        context={}
    )

    # Should NOT have "Not allowed." appended
    assert "Not allowed" not in result["response"]
    assert result["move_id"] == "product_search"


@pytest.mark.asyncio
async def test_support_game_capability_calls():
    """Support game can execute its own capabilities."""
    registry = GameRegistry()
    registry.register_game("support", "examples/support/game.lgdl")

    entry = registry.get_game("support")
    runtime = entry.runtime

    result = await runtime.process_turn(
        conversation_id="test",
        user_id="user1",
        text="reset password",
        context={"account_email": "test@example.com"}
    )

    # Should NOT have "Not allowed." appended
    assert "Not allowed" not in result["response"]
    assert result["move_id"] == "reset_password"
```

---

## Migration Guide

### For Existing Code

**Old** (still works with deprecation warning):
```python
runtime = LGDLRuntime(compiled_ir)
```

**New** (recommended):
```python
from lgdl.parser.ir import extract_capability_allowlist

allowlist = extract_capability_allowlist(compiled_ir)
runtime = LGDLRuntime(
    compiled=compiled_ir,
    allowlist=allowlist,
    capability_contract_path="examples/mygame/capability_contract.json"
)
```

**Via GameRegistry** (best practice):
```python
registry = GameRegistry()
entry = registry.register_game("mygame", "examples/mygame/game.lgdl")
runtime = entry.runtime  # Already configured
```

### Breaking Changes

**None** - Backward compatible!

- `LGDLRuntime(compiled)` still works (auto-extracts allowlist)
- Existing medical game continues to work
- New games get proper per-game configuration

---

## Expected Outcomes

### Before Enhancement

```bash
$ curl -X POST http://localhost:9000/games/shopping/move \
  -d '{"conversation_id":"c1","user_id":"u1","input":"looking for laptops"}'

{
  "move_id": "product_search",
  "response": "Great there! I'll search for laptops for you. Not allowed.",
                                                             ^^^^^^^^^^^^
  "confidence": 0.6
}
```

### After Enhancement

```bash
$ curl -X POST http://localhost:9000/games/shopping/move \
  -d '{"conversation_id":"c1","user_id":"u1","input":"looking for laptops"}'

{
  "move_id": "product_search",
  "response": "Great there! I'll search for laptops for you.",
  "action": "search_products",
  "confidence": 0.6
}
```

---

## Success Criteria

- ✅ Each game has its own `LGDLRuntime` instance
- ✅ Each runtime has game-specific `PolicyGuard` allowlist
- ✅ Each runtime has game-specific `CapabilityClient`
- ✅ Allowlist auto-extracted from compiled IR
- ✅ Capability contract auto-located (same dir as .lgdl file)
- ✅ All 5 example games execute capabilities without "Not allowed."
- ✅ All golden tests pass for shopping, support, restaurant
- ✅ Backward compatible with existing medical game code
- ✅ No breaking changes to public API

---

## Timeline Estimate

**Total**: ~4-6 hours

- Phase 1 (Extract allowlist): 45 min
- Phase 2 (Refactor constructor): 30 min
- Phase 3 (Update registry): 1 hour
- Phase 4 (Update API): 30 min
- Phase 5 (Handle execution): 30 min
- Phase 6 (Testing): 1.5-2 hours
- Documentation updates: 30 min

---

## Dependencies

**Requires**:
- P0-2 (Multi-Game API) - Already implemented
- Current IR structure includes capability metadata

**Enables**:
- Full multi-game capability support
- Shopping/support/restaurant examples to work correctly
- Third-party games with custom capabilities

**Blocks**:
- None (enhancement, not blocker)

---

## Alternatives Considered

### Alternative 1: Global Capability Allowlist

**Idea**: Merge all games' allowlists into one shared PolicyGuard.

**Pros**: Simple, one-line change.

**Cons**:
- Security issue: any game can call any capability
- Shopping game could call medical's `check_availability`
- Violates least-privilege principle

**Verdict**: ❌ Rejected for security reasons

### Alternative 2: Pass Game ID to Capability Client

**Idea**: Keep shared runtime, pass game_id to select contract at execution time.

**Pros**: Minimal code changes.

**Cons**:
- Runtime becomes stateful and complex
- Contract lookup on every capability call (performance)
- Harder to test and reason about
- Still requires per-game allowlists

**Verdict**: ❌ Rejected for complexity

### Alternative 3: Per-Game Runtime Instances (CHOSEN)

**Pros**:
- Clean separation of concerns
- Each game is isolated
- Easy to test
- Scales to N games
- Natural fit with registry architecture

**Cons**:
- More memory (N runtimes vs 1)
- Slightly more complex registration

**Verdict**: ✅ **SELECTED** - Best long-term solution

---

## Related Issues

**Discovered during**: Example game generation (2025-10-30)
**Affects**: Shopping, support, restaurant games
**Does NOT affect**: Medical, greeting games (no/allowed capabilities)

**Related documents**:
- [docs/P0_P1_CRITICAL_FIXES.md](P0_P1_CRITICAL_FIXES.md) - P0-2 Multi-Game API implementation
- [examples/shopping/capability_contract.json](../examples/shopping/capability_contract.json)
- [examples/support/capability_contract.json](../examples/support/capability_contract.json)
- [examples/restaurant/capability_contract.json](../examples/restaurant/capability_contract.json)

---

## Appendix: Current vs Proposed Code Comparison

### Current: Shared Runtime

```python
# lgdl/runtime/api.py
game_runtimes: Dict[str, LGDLRuntime] = {}

@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest):
    entry = registry.get_game(game_id)

    # ALL games use SAME runtime config
    if game_id not in game_runtimes:
        game_runtimes[game_id] = LGDLRuntime(entry.compiled)

    runtime = game_runtimes[game_id]
    # runtime.policy.allowlist = {"check_availability"}  # Medical only!
    # runtime.cap points to medical contract              # Medical only!
```

### Proposed: Per-Game Runtimes

```python
# lgdl/runtime/registry.py
def register_game(self, game_id: str, file_path: str) -> GameEntry:
    compiled = compile_game(parse_lgdl(file_path))

    # Extract THIS game's capabilities
    allowlist = extract_capability_allowlist(compiled)

    # Find THIS game's contract
    contract_path = Path(file_path).parent / "capability_contract.json"

    # Create THIS game's runtime
    runtime = LGDLRuntime(
        compiled=compiled,
        allowlist=allowlist,  # shopping: {search_products, add_item, ...}
        capability_contract_path=str(contract_path)  # shopping's contract
    )

    return GameEntry(..., runtime=runtime)

# lgdl/runtime/api.py
@app.post("/games/{game_id}/move")
async def move(game_id: str, req: MoveRequest):
    entry = registry.get_game(game_id)
    runtime = entry.runtime  # Each game's own runtime!
```

---

## Next Steps

1. **Approval**: Review this plan
2. **Implementation**: Follow phases 1-6 sequentially
3. **Testing**: Run all golden tests (shopping, support, restaurant)
4. **Documentation**: Update README with working capability examples
5. **Tag release**: v1.0-alpha-per-game-capabilities

**Question for review**: Should we make this part of v1.0 or defer to v1.1?
