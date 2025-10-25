"""
Tests for LGDL error taxonomy.

Copyright (c) 2025 Graziano Labs Corp.
"""

import pytest
from lgdl.errors import (
    LGDLError,
    TemplateError,
    SecurityError,
    CompileError,
    RuntimeError,
    PolicyError,
    LearningError
)


def test_error_has_code():
    """Error has code attribute and includes it in string representation."""
    err = TemplateError("E001", "test message")
    assert err.code == "E001"
    assert "[E001]" in str(err)


def test_error_has_message():
    """Error has message attribute."""
    err = TemplateError("E001", "test message")
    assert err.message == "test message"
    assert "test message" in str(err)


def test_error_with_location():
    """Error can store location information."""
    err = TemplateError("E001", "test", loc=(5, 10))
    assert err.loc == (5, 10)


def test_error_with_hint():
    """Error can store hint for fixing."""
    err = TemplateError("E001", "test", hint="Try this instead")
    assert err.hint == "Try this instead"


def test_error_with_all_fields():
    """Error can have code, message, location, and hint."""
    err = TemplateError(
        code="E001",
        message="Invalid syntax",
        loc=(10, 5),
        hint="Check for mismatched parentheses"
    )
    assert err.code == "E001"
    assert err.message == "Invalid syntax"
    assert err.loc == (10, 5)
    assert err.hint == "Check for mismatched parentheses"


def test_error_inheritance():
    """Verify error class hierarchy."""
    err = SecurityError("E010", "security violation")
    assert isinstance(err, TemplateError)
    assert isinstance(err, LGDLError)
    assert isinstance(err, Exception)


def test_template_error_is_lgdl_error():
    """TemplateError inherits from LGDLError."""
    err = TemplateError("E001", "test")
    assert isinstance(err, LGDLError)


def test_security_error_is_template_error():
    """SecurityError inherits from TemplateError."""
    err = SecurityError("E010", "test")
    assert isinstance(err, TemplateError)
    assert isinstance(err, LGDLError)


def test_compile_error_is_lgdl_error():
    """CompileError inherits from LGDLError."""
    err = CompileError("E100", "test")
    assert isinstance(err, LGDLError)


def test_runtime_error_is_lgdl_error():
    """RuntimeError inherits from LGDLError."""
    err = RuntimeError("E200", "test")
    assert isinstance(err, LGDLError)


def test_policy_error_is_lgdl_error():
    """PolicyError inherits from LGDLError."""
    err = PolicyError("E300", "test")
    assert isinstance(err, LGDLError)


def test_learning_error_is_lgdl_error():
    """LearningError inherits from LGDLError."""
    err = LearningError("E400", "test")
    assert isinstance(err, LGDLError)


def test_error_can_be_caught_as_exception():
    """LGDL errors can be caught as standard exceptions."""
    try:
        raise TemplateError("E001", "test")
    except Exception as e:
        assert isinstance(e, LGDLError)
        assert e.code == "E001"


def test_error_preserves_traceback():
    """LGDL errors preserve traceback information."""
    try:
        raise ValueError("original error")
    except ValueError as e:
        new_err = TemplateError("E001", "wrapped error")
        # Verify we can raise with from clause
        try:
            raise new_err from e
        except TemplateError as caught:
            assert caught.__cause__ is e
