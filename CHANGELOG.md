# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-19

### Added

- `src/validators.py` exposing the four checks (json_schema, toxicity,
  factuality, format) as a small public API for downstream tooling.
- `test/test_validators.py` with 12 unit tests for the public API.
- `src/py.typed` marker.
- `SECURITY.md` covering supported versions, threat model, and
  secret-handling rules.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/dependabot.yml`,
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`,
  `.github/PULL_REQUEST_TEMPLATE.md`.
- Matrix CI on Python 3.10-3.13 with ruff.

### Changed

- README rewritten to use the public-action style (H1, badges,
  usage-first, mermaid diagram, development section, project layout).
- Em dashes replaced with hyphens across Python and Markdown files.
- pyproject.toml bumped to 0.2.0; adds `py.typed`, ruff config, and a
  wider python_requires floor.

## [0.1.0] - 2026-09-08

### Added

- Initial release: Guard, Verifier, and ProofPacket signing modules
  with 16 tests.
