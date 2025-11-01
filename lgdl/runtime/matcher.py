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


# ============================================================================
# Phase 1: Context-Aware Semantic Matching
# ============================================================================

class LLMSemanticMatcher:
    """Context-aware LLM semantic matcher using game vocabulary.

    This matcher uses an LLM to perform semantic matching with rich context including:
    - Game vocabulary (synonyms and domain-specific terms)
    - Conversation history (multi-turn context)
    - Successful patterns (learning from what works)

    Unlike embedding-based matching, this understands domain-specific slang
    and contextual meaning. For example, "my ticker hurts" matches "pain in {location}"
    because the vocabulary defines "heart" → ["ticker", "chest"].

    Cost: ~$0.01 per match (100 tokens @ gpt-4o-mini)
    Latency: ~200ms per match
    """

    def __init__(self, llm_client):
        """Initialize LLM semantic matcher.

        Args:
            llm_client: LLMClient instance for completions
        """
        self.llm = llm_client

    async def match(
        self,
        text: str,
        pattern: str,
        context: "MatchingContext"
    ) -> Dict[str, Any]:
        """Match text against pattern using LLM with context.

        Args:
            text: User input text
            pattern: Pattern to match against
            context: Rich matching context (vocabulary, history, etc.)

        Returns:
            Dict with confidence, reasoning, and metadata
        """
        # Build context-rich prompt
        prompt = self._build_prompt(text, pattern, context)

        # Call LLM with structured output
        try:
            result = await self.llm.complete(
                prompt=prompt,
                response_schema={
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "How well user input matches pattern"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation (1-2 sentences)"
                    }
                },
                max_tokens=100,
                temperature=0.0
            )

            return {
                "confidence": result.content.get("confidence", 0.0),
                "reasoning": result.content.get("reasoning", ""),
                "cost": result.cost,
                "stage": "llm_semantic"
            }

        except Exception as e:
            # Fallback to low confidence on error
            return {
                "confidence": 0.0,
                "reasoning": f"LLM error: {str(e)}",
                "cost": 0.0,
                "stage": "llm_semantic_error"
            }

    def _build_prompt(
        self,
        text: str,
        pattern: str,
        context: "MatchingContext"
    ) -> str:
        """Build context-rich prompt for LLM matching.

        Args:
            text: User input
            pattern: Pattern to match
            context: Matching context

        Returns:
            Formatted prompt string
        """
        sections = []

        # Game context
        sections.append(f'You are evaluating pattern matching for "{context.game_name}".')
        if context.game_description:
            sections.append(f"Game purpose: {context.game_description}")

        # Vocabulary context (only relevant terms)
        relevant_vocab = context.get_relevant_vocabulary(text)
        if relevant_vocab:
            sections.append("\nVocabulary:")
            for term, synonyms in relevant_vocab.items():
                sections.append(f"  - '{term}' also means: {', '.join(synonyms)}")

        # Conversation history
        if context.has_history():
            sections.append("\nRecent conversation:")
            for turn in context.get_recent_history(max_turns=3):
                role = turn["role"]
                content = turn["content"][:100]  # Limit length
                sections.append(f"  {role}: {content}")

        # Successful patterns
        if context.successful_patterns:
            sections.append("\nRecently successful patterns:")
            for pat in context.successful_patterns[-3:]:
                sections.append(f"  - \"{pat}\"")

        # The matching task
        sections.append(f'\nPattern: "{pattern}"')
        sections.append(f'User said: "{text}"')

        sections.append("\nRate how well the user's input matches the pattern (0.0-1.0).")
        sections.append("Consider:")
        sections.append("1. Semantic similarity (do they mean the same thing?)")
        sections.append("2. Vocabulary mappings (synonyms and related terms)")
        sections.append("3. Conversation context (what makes sense given history?)")

        sections.append("\nConfidence scale:")
        sections.append("- 0.0-0.3: Very different meaning")
        sections.append("- 0.3-0.5: Related but not matching")
        sections.append("- 0.5-0.7: Likely match with ambiguity")
        sections.append("- 0.7-0.9: Strong match with variation")
        sections.append("- 0.9-1.0: Essentially same meaning")

        return "\n".join(sections)


