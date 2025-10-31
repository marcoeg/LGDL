"""
Tests for response parsing and question detection.

Tests ResponseParser functionality for detecting and classifying
questions in system responses.
"""

import pytest
from lgdl.runtime.response_parser import ResponseParser, QuestionType, ParsedResponse


class TestResponseParser:
    """Test ResponseParser question detection and classification"""

    @pytest.fixture
    def parser(self):
        """Create ResponseParser instance"""
        return ResponseParser()

    def test_detect_simple_question(self, parser):
        """Test detection of a single simple question"""
        response = "Where does it hurt?"
        parsed = parser.parse_response(response)

        assert parsed.has_questions is True
        assert len(parsed.questions) == 1
        assert parsed.questions[0] == "Where does it hurt?"
        assert parsed.primary_question == "Where does it hurt?"
        assert parsed.awaiting_response is True

    def test_detect_multiple_questions(self, parser):
        """Test detection of multiple questions in response"""
        response = "Where does it hurt? When did it start? How severe is it?"
        parsed = parser.parse_response(response)

        assert parsed.has_questions is True
        assert len(parsed.questions) == 3
        assert parsed.primary_question == "Where does it hurt?"
        assert "When did it start?" in parsed.questions
        assert "How severe is it?" in parsed.questions

    def test_no_question_detected(self, parser):
        """Test that statements without questions are not detected"""
        response = "I understand you have pain in your chest."
        parsed = parser.parse_response(response)

        assert parsed.has_questions is False
        assert len(parsed.questions) == 0
        assert parsed.primary_question is None
        assert parsed.question_type is None
        assert parsed.awaiting_response is False

    def test_classify_where_question(self, parser):
        """Test classification of WHERE questions"""
        test_cases = [
            "Where does it hurt?",
            "Which part of your body?",
            "Which area is affected?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.WHERE, f"Failed for: {question}"

        # "What location" is classified as WHAT (expected behavior - WHAT takes priority)
        parsed = parser.parse_response("What location is the pain?")
        assert parsed.question_type == QuestionType.WHAT

    def test_classify_when_question(self, parser):
        """Test classification of WHEN questions"""
        test_cases = [
            "When did this start?",
            "What time did the pain begin?",
            "How long ago did this happen?",
            "Which day did you first notice it?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.WHEN, f"Failed for: {question}"

    def test_classify_how_question(self, parser):
        """Test classification of HOW questions"""
        test_cases = [
            "How severe is the pain?",
            "How much does it hurt?",
            "How often does it occur?",
            "How long has this been happening?",
            "How bad is it?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.HOW, f"Failed for: {question}"

    def test_classify_yes_no_question(self, parser):
        """Test classification of YES/NO questions"""
        test_cases = [
            "Is it constant?",
            "Are you experiencing nausea?",
            "Do you have a fever?",
            "Does it hurt when you breathe?",
            "Can you move your arm?",
            "Will you be available tomorrow?",
            "Have you taken any medication?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.YES_NO, f"Failed for: {question}"

    def test_classify_choice_question(self, parser):
        """Test classification of CHOICE questions (contains 'or')"""
        # CHOICE type only applies when not starting with YES/NO markers
        test_cases = [
            "Morning or afternoon?",
            "Red or blue?",
            "Coffee or tea?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.CHOICE, f"Failed for: {question}"

        # YES/NO takes priority over CHOICE (expected behavior)
        parsed = parser.parse_response("Is it sharp or dull?")
        assert parsed.question_type == QuestionType.YES_NO

    def test_extract_primary_question(self, parser):
        """Test extraction of primary question from multi-sentence response"""
        response = "I understand you have chest pain. Where exactly is the pain? Is it severe?"
        parsed = parser.parse_response(response)

        assert parsed.has_questions is True
        assert parsed.primary_question == "Where exactly is the pain?"
        assert len(parsed.questions) == 2

    def test_awaiting_response_flag(self, parser):
        """Test that awaiting_response flag is set correctly"""
        # With question
        response_with_q = "What is your temperature?"
        parsed_q = parser.parse_response(response_with_q)
        assert parsed_q.awaiting_response is True

        # Without question
        response_no_q = "Your temperature has been recorded."
        parsed_no_q = parser.parse_response(response_no_q)
        assert parsed_no_q.awaiting_response is False

    def test_empty_response(self, parser):
        """Test edge case: empty response"""
        response = ""
        parsed = parser.parse_response(response)

        assert parsed.has_questions is False
        assert len(parsed.questions) == 0
        assert parsed.primary_question is None
        assert parsed.awaiting_response is False

    def test_question_with_statement(self, parser):
        """Test response with both statement and question"""
        response = "I can help with that. What date works best for you?"
        parsed = parser.parse_response(response)

        assert parsed.has_questions is True
        assert parsed.primary_question == "What date works best for you?"
        assert parsed.question_type == QuestionType.WHAT

    def test_classify_who_question(self, parser):
        """Test classification of WHO questions"""
        # WHO pattern matches questions starting with "who"
        test_cases = [
            "Who is your doctor?",
            "Who should I contact?"
        ]

        for question in test_cases:
            parsed = parser.parse_response(question)
            assert parsed.question_type == QuestionType.WHO, f"Failed for: {question}"

        # "Which provider" is classified as WHAT (expected - WHAT takes priority)
        parsed = parser.parse_response("Which provider would you like?")
        assert parsed.question_type == QuestionType.WHAT

    def test_classify_why_question(self, parser):
        """Test classification of WHY questions"""
        response = "Why did you come to the ER?"
        parsed = parser.parse_response(response)

        assert parsed.question_type == QuestionType.WHY

    def test_original_response_preserved(self, parser):
        """Test that original response text is preserved"""
        response = "Testing preservation. Is this working?"
        parsed = parser.parse_response(response)

        assert parsed.original_response == response
        assert parsed.has_questions is True
