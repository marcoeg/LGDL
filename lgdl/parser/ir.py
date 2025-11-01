import re
from typing import Dict, Any, Set
from .ast import Game, Move

LEVELS = {"low":0.2, "medium":0.5, "high":0.8, "critical":0.95, "adaptive":0.7}

def _to_threshold(conf: Dict[str, Any]) -> float:
    if conf.get("kind") == "numeric":
        return float(conf.get("value", 0.75))
    if conf.get("kind") == "level":
        return float(conf.get("numeric", LEVELS.get(conf.get("value"), 0.7)))
    return 0.75

def compile_regex(pat: str) -> re.Pattern:
    rx = pat
    rx = rx.replace("*", ".*")
    rx = re.sub(r"\{([A-Za-z_][A-Za-z0-9_\.]*)(\?)?\}", r"(?P<\1>.+)", rx)
    return re.compile(rx, re.I)

def compile_game(game: Game) -> Dict[str, Any]:
    moves = []
    for mv in game.moves:
        moves.append(compile_move(mv))

    # Compile vocabulary to Dict[str, List[str]] for runtime matching
    vocabulary = {}
    for entry in game.vocabulary:
        vocabulary[entry.term] = entry.synonyms

    return {
        "name": game.name,
        "description": game.description or "",  # Phase 1: context for LLM prompts
        "vocabulary": vocabulary,  # Phase 1: context-aware matching
        "moves": moves,
        "capabilities": []
    }

def compile_move(mv: Move) -> Dict[str, Any]:
    trigz = []
    for t in mv.triggers:
        pats = []
        for p in t.patterns:
            pats.append({
                "text": p.text,
                "mods": p.modifiers,
                "regex": compile_regex(p.text)
            })
        trigz.append({"participant": t.participant, "patterns": pats})

    blocks = []
    slot_prompts = {}  # Map slot names to their prompts
    slot_conditions = {}  # Map condition types to actions

    for b in mv.blocks:
        # Extract slot-specific conditions for easier runtime access
        if b.kind == "when" and isinstance(b.condition, dict):
            if b.condition.get("special") == "slot_missing":
                slot_name = b.condition.get("slot")
                # Extract prompt from actions
                for action in b.actions:
                    if action.type == "respond" and action.data.get("kind") == "prompt_slot":
                        slot_prompts[slot_name] = action.data.get("text")
            elif b.condition.get("special") == "all_slots_filled":
                slot_conditions["all_slots_filled"] = [a.__dict__ for a in b.actions]

        if b.kind == "if_chain":
            chain = []
            for link in b.condition.get("chain", []):
                chain.append({
                    "condition": link.get("condition"),
                    "actions": [a.__dict__ for a in link.get("actions", [])]
                })
            blocks.append({"kind": "if_chain", "chain": chain})
        else:
            blocks.append({
                "kind": b.kind,
                "condition": b.condition,
                "actions": [a.__dict__ for a in b.actions]
            })

    # Compile slots if present
    compiled_slots = None
    if mv.slots is not None and mv.slots.slots:
        compiled_slots = {}
        for slot_def in mv.slots.slots:
            slot_data = {
                "type": slot_def.slot_type,
                "required": slot_def.required,
                "default": slot_def.default
            }
            if slot_def.slot_type == "range":
                # Note: Range bounds are inclusive (min <= value <= max)
                slot_data["min"] = slot_def.min_value
                slot_data["max"] = slot_def.max_value
            elif slot_def.slot_type == "enum":
                slot_data["enum_values"] = slot_def.enum_values
            compiled_slots[slot_def.name] = slot_data

    result = {
        "id": mv.name,
        "threshold": _to_threshold(mv.confidence),
        "triggers": trigz,
        "blocks": blocks
    }

    # Add slots to IR if present
    if compiled_slots:
        result["slots"] = compiled_slots
        result["slot_prompts"] = slot_prompts
        result["slot_conditions"] = slot_conditions

    return result

def extract_capability_allowlist(compiled_ir: Dict[str, Any]) -> Set[str]:
    """
    Extract all capability functions from compiled IR.

    This function traverses the compiled IR and collects all unique capability
    function names that are called across all moves. This allowlist can be used
    to configure a PolicyGuard for per-game capability authorization.

    Args:
        compiled_ir: Compiled game IR (output of compile_game)

    Returns:
        Set of allowed function names (e.g., {"search_products", "add_item"})

    Example:
        >>> ir = compile_game(game)
        >>> allowlist = extract_capability_allowlist(ir)
        >>> allowlist
        {'search_products', 'get_price', 'add_item', 'process_payment'}
    """
    allowlist = set()

    for move in compiled_ir.get("moves", []):
        for block in move.get("blocks", []):
            # Handle regular blocks (when, if_uncertain)
            if block.get("kind") != "if_chain":
                for action in block.get("actions", []):
                    if action.get("type") == "capability":
                        call = action.get("data", {}).get("call", {})
                        function = call.get("function")
                        if function:
                            allowlist.add(function)
            else:
                # Handle if_chain blocks
                for link in block.get("chain", []):
                    for action in link.get("actions", []):
                        if action.get("type") == "capability":
                            call = action.get("data", {}).get("call", {})
                            function = call.get("function")
                            if function:
                                allowlist.add(function)

    return allowlist
