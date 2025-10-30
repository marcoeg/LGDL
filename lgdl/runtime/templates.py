"""
Secure template renderer with arithmetic evaluation.

Supports:
- {var}: Direct variable lookup from context dictionary
- {var.nested.path}: Nested dictionary traversal (safe, not Python attribute access)
- {var?fallback}: Variable with fallback value if missing
- ${expr}: Arithmetic expressions with AST validation (variables only, no dots)

Security:
- Whitelist AST node validation for ${...} expressions
- Length constraint: max 256 chars per expression
- Magnitude constraint: ±1e9 numeric limit
- Forbidden in ${...}: attribute access, subscripts, calls, exponentiation, comprehensions

Key distinction:
- {user.name} = dictionary traversal (SAFE, allowed)
- ${user.name} = Python attribute access (UNSAFE, blocked with E010)

Use {user.name} for nested data, ${age + 5} for arithmetic.

Copyright (c) 2025 Graziano Labs Corp.
"""

import ast
import re
import logging
from typing import Any, Dict

from ..errors import TemplateError, SecurityError

logger = logging.getLogger(__name__)

# Security configuration
MAX_EXPR_LENGTH = 256
MAX_NUMERIC_VALUE = 1e9


class SafeArithmeticValidator(ast.NodeVisitor):
    """
    Whitelist validator for safe arithmetic expressions.

    ALLOWED: + - * / // %
    FORBIDDEN: ** (exponent), attribute access, subscripts, calls
    """

    ALLOWED_NODES = (
        ast.Expression,     # Top-level expression wrapper
        ast.Constant,       # Modern literal (Python 3.8+)
        ast.Num,           # Legacy numeric literal (compat)
        ast.BinOp,         # Binary operations
        ast.UnaryOp,       # Unary operations
        ast.Add,           # +
        ast.Sub,           # -
        ast.Mult,          # *
        ast.Div,           # /
        ast.FloorDiv,      # //
        ast.Mod,           # %
        ast.USub,          # Unary minus
        ast.UAdd,          # Unary plus
        ast.Name,          # Variable references
        ast.Load,          # Load context
    )

    FORBIDDEN_NODES = (
        ast.Pow,           # ** exponentiation (CPU bomb risk)
        ast.Attribute,     # obj.attr (dunder access risk)
        ast.Subscript,     # obj[key] (injection risk)
        ast.Call,          # func() (RCE risk)
        ast.Lambda,        # Lambda expressions
        ast.IfExp,         # Ternary conditionals
        ast.ListComp,      # List comprehensions
        ast.DictComp,      # Dict comprehensions
        ast.GeneratorExp,  # Generator expressions
        ast.Await,         # Async await
        ast.Yield,         # Generator yield
        ast.YieldFrom,     # Yield from
    )

    def visit(self, node):
        # Explicit forbidden check (clearer errors)
        if isinstance(node, self.FORBIDDEN_NODES):
            raise SecurityError(
                code="E010",
                message=f"Forbidden expression node: {type(node).__name__}",
                hint="Template arithmetic only supports: + - * / // % with variables and numbers"
            )

        # Whitelist check
        if not isinstance(node, self.ALLOWED_NODES):
            raise SecurityError(
                code="E010",
                message=f"Unsupported expression node: {type(node).__name__}",
                hint="Only basic arithmetic is allowed in templates"
            )

        self.generic_visit(node)


class TemplateRenderer:
    """Render templates with {var} and ${expr} substitutions."""

    def render(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render template with variable and arithmetic substitutions.

        Args:
            template: Template string with {var} and ${expr} placeholders
            context: Variable context dictionary

        Returns:
            Rendered string with substitutions applied

        Raises:
            TemplateError: On syntax errors or invalid expressions
            SecurityError: On security violations
        """
        # Arithmetic: ${doctor.age + 5} (do this first to avoid conflicts)
        template = re.sub(
            r'\$\{([^\}]+)\}',
            lambda m: self._eval_arithmetic(m.group(1), context),
            template
        )

        # Simple variables: {doctor}, {context.locale}, {var?fallback}
        # (after arithmetic to avoid matching ${...} patterns)
        template = re.sub(
            r'\{([a-zA-Z_][a-zA-Z0-9_\.]*?)(\?([^\}]+))?\}',
            lambda m: self._resolve_var(m, context),
            template
        )

        return template

    def _resolve_var(self, match, context):
        """Resolve {var.path?fallback} references."""
        path = match.group(1)
        fallback = match.group(3) if match.group(2) else ""

        keys = path.split('.')
        val = context
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                val = getattr(val, key, None)
            if val is None:
                return fallback
        return str(val) if val is not None else fallback

    def _eval_arithmetic(self, expr: str, context: Dict[str, Any]) -> str:
        """
        Evaluate arithmetic expression with security constraints.

        Args:
            expr: Arithmetic expression string
            context: Variable context

        Returns:
            String representation of result

        Raises:
            SecurityError: If expression violates safety rules
            TemplateError: If expression is invalid
        """
        expr = expr.strip()

        # Length constraint
        if len(expr) > MAX_EXPR_LENGTH:
            raise SecurityError(
                code="E011",
                message=f"Expression too long: {len(expr)} > {MAX_EXPR_LENGTH} chars",
                hint="Break complex calculations into multiple steps"
            )

        try:
            # Parse and validate AST
            tree = ast.parse(expr, mode='eval')
            SafeArithmeticValidator().visit(tree)

            # Extract variable names from expression
            var_names = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expr))

            # Create safe context with defaults for missing variables
            # This prevents HTTP 500 errors when capability responses are incomplete
            safe_context = {}
            missing_vars = []
            for var in var_names:
                if var in context:
                    val = context[var]
                    # Try to convert strings to numbers for arithmetic
                    if isinstance(val, str):
                        try:
                            # Try int first, then float
                            safe_context[var] = int(val) if '.' not in val else float(val)
                        except (ValueError, AttributeError):
                            # E001: Cannot convert variable to number
                            raise TemplateError(
                                code="E001",
                                message=f"Cannot convert variable '{var}' (value: '{val}') to number in expression: {expr}",
                                hint="Ensure variables used in arithmetic are numeric or convertible to numbers"
                            )
                    else:
                        safe_context[var] = val
                else:
                    # E001: Undefined variable in arithmetic expression
                    raise TemplateError(
                        code="E001",
                        message=f"Undefined variable '{var}' in arithmetic expression: {expr}",
                        hint="Ensure all variables used in ${...} expressions are provided in the context"
                    )

            # Compile with no builtins
            code = compile(tree, '<template>', 'eval')
            result = eval(code, {"__builtins__": {}}, safe_context)

            # Magnitude constraint
            if isinstance(result, (int, float)):
                if abs(result) > MAX_NUMERIC_VALUE:
                    raise SecurityError(
                        code="E012",
                        message=f"Result exceeds safe range: {result}",
                        hint=f"Results must be within ±{MAX_NUMERIC_VALUE}"
                    )

            return str(result)

        except SyntaxError as e:
            raise TemplateError(
                code="E001",
                message=f"Invalid arithmetic syntax: {expr}",
                loc=(e.lineno, e.offset) if hasattr(e, 'lineno') else None,
                hint="Check for mismatched parentheses or invalid operators"
            ) from e
        except (TemplateError, SecurityError):
            raise  # Re-raise LGDL errors as-is
        except Exception as e:
            raise TemplateError(
                code="E001",
                message=f"Template evaluation failed: {e}",
                hint="Ensure all variables are defined in context"
            ) from e
