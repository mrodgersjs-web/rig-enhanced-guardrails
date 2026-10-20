"""Every GitHub Actions workflow in this repo must be valid YAML with at least one job.

GitHub marks an unparsable workflow as a failed run named after its path; this test
catches that locally before it reaches CI.
"""
from pathlib import Path

import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def test_workflows_exist():
    assert WORKFLOWS


def test_every_workflow_parses_and_has_jobs():
    for path in WORKFLOWS:
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict), path.name
        assert data.get("jobs"), f"{path.name} has no jobs"
