# v1.0 Slot-Filling Implementation Plan

**Status**: Planning phase (2025-10-30)
**Prerequisites**: v1.0-beta complete (state management, context enrichment)
**Duration**: 2-3 weeks
**Effort**: ~800 lines of code, 15-20 tests

---

## Current State Analysis

### ✅ Completed (v1.0-beta)
- State management with SQLite backend (196 tests passing)
- Turn history persistence (<10ms latency)
- Context enrichment infrastructure
- ResponseParser for question detection
- Multi-turn conversation state tracking
- 100% backward compatibility

### ⚠️ Current Limitation
- Medical example has game design limitation (all patterns in one move)
- Users see repeated questions (enriched input routes back to same move)
- **Root cause**: No slot-filling mechanism to manage progressive information gathering

### 📋 DESIGN.md Status
- Line 209: "Advanced State" moved from "Out of Scope" to **IMPLEMENTED** in v1.0-beta
- Next evolution: Slot-filling for structured multi-turn conversations

---

## Overview

Implement declarative slot-filling to enable proper multi-turn information gathering. This allows moves to define required/optional information slots, automatically prompt for missing data, validate responses, and only execute capabilities when all required slots are filled.

**Example syntax**:
```lgdl
move pain_assessment {
  slots {
    location: string required
    severity: range(1, 10) required
    onset: timeframe optional
  }

  when slot location is missing {
    ask: "Where does it hurt?"
  }

  when all_slots_filled {
    medical.assess_pain(location, severity, onset)
  }
}
```

---

## Phase Breakdown

### Phase 1: Grammar Extension (Week 1, Days 1-2)

**Files**: `lgdl/spec/grammar_v0_1.lark`

**Add slot syntax to LGDL grammar**:

**Tasks**:
- [ ] Add `slots` block to move grammar
- [ ] Define slot types: `string`, `number`, `range(min,max)`, `enum`, `timeframe`, `date`
- [ ] Add modifiers: `required`, `optional`, `default`
- [ ] Add slot conditions: `when slot X is missing`, `when all_slots_filled`
- [ ] Update parser tests (5-10 new tests)

**Grammar additions**:
```ebnf
move_block: "move" IDENTIFIER "{" move_content* "}"

move_content: triggers
            | confidence
            | slots_block        // NEW
            | conditional_block
            | action

slots_block: "slots" "{" slot_definition+ "}"  // NEW

slot_definition: IDENTIFIER ":" slot_type slot_modifier*  // NEW

slot_type: "string"
         | "number"
         | "range" "(" NUMBER "," NUMBER ")"
         | "enum" "(" string_list ")"
         | "timeframe"
         | "date"

slot_modifier: "required" | "optional" | "default" "(" value ")"

conditional_block: slot_condition | confidence_condition | ...

slot_condition: "when" "slot" IDENTIFIER "is" "missing" "{" action+ "}"  // NEW
              | "when" "all_slots_filled" "{" action+ "}"                // NEW
```

**Deliverable**: Extended grammar parses slot definitions (~100 lines)

---

### Phase 2: IR Compilation (Week 1, Days 3-4)

**Files**: `lgdl/parser/ir.py`, `lgdl/parser/ast.py`

**Compile slots to IR format**:
```python
{
  "move_id": "pain_assessment",
  "slots": {
    "location": {
      "type": "string",
      "required": True,
      "default": None
    },
    "severity": {
      "type": "range",
      "min": 1,
      "max": 10,
      "required": True
    },
    "onset": {
      "type": "timeframe",
      "required": False
    }
  },
  "slot_prompts": {
    "location": "Where does it hurt?",
    "severity": "On a scale of 1-10, how severe is the pain?"
  },
  "slot_conditions": {
    "all_slots_filled": [
      {
        "type": "respond",
        "data": {"text": "Thank you..."}
      },
      {
        "type": "capability",
        "data": {...}
      }
    ]
  }
}
```

**Tasks**:
- [ ] Extend AST with `SlotBlock`, `SlotDefinition` classes
- [ ] Compile slot blocks to IR in `compile_move()`
- [ ] Store slot metadata (types, constraints, prompts)
- [ ] Compile slot conditions (`slot_missing`, `all_slots_filled`)
- [ ] Add IR validation for slot definitions
- [ ] Update existing IR tests

**Deliverable**: Slot definitions in compiled IR (~150 lines)

---

### Phase 3: Slot Manager (Week 1-2, Days 5-7)

**Files**: `lgdl/runtime/slots.py` (new)

