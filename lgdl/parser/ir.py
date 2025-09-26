import re
from typing import Dict, Any
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
    return {"name": game.name, "moves": moves, "capabilities": []}

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
    for b in mv.blocks:
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
    return {
        "id": mv.name,
        "threshold": _to_threshold(mv.confidence),
        "triggers": trigz,
        "blocks": blocks
    }
