"""
LGDL Slot Extraction Strategies

Provides flexible slot extraction with multiple strategies:
- Regex: Fast, deterministic pattern matching (default)
- Semantic: LLM-based natural language understanding
- Hybrid: Try regex first, fallback to LLM if needed

Phase 2: Semantic Slot Extraction
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Tuple
from datetime import datetime


# ============================================================================
# Result Types
# ============================================================================

@dataclass
class ExtractionResult:
    """Result from slot extraction.

    Attributes:
        success: Whether extraction succeeded
        value: Extracted value (validated)
        confidence: Confidence score 0.0-1.0
        strategy_used: Which strategy produced this result
        reasoning: Optional explanation (from LLM)
        alternatives: Other possible values (for ambiguous cases)
    """
    success: bool
    value: Any
    confidence: float  # 0.0-1.0
    strategy_used: str  # "regex", "semantic", "hybrid"
    reasoning: Optional[str] = None
    alternatives: Optional[List[Any]] = None


# ============================================================================
# Abstract Base
# ============================================================================

class SlotExtractor(ABC):
    """Abstract base class for slot extraction strategies."""

    @abstractmethod
    async def extract(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> ExtractionResult:
        """Extract slot value from user input.

        Args:
            user_input: User's input text
            slot_def: Slot definition with type, vocabulary, context, etc.
            context: Rich context (conversation history, filled slots)

        Returns:
            ExtractionResult with extracted value and metadata
        """
        pass


# ============================================================================
# Regex Extractor (Deterministic)
# ============================================================================

class RegexSlotExtractor(SlotExtractor):
    """Deterministic regex-based slot extraction.

    Refactored from existing SlotManager.extract_slot_from_input() logic.
    Fast, free, but brittle for natural language.

    Use for:
    - Simple numeric values
    - Fixed enum values
    - Structured date/time formats
    - Exact string matches
    """

    async def extract(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> ExtractionResult:
        """Extract using regex patterns.

        Args:
            user_input: User's input
            slot_def: Slot definition
            context: Ignored for regex (deterministic)

        Returns:
            ExtractionResult with extracted value
        """
        slot_type = slot_def.get("type", "string")

        if slot_type == "number" or slot_type == "range":
            return self._extract_number(user_input, slot_def)
        elif slot_type == "enum":
            return self._extract_enum(user_input, slot_def)
        elif slot_type == "date":
            return self._extract_date(user_input, slot_def)
        elif slot_type == "timeframe":
            return self._extract_timeframe(user_input, slot_def)
        else:  # string or unknown
            return self._extract_string(user_input, slot_def)

    def _extract_number(
        self,
        text: str,
        slot_def: dict
    ) -> ExtractionResult:
        """Extract numeric value with regex.

        Pattern: -?\\d+\\.?\\d*

        Returns:
            ExtractionResult with float value or failure
        """
        match = re.search(r'-?\d+\.?\d*', text)

        if match:
            try:
                value = float(match.group())

                # Validate range if specified
                if slot_def.get("type") == "range":
                    min_val = slot_def.get("min")
                    max_val = slot_def.get("max")

                    if min_val is not None and value < min_val:
                        return ExtractionResult(
                            success=False,
                            value=value,
                            confidence=0.0,
                            strategy_used="regex",
                            reasoning=f"Value {value} below minimum {min_val}"
                        )

                    if max_val is not None and value > max_val:
                        return ExtractionResult(
                            success=False,
                            value=value,
                            confidence=0.0,
                            strategy_used="regex",
                            reasoning=f"Value {value} above maximum {max_val}"
                        )

                # Success
                return ExtractionResult(
                    success=True,
                    value=value,
                    confidence=0.9,  # High confidence for regex number match
                    strategy_used="regex"
                )

            except (ValueError, TypeError):
                pass

        # No number found
        return ExtractionResult(
            success=False,
            value=None,
            confidence=0.0,
            strategy_used="regex",
            reasoning="No number found in input"
        )

    def _extract_enum(
        self,
        text: str,
        slot_def: dict
    ) -> ExtractionResult:
        """Extract enum value with exact/partial matching.

        Tries:
        1. Exact match
        2. Partial match (case-insensitive)
        3. Substring match

        If no enum_values defined, accepts input (for backward compat).

        Returns:
            ExtractionResult with matched enum value or raw input
        """
        enum_values = slot_def.get("enum_values", [])

        # Backward compatibility: if no enum values, accept input for later validation
        if not enum_values:
            return ExtractionResult(
                success=True,
                value=text.strip(),
                confidence=0.5,  # Low confidence without validation
                strategy_used="regex"
            )

        text_lower = text.lower()

        # Try exact match
        for value in enum_values:
            if value.lower() == text_lower:
                return ExtractionResult(
                    success=True,
                    value=value,
                    confidence=1.0,  # Perfect match
                    strategy_used="regex"
                )

        # Try partial match
        for value in enum_values:
            if value.lower() in text_lower or text_lower in value.lower():
                return ExtractionResult(
                    success=True,
                    value=value,
                    confidence=0.8,  # Good match
                    strategy_used="regex"
                )

        # No match
        return ExtractionResult(
            success=False,
            value=None,
            confidence=0.0,
            strategy_used="regex",
            reasoning=f"No match for enum values: {enum_values}"
        )

    def _extract_date(
        self,
        text: str,
        slot_def: dict
    ) -> ExtractionResult:
        """Extract date with multiple format support.

        Formats:
        - ISO: YYYY-MM-DD
        - US: MM/DD/YYYY
        - Dashed: YYYY-MM-DD

        Returns:
            ExtractionResult with ISO date string or fallback to raw text
        """
        # Try ISO format: YYYY-MM-DD
        iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if iso_match:
            try:
                date = datetime(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3))
                )
                return ExtractionResult(
                    success=True,
                    value=date.isoformat()[:10],
                    confidence=0.95,
                    strategy_used="regex"
                )
            except ValueError:
                pass

        # Try US format: MM/DD/YYYY
        us_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if us_match:
            try:
                date = datetime(
                    int(us_match.group(3)),
                    int(us_match.group(1)),
                    int(us_match.group(2))
                )
                return ExtractionResult(
                    success=True,
                    value=date.isoformat()[:10],
                    confidence=0.85,
                    strategy_used="regex"
                )
            except ValueError:
                pass

        # Fallback: Accept raw text with low confidence
        return ExtractionResult(
            success=True,
            value=text,
            confidence=0.3,
            strategy_used="regex",
            reasoning="Date format not recognized, using raw text"
        )

    def _extract_timeframe(
        self,
        text: str,
        slot_def: dict
    ) -> ExtractionResult:
        """Extract timeframe with pattern matching.

        Patterns:
        - "N hours/days/weeks/months/years"
        - "yesterday", "today", "this morning", "last night"
        - Accepts "ago" phrases

        Returns:
            ExtractionResult with timeframe string
        """
        value_str = text.strip()

        # Common timeframe patterns
        patterns = [
            (r'(\d+)\s*hour', 'hours'),
            (r'(\d+)\s*day', 'days'),
            (r'(\d+)\s*week', 'weeks'),
            (r'(\d+)\s*month', 'months'),
            (r'(\d+)\s*year', 'years'),
        ]

        for pattern, unit in patterns:
            match = re.search(pattern, text.lower())
            if match:
                num = match.group(1)
                return ExtractionResult(
                    success=True,
                    value=f"{num} {unit}",
                    confidence=0.9,
                    strategy_used="regex"
                )

        # Check for common phrases
        phrases = [
            'yesterday', 'today', 'this morning', 'last night',
            'this week', 'last week', 'ago', 'recently', 'just now'
        ]

        if any(phrase in value_str.lower() for phrase in phrases):
            return ExtractionResult(
                success=True,
                value=value_str,
                confidence=0.7,
                strategy_used="regex"
            )

        # Accept any input with low confidence
        return ExtractionResult(
            success=True,
            value=value_str,
            confidence=0.5,
            strategy_used="regex"
        )

    def _extract_string(
        self,
        text: str,
        slot_def: dict
    ) -> ExtractionResult:
        """Extract string (accepts anything).

        Returns:
            ExtractionResult with string value
        """
        return ExtractionResult(
            success=True,
            value=text.strip(),
            confidence=0.9,
            strategy_used="regex"
        )


# ============================================================================
# Semantic Extractor (LLM-based)
# ============================================================================

class SemanticSlotExtractor(SlotExtractor):
    """LLM-based semantic slot extraction.

    Uses LLM to understand natural language and extract structured values.
    Supports:
    - Vocabulary/synonym mapping
    - Context-aware extraction
    - Natural language to structured data

    Cost: ~$0.005 per extraction
    Latency: ~200ms per extraction

    Use for:
    - Complex entities (locations, medical terms)
    - Natural language descriptions
    - When vocabulary/synonyms matter
    """

    def __init__(self, llm_client):
        """Initialize semantic extractor.

        Args:
            llm_client: LLMClient instance for completions
        """
        self.llm = llm_client

    async def extract(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> ExtractionResult:
        """Extract using LLM with semantic understanding.

        Args:
            user_input: User's input text
            slot_def: Slot definition with vocabulary, context
            context: Conversation history, filled slots

        Returns:
            ExtractionResult with LLM-extracted value
        """
        # Build rich prompt
        prompt = self._build_prompt(user_input, slot_def, context)

        # Define response schema
        response_schema = self._get_response_schema(slot_def)

        try:
            # Call LLM
            result = await self.llm.complete(
                prompt=prompt,
                response_schema=response_schema,
                max_tokens=150,
                temperature=0.0
            )

            extracted_value = result.content.get("value")
            confidence = result.content.get("confidence", 0.0)
            reasoning = result.content.get("reasoning", "")
            alternatives = result.content.get("alternatives", [])

            # Validate extracted value
            valid, validated_value = self._validate_value(extracted_value, slot_def)

            return ExtractionResult(
                success=valid,
                value=validated_value if valid else extracted_value,
                confidence=confidence,
                strategy_used="semantic",
                reasoning=reasoning,
                alternatives=alternatives
            )

        except Exception as e:
            # Fallback on error
            return ExtractionResult(
                success=False,
                value=None,
                confidence=0.0,
                strategy_used="semantic",
                reasoning=f"LLM extraction error: {str(e)}"
            )

    def _build_prompt(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> str:
        """Build rich prompt for semantic extraction.

        Args:
            user_input: User's input
            slot_def: Slot definition
            context: Conversation context

        Returns:
            Formatted prompt string
        """
        sections = []

        # Slot metadata
        slot_name = slot_def.get("name", "unknown")
        slot_type = slot_def.get("type", "string")
        semantic_context = slot_def.get("semantic_context", "")

        sections.append(f'You are extracting the "{slot_name}" slot.')
        sections.append(f"Slot type: {slot_type}")

        if semantic_context:
            sections.append(f"Context: {semantic_context}")

        # Vocabulary
        vocabulary = slot_def.get("vocabulary", {})
        if vocabulary:
            sections.append("\nVocabulary:")
            for term, synonyms in vocabulary.items():
                sections.append(f"  - '{term}' also means: {', '.join(synonyms)}")

        # Enum values
        enum_values = slot_def.get("enum_values", [])
        if enum_values:
            sections.append(f"\nValid values: {', '.join(enum_values)}")

        # Range constraints
        if slot_type == "range":
            min_val = slot_def.get("min")
            max_val = slot_def.get("max")
            if min_val is not None and max_val is not None:
                sections.append(f"\nValue must be between {min_val} and {max_val} (inclusive)")

        # Conversation history
        conversation_history = context.get("conversation_history", [])
        if conversation_history:
            sections.append("\nRecent conversation:")
            for turn in conversation_history[-3:]:
                role = turn.get("role", "unknown")
                content = turn.get("content", "")[:100]
                sections.append(f"  {role}: {content}")

        # Already filled slots
        filled_slots = context.get("filled_slots", {})
        if filled_slots:
            sections.append("\nAlready filled:")
            for name, value in filled_slots.items():
                sections.append(f"  {name}: {value}")

        # The extraction task
        sections.append(f'\nUser said: "{user_input}"')
        sections.append(f"\nExtract the {slot_name} from the user's input.")
        sections.append("Consider:")
        sections.append("1. Semantic meaning (what did they intend?)")
        sections.append("2. Vocabulary mappings (synonyms)")
        sections.append("3. Conversation context")
        sections.append("4. Previously filled slots")

        sections.append("\nIf value not clearly present:")
        sections.append("- Provide best guess with low confidence (<0.5)")
        sections.append("- Suggest alternatives if ambiguous")

        return "\n".join(sections)

    def _get_response_schema(self, slot_def: dict) -> Dict[str, Any]:
        """Get JSON schema for LLM response.

        Args:
            slot_def: Slot definition

        Returns:
            JSON schema for structured output
        """
        slot_type = slot_def.get("type", "string")

        schema = {
            "value": {
                "description": f"The extracted {slot_def.get('name', 'value')}"
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in extraction (0.0-1.0)"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of extraction"
            },
            "alternatives": {
                "type": "array",
                "description": "Other possible values if ambiguous"
            }
        }

        # Customize value type
        if slot_type in ("number", "range"):
            schema["value"]["type"] = "number"
        elif slot_type == "enum":
            schema["value"]["type"] = "string"
            if slot_def.get("enum_values"):
                schema["value"]["enum"] = slot_def["enum_values"]
        else:
            schema["value"]["type"] = "string"

        return schema

    def _validate_value(
        self,
        value: Any,
        slot_def: dict
    ) -> Tuple[bool, Any]:
        """Validate extracted value against slot constraints.

        Args:
            value: Extracted value
            slot_def: Slot definition with constraints

        Returns:
            (is_valid, validated_value)
        """
        if value is None:
            return (False, None)

        slot_type = slot_def.get("type", "string")

        # Type-specific validation
        if slot_type == "range":
            if not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    return (False, value)

            min_val = slot_def.get("min")
            max_val = slot_def.get("max")

            if min_val is not None and value < min_val:
                return (False, value)
            if max_val is not None and value > max_val:
                return (False, value)

        elif slot_type == "enum":
            enum_values = slot_def.get("enum_values", [])
            if enum_values and value not in enum_values:
                return (False, value)

        return (True, value)


# ============================================================================
# Hybrid Extractor (Best of Both)
# ============================================================================

class HybridSlotExtractor(SlotExtractor):
    """Hybrid extraction: try regex first, fallback to semantic.

    Strategy:
    1. Try regex (fast, free)
    2. If success and confidence >= 0.7 → return regex result
    3. Otherwise, try semantic (expensive but accurate)
    4. Return best result

    Use for:
    - Slots that might be structured OR natural language
    - When cost-conscious but need accuracy
    - Progressive enhancement (start regex, upgrade to semantic if needed)
    """

    def __init__(
        self,
        regex_extractor: RegexSlotExtractor,
        semantic_extractor: SemanticSlotExtractor
    ):
        """Initialize hybrid extractor.

        Args:
            regex_extractor: RegexSlotExtractor instance
            semantic_extractor: SemanticSlotExtractor instance
        """
        self.regex = regex_extractor
        self.semantic = semantic_extractor

    async def extract(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> ExtractionResult:
        """Try regex first, fallback to semantic if needed.

        Args:
            user_input: User's input
            slot_def: Slot definition
            context: Rich context

        Returns:
            Best ExtractionResult from either strategy
        """
        # Try regex first (fast, free)
        regex_result = await self.regex.extract(user_input, slot_def, context)

        # If regex succeeded with good confidence, use it
        if regex_result.success and regex_result.confidence >= 0.7:
            regex_result.strategy_used = "hybrid(regex)"
            return regex_result

        # Regex failed or low confidence, try semantic
        semantic_result = await self.semantic.extract(user_input, slot_def, context)

        # Return better result
        if semantic_result.confidence > regex_result.confidence:
            semantic_result.strategy_used = "hybrid(semantic)"
            return semantic_result
        else:
            regex_result.strategy_used = "hybrid(regex)"
            return regex_result


# ============================================================================
# Slot Extraction Engine (Orchestrator)
# ============================================================================

class SlotExtractionEngine:
    """Main engine for slot extraction with strategy selection.

    Routes extraction to appropriate strategy based on slot configuration.
    Handles graceful degradation if semantic extraction unavailable.
    """

    def __init__(self, config, state_manager=None):
        """Initialize extraction engine.

        Args:
            config: LGDLConfig with feature flags
            state_manager: Optional StateManager for persistence

        Raises:
            ValueError: If semantic enabled but no API key
        """
        from ..config import LGDLConfig

        self.config = config if isinstance(config, LGDLConfig) else LGDLConfig.from_env()
        self.state_manager = state_manager

        # Always have regex extractor
        self.regex = RegexSlotExtractor()

        # Conditionally create semantic extractor
        if self.config.enable_semantic_slot_extraction:
            if not self.config.openai_api_key:
                raise ValueError(
                    "Semantic slot extraction enabled but OPENAI_API_KEY not set. "
                    "Set API key or disable with LGDL_ENABLE_SEMANTIC_SLOT_EXTRACTION=false"
                )

            from .llm_client import create_llm_client

            llm_client = create_llm_client(
                api_key=self.config.openai_api_key,
                model=self.config.openai_llm_model,
                allow_mock_fallback=False  # Explicit failure
            )

            self.semantic = SemanticSlotExtractor(llm_client)
            self.hybrid = HybridSlotExtractor(self.regex, self.semantic)

            print(f"[Slots] Semantic slot extraction ENABLED")
            print(f"[Slots] Model: {self.config.openai_llm_model}")
        else:
            self.semantic = None
            self.hybrid = None
            print(f"[Slots] Semantic slot extraction DISABLED (regex only)")

    async def extract_slot(
        self,
        user_input: str,
        slot_def: dict,
        context: dict
    ) -> ExtractionResult:
        """Extract slot using configured strategy.

        Args:
            user_input: User's input text
            slot_def: Slot definition with extraction_strategy
            context: Rich context for semantic extraction

        Returns:
            ExtractionResult from appropriate extractor
        """
        strategy = slot_def.get("extraction_strategy", "regex")

        # Route to appropriate extractor
        if strategy == "semantic":
            if not self.semantic:
                # Fallback to regex if semantic not available
                print(f"[Slots] Semantic extraction not available, using regex fallback")
                return await self.regex.extract(user_input, slot_def, context)
            return await self.semantic.extract(user_input, slot_def, context)

        elif strategy == "hybrid":
            if not self.hybrid:
                # Fallback to regex if hybrid not available
                return await self.regex.extract(user_input, slot_def, context)
            return await self.hybrid.extract(user_input, slot_def, context)

        else:  # "regex" or unknown (default)
            return await self.regex.extract(user_input, slot_def, context)