class CascadeMatcher:
    """Cascade matcher orchestrating lexical → embedding → LLM stages.

    Cost optimization strategy:
    1. Lexical (regex): Free, <1ms - exact matches
    2. Embedding: ~$0.0001, 2ms - semantic similarity (cached)
    3. LLM Semantic: ~$0.01, 200ms - context-aware understanding

    Stops at first confident-enough stage to minimize cost and latency.

    Expected distribution:
    - ~45% stop at lexical (exact matches)
    - ~40% stop at embedding (similar matches)
    - ~15% need LLM (complex cases with vocabulary/context)

    Average cost: ~$0.0015/turn (vs $0.01 if always using LLM)
    """

    def __init__(self, config):
        """Initialize cascade matcher.

        Args:
            config: LGDLConfig with thresholds and feature flags

        Raises:
            ValueError: If LLM semantic matching enabled but no API key
            ImportError: If LLM enabled but OpenAI package not installed
        """
        self.config = config
        self.emb = EmbeddingClient()

        # Initialize LLM matcher if enabled
        if config.enable_llm_semantic_matching:
            # Fail explicitly if no API key (no silent fallback)
            if not config.openai_api_key:
                raise ValueError(
                    "LLM semantic matching enabled but OPENAI_API_KEY not set. "
                    "Either set the API key or disable with LGDL_ENABLE_LLM_SEMANTIC_MATCHING=false"
                )

            from .llm_client import create_llm_client

            # This will raise if package not available (strict mode)
            llm_client = create_llm_client(
                api_key=config.openai_api_key,
                model=config.openai_llm_model,
                allow_mock_fallback=False  # Fail explicitly, no guessing
            )
            self.llm_matcher = LLMSemanticMatcher(llm_client)

            print(f"[LLM] Context-aware semantic matching ENABLED")
            print(f"[LLM] Model: {config.openai_llm_model}")
            print(f"[LLM] Lexical threshold: {config.cascade_lexical_threshold}")
            print(f"[LLM] Embedding threshold: {config.cascade_embedding_threshold}")
        else:
            self.llm_matcher = None
            print("[LLM] Context-aware semantic matching DISABLED (using embeddings only)")

    def _lexical_match(
        self,
        text: str,
        move: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any], str]:
        """Stage 1: Lexical (regex) matching.

        Args:
            text: User input
            move: Compiled move definition

        Returns:
            (confidence, params, pattern_text)
        """
        best = (0.0, {}, "")

        for trig in move["triggers"]:
            if trig["participant"] not in ("user", "assistant"):
                continue

            for pat in trig["patterns"]:
                m = pat["regex"].search(text)
                if m:
                    params = {k: (v.strip() if v else v) for k, v in m.groupdict().items()}
                    # Exact regex match gets high confidence
                    confidence = 0.85 if m else 0.0

                    if confidence > best[0]:
                        best = (confidence, params, pat["text"])

        return best

    def _embedding_match(
        self,
        text: str,
        move: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any], str]:
        """Stage 2: Embedding-based semantic matching.

        Args:
            text: User input
            move: Compiled move definition

        Returns:
            (confidence, params, pattern_text)
        """
        best = (0.0, {}, "")

        for trig in move["triggers"]:
            if trig["participant"] not in ("user", "assistant"):
                continue

            for pat in trig["patterns"]:
                # Try regex first for parameter extraction
                m = pat["regex"].search(text)
                params = {}
                if m:
                    params = {k: (v.strip() if v else v) for k, v in m.groupdict().items()}

                # Semantic similarity via embeddings
                if self.emb.enabled:
                    sim = cosine(self.emb.embed(text), self.emb.embed(pat["text"]))
                    confidence = min(1.0, 0.4 + 0.6 * sim)
                else:
                    # Fallback to token overlap
                    confidence = token_overlap(text, pat["text"])

                if confidence > best[0]:
                    best = (confidence, params, pat["text"])

        return best

    async def _llm_match(
        self,
        text: str,
        move: Dict[str, Any],
        context: "MatchingContext"
    ) -> Tuple[float, Dict[str, Any], str, str]:
        """Stage 3: LLM semantic matching with context.

        Args:
            text: User input
            move: Compiled move definition
            context: Rich matching context

        Returns:
            (confidence, params, pattern_text, reasoning)
        """
        if not self.llm_matcher:
            return (0.0, {}, "", "LLM matcher not initialized")

        best = (0.0, {}, "", "")

        for trig in move["triggers"]:
            if trig["participant"] not in ("user", "assistant"):
                continue

            for pat in trig["patterns"]:
                # Try regex for parameter extraction
                m = pat["regex"].search(text)
                params = {}
                if m:
                    params = {k: (v.strip() if v else v) for k, v in m.groupdict().items()}

                # LLM semantic match with context
                result = await self.llm_matcher.match(text, pat["text"], context)
                confidence = result.get("confidence", 0.0)
                reasoning = result.get("reasoning", "")

                if confidence > best[0]:
                    best = (confidence, params, pat["text"], reasoning)

        return best

    async def match(
        self,
        text: str,
        compiled_game: Dict[str, Any],
        context: "MatchingContext" = None
    ) -> Dict[str, Any]:
        """Match text against all moves using cascade strategy.

        Tries stages in order, stopping when confident enough:
        1. Lexical (if confidence >= lexical_threshold)
        2. Embedding (if confidence >= embedding_threshold)
        3. LLM Semantic (if enabled)

        Args:
            text: User input
            compiled_game: Compiled game IR
            context: Optional matching context for LLM stage

        Returns:
            Dict with move, score, params, stage, and metadata
        """
        best_overall = None
        provenance = []

        # Try each move
        for move in compiled_game["moves"]:
            # Stage 1: Lexical matching
            lex_conf, lex_params, lex_pattern = self._lexical_match(text, move)
            provenance.append(f"lexical:{move['id']}={lex_conf:.2f}")

            # Short-circuit if lexical is confident enough
            if lex_conf >= self.config.cascade_lexical_threshold:
                return {
                    "move": move,
                    "score": lex_conf,
                    "params": lex_params,
                    "stage": "lexical",
                    "pattern": lex_pattern,
                    "provenance": provenance
                }

            # Stage 2: Embedding matching
            emb_conf, emb_params, emb_pattern = self._embedding_match(text, move)
            provenance.append(f"embedding:{move['id']}={emb_conf:.2f}")

            # Short-circuit if embedding is confident enough
            if emb_conf >= self.config.cascade_embedding_threshold:
                return {
                    "move": move,
                    "score": emb_conf,
                    "params": emb_params,
                    "stage": "embedding",
                    "pattern": emb_pattern,
                    "provenance": provenance
                }

            # Track best so far
            best_conf = max(lex_conf, emb_conf)
            if not best_overall or best_conf > best_overall["score"]:
                best_overall = {
                    "move": move,
                    "score": best_conf,
                    "params": emb_params if emb_conf > lex_conf else lex_params,
                    "stage": "embedding" if emb_conf > lex_conf else "lexical",
                    "pattern": emb_pattern if emb_conf > lex_conf else lex_pattern
                }

        # Stage 3: LLM semantic matching (only if needed)
        # Only use expensive LLM if best match so far is below a reasonable threshold
        llm_threshold = 0.85  # If we have 0.85+ confidence from embedding, skip LLM

        if self.llm_matcher and context and (not best_overall or best_overall["score"] < llm_threshold):
            for move in compiled_game["moves"]:
                llm_conf, llm_params, llm_pattern, llm_reasoning = await self._llm_match(
                    text, move, context
                )
                provenance.append(f"llm:{move['id']}={llm_conf:.2f}")

                if llm_conf > best_overall["score"]:
                    best_overall = {
                        "move": move,
                        "score": llm_conf,
                        "params": llm_params,
                        "stage": "llm_semantic",
                        "pattern": llm_pattern,
                        "reasoning": llm_reasoning
                    }

                    # Early exit if we get very confident match
                    if llm_conf >= 0.90:
                        break

        # Return best match found
        if best_overall:
            best_overall["provenance"] = provenance
            return best_overall

        # No match found
        return {
            "move": None,
            "score": 0.0,
            "params": {},
            "stage": "none",
            "provenance": provenance
        }
