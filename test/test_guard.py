"""
test_guard.py — pytest suite covering valid/invalid/tampered scenarios.

Tests exercise the real Guard + Verifier objects (no mocking of the
cryptographic path) so a broken signature scheme or a broken check would
actually fail these tests.
"""

from __future__ import annotations

import copy
import json

import pytest

from src.guard import Guard, check_factuality_placeholder, check_toxicity
from src.verify import Verifier

FIXED_KEY = b"test-fixed-key-not-for-production"
FIXED_KEY_ID = "test-key-id"


@pytest.fixture
def guard() -> Guard:
    return Guard(key=FIXED_KEY, key_id=FIXED_KEY_ID)


@pytest.fixture
def verifier() -> Verifier:
    return Verifier(key=FIXED_KEY, key_id=FIXED_KEY_ID)


# --------------------------------------------------------------------------
# Valid output
# --------------------------------------------------------------------------


def test_valid_output_produces_green_packet(guard: Guard):
    output = "The forecast calls for mild temperatures and light wind."
    packet = guard.validate(output, input_text="what is the forecast?")

    assert packet["status"] == "green"
    assert packet["reason"] is None
    assert all(c["passed"] for c in packet["checks"].values())
    assert "signature" in packet
    assert len(packet["signature"]) == 64  # sha256 hex digest length


def test_valid_output_verifies_successfully(guard: Guard, verifier: Verifier):
    output = "Paris is a city in France known for its architecture."
    packet = guard.validate(output)

    result = verifier.verify(packet, expected_output=output)

    assert result.overall_valid is True
    assert result.signature_valid is True
    assert result.status_consistent is True
    assert result.output_matches is True
    assert result.reasons == []


# --------------------------------------------------------------------------
# Invalid output (toxic / bad schema / bad format)
# --------------------------------------------------------------------------


def test_toxic_output_produces_red_packet(guard: Guard):
    output = "You are such an idiot, shut up, you are worthless."
    packet = guard.validate(output)

    assert packet["status"] == "red"
    assert packet["reason"] is not None
    assert "toxicity" in packet["reason"]
    assert packet["checks"]["toxicity"]["passed"] is False


def test_red_packet_still_verifies_as_internally_consistent(
    guard: Guard, verifier: Verifier
):
    """A correctly-signed red packet is a VALID proof of failure — the
    Verifier's job is to confirm the packet is authentic and internally
    consistent, not to demand a green outcome."""
    output = "You are such an idiot, shut up, you are worthless."
    packet = guard.validate(output)

    result = verifier.verify(packet, expected_output=output)

    assert packet["status"] == "red"
    assert result.overall_valid is True  # the RED claim itself checks out
    assert result.status_consistent is True


def test_schema_violation_fails_json_schema_check(guard: Guard):
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    bad_output = json.dumps({"wrong_field": "value"})

    packet = guard.validate(bad_output, schema=schema)

    assert packet["status"] == "red"
    assert packet["checks"]["json_schema"]["passed"] is False
    assert "answer" in packet["checks"]["json_schema"]["detail"]


def test_schema_valid_output_passes(guard: Guard):
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    good_output = json.dumps({"answer": "42"})

    packet = guard.validate(good_output, schema=schema)

    assert packet["checks"]["json_schema"]["passed"] is True


def test_empty_output_fails_format_check(guard: Guard):
    packet = guard.validate("   ")

    assert packet["status"] == "red"
    assert packet["checks"]["format"]["passed"] is False


def test_overlong_output_fails_format_check(guard: Guard):
    packet = guard.validate("x" * 100, max_length=50)

    assert packet["checks"]["format"]["passed"] is False
    assert "max_length" in packet["checks"]["format"]["detail"]


def test_unbalanced_code_fences_fail_format_check(guard: Guard):
    packet = guard.validate("here is some code ```python\nprint(1)\n")

    assert packet["checks"]["format"]["passed"] is False


def test_factuality_placeholder_flags_unsourced_absolute_claim():
    passed, detail = check_factuality_placeholder(
        "This treatment is 100% guaranteed to work with zero risk."
    )
    assert passed is False
    assert "unverified" in detail


def test_factuality_placeholder_allows_sourced_absolute_claim():
    passed, _ = check_factuality_placeholder(
        "This treatment is guaranteed to work according to [1]."
    )
    assert passed is True


def test_toxicity_check_is_deterministic():
    r1 = check_toxicity("a perfectly normal sentence")
    r2 = check_toxicity("a perfectly normal sentence")
    assert r1 == r2


# --------------------------------------------------------------------------
# Tampered ProofPacket
# --------------------------------------------------------------------------


def test_tampered_status_field_fails_signature_verification(
    guard: Guard, verifier: Verifier
):
    output = "This is a perfectly fine, boring, valid sentence."
    packet = guard.validate(output)
    assert packet["status"] == "green"

    tampered = copy.deepcopy(packet)
    # Flip a real failure's outcome without re-signing — simulates an
    # attacker trying to launder a red packet into a green one.
    tampered["checks"]["toxicity"]["passed"] = False
    tampered["status"] = "red"

    result = verifier.verify(tampered, expected_output=output)

    assert result.overall_valid is False
    assert result.signature_valid is False
    assert any("signature mismatch" in r for r in result.reasons)


def test_tampered_output_hash_is_caught_by_output_binding(
    guard: Guard, verifier: Verifier
):
    output = "Original approved sentence."
    packet = guard.validate(output)

    swapped_output = "This is a completely different sentence."
    result = verifier.verify(packet, expected_output=swapped_output)

    assert result.overall_valid is False
    assert result.output_matches is False
    assert any("output_hash mismatch" in r for r in result.reasons)


def test_wrong_key_fails_verification(guard: Guard):
    output = "Some benign output text."
    packet = guard.validate(output)

    wrong_key_verifier = Verifier(key=b"totally-different-key", key_id="other")
    result = wrong_key_verifier.verify(packet, expected_output=output)

    assert result.overall_valid is False
    assert result.signature_valid is False


def test_status_forged_to_green_without_editing_checks_still_caught(
    guard: Guard, verifier: Verifier
):
    """Even a single-field tamper (only `status`, checks left alone) must
    be caught by the signature — that is the entire point of signing the
    whole payload rather than just a status flag."""
    output = "idiot shut up worthless"  # will legitimately fail toxicity
    packet = guard.validate(output)
    assert packet["status"] == "red"

    tampered = copy.deepcopy(packet)
    tampered["status"] = "green"
    tampered["reason"] = None

    result = verifier.verify(tampered, expected_output=output)

    assert result.overall_valid is False
    assert result.signature_valid is False
