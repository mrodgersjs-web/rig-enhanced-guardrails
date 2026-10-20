# Contributing

Thanks for considering a contribution. The library is stdlib-only on
purpose: no transitive supply-chain risk, no version drift.

## Local setup

```bash
git clone https://github.com/mrodgersjs-web/rig-enhanced-guardrails
cd rig-enhanced-guardrails
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
python3 -m pytest -q
```

## Making a change

1. Open an issue describing the problem and the proposed change.
2. Add or update tests in `test/` first.
3. Keep the library stdlib-only.
4. Run `ruff check .` and `python3 -m pytest -q` before opening a PR.
5. Use a Conventional Commits subject (`feat:`, `fix:`, `test:`,
   `docs:`, `build:`, `chore:`).

## Threat model

A guardrail decision is a signed record. Any change to the signing
scheme, the JSON layout, or the verifier's check set is a
backward-compatibility break. Discuss it in an issue first.

## Code of conduct

See `CODE_OF_CONDUCT.md`. By participating you agree to it.
