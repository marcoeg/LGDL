"""
LLM Client Abstraction for LGDL

Provides abstract interface for LLM completions with structured output support.
Includes OpenAI implementation with cost estimation and error handling.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """Result from LLM completion.

    Attributes:
        content: The structured JSON response
        cost: Estimated cost in dollars
        tokens_used: Total tokens (input + output)
        model: Model that generated the response
    """
    content: Dict[str, Any]
    cost: float
    tokens_used: int
    model: str


class LLMClient(ABC):
    """Abstract base class for LLM clients.

    Defines interface for structured completions with cost tracking.
    Implementations must handle:
    - Async completion requests
    - JSON schema enforcement
    - Cost estimation
    - Error handling
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        max_tokens: int = 100,
        temperature: float = 0.0
    ) -> CompletionResult:
        """Get structured completion from LLM.

        Args:
            prompt: The prompt to send to the LLM
            response_schema: JSON schema for expected response structure
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 = deterministic)

        Returns:
            CompletionResult with parsed JSON and metadata

        Raises:
            LLMError: If completion fails
            JSONDecodeError: If response doesn't match schema
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        prompt: str,
        max_tokens: int
    ) -> float:
        """Estimate cost of completion in dollars.

        Args:
            prompt: The prompt text
            max_tokens: Maximum output tokens

        Returns:
            Estimated cost in USD
        """
        pass


class OpenAIClient(LLMClient):
    """OpenAI implementation of LLM client.

    Supports structured JSON output via OpenAI's API.
    Includes cost estimation based on current pricing.

    Pricing (as of Jan 2025):
        gpt-4o-mini: $0.00015/1k input, $0.0006/1k output
        gpt-4o: $0.0025/1k input, $0.01/1k output

    Example:
        client = OpenAIClient(api_key="sk-...", model="gpt-4o-mini")
        result = await client.complete(
            prompt="Match this pattern",
            response_schema={"confidence": {"type": "number"}},
            max_tokens=50
        )
        print(result.content["confidence"])  # 0.85
        print(result.cost)  # 0.00002
    """

    # Model pricing (per 1000 tokens)
    PRICING = {
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_retries: int = 2,
        timeout: float = 5.0
    ):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-4o-mini)
            max_retries: Maximum retry attempts on failure
            timeout: Request timeout in seconds

        Raises:
            ImportError: If openai package not installed
            ValueError: If model not supported
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package required for OpenAI client. "
                "Install with: uv pip install openai"
            )

        if model not in self.PRICING:
            logger.warning(
                f"Model {model} not in pricing table. Using gpt-4o-mini pricing as fallback."
            )

        self.client = AsyncOpenAI(
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout
        )
        self.model = model

    async def complete(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        max_tokens: int = 100,
        temperature: float = 0.0
    ) -> CompletionResult:
        """Get structured JSON completion from OpenAI.

        Uses OpenAI's JSON mode to enforce structured output.

        Args:
            prompt: System + user prompt
            response_schema: Expected JSON schema (for documentation)
            max_tokens: Maximum output tokens
            temperature: Sampling temperature

        Returns:
            CompletionResult with parsed JSON

        Raises:
            OpenAI.APIError: On API failure
            JSONDecodeError: If response isn't valid JSON
        """
        # Build prompt with schema hint
        schema_description = self._format_schema_description(response_schema)
        full_prompt = f"{prompt}\n\nReturn JSON with these fields:\n{schema_description}"

        try:
            # Call OpenAI with JSON mode
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise pattern matching assistant. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Extract and parse response
            content_text = response.choices[0].message.content
            parsed_content = json.loads(content_text)

            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            cost = self._calculate_cost(input_tokens, output_tokens)

            logger.debug(
                f"LLM completion: {total_tokens} tokens, ${cost:.6f}, "
                f"confidence={parsed_content.get('confidence', 'N/A')}"
            )

            return CompletionResult(
                content=parsed_content,
                cost=cost,
                tokens_used=total_tokens,
                model=self.model
            )

        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {content_text}")
            raise

        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise

    def estimate_cost(
        self,
        prompt: str,
        max_tokens: int
    ) -> float:
        """Estimate completion cost.

        Uses rough tokenization estimate (4 chars ≈ 1 token).

        Args:
            prompt: The prompt text
            max_tokens: Maximum output tokens

        Returns:
            Estimated cost in USD
        """
        # Rough token estimate: ~4 characters per token
        estimated_input_tokens = len(prompt) / 4
        estimated_output_tokens = max_tokens

        return self._calculate_cost(
            int(estimated_input_tokens),
            int(estimated_output_tokens)
        )

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate actual cost from token counts.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(
            self.model,
            self.PRICING["gpt-4o-mini"]  # Fallback
        )

        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]

        return input_cost + output_cost

    def _format_schema_description(
        self,
        schema: Dict[str, Any]
    ) -> str:
        """Format JSON schema as human-readable description.

        Args:
            schema: JSON schema dictionary

        Returns:
            Formatted description string
        """
        lines = []
        for field, spec in schema.items():
            field_type = spec.get("type", "any")
            description = spec.get("description", "")

            line = f"- {field} ({field_type})"
            if description:
                line += f": {description}"

            # Add constraints
            if "minimum" in spec and "maximum" in spec:
                line += f" [range: {spec['minimum']}-{spec['maximum']}]"
            elif "enum" in spec:
                line += f" [one of: {', '.join(spec['enum'])}]"

            lines.append(line)

        return "\n".join(lines)


class MockLLMClient(LLMClient):
    """Mock LLM client for testing.

    Returns predefined responses without making actual API calls.
    Useful for:
    - Unit testing
    - Offline development
    - Cost-free testing

    Example:
        client = MockLLMClient(default_confidence=0.85)
        result = await client.complete("test", {})
        assert result.content["confidence"] == 0.85
    """

    def __init__(
        self,
        default_confidence: float = 0.75,
        default_reasoning: str = "Mock LLM response"
    ):
        """Initialize mock client.

        Args:
            default_confidence: Default confidence score to return
            default_reasoning: Default reasoning text to return
        """
        self.default_confidence = default_confidence
        self.default_reasoning = default_reasoning

    async def complete(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        max_tokens: int = 100,
        temperature: float = 0.0
    ) -> CompletionResult:
        """Return mock completion.

        Args:
            prompt: Ignored
            response_schema: Used to determine response structure
            max_tokens: Ignored
            temperature: Ignored

        Returns:
            CompletionResult with mock data
        """
        # Build mock response matching schema
        content = {}

        for field, spec in response_schema.items():
            if field == "confidence":
                content[field] = self.default_confidence
            elif field == "reasoning":
                content[field] = self.default_reasoning
            elif spec.get("type") == "number":
                content[field] = 0.5
            elif spec.get("type") == "boolean":
                content[field] = True
            elif spec.get("type") == "array":
                content[field] = []
            else:
                content[field] = "mock_value"

        return CompletionResult(
            content=content,
            cost=0.0,  # No cost for mock
            tokens_used=50,
            model="mock"
        )

    def estimate_cost(
        self,
        prompt: str,
        max_tokens: int
    ) -> float:
        """Mock cost estimation (always returns 0).

        Args:
            prompt: Ignored
            max_tokens: Ignored

        Returns:
            0.0 (no cost for mock)
        """
        return 0.0


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    pass


class LLMCostExceededError(LLMError):
    """Raised when estimated cost exceeds limit."""
    pass


# Convenience function for quick client creation
def create_llm_client(
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    use_mock: bool = False,
    allow_mock_fallback: bool = False
) -> LLMClient:
    """Create LLM client instance.

    Args:
        api_key: OpenAI API key (required unless use_mock=True)
        model: Model name
        use_mock: Force mock client (for testing only)
        allow_mock_fallback: Allow falling back to mock on errors (default: False)

    Returns:
        LLMClient instance (OpenAI or Mock)

    Raises:
        ValueError: If api_key is None and not using mock
        ImportError: If OpenAI package not available and not using mock
    """
    # Explicit mock for testing
    if use_mock:
        logger.info("Using mock LLM client (explicit test mode)")
        return MockLLMClient()

    # Auto-detect test keys for test suite ONLY
    if api_key in ("test", "test-key", "sk-test"):
        logger.info("Detected test API key, using mock client")
        return MockLLMClient()

    # Production path: REQUIRE valid API key
    if not api_key:
        if allow_mock_fallback:
            logger.warning("No API key provided, falling back to mock client")
            return MockLLMClient()
        else:
            raise ValueError(
                "OpenAI API key required for LLM semantic matching. "
                "Set OPENAI_API_KEY environment variable or disable feature with "
                "LGDL_ENABLE_LLM_SEMANTIC_MATCHING=false"
            )

    # Check OpenAI package availability
    if not OPENAI_AVAILABLE:
        if allow_mock_fallback:
            logger.warning("OpenAI package not available, falling back to mock client")
            return MockLLMClient()
        else:
            raise ImportError(
                "openai package required for LLM semantic matching. "
                "Install with: uv sync --extra openai"
            )

    # Create real OpenAI client
    logger.info(f"Using OpenAI client with model: {model}")
    return OpenAIClient(api_key=api_key, model=model)
