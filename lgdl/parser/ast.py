from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Pattern:
    text: str
    modifiers: List[str] = field(default_factory=list)

@dataclass
class Trigger:
    participant: str
    patterns: List[Pattern]

@dataclass
class Action:
    type: str
    data: Dict[str, Any]

@dataclass
class Block:
    kind: str  # "when" | "if_chain"
    condition: Dict[str, Any]
    actions: List[Action]

@dataclass
class Move:
    name: str
    triggers: List[Trigger] = field(default_factory=list)
    confidence: Dict[str, Any] = field(default_factory=lambda: {"kind": "numeric", "value": 0.75})
    blocks: List[Block] = field(default_factory=list)

@dataclass
class Capability:
    name: str
    functions: List[str] | str

@dataclass
class Game:
    name: str
    description: Optional[str] = None
    capabilities: Dict[str, Capability] = field(default_factory=dict)
    moves: List[Move] = field(default_factory=list)
