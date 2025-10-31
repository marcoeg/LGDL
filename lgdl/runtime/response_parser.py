"""
Response parsing for multi-turn conversation question detection.

Parses system responses to detect questions and update conversation state
with awaiting_response flags and question context for enrichment.

Copyright (c) 2025 Graziano Labs Corp.
"""

import re
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QuestionType(Enum):
    """Types of questions for enrichment hints"""
    WHERE = "where"          # Location questions: "Where does it hurt?"
    WHEN = "when"            # Time questions: "When did this start?"
    HOW = "how"              # Manner/degree: "How severe is it?"
    WHAT = "what"            # General information: "What symptoms?"
    WHO = "who"              # Person questions: "Who should I see?"
    WHY = "why"              # Reason questions: "Why did you come?"
    YES_NO = "yes_no"        # Binary questions: "Is it constant?"
    CHOICE = "choice"        # Multiple choice: "A or B?"
    UNKNOWN = "unknown"      # Couldn't classify


@dataclass
class ParsedResponse:
    """Result of parsing a system response"""
    original_response: str
    has_questions: bool
    questions: List[str]                    # All detected questions
    primary_question: Optional[str]         # First/main question
    question_type: Optional[QuestionType]   # Type of primary question
    awaiting_response: bool                 # Should we expect an answer?


class ResponseParser:
    """Parses system responses to detect questions and update conversation state"""

    # Question word patterns for classification
    QUESTION_PATTERNS = {
        QuestionType.WHERE: re.compile(r'\b(where|which\s+(?:part|area|location))\b', re.IGNORECASE),
        QuestionType.WHEN: re.compile(r'\b(when|what\s+time|which\s+day|how\s+long\s+ago)\b', re.IGNORECASE),
        QuestionType.HOW: re.compile(r'\b(how\s+(?:much|many|severe|bad|long|often))\b', re.IGNORECASE),
        QuestionType.WHAT: re.compile(r'\b(what|which)\b', re.IGNORECASE),
        QuestionType.WHO: re.compile(r'\b(who|which\s+(?:doctor|provider))\b', re.IGNORECASE),
        QuestionType.WHY: re.compile(r'\bwhy\b', re.IGNORECASE),
    }

    def __init__(self):
        """Initialize response parser"""
        self.question_marker = re.compile(r'\?')

    def parse_response(self, response: str) -> ParsedResponse:
        """
        Parse a system response to detect questions.

        Args:
            response: The system's response text

        Returns:
            ParsedResponse with question detection results

        Example:
            >>> parser = ResponseParser()
            >>> result = parser.parse_response("Where does it hurt? Is it constant?")
            >>> result.has_questions
            True
            >>> result.primary_question
            "Where does it hurt?"
            >>> result.question_type
            QuestionType.WHERE
        """
        # Check if response contains any questions
        has_questions = bool(self.question_marker.search(response))

        if not has_questions:
            return ParsedResponse(
                original_response=response,
                has_questions=False,
                questions=[],
                primary_question=None,
                question_type=None,
                awaiting_response=False
            )

        # Extract all questions
        questions = self._extract_questions(response)

        # Get primary (first) question
        primary_question = questions[0] if questions else None

        # Classify primary question type
        question_type = self._classify_question(primary_question) if primary_question else None

        # We're awaiting response if we found questions
        awaiting_response = has_questions

        logger.debug(
            f"Parsed response: {len(questions)} question(s), "
            f"primary='{primary_question}', type={question_type}"
        )

        return ParsedResponse(
            original_response=response,
            has_questions=has_questions,
            questions=questions,
            primary_question=primary_question,
            question_type=question_type,
            awaiting_response=awaiting_response
        )

    def _extract_questions(self, response: str) -> List[str]:
        """
        Extract individual question sentences from response.

        Args:
            response: Full response text

        Returns:
            List of question strings

        Example:
            >>> parser = ResponseParser()
            >>> parser._extract_questions("Where? How? When?")
            ["Where?", "How?", "When?"]
        """
        # Split by sentence boundaries (., !, ?) but keep the delimiter
        sentences = re.split(r'([.!?])', response)

        # Reconstruct sentences with their delimiters
        reconstructed = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences):
                sentence = (sentences[i] + sentences[i + 1]).strip()
                if sentence:
                    reconstructed.append(sentence)
                i += 2
            else:
                if sentences[i].strip():
                    reconstructed.append(sentences[i].strip())
                i += 1

        # Filter to only sentences ending with ?
        questions = [s for s in reconstructed if s.endswith('?')]

        return questions

    def extract_primary_question(self, response: str) -> Optional[str]:
        """
        Extract the first/main question from a response.

        Prioritizes questions at the end of the response, as they're
        typically the most important for context enrichment.

        Args:
            response: Full response text

        Returns:
            Primary question or None

        Example:
            >>> parser = ResponseParser()
            >>> parser.extract_primary_question("I understand. Where does it hurt?")
            "Where does it hurt?"
        """
        questions = self._extract_questions(response)

        if not questions:
            return None

        # For now, use the first question
        # Future: could use heuristics to prioritize end questions
        return questions[0]

    def _classify_question(self, question: str) -> QuestionType:
        """
        Classify a question by type for enrichment hints.

        Args:
            question: Question text

        Returns:
            QuestionType enum value

        Example:
            >>> parser = ResponseParser()
            >>> parser._classify_question("Where does it hurt?")
            QuestionType.WHERE
        """
        if not question:
            return QuestionType.UNKNOWN

        # Check for yes/no questions (typically start with is/are/do/does/can/will)
        if re.match(r'^\s*(is|are|do|does|did|can|could|will|would|has|have|had)\b', question, re.IGNORECASE):
            return QuestionType.YES_NO

        # Check for choice questions (contains "or")
        if re.search(r'\bor\b', question, re.IGNORECASE):
            return QuestionType.CHOICE

        # Match against question word patterns
        for qtype, pattern in self.QUESTION_PATTERNS.items():
            if pattern.search(question):
                return qtype

        # Default to unknown if no pattern matches
        return QuestionType.UNKNOWN

    def should_await_response(self, response: str) -> bool:
        """
        Quick check if response requires user input.

        Args:
            response: System response text

        Returns:
            True if response contains questions

        Example:
            >>> parser = ResponseParser()
            >>> parser.should_await_response("Where does it hurt?")
            True
            >>> parser.should_await_response("OK, got it.")
            False
        """
        return bool(self.question_marker.search(response))
