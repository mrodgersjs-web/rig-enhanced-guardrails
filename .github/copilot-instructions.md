# rig-enhanced-guardrails copilot instructions

## What it is
Independent reimplementation of the guardrails-ai concept. A
Guard seals a verdict into a signed ProofPacket; a Verifier
(one that never imports the Guard) recomputes the claim.

## Layout
- `src/`: `guard.py`, `verify.py`, `proofpacket.py`, `_main.py`.
- `tests/`: pytest suite.
- `.rig/smoke.sh`: smoke shell.
- `.github/workflows/ci.yml`: matrix pytest (3.10-3.13).

## Setup and tests
```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

The CLI scripts are `rig-guard` and `rig-verify`.

## Conventions
Conventional commits. Tests for every public-code change. No
secrets (`RIG_PROOF_HMAC_KEY` is per CI run only). No machine
paths (`/Users/...`, `~/Developer/...`, `$HOME/Developer/...`).
No prices; no client names; no credential/military/personnel
claims. Banned words: unlock, empower, synergy, leverage,
disrupt, hustle, utilize, iterate, optimize. No em dashes.

## Truth rule
Every README number must come from a command you just ran.

## Coverage
The CI `test` job runs `pytest -q` first (gates the build) and
`coverage run -m pytest` as a separate step with its own
timeout-minutes so a hung coverage subprocess cannot hold the
whole job open.

## Do not touch
The `Ver` HMAC algorithm and the `ProofPacket` v1 contract.

## Done-test
`ruff check .` and `pytest -q` clean on a fresh venv.
