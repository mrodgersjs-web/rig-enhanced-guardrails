"""validators.py - public API for individual guardrail checks.

The Guard object runs all four checks together and signs the result. This
module exposes each check as a standalone callable so downstream tooling
can compose its own checks, decide which ones to run, or reuse one
without paying the cost of the others.

Every check returns a tuple (passed: bool, detail: str). The Guard object
wraps each tuple into a dict entry; this module is the lower-level API
for callers that want the raw tuples.

Check signatures are kept identical so callers can swap implementations
or build a registry:

    from src.validators import (
        check_json_schema,
        check_toxicity,
        check_factuality,
        check_format,
    )

Each function returns ``(passed: bool, detail: str)``. ``detail`` is the
empty string when ``passed`` is True.
"""

from __future__ import annotations

import re
from typing import Any

from src.guard import (
    _validate_json_schema,
    check_factuality_placeholder,
    check_format,
    check_toxicity,
)

# --------------------------------------------------------------------------
# Public re-exports (single, stable surface for downstream tooling)
# --------------------------------------------------------------------------


def check_json_schema(value: Any, schema: dict | None) -> tuple[bool, str]:
    """Run the structural JSON-schema check against ``value``.

    When ``schema`` is None the check passes with an empty detail string,
    matching Guard's behaviour (a missing schema is not a failure).
    """
    if schema is None:
        return True, ""
    errors = _validate_json_schema(value, schema)
    if not errors:
        return True, ""
    return False, "; ".join(errors)


def check_toxicity_callable(text: str) -> tuple[bool, str]:
    """Run the toxicity check as a public API. Pure re-export."""
    passed, detail = check_toxicity(text)
    return passed, detail


def check_factuality(text: str) -> tuple[bool, str]:
    """Run the factuality placeholder check as a public API.

    Returns ``(passed, detail)`` where detail is empty on pass and a
    short reason on fail.
    """
    passed, detail = check_factuality_placeholder(text)
    return passed, detail


def check_format_callable(
    text: str, max_length: int = 4000
) -> tuple[bool, str]:
    """Run the format check as a public API.

    The format check enforces:
      - non-empty after whitespace stripping
      - length below ``max_length`` characters
      - balanced code fences (triple backticks come in pairs)
    """
    passed, detail = check_format(text, max_length=max_length)
    return passed, detail


# --------------------------------------------------------------------------
# Convenience: run a named subset of checks against a single text input.
# --------------------------------------------------------------------------


CHECK_NAMES = ("json_schema", "toxicity", "factuality", "format")


def run_checks(
    text: str,
    *,
    schema: dict | None = None,
    max_length: int = 4000,
    only: tuple[str, ...] | None = None,
) -> dict[str, tuple[bool, str]]:
    """Run the requested checks and return ``{name: (passed, detail)}``.

    ``only`` is an optional whitelist of check names; default runs all
    four. The whitelist is validated against ``CHECK_NAMES`` and an
    unknown name raises ``ValueError``.
    """
    if only is not None:
        unknown = set(only) - set(CHECK_NAMES)
        if unknown:
            raise ValueError(
                f"unknown check name(s): {sorted(unknown)}; valid: {CHECK_NAMES}"
            )
    selected = set(only) if only is not None else set(CHECK_NAMES)

    results: dict[str, tuple[bool, str]] = {}
    if "json_schema" in selected:
        # The schema check works on the raw value; for text inputs a
        # best-effort parse attempts to treat the text as JSON.
        if schema is None:
            results["json_schema"] = (True, "")
        else:
            import json

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                results["json_schema"] = (False, "value is not valid JSON")
            else:
                results["json_schema"] = check_json_schema(parsed, schema)
    if "toxicity" in selected:
        results["toxicity"] = check_toxicity_callable(text)
    if "factuality" in selected:
        results["factuality"] = check_factuality(text)
    if "format" in selected:
        results["format"] = check_format_callable(text, max_length=max_length)
    return results


# --------------------------------------------------------------------------
# Pattern catalog (kept small and intentional - this is a heuristic layer)
# --------------------------------------------------------------------------


# A short, conservative set of patterns used by the format check. Kept
# here so downstream consumers can extend it without modifying the
# implementation module.
_BALANCED_FENCES_RE = re.compile(r"```")


def balanced_code_fences(text: str) -> bool:
    """True if the number of triple-backtick fences in ``text`` is even.

    A single unbalanced fence means the output contains a partial code
    block that no parser can render.
    """
    return len(_BALANCED_FENCES_RE.findall(text)) % 2 == 0
