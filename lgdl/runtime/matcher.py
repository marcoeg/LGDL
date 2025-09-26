import os, re, math, json, hashlib, time
from typing import Dict, Any, Tuple, List

# Optional OpenAI embeddings: if OPENAI_API_KEY is set, use embeddings; else fallback to overlap.
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z]+", a.lower()))
    tb = set(re.findall(r"[a-z]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return min(1.0, 0.4 + 0.1 * len(ta & tb))

class EmbeddingClient:
    def __init__(self):
        self.cache: Dict[str, List[float]] = {}
        self.model = "text-embedding-3-small"
        self.enabled = USE_OPENAI
        if self.enabled:
            try:
                from openai import OpenAI
                self.client = OpenAI()
            except Exception:
                self.enabled = False

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> List[float]:
        k = self._key(text)
        if k in self.cache:
            return self.cache[k]
        if not self.enabled:
            # Fallback deterministic pseudo-embedding: bag-of-letters freq
            vec = [0]*26
            for ch in re.findall(r"[a-z]", text.lower()):
                vec[ord(ch)-97] += 1
            norm = math.sqrt(sum(v*v for v in vec)) or 1.0
            vec = [v/norm for v in vec]
            self.cache[k] = vec
            return vec
        # Real OpenAI embeddings
        try:
            res = self.client.embeddings.create(model=self.model, input=[text])
            vec = res.data[0].embedding
            self.cache[k] = vec
            return vec
        except Exception:
            # Fail closed to fallback
            self.enabled = False
            return self.embed(text)

def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a)) or 1.0
    nb = math.sqrt(sum(y*y for y in b)) or 1.0
    return max(0.0, min(1.0, dot/(na*nb)))

class TwoStageMatcher:
    HIGH_EXIT = 0.90

    def __init__(self):
        self.emb = EmbeddingClient()

    def _apply_patterns(self, text: str, move: Dict[str, Any]) -> Tuple[float, Dict[str, Any], str]:
        best = (0.0, {}, "")
        for trig in move["triggers"]:
            if trig["participant"] not in ("user","assistant"):
                continue
            for pat in trig["patterns"]:
                m = pat["regex"].search(text)
                if not m:
                    continue
                params = {k: (v.strip() if v else v) for k, v in m.groupdict().items()}
                base = 0.75 if m else 0.0
                # semantic via embeddings (or fallback overlap)
                if self.emb.enabled:
                    sim = cosine(self.emb.embed(text), self.emb.embed(pat["text"]))
                    sem = min(1.0, 0.4 + 0.6 * sim)
                else:
                    sem = token_overlap(text, pat["text"])
                mods = pat.get("mods", [])
                if "strict" in mods:
                    score = max(0.92, sem)
                elif "fuzzy" in mods:
                    score = sem
                else:
                    score = max(base, 0.7*sem + 0.3*base)
                if score > best[0]:
                    best = (score, params, pat["text"])
        return best

    def match(self, text: str, compiled_game: Dict[str, Any]) -> Dict[str, Any]:
        best = None
        for mv in compiled_game["moves"]:
            score, params, pat_text = self._apply_patterns(text, mv)
            if score == 0:
                continue
            if score >= self.High_EXIT if False else False:  # keep constant case safe
                pass
            if score >= self.HIGH_EXIT:
                return {"move": mv, "score": score, "params": params}
            if not best or score > best["score"]:
                best = {"move": mv, "score": score, "params": params}
        return best or {"move": None, "score": 0.0, "params": {}}
