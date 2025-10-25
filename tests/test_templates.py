"""
Tests for secure template rendering.

Copyright (c) 2025 Graziano Labs Corp.
"""

import pytest
from lgdl.runtime.templates import TemplateRenderer, MAX_NUMERIC_VALUE, MAX_EXPR_LENGTH
from lgdl.errors import SecurityError, TemplateError


# Basic functionality tests

def test_simple_variable():
    """Simple variable substitution works."""
    r = TemplateRenderer()
    assert r.render("{name}", {"name": "Alice"}) == "Alice"


def test_nested_variable():
    """Nested variable lookup works."""
    r = TemplateRenderer()
    assert r.render("{user.age}", {"user": {"age": 30}}) == "30"


def test_deeply_nested_variable():
    """Deeply nested variable lookup works."""
    r = TemplateRenderer()
    context = {"user": {"profile": {"name": "Alice"}}}
    assert r.render("{user.profile.name}", context) == "Alice"


def test_missing_variable():
    """Missing variable returns empty string."""
    r = TemplateRenderer()
    assert r.render("{missing}", {}) == ""


def test_fallback():
    """Fallback value used when variable missing."""
    r = TemplateRenderer()
    assert r.render("{missing?fallback}", {}) == "fallback"
    assert r.render("{missing?default value}", {}) == "default value"


def test_fallback_not_used_when_present():
    """Fallback not used when variable is present."""
    r = TemplateRenderer()
    assert r.render("{name?fallback}", {"name": "Alice"}) == "Alice"


def test_multiple_variables():
    """Multiple variables in one template."""
    r = TemplateRenderer()
    result = r.render("Hello {name}, you are {age} years old", {
        "name": "Alice",
        "age": 30
    })
    assert result == "Hello Alice, you are 30 years old"


def test_mixed_variables_and_fallbacks():
    """Mix of variables with and without fallbacks."""
    r = TemplateRenderer()
    result = r.render("{greeting?Hello} {name?stranger}", {"name": "Alice"})
    assert result == "Hello Alice"


# Arithmetic tests

def test_arithmetic_addition():
    """Basic addition works."""
    r = TemplateRenderer()
    assert r.render("${age + 5}", {"age": 30}) == "35"
    assert r.render("${a + b}", {"a": 10, "b": 20}) == "30"


def test_arithmetic_subtraction():
    """Basic subtraction works."""
    r = TemplateRenderer()
    assert r.render("${a - b}", {"a": 100, "b": 30}) == "70"


def test_arithmetic_multiplication():
    """Basic multiplication works."""
    r = TemplateRenderer()
    assert r.render("${x * 2}", {"x": 10}) == "20"
    assert r.render("${a * b}", {"a": 5, "b": 7}) == "35"


def test_arithmetic_division():
    """Basic division works."""
    r = TemplateRenderer()
    assert r.render("${a / b}", {"a": 10, "b": 2}) == "5.0"


def test_arithmetic_floor_division():
    """Floor division works."""
    r = TemplateRenderer()
    assert r.render("${a // b}", {"a": 10, "b": 3}) == "3"


def test_arithmetic_modulo():
    """Modulo operation works."""
    r = TemplateRenderer()
    assert r.render("${a % b}", {"a": 10, "b": 3}) == "1"


def test_arithmetic_unary_minus():
    """Unary minus works."""
    r = TemplateRenderer()
    assert r.render("${-x}", {"x": 5}) == "-5"


def test_arithmetic_complex():
    """Complex arithmetic expressions work."""
    r = TemplateRenderer()
    assert r.render("${(x + y) * 2}", {"x": 3, "y": 7}) == "20"
    assert r.render("${a / b + c}", {"a": 10, "b": 2, "c": 3}) == "8.0"
    assert r.render("${(a + b) // c}", {"a": 10, "b": 5, "c": 4}) == "3"


def test_arithmetic_with_parentheses():
    """Parentheses control operation order."""
    r = TemplateRenderer()
    assert r.render("${a + b * c}", {"a": 2, "b": 3, "c": 4}) == "14"
    assert r.render("${(a + b) * c}", {"a": 2, "b": 3, "c": 4}) == "20"


# Security tests - Forbidden nodes

def test_security_reject_exponentiation():
    """E010: Reject ** operator (CPU bomb risk)."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${2 ** 999999}", {})
    assert exc.value.code == "E010"
    assert "Pow" in exc.value.message


def test_security_reject_import():
    """E010: Reject __import__ call."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${__import__('os').system('ls')}", {})
    assert exc.value.code == "E010"
    assert "Call" in exc.value.message