**Core slot-filling logic**:
```python
from typing import Dict, Any, List, Optional, Tuple
from .state import PersistentState

class SlotManager:
    """Manages slot-filling for multi-turn conversations"""

    def get_missing_slots(
        self,
        move: dict,
        state: PersistentState
    ) -> List[str]:
        """Return list of required slots not yet filled"""

    def validate_slot_value(
        self,
        slot_def: dict,
        value: Any
    ) -> Tuple[bool, Any]:
        """Validate and coerce value against slot type constraints

        Returns: (is_valid, coerced_value)
        """

    def extract_slot_from_input(
        self,
        input: str,
        slot_type: str,
        context: dict
    ) -> Optional[Any]:
        """Extract slot value from user input using pattern matching

        Integrates with context enrichment for entity extraction
        """

    def fill_slot(
        self,
        conversation_id: str,
        move_id: str,
        slot_name: str,
        value: Any
    ) -> bool:
        """Store filled slot value in conversation state

        Returns: True if value was valid and stored
        """

    def all_required_filled(
        self,
        move: dict,
        state: PersistentState
    ) -> bool:
        """Check if all required slots are filled"""

    def get_slot_values(
        self,
        move_id: str,
        state: PersistentState
    ) -> Dict[str, Any]:
        """Get all filled slot values for a move"""

    def clear_slots(
        self,
        conversation_id: str,
        move_id: str
    ):
        """Clear all slots for a move (when move completes)"""
```

**Slot storage in PersistentState**:
```python
# Add to lgdl/runtime/state.py
class PersistentState:
    # ... existing fields ...

    slot_values: Dict[str, Dict[str, Any]]  # NEW: {move_id: {slot_name: value}}
```

**Tasks**:
- [ ] Implement SlotManager class
- [ ] Track filled/missing slots per conversation per move
- [ ] Validate slot values against type constraints
- [ ] Extract slot values from user input (integrate with context enrichment)
- [ ] Store slot values in conversation state
- [ ] Check if all required slots filled
- [ ] Unit tests for slot validation (10 tests)

**Deliverable**: Slot management with validation (~250 lines, 10 tests)

---

### Phase 4: Engine Integration (Week 2, Days 8-10)

**Files**: `lgdl/runtime/engine.py` (modify)

**Update `process_turn()` flow**:
```python
async def process_turn(self, conversation_id: str, user_id: str, text: str, context: Dict[str, Any]):
    # ... existing sanitization, enrichment, matching logic ...

    match = self.matcher.match(input_for_matching, self.compiled)
    if not match["move"]:
        return {"move_id": "none", ...}

    mv = match["move"]
    score = match["score"]
    params = match["params"]

    # Load conversation state
    state = None
    if self.state_manager:
        state = await self.state_manager.get_or_create(conversation_id)

    # NEW: Slot-filling logic
    if "slots" in mv and self.slot_manager and state:
        # Check for missing required slots
        missing = self.slot_manager.get_missing_slots(mv, state)

        if missing:
            # Get prompt for first missing slot
            slot_name = missing[0]
            prompt = mv["slot_prompts"].get(slot_name, f"Please provide {slot_name}")

            # Mark state as awaiting slot
            state.awaiting_slot = slot_name
            state.awaiting_slot_move = mv["id"]
            await self.state_manager.persistent_storage.save_conversation(state)

            return {
                "move_id": mv["id"],
                "confidence": score,
                "response": prompt,
                "awaiting_slot": slot_name,
                "manifest_id": str(uuid.uuid4())
            }

        # Try to extract slots from current input
        for slot_name, slot_def in mv["slots"].items():
            value = self.slot_manager.extract_slot_from_input(
                cleaned,
                slot_def["type"],
                params
            )
            if value is not None:
                is_valid, coerced = self.slot_manager.validate_slot_value(slot_def, value)
                if is_valid:
                    self.slot_manager.fill_slot(conversation_id, mv["id"], slot_name, coerced)

        # Check if all required slots are now filled
        if self.slot_manager.all_required_filled(mv, state):
            # Get filled slot values
            slot_values = self.slot_manager.get_slot_values(mv["id"], state)
            params.update(slot_values)

            # Execute all_slots_filled actions
            response_acc = ""
            action_out = None
            if "all_slots_filled" in mv.get("slot_conditions", {}):
                for action in mv["slot_conditions"]["all_slots_filled"]:
                    r, action_out, last_status = await self._exec_action(action, params)
                    if r:
                        response_acc += ("" if not response_acc else " ") + r

            # Clear slots after successful execution
            self.slot_manager.clear_slots(conversation_id, mv["id"])

            return {
                "move_id": mv["id"],
                "confidence": score,
                "response": response_acc,
                "action": action_out,
                "slots_filled": slot_values,
                "manifest_id": str(uuid.uuid4())
            }

    # ... existing conditional block execution for non-slot moves ...
```

