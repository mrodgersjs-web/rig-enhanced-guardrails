"""Repo-hygiene assertions checked into the repo and run by `pytest -q`.

This file was added by the polish wave to exercise the four
polish-brief items on the disk after every commit. The cases
are intentionally compact: each one reads files from disk
and asserts a single concrete property.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_codeowners_routes_to_org() -> None:
    co = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert any("* @mrodgersjs-web" in line for line in co.splitlines())


def test_copilot_file_size_and_test_word() -> None:
    p = ROOT / ".github" / "copilot-instructions.md"
    assert p.exists()
    assert p.stat().st_size <= 8000
    assert "pytest" in p.read_text(encoding="utf-8").lower()


def test_readme_badge_and_footer_and_self_clone() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(
        r"https://img\.shields\.io/github/actions/workflow/status/"
        r"mrodgersjs-web/rig-enhanced-guardrails/[^/?]+\?[^\s)]*\bbranch=",
        text,
    )
    assert "rodgersintelligence.com" in text
    assert "git clone https://github.com/mrodgersjs-web/rig-enhanced-guardrails" in text


def test_workflow_jobs_have_timeouts_no_continue_on_error() -> None:
    workflows = list((ROOT / ".github" / "workflows").rglob("*.yml"))
    assert workflows
    for wf in workflows:
        text = wf.read_text(encoding="utf-8")
        assert "continue-on-error" not in text, f"{wf.name} uses continue-on-error"
        # ci.yml's documented coverage fix uses a coverage step.
        assert "timeout-minutes" in text


def test_ci_uses_coverage_run_subprocess_for_coverage() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "coverage run -m pytest" in ci, (
        "ci.yml must invoke 'coverage run -m pytest' on its own step"
    )


def test_gitignore_excludes_coverage_artifact() -> None:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".coverage" in gi


def test_ci_triggers_on_push_and_pull_request() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s+push:\s*$", ci)
    assert re.search(r"(?m)^\s+pull_request:\s*$", ci)
