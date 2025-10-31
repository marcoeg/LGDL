from lark import Lark, Transformer, Token
from pathlib import Path
from typing import List
from .ast import Game, Move, Trigger, Pattern, Block, Action, Capability, SlotBlock, SlotDefinition

GRAMMAR_PATH = Path(__file__).resolve().parents[1] / "spec" / "grammar_v0_1.lark"

CONF_LEVELS = {"low":0.2, "medium":0.5, "high":0.8, "critical":0.95, "adaptive":0.7}

def _strip_quotes(s: str) -> str:
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if (s.startswith('"""') and s.endswith('"""')) or (s.startswith(") and s.endswith(")):
        return s[3:-3]
    return s

class ToAST(Transformer):
    def start(self, items):
        return items[0] if items else None

    def program(self, items):
        return [i for i in items if isinstance(i, Game)]

    def game_def(self, items):
        name = items[0].value if isinstance(items[0], Token) else str(items[0])
        body = items[-1]
        return Game(
            name=name,
            description=body.get("description"),
            capabilities=body.get("capabilities", {}),
            moves=body.get("moves", [])
        )

    def game_body(self, items):
        out = {"moves": []}
        for it in items:
            if isinstance(it, dict) and "capabilities" in it:
                out["capabilities"] = it["capabilities"]
            elif isinstance(it, list):  # moves
                out["moves"] = it
            elif isinstance(it, str):   # description
                out["description"] = it
        return out

    def description_section(self, items):
        return _strip_quotes(items[0])

    def capabilities_section(self, items):
        caps = {}
        for c in items:
            if isinstance(c, Capability):
                caps[c.name] = c
        return {"capabilities": caps}

    def capability(self, items):
        name = items[0].value
        spec = items[1]
        return Capability(name=name, functions=spec)

    def capability_spec(self, items):
        if not items:
            return []
        val = items[0]
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return _strip_quotes(val)
        return _strip_quotes(getattr(val, "value", str(val)))

    def func_list(self, items):
        return items

    def func_name(self, items):
        tok = items[0]
        val = tok.value if hasattr(tok, "value") else str(tok)
        return _strip_quotes(val)

    def moves_section(self, items):
        return [m for m in items if isinstance(m, Move)]

    def move_def(self, items):
        name = items[0].value
        triggers: List[Trigger] = []
        blocks: List[Block] = []
        confidence = {"kind":"numeric","value":0.75}
        slots: SlotBlock = None
        for it in items[1:]:
            if isinstance(it, Trigger):
                triggers.append(it)
            elif isinstance(it, Block):
                blocks.append(it)
            elif isinstance(it, SlotBlock):
                slots = it
            elif isinstance(it, dict) and it.get("confidence") is not None:
                confidence = it["confidence"]
        return Move(name=name, triggers=triggers, blocks=blocks, confidence=confidence, slots=slots)

    def move_elem(self, items):
        return items[0] if items else None

    def action(self, items):
        return items[0] if items else None

    def trigger_clause(self, items):
        participant = items[0].value if hasattr(items[0], "value") else str(items[0])
        plist = items[1]
        return Trigger(participant=participant, patterns=plist)

    def participant(self, items):
        if not items:
            return ""
        tok = items[0]
        return tok.value if hasattr(tok, "value") else str(tok)

    def pattern_spec_list(self, items):
        return items

    def pattern_spec(self, items):
        text = _strip_quotes(items[0])
        mods = []
        if len(items) > 1:
            mods = [m for m in items[1] if isinstance(m, str)]
        return Pattern(text=text, modifiers=mods)

    def pattern(self, items):
        tok = items[0]
        val = tok.value if hasattr(tok, "value") else str(tok)
        return _strip_quotes(val)

    def modifier_list(self, items):
        return [m.value if hasattr(m, "value") else str(m) for m in items]

    def confidence_clause(self, items):
        v = items[0]
        if isinstance(v, (int, float)):
            return {"confidence":{"kind":"numeric","value": float(v)}}
        key = str(v)
        return {"confidence":{"kind":"level","value": key, "numeric": CONF_LEVELS.get(key, 0.7)}}

    def confidence_expr(self, items):
        if not items:
            return ""
        tok = items[0]
        if hasattr(tok, "type") and tok.type == "NUMBER":
            return float(tok.value)
        return tok.value if hasattr(tok, "value") else str(tok)

    def slots_block(self, items):
        """Parse slots block: slots { ... }"""
        slots = [s for s in items if isinstance(s, SlotDefinition)]
        return SlotBlock(slots=slots)

    def slot_definition(self, items):
        """Parse slot definition: name: type required"""
        name = items[0].value if hasattr(items[0], "value") else str(items[0])
        slot_type_data = items[1]  # dict with type info

        # Extract modifiers
        required = True
        optional = False
        default = None

        for mod in items[2:]:
            if isinstance(mod, dict):
                if mod.get("modifier") == "required":
                    required = True
                    optional = False
                elif mod.get("modifier") == "optional":
                    required = False
                    optional = True
                elif mod.get("modifier") == "default":
                    default = mod.get("value")

        return SlotDefinition(
            name=name,
            slot_type=slot_type_data.get("type"),
            required=required,
            optional=optional,
            default=default,
            min_value=slot_type_data.get("min"),
            max_value=slot_type_data.get("max"),
            enum_values=slot_type_data.get("enum_values", [])
        )

    def slot_type(self, items):
        """Parse slot type: SLOT_TYPE_SIMPLE"""
        if not items:
            return {"type": "string"}

        first = items[0]
        type_name = first.value if hasattr(first, "value") else str(first)
        return {"type": type_name}

    def slot_type_range(self, items):
        """Parse range type: range(min, max)"""
        min_val = float(items[0].value) if hasattr(items[0], "value") else float(items[0])
        max_val = float(items[1].value) if hasattr(items[1], "value") else float(items[1])
        return {"type": "range", "min": min_val, "max": max_val}

    def slot_type_enum(self, items):
        """Parse enum type: enum(val1, val2, ...)"""
        enum_vals = items[0] if isinstance(items[0], list) else []
        return {"type": "enum", "enum_values": enum_vals}

    def slot_modifier(self, items):
        """Parse slot modifier: SLOT_MOD_SIMPLE"""
        if not items:
            return {"modifier": "required"}

        first = items[0]
        mod_name = first.value if hasattr(first, "value") else str(first)
        return {"modifier": mod_name}

    def slot_modifier_default(self, items):
        """Parse default modifier: default(value)"""
        return {"modifier": "default", "value": items[0]}

    def slot_is_missing(self, items):
        """Parse: slot location is missing"""
        slot_name = items[0].value if hasattr(items[0], "value") else str(items[0])
        return {"special": "slot_missing", "slot": slot_name}

    def all_slots_filled(self, items):
        """Parse: all_slots_filled"""
        return {"special": "all_slots_filled"}

    def when_block(self, items):
        cond = items[0]
        actions = [a for a in items[1:] if isinstance(a, Action)]
        return Block(kind="when", condition=cond, actions=actions)

    def if_block(self, items):
        chain = []
        current = {"condition": None, "actions": []}
        for x in items:
            if isinstance(x, dict) and ( "op" in x or "special" in x or "ref" in x or "cmp" in x ):
                if current["condition"] is not None:
                    chain.append(current)
                    current = {"condition": x, "actions": []}
                else:
                    current["condition"] = x
            elif isinstance(x, Action):
                current["actions"].append(x)
        if current["condition"] is not None:
            chain.append(current)
        return Block(kind="if_chain", condition={"chain": chain}, actions=[])

    def condition(self, items):
        if len(items)==1:
            return items[0]
        if len(items)==3 and hasattr(items[1], "type") and items[1].type == "LOGICAL_OP":
            return {"op": items[1].value, "left": items[0], "right": items[2]}
        return items[0]

    def simple_condition(self, items):
        if len(items)==1:
            return items[0]
        if len(items)==2 and isinstance(items[0], str) and items[0]=="not":
            return {"not": items[1]}
        if len(items)==3 and hasattr(items[1], "type") and items[1].type == "COMPARATOR":
            return {"cmp": items[1].value, "lhs": items[0], "rhs": items[2]}
        return {"unknown": [str(i) for i in items]}

    def special_condition(self, items):
        if not items:
            return {"special": ""}
        tok = items[0]
        # If it's already a dict (from slot_condition), return it directly
        if isinstance(tok, dict):
            return tok
        text = tok.value if hasattr(tok, "value") else str(tok)
        if text == "confidence is below threshold":
            return {"special": "uncertain"}
        return {"special": text}

    def value_ref(self, items):
        return {"ref": ".".join([i.value for i in items])}

    def value(self, items):
        tok = items[0]
        if hasattr(tok, "type") and tok.type == "NUMBER":
            return float(tok.value)
        v = getattr(tok, "value", str(tok))
        v_low = v.lower()
        if v_low in ("true","false"):
            return v_low == "true"
        return _strip_quotes(v)

    def ask_clarification(self, items):
        text = items[-1]
        return Action(type="respond", data={"text": text, "kind": "clarify"})

    def prompt_slot(self, items):
        """Parse: prompt: "Where does it hurt?" """
        text = items[-1]
        return Action(type="respond", data={"text": text, "kind": "prompt_slot"})

    def respond_with(self, items):
        text = items[-1]
        return Action(type="respond", data={"text": text})

    def offer_choices(self, items):
        choices = items[-1] if items else []
        return Action(type="offer_choices", data={"choices": choices})

    def generate_response(self, items):
        style = None
        if items:
            val = items[-1]
            style = val if isinstance(val, str) else _strip_quotes(getattr(val, "value", str(val)))
        return Action(type="generate", data={"style": style})

    def string_list(self, items):
        out = []
        for it in items:
            if isinstance(it, str):
                out.append(_strip_quotes(it))
            elif hasattr(it, "value"):
                out.append(_strip_quotes(it.value))
            else:
                out.append(_strip_quotes(str(it)))
        return out

    def text_value(self, items):
        val = items[0]
        if isinstance(val, str):
            return _strip_quotes(val)
        if hasattr(val, "value"):
            return _strip_quotes(val.value)
        return _strip_quotes(str(val))

    def template_string(self, items):
        tok = items[0]
        return _strip_quotes(tok.value if hasattr(tok, "value") else str(tok))

    def capability_action(self, items):
        call = items[0]
        act = items[1] if len(items)>1 and isinstance(items[1], Action) else None
        data = {"call": call}
        if act: data["then"] = act
        return Action(type="capability", data=data)

    def capability_call(self, items):
        service = items[0].value
        func = items[1].value
        params = {"intent": None, "await": False, "timeout": None}
        if len(items)>2 and isinstance(items[2], dict):
            params.update(items[2])
        return {"service": service, "function": func, **params}

    def capability_params(self, items):
        out = {"intent": None, "await": False, "timeout": None}
        for it in items:
            if hasattr(it, "type") and it.type == "STRING":
                out["intent"] = _strip_quotes(it.value)
            elif hasattr(it, "type") and it.type == "NUMBER":
                out["timeout"] = float(it.value)
            elif getattr(it, "value", "") == "await":
                out["await"] = True
        return out

    def flow_action(self, items):
        head = items[0].value if hasattr(items[0],"value") else str(items[0])
        if head == "escalate":
            return Action(type="escalate", data={"to": items[-1].value})
        if head == "continue":
            return Action(type="continue", data={})
        if head == "retry":
            reason = None
            if len(items) > 1 and hasattr(items[-1], "value"):
                reason = items[-1].value
            return Action(type="retry", data={"reason": reason})
        if head == "delegate":
            return Action(type="delegate", data={"to": items[-1].value})
        if head == "return":
            return Action(type="return", data={})
        return Action(type="noop", data={})

    def negotiation_action(self, items):
        head = items[0].value if hasattr(items[0],"value") else str(items[0])
        if head == "negotiate":
            text = _strip_quotes(items[1].value if hasattr(items[1],"value") else items[1])
            cond = items[2]
            return Action(type="negotiate_until", data={"text": text, "until": cond})
        if head == "clarify":
            slot = items[1].value
            choices = [ _strip_quotes(x.value if hasattr(x,"value") else x) for x in items[-1] ]
            return Action(type="clarify_with_options", data={"slot": slot, "choices": choices})
        return Action(type="noop", data={})

def parse_lgdl(path: str) -> Game:
    parser = Lark(Path(GRAMMAR_PATH).read_text(), start="start", parser="lalr")
    tree = parser.parse(Path(path).read_text())
    games = ToAST().transform(tree)
    if isinstance(games, list) and games:
        return games[0]
    return games