**Tasks**:
- [ ] Add SlotManager to LGDLRuntime initialization
- [ ] Check for missing slots before executing capabilities
- [ ] Prompt for missing slots (integrate with ResponseParser)
- [ ] Extract slot values from user input
- [ ] Execute `all_slots_filled` actions when ready
- [ ] Clear slot state when move completes
- [ ] Update state persistence to store slot values
- [ ] Add slot-related fields to response manifest

**Deliverable**: Slot-filling integrated into runtime (~200 lines)

---

### Phase 5: Medical Example Update (Week 2-3, Days 11-12)

**Files**: `examples/medical/game.lgdl`

**Rewrite `pain_assessment` with slots**:
```lgdl
move pain_assessment {
  slots {
    location: string required
    severity: range(1, 10) required
    onset: timeframe required
    characteristics: string optional
  }

  when user says something like: [
    "I'm in pain" (fuzzy),
    "pain in {location}",
    "pain level {severity}",
    "started {onset} ago"
  ]
  confidence: medium

  when slot location is missing {
    ask: "Where does it hurt?"
  }

  when slot severity is missing {
    ask: "On a scale of 1-10, how severe is the pain?"
  }

  when slot onset is missing {
    ask: "When did this pain start?"
  }

  when all_slots_filled {
    respond with: "Thank you. I understand you have {severity}/10 pain in your {location} that started {onset}. Let me assess the urgency."
    medical.assess_pain(location, severity, onset, characteristics) for "pain assessment" timeout 3
  }

  when successful {
    respond with: "Based on your symptoms, urgency level is {urgency}. Estimated wait time: {wait_time} minutes."
  }

  when failed {
    respond with: "I'm having trouble assessing your pain. Let me connect you with a nurse."
    escalate to: nurse
  }
}
```

**Tasks**:
- [ ] Update `pain_assessment` with slot definitions
- [ ] Remove duplicate patterns (slots handle extraction now)
- [ ] Add slot prompts for missing information
- [ ] Simplify conditional blocks (slot logic replaces manual tracking)
- [ ] Update `golden_dialogs.yaml` with multi-turn slot-filling tests
- [ ] Add test cases for progressive slot filling
- [ ] Verify medical example works end-to-end

**Golden dialog example**:
```yaml
- name: multi_turn_slot_filling
  turns:
    - input: "I'm in pain"
      expect:
        move: pain_assessment
        awaiting_slot: location
        response_contains: ["Where does it hurt"]

    - input: "My chest"
      expect:
        move: pain_assessment
        awaiting_slot: severity
        response_contains: ["scale of 1-10"]

    - input: "8 out of 10"
      expect:
        move: pain_assessment
        awaiting_slot: onset
        response_contains: ["When did this start"]

    - input: "About an hour ago"
      expect:
        move: pain_assessment
        slots_filled: {location: "chest", severity: 8, onset: "1 hour"}
        response_contains: ["8/10 pain", "chest", "hour"]
```

**Deliverable**: Medical example demonstrates slot-filling (~100 lines changed)

---

### Phase 6: Testing (Week 3, Days 13-15)

**Files**: `tests/test_slots.py` (new), `tests/test_slot_integration.py` (new)

**Test coverage (15-20 tests)**:

#### `tests/test_slots.py` - Unit tests
- [ ] `test_slot_extraction_from_patterns` - Extract slot values from input
- [ ] `test_slot_validation_string` - Validate string slots
- [ ] `test_slot_validation_number` - Validate number slots
- [ ] `test_slot_validation_range` - Validate range constraints
- [ ] `test_slot_validation_enum` - Validate enum values
- [ ] `test_slot_validation_timeframe` - Validate timeframe parsing
- [ ] `test_missing_slot_detection` - Detect unfilled required slots
- [ ] `test_all_slots_filled` - Check completion status
- [ ] `test_slot_storage` - Store/retrieve slot values from state
- [ ] `test_slot_clearing` - Clear slots after move completes

