"""
guard.py — the Builder. Validates LLM output and seals the result in a
signed ProofPacket.

Per TAC doctrine (Builder != Verifier), this module is the ONLY place
validation checks are implemented. verify.py deliberately does NOT import
anything from this file except (indirectly, via proofpacket.py) the
signing primitives — an independent Verifier must never re-run the
Builder's own logic to "confirm" its own claim.

Four checks run on every call to Guard.validate():
  1. json_schema  — structural validation against an optional schema
  2. toxicity     — lexicon/heuristic toxicity scoring
  3. factuality   — PLACEHOLDER heuristic for unverifiable absolute claims
                    (true factuality checking needs retrieval; this is a
                    documented, functioning heuristic, not a stub)
  4. format       — basic well-formedness (length, encoding, fences)

Guard.validate() ALWAYS returns a fully signed ProofPacket: green when
every check passes, red (with `reason`) the moment any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from src import proofpacket as pp

# --------------------------------------------------------------------------
# Check 1: JSON schema
# --------------------------------------------------------------------------

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _validate_json_schema(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Minimal recursive JSON-schema validator (stdlib only).

    Supports: type, required, properties, items, enum — enough to catch
    the structural defects that matter for guardrails use cases without
    pulling in an external `jsonschema` dependency.
    """
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type:
        py_type = _TYPE_MAP.get(expected_type)
        if py_type is None:
            errors.append(f"{path}: unknown schema type '{expected_type}'")
        elif expected_type == "integer" and isinstance(value, bool):
            errors.append(f"{path}: expected integer, got boolean")
        elif not isinstance(value, py_type):
            errors.append(
                f"{path}: expected {expected_type}, got {type(value).__name__}"
            )
            return errors  # further checks meaningless on wrong type

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

    if expected_type == "object" and isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                errors.extend(
                    _validate_json_schema(value[key], subschema, f"{path}.{key}")
                )

    if expected_type == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(
                    _validate_json_schema(item, item_schema, f"{path}[{i}]")
                )

    return errors


def check_json_schema(output: str, schema: dict | None) -> tuple[bool, str]:
    if schema is None:
        return True, "no schema provided — structural check skipped"
    try:
        parsed = json.loads(output) if isinstance(output, str) else output
    except json.JSONDecodeError as exc:
        return False, f"output is not valid JSON: {exc}"
    errors = _validate_json_schema(parsed, schema)
    if errors:
        return False, "; ".join(errors)
    return True, "output conforms to schema"


# --------------------------------------------------------------------------
# Check 2: toxicity (lexicon-based heuristic — real, deterministic, not a
# stub; not a state-of-the-art classifier)
# --------------------------------------------------------------------------

_SEVERE_TERMS = {
    "kill you",
    "i hope you die",
    "subhuman",
}
_MILD_TERMS = {
    "idiot",
    "stupid",
    "shut up",
    "hate you",
    "worthless",
    "moron",
    "pathetic",
}
_TOXICITY_SCORE_THRESHOLD = 0.02


def check_toxicity(output: str) -> tuple[bool, str]:
    text = output.lower()
    for term in _SEVERE_TERMS:
        if term in text:
            return False, f"severe toxic phrase detected: '{term}'"

    words = re.findall(r"[a-z']+", text)
    word_count = max(len(words), 1)
    matches = [term for term in _MILD_TERMS if term in text]
    score = len(matches) / word_count

    if score >= _TOXICITY_SCORE_THRESHOLD:
        return False, (
            f"toxicity score {score:.4f} >= threshold "
            f"{_TOXICITY_SCORE_THRESHOLD}; matched terms: {matches}"
        )
    return True, f"toxicity score {score:.4f} below threshold; no severe terms"


# --------------------------------------------------------------------------
# Check 3: factuality — PLACEHOLDER heuristic
# --------------------------------------------------------------------------

_OVERCONFIDENT_PATTERN = re.compile(
    r"\b(always|never|guaranteed|100%|proven fact|undeniably|"
    r"everyone knows|impossible to fail|zero risk)\b",
    re.IGNORECASE,
)
_EVIDENCE_MARKERS = ("[", "according to", "source:", "citation", "(see ", "http")


