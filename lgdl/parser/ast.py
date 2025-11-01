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
class SlotDefinition:
    """Definition of a single slot in a move"""
    name: str
    slot_type: str  # "string" | "number" | "range" | "enum" | "timeframe" | "date"
    required: bool = True
    optional: bool = False
    default: Any = None
    # For range type
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    # For enum type
    enum_values: List[str] = field(default_factory=list)

@dataclass
class SlotBlock:
    """Container for slot definitions in a move"""
    slots: List[SlotDefinition] = field(default_factory=list)

@dataclass
class Move:
    name: str
    triggers: List[Trigger] = field(default_factory=list)
    confidence: Dict[str, Any] = field(default_factory=lambda: {"kind": "numeric", "value": 0.75})
    blocks: List[Block] = field(default_factory=list)
    slots: Optional[SlotBlock] = None

@dataclass
class Capability:
    name: str
    functions: List[str] | str

@dataclass
class VocabularyEntry:
    """Single vocabulary entry mapping a term to its synonyms.

    Example:
        VocabularyEntry(term="heart", synonyms=["ticker", "chest", "cardiovascular"])
    """
    term: str
    synonyms: List[str] = field(default_factory=list)

@dataclass
class Game:
    name: str
    description: Optional[str] = None
    vocabulary: List[VocabularyEntry] = field(default_factory=list)  # Phase 1: context-aware matching
    capabilities: Dict[str, Capability] = field(default_factory=dict)
    moves: List[Move] = field(default_factory=list)