def test_security_reject_attribute_access():
    """E010: Reject dunder attribute access."""
    r = TemplateRenderer()
    # Test simpler attribute access since __class__ requires obj to exist
    with pytest.raises(SecurityError) as exc:
        r.render("${obj.attr}", {"obj": {"attr": "value"}})
    assert exc.value.code == "E010"
    assert "Attribute" in exc.value.message


def test_security_reject_subscript():
    """E010: Reject subscript access."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${data['key']}", {"data": {"key": "val"}})
    assert exc.value.code == "E010"
    assert "Subscript" in exc.value.message


def test_security_reject_lambda():
    """E010: Reject lambda expressions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${(lambda x: x+1)(5)}", {})
    assert exc.value.code == "E010"
    # Call node caught before Lambda node in AST traversal
    assert "Call" in exc.value.message or "Lambda" in exc.value.message


def test_security_reject_list_comprehension():
    """E010: Reject list comprehensions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${[x for x in range(10)]}", {})
    assert exc.value.code == "E010"


def test_security_reject_dict_comprehension():
    """E010: Reject dict comprehensions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${dict((x, x) for x in range(10))}", {})
    assert exc.value.code == "E010"


def test_security_reject_generator_expression():
    """E010: Reject generator expressions."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${sum(x for x in range(10))}", {})
    assert exc.value.code == "E010"


def test_security_reject_ternary():
    """E010: Reject ternary conditional."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${a if a > 0 else b}", {"a": 5, "b": 10})
    assert exc.value.code == "E010"
    assert "IfExp" in exc.value.message


def test_security_reject_function_call():
    """E010: Reject any function calls."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${len([1,2,3])}", {})
    assert exc.value.code == "E010"
    assert "Call" in exc.value.message


# Security tests - Length and magnitude

def test_security_expression_too_long():
    """E011: Reject expressions exceeding max length."""
    r = TemplateRenderer()
    long_expr = "x + " * 100 + "1"  # >256 chars
    assert len(long_expr) > MAX_EXPR_LENGTH
    with pytest.raises(SecurityError) as exc:
        r.render(f"${{{long_expr}}}", {"x": 1})
    assert exc.value.code == "E011"
    assert "too long" in exc.value.message.lower()


def test_security_expression_at_limit():
    """Expression at max length is allowed."""
    r = TemplateRenderer()
    # Create expression exactly at limit
    expr = "x" + " + 1" * ((MAX_EXPR_LENGTH - 1) // 5)
    expr = expr[:MAX_EXPR_LENGTH]  # Trim to exact limit
    # Should not raise
    result = r.render(f"${{{expr}}}", {"x": 1})
    assert result is not None


def test_security_magnitude_overflow():
    """E012: Reject results exceeding safe numeric range."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${x * y}", {"x": 1e8, "y": 1e8})  # Result: 1e16 > 1e9
    assert exc.value.code == "E012"
    assert "exceeds safe range" in exc.value.message.lower()


def test_security_magnitude_at_limit():
    """Values at magnitude limit are allowed."""
    r = TemplateRenderer()
    # Exactly at limit
    result = r.render("${x}", {"x": MAX_NUMERIC_VALUE})
    assert result == str(MAX_NUMERIC_VALUE)

    # Just under limit
    result = r.render("${x}", {"x": MAX_NUMERIC_VALUE - 1})
    assert result == str(MAX_NUMERIC_VALUE - 1)


def test_security_magnitude_negative():
    """Negative magnitude overflow also rejected."""
    r = TemplateRenderer()
    with pytest.raises(SecurityError) as exc:
        r.render("${x * y}", {"x": -1e8, "y": 1e8})  # Result: -1e16 < -1e9
    assert exc.value.code == "E012"


# Syntax error tests

def test_error_invalid_syntax():
    """E001: Syntax errors have proper error code."""
    r = TemplateRenderer()
    with pytest.raises(TemplateError) as exc:
        r.render("${(x + }", {"x": 1})  # Mismatched parens
    assert exc.value.code == "E001"
    assert exc.value.hint is not None


def test_error_mismatched_parentheses():
    """E001: Mismatched parentheses detected."""
    r = TemplateRenderer()
    with pytest.raises(TemplateError) as exc:
        r.render("${((a + b)}", {"a": 1, "b": 2})
    assert exc.value.code == "E001"


def test_error_undefined_variable():
    """E001: Undefined variable in arithmetic."""
    r = TemplateRenderer()
    with pytest.raises(TemplateError) as exc:
        r.render("${undefined_var + 1}", {})
    assert exc.value.code == "E001"
    assert "undefined_var" in str(exc.value).lower() or "failed" in exc.value.message.lower()


