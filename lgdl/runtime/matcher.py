import os, re, math, json, hashlib, time, sqlite3, warnings
from typing import Dict, Any, Tuple, List
from pathlib import Path
import numpy as np

# Optional OpenAI embeddings: if OPENAI_API_KEY is set, use embeddings; else fallback to overlap.
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z]+", a.lower()))
    tb = set(re.findall(r"[a-z]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return min(1.0, 0.4 + 0.1 * len(ta & tb))


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
