"""test_validators.py - exercises the public validators API."""

from __future__ import annotations

import json

import pytest

from src.validators import (
    CHECK_NAMES,
    balanced_code_fences,
    check_factuality,
    check_format_callable,
    check_json_schema,
    check_toxicity_callable,
    run_checks,
)


# --------------------------------------------------------------------------
# check_json_schema
# --------------------------------------------------------------------------


def test_check_json_schema_none_schema_passes():
    passed, detail = check_json_schema("anything", None)
    assert passed is True
    assert detail == ""


def test_check_json_schema_object_match_passes():
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    passed, _ = check_json_schema({"answer": "42"}, schema)
    assert passed is True


def test_check_json_schema_missing_required_fails():
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    passed, detail = check_json_schema({"wrong": "x"}, schema)
    assert passed is False
    assert "answer" in detail


def test_check_json_schema_wrong_type_fails():
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    passed, _ = check_json_schema({"answer": 42}, schema)
    assert passed is False


# --------------------------------------------------------------------------
# check_toxicity_callable
# --------------------------------------------------------------------------


def test_check_toxicity_clean_passes():
    passed, _ = check_toxicity_callable("a perfectly normal sentence")
    assert passed is True


def test_check_toxicity_insult_fails():
    passed, detail = check_toxicity_callable("you idiot shut up worthless")
    assert passed is False
    assert detail


# --------------------------------------------------------------------------
# check_factuality
# --------------------------------------------------------------------------


def test_check_factuality_absolute_unsourced_fails():
    passed, detail = check_factuality(
        "This treatment is 100% guaranteed to work with zero risk."
    )
    assert passed is False
    assert "unverified" in detail


def test_check_factuality_sourced_passes():
    passed, _ = check_factuality(
        "This treatment is guaranteed to work according to [1]."
    )
    assert passed is True


# --------------------------------------------------------------------------
# check_format_callable
# --------------------------------------------------------------------------


def test_check_format_empty_fails():
    passed, detail = check_format_callable("   ")
    assert passed is False


def test_check_format_overlong_fails():
    passed, detail = check_format_callable("x" * 100, max_length=50)
    assert passed is False
    assert "max_length" in detail


def test_check_format_unbalanced_fence_fails():
    passed, _ = check_format_callable("here is some code ```python\nprint(1)\n")
    assert passed is False


def test_check_format_balanced_fence_passes():
    passed, _ = check_format_callable("a ```python\nprint(1)\n``` block")
    assert passed is True


# --------------------------------------------------------------------------
# run_checks (subset whitelist)
# --------------------------------------------------------------------------


def test_run_checks_all_by_default():
    results = run_checks("A normal sentence about Paris.")
    assert set(results.keys()) == set(CHECK_NAMES)


def test_run_checks_only_subset():
    results = run_checks("A normal sentence about Paris.", only=("format",))
    assert set(results.keys()) == {"format"}


def test_run_checks_unknown_name_raises():
    with pytest.raises(ValueError):
        run_checks("text", only=("nonsense",))


def test_run_checks_schema_on_invalid_json_fails_schema_only():
    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    results = run_checks("not json", schema=schema)
    assert results["json_schema"][0] is False
    assert "JSON" in results["json_schema"][1]


# --------------------------------------------------------------------------
# balanced_code_fences
# --------------------------------------------------------------------------


def test_balanced_code_fences_zero():
    assert balanced_code_fences("plain text") is True


def test_balanced_code_fences_two():
    assert balanced_code_fences("```\ncode\n```") is True


def test_balanced_code_fences_one_fails():
    assert balanced_code_fences("```\ncode") is False


def test_balanced_code_fences_three_fails():
    assert balanced_code_fences("```a```b```") is False