def check_factuality_placeholder(output: str) -> tuple[bool, str]:
    """NOT true factuality checking (that requires retrieval + a knowledge
    base). This heuristic flags absolute/overconfident claims that carry
    no adjacent evidence marker, which is a real, useful, and honest
    signal on its own — but it is explicitly a placeholder for a fuller
    factuality pipeline.
    """
    matches = _OVERCONFIDENT_PATTERN.findall(output)
    if not matches:
        return True, "no unverified absolute claims detected"
    has_evidence = any(marker in output.lower() for marker in _EVIDENCE_MARKERS)
    if has_evidence:
        return True, (
            f"absolute claim(s) {matches} present but adjacent evidence "
            "marker found — treated as sourced"
        )
    return False, (
        f"unverified absolute claim(s) with no evidence marker: {matches} "
        "(factuality placeholder heuristic — not a full fact-check)"
    )


# --------------------------------------------------------------------------
# Check 4: format
# --------------------------------------------------------------------------


def check_format(output: str, max_length: int = 4000) -> tuple[bool, str]:
    if not isinstance(output, str):
        return False, f"output must be a string, got {type(output).__name__}"
    if len(output.strip()) == 0:
        return False, "output is empty"
    if "\x00" in output:
        return False, "output contains null bytes"
    if len(output) > max_length:
        return False, f"output length {len(output)} exceeds max_length {max_length}"
    fence_count = output.count("```")
    if fence_count % 2 != 0:
        return False, "unbalanced markdown code fences (```)"
    control_chars = [c for c in output if ord(c) < 32 and c not in "\n\r\t"]
    if control_chars:
        return False, f"output contains {len(control_chars)} disallowed control char(s)"
    return True, "output is well-formed"


# --------------------------------------------------------------------------
# Guard
# --------------------------------------------------------------------------

CHECK_NAMES = ("json_schema", "toxicity", "factuality", "format")


class Guard:
    """Validates LLM output and seals the result in a signed ProofPacket."""

    def __init__(self, key: bytes | None = None, key_id: str | None = None):
        if key is None or key_id is None:
            loaded_key, loaded_key_id = pp.load_key()
            key = key if key is not None else loaded_key
            key_id = key_id if key_id is not None else loaded_key_id
        self.key = key
        self.key_id = key_id

    def validate(
        self,
        output: str,
        input_text: str = "",
        schema: dict | None = None,
        max_length: int = 4000,
    ) -> dict:
        """Run all four checks and return a signed ProofPacket (dict)."""
        results: dict[str, dict] = {}

        passed, detail = check_json_schema(output, schema)
        results["json_schema"] = {"passed": passed, "detail": detail}

        passed, detail = check_toxicity(output)
        results["toxicity"] = {"passed": passed, "detail": detail}

        passed, detail = check_factuality_placeholder(output)
        results["factuality"] = {"passed": passed, "detail": detail}

        passed, detail = check_format(output, max_length=max_length)
        results["format"] = {"passed": passed, "detail": detail}

        failing = [name for name in CHECK_NAMES if not results[name]["passed"]]
        status = "red" if failing else "green"
        reason = None
        if failing:
            reason = "; ".join(
                f"{name}: {results[name]['detail']}" for name in failing
            )

        payload = {
            "packet_type": pp.PACKET_TYPE_GUARD_VALIDATION,
            "schema_version": pp.PACKET_SCHEMA_VERSION,
            "timestamp": pp.utc_timestamp(),
            "input_hash": pp.sha256_hex(input_text),
            "output_hash": pp.sha256_hex(output if isinstance(output, str) else ""),
            "checks": results,
            "status": status,
            "reason": reason,
        }
        return pp.seal(payload, self.key, self.key_id)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.guard",
        description="Validate LLM output and emit a signed ProofPacket.",
    )
    parser.add_argument("--output", help="output text to validate")
    parser.add_argument(
        "--output-file", help="path to a file containing the output text"
    )
    parser.add_argument("--input", default="", help="original prompt/input text")
    parser.add_argument("--schema", help="path to a JSON schema file")
    parser.add_argument("--max-length", type=int, default=4000)
    parser.add_argument("--out", help="write the ProofPacket JSON to this path")
    args = parser.parse_args(argv)

    if args.output is not None:
        output_text = args.output
    elif args.output_file:
        with open(args.output_file, "r", encoding="utf-8") as f:
            output_text = f.read()
    else:
        output_text = sys.stdin.read()

    schema = None
    if args.schema:
        with open(args.schema, "r", encoding="utf-8") as f:
            schema = json.load(f)

    guard = Guard()
    packet = guard.validate(
        output_text, input_text=args.input, schema=schema, max_length=args.max_length
    )

    packet_json = json.dumps(packet, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(packet_json + "\n")
    print(packet_json)

    return 0 if packet["status"] == "green" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
