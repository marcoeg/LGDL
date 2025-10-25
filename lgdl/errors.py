"""
Error taxonomy for LGDL system.

Error code ranges:
- E001-E099: Syntax and template errors
- E100-E199: Semantic and compile errors
- E200-E299: Runtime and capability errors
- E300-E399: Policy violations
- E400-E499: Learning errors

Copyright (c) 2025 Graziano Labs Corp.
"""


class LGDLError(Exception):
    """Base class for all LGDL errors."""

    def __init__(
        self,
        code: str,
        message: str,
        loc: tuple[int, int] | None = None,
        hint: str | None = None
    ):
        """
        Initialize LGDL error.

        Args:
            code: Error code (e.g., "E001")
            message: Human-readable error message
            loc: Optional (line, column) location
            hint: Optional suggestion for fixing the error
        """
        self.code = code
        self.message = message
        self.loc = loc
        self.hint = hint
        super().__init__(f"[{code}] {message}")


class TemplateError(LGDLError):
    """Template rendering errors (E001-E099)."""
    pass


class SecurityError(TemplateError):
    """Security violations in templates (E010-E019)."""
    pass


class CompileError(LGDLError):
    """Compilation errors (E100-E199)."""
    pass


class RuntimeError(LGDLError):
    """Runtime execution errors (E200-E299)."""
    pass


class PolicyError(LGDLError):
    """Policy/capability violations (E300-E399)."""
    pass


class LearningError(LGDLError):
    """Learning pipeline errors (E400-E499)."""
    pass


# Specific error codes documentation:
#
# E001: Invalid template syntax (parse error)
# E010: Forbidden expression node (security violation)
# E011: Expression too complex (length limit exceeded)
# E012: Numeric value exceeds safe range (magnitude overflow)
