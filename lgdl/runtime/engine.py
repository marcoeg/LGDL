import uuid, re
from typing import Dict, Any
from pathlib import Path
from ..parser.parser import parse_lgdl
from ..parser.ir import compile_game
from .matcher import TwoStageMatcher
from .firewall import sanitize
from .policy import PolicyGuard
from .capability import CapabilityClient

def _subst_template(text: str, params: Dict[str, Any]) -> str:
    def repl(m):
        key = m.group(1)
        fallback = None
        if "?" in key:
            key, fallback = key.split("?",1)
        val = params.get(key)
        return str(val if val is not None and val != "" else (fallback or ""))
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_\.]*(\?[^\}]+)?)\}", repl, text)

def eval_condition(cond: Dict[str, Any], score: float, threshold: float, last_status: str, ctx: Dict[str, Any]) -> bool:
    if not cond:
        return False
    if "special" in cond:
        if cond["special"] == "confident":
            return score >= threshold
        if cond["special"] == "uncertain":
            return score < threshold
        if cond["special"] == "successful":
            return last_status == "ok"
        if cond["special"] == "failed":
            return last_status == "err"
    if "op" in cond and cond["op"] in ("and","or"):
        a = eval_condition(cond["left"], score, threshold, last_status, ctx)
        b = eval_condition(cond["right"], score, threshold, last_status, ctx)
        return (a and b) if cond["op"] == "and" else (a or b)
    if "cmp" in cond:
        lhs = ctx.get(cond["lhs"]["ref"], None) if isinstance(cond["lhs"], dict) and "ref" in cond["lhs"] else None
        rhs = cond["rhs"]
        cmp = cond["cmp"]
        try:
            if cmp == "=": return lhs == rhs
            if cmp == "!=": return lhs != rhs
            if cmp == ">": return lhs > rhs
            if cmp == "<": return lhs < rhs
            if cmp == ">=": return lhs >= rhs
            if cmp == "<=": return lhs <= rhs
        except Exception:
            return False
    if "ref" in cond:
        return bool(ctx.get(cond["ref"]))
    if "not" in cond:
        return not eval_condition(cond["not"], score, threshold, last_status, ctx)
    return False

class LGDLRuntime:
    def __init__(self, compiled):
        self.compiled = compiled
        self.matcher = TwoStageMatcher()
        self.policy = PolicyGuard(allowlist={"check_availability"})
        self.cap = CapabilityClient(str(Path(__file__).resolve().parents[2] / "examples" / "medical" / "capability_contract.json"))

    async def process_turn(self, conversation_id: str, user_id: str, text: str, context: Dict[str, Any]):
        cleaned, flagged = sanitize(text)
        match = self.matcher.match(cleaned, self.compiled)
        if not match["move"]:
            return {
                "move_id": "none",
                "confidence": 0.0,
                "response": "Sorry, I didn't catch that.",
                "action": None,
                "manifest_id": str(uuid.uuid4()),
                "firewall_triggered": flagged
            }
        mv = match["move"]
        score = match["score"]
        params = match["params"]
        threshold = mv["threshold"]
        last_status = "ok"

        response_acc = ""
        action_out = None

        for blk in mv["blocks"]:
            if blk["kind"] == "if_chain":
                for link in blk["chain"]:
                    cond = link["condition"]
                    if eval_condition(cond, score, threshold, last_status, params):
                        for act in link["actions"]:
                            r, action_out, last_status = await self._exec_action(act, params)
                            if r:
                                response_acc += ("" if not response_acc else " ") + r
                        break
                continue

            cond = blk.get("condition")
            if eval_condition(cond, score, threshold, last_status, params):
                for act in blk.get("actions", []):
                    r, action_out, last_status = await self._exec_action(act, params)
                    if r:
                        response_acc += ("" if not response_acc else " ") + r

        if not response_acc:
            response_acc = "OK."

        return {
            "move_id": mv["id"],
            "confidence": float(score),
            "response": response_acc,
            "action": action_out,
            "manifest_id": str(uuid.uuid4()),
            "firewall_triggered": flagged
        }

    async def _exec_action(self, action: Dict[str, Any], params: Dict[str, Any]):
        atype = action.get("type")
        data = action.get("data", {})
        status = "ok"
        if atype == "respond":
            return _subst_template(data.get("text",""), params), None, status
        if atype == "offer_choices":
            return "Options: " + ", ".join(data.get("choices", [])), None, status
        if atype == "capability":
            call = data.get("call", {})
            func = call.get("function")
            if not self.policy.allowed(func):
                return "Not allowed.", None, "err"
            payload = {}
            for k in ("doctor","date"):
                if k in params and params[k] is not None:
                    payload[k] = params[k]
            res = await self.cap.execute(f'{call.get("service")}.{func}', payload)
            return res.get("message",""), func, status
        if atype in ("continue","return"):
            return "", None, status
        if atype == "escalate":
            return "Escalating to " + data.get("to","human"), "escalate", status
        return "", None, status

def load_compiled_game(path: str):
    game = parse_lgdl(path)
    return compile_game(game)