def test_error_has_hint():
    """Errors include helpful hints."""
    r = TemplateRenderer()
    with pytest.raises(TemplateError) as exc:
        r.render("${(x + }", {"x": 1})
    assert exc.value.hint is not None
    assert len(exc.value.hint) > 0


# Regression tests (MVP compatibility)

def test_regression_existing_templates_work():
    """Ensure existing MVP templates still work."""
    r = TemplateRenderer()

    # From golden tests - appointment_request response
    result = r.render(
        "I can check availability for {doctor?any provider}.",
        {"doctor": "Smith"}
    )
    assert result == "I can check availability for Smith."

    result = r.render(
        "I can check availability for {doctor?any provider}.",
        {}
    )
    assert result == "I can check availability for any provider."


def test_regression_fallback_values():
    """Original fallback syntax still works."""
    r = TemplateRenderer()
    assert r.render("{var?default}", {}) == "default"
    assert r.render("{var?default}", {"var": "value"}) == "value"


def test_regression_no_arithmetic():
    """Templates without arithmetic still work."""
    r = TemplateRenderer()
    result = r.render("Hello {name}, welcome!", {"name": "Alice"})
    assert result == "Hello Alice, welcome!"


# Edge cases

def test_empty_template():
    """Empty template returns empty string."""
    r = TemplateRenderer()
    assert r.render("", {}) == ""


def test_no_variables():
    """Template with no variables returns as-is."""
    r = TemplateRenderer()
    assert r.render("Hello world", {}) == "Hello world"


def test_mixed_content():
    """Mix of text, variables, and arithmetic."""
    r = TemplateRenderer()
    result = r.render(
        "Hello {name}, you will be {age} in ${year + 1}",
        {"name": "Alice", "age": 30, "year": 2025}
    )
    assert result == "Hello Alice, you will be 30 in 2026"


def test_consecutive_variables():
    """Multiple variables without separator."""
    r = TemplateRenderer()
    result = r.render("{first}{last}", {"first": "Alice", "last": "Smith"})
    assert result == "AliceSmith"


def test_variable_with_underscore():
    """Variables with underscores work."""
    r = TemplateRenderer()
    assert r.render("{user_name}", {"user_name": "Alice"}) == "Alice"


def test_arithmetic_with_underscore_var():
    """Arithmetic with underscore variables."""
    r = TemplateRenderer()
    assert r.render("${user_age + 1}", {"user_age": 30}) == "31"


def test_zero_values():
    """Zero values handled correctly."""
    r = TemplateRenderer()
    assert r.render("{count}", {"count": 0}) == "0"
    assert r.render("${count + 1}", {"count": 0}) == "1"


def test_negative_values():
    """Negative values work."""
    r = TemplateRenderer()
    assert r.render("{temp}", {"temp": -5}) == "-5"
    assert r.render("${temp - 10}", {"temp": -5}) == "-15"


def test_float_values():
    """Float values work."""
    r = TemplateRenderer()
    assert r.render("{price}", {"price": 19.99}) == "19.99"
    assert r.render("${price * 2}", {"price": 10.5}) == "21.0"


def test_whitespace_in_expressions():
    """Whitespace in expressions handled correctly."""
    r = TemplateRenderer()
    assert r.render("${  x  +  y  }", {"x": 1, "y": 2}) == "3"
    assert r.render("${x+y}", {"x": 1, "y": 2}) == "3"


def test_dotted_path_in_variable_vs_expression():
    """Dotted paths: allowed in {var}, forbidden in ${expr}."""
    r = TemplateRenderer()

    # Allowed: {user.name} uses dictionary traversal
    context = {"user": {"name": "Alice", "age": 30}}
    assert r.render("{user.name}", context) == "Alice"
    assert r.render("{user.age}", context) == "30"
    assert r.render("{user.name?Guest}", context) == "Alice"

    # Forbidden: ${user.name} would use Python attribute access
    with pytest.raises(SecurityError) as exc:
        r.render("${user.name}", context)
    assert exc.value.code == "E010"
    assert "Attribute" in exc.value.message

    # Workaround: use separate variables in arithmetic
    # ${user_age + 5} works if context = {"user_age": 30}
    context_flat = {"user_age": 30}
    assert r.render("${user_age + 5}", context_flat) == "35"


def test_deep_nesting_in_variables():
    """Deeply nested dictionary paths work in {var} syntax."""
    r = TemplateRenderer()
    context = {
        "user": {
            "profile": {
                "settings": {
                    "theme": "dark"
                }
            }
        }
    }
    assert r.render("{user.profile.settings.theme}", context) == "dark"
    assert r.render("{user.profile.settings.theme?light}", context) == "dark"

    # Missing nested path uses fallback
    assert r.render("{user.profile.missing?default}", context) == "default"