#### `tests/test_slot_integration.py` - Integration tests
- [ ] `test_single_turn_slot_filling` - All slots filled in one turn
- [ ] `test_multi_turn_progressive_filling` - Fill slots across multiple turns
- [ ] `test_slot_prompting_flow` - Verify prompts for missing slots
- [ ] `test_all_slots_filled_execution` - Execute actions when complete
- [ ] `test_slot_validation_rejection` - Reject invalid slot values
- [ ] `test_optional_slots` - Handle optional slots correctly
- [ ] `test_context_enrichment_with_slots` - Slots + enrichment integration
- [ ] `test_slot_extraction_with_patterns` - Pattern variable → slot filling
- [ ] `test_backward_compatibility` - Moves without slots still work
- [ ] `test_concurrent_slot_filling` - Multiple conversations with slots

**Deliverable**: 15-20 tests covering slot-filling (~150 lines)

---

## Success Criteria

### Technical
- ✅ Grammar extension supports slot definitions
- ✅ Slots compile to IR correctly
- ✅ SlotManager tracks and validates slots
- ✅ Engine prompts for missing slots automatically
- ✅ Capabilities execute only when all required slots filled
- ✅ Medical example demonstrates complete multi-turn flow
- ✅ 15-20 new tests passing
- ✅ All existing 178 tests still pass

### User Experience
- ✅ No repeated questions (proper slot-based flow)
- ✅ Natural progressive information gathering
- ✅ Type-safe slot validation
- ✅ Clear prompts for missing information
- ✅ Context-aware slot extraction

---

## Estimated Effort

**Total: ~800 lines of code, 15-20 tests, 2-3 weeks**

| Phase | Lines | Tests | Duration |
|-------|-------|-------|----------|
| 1. Grammar Extension | ~100 | 5-10 | 2 days |
| 2. IR Compilation | ~150 | 0 | 2 days |
| 3. Slot Manager | ~250 | 10 | 3 days |
| 4. Engine Integration | ~200 | 0 | 3 days |
| 5. Medical Example | ~100 | 0 | 2 days |
| 6. Integration Tests | ~150 | 5-10 | 3 days |
| **Total** | **~950** | **20-30** | **15 days** |

---

## Dependencies

### Prerequisites
- ✅ v1.0-beta state management complete
- ✅ Context enrichment working
- ✅ ResponseParser implemented
- ✅ Turn history persistence

### No Blockers
All required infrastructure is in place. Slot-filling builds on top of existing state management without requiring changes to core infrastructure.

---

## Risk Mitigation

1. **Grammar compatibility**: Slots are additive, existing games work unchanged
2. **State persistence**: Leverage v1.0-beta's existing state infrastructure
3. **Backward compatibility**: Moves without slots work exactly as before
4. **Testing**: Extensive unit + integration tests before medical example update
5. **Rollout**: Can be feature-flagged if needed

---

## Next Steps After Slot-Filling

Once slot-filling is complete, proceed with production hardening (V1_ROADMAP.md lines 425-530):

1. **Production Storage Backends** (~300 lines, 1 week)
   - Redis for ephemeral state
   - PostgreSQL for persistent history
   - Migration tooling from SQLite

2. **Performance Optimization** (~200 lines, 1 week)
   - Pattern cache warming
   - Connection pooling
   - Batch state operations
   - P95/P99 latency monitoring

3. **Production Safety** (~300 lines, 1 week)
   - Rate limiting
   - Circuit breakers
   - TTL enforcement
   - Graceful degradation

4. **Monitoring & Observability** (~400 lines, 1 week)
   - Metrics collection
   - Prometheus/CloudWatch exporters
   - Grafana dashboards

5. **Load Testing** (~2 days)
   - Locust scripts
   - 100+ concurrent conversations
   - <500ms P95 latency target

6. **Security Hardening** (~1 week)
   - State encryption
   - PII redaction
   - GDPR compliance

7. **Documentation** (~1 week)
   - Deployment guides
   - Monitoring runbooks
   - API migration guide

**Total to v1.0 production**: 8-10 weeks from now

---

## Open Questions

1. **Slot extraction sophistication**: Should we use LLM for entity extraction or rely on pattern matching + context enrichment?
   - **Recommendation**: Start with pattern matching, add LLM extraction as optional enhancement

2. **Slot persistence**: How long should slot values persist after move completion?
   - **Recommendation**: Clear on move completion, optionally store in extracted_context for reference

3. **Nested slots**: Do we need support for complex/nested slot types?
   - **Recommendation**: Not for v1.0, add in v1.1 if needed

4. **Slot inheritance**: Should slots be inheritable across moves?
   - **Recommendation**: No, keep slots per-move for simplicity

---

## References

- **V1_ROADMAP.md**: Lines 390-423 (slot-filling specification)
- **DESIGN.md**: Line 209 (state management scope)
- **examples/medical/game.lgdl**: Current pain_assessment implementation
- **lgdl/runtime/state.py**: Existing state management infrastructure
