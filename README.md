# RIG-Enhanced Guardrails — LLM output validation with proof-gated completion

A reference implementation of the **RIG doctrine overlay** applied to the
[guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails)
concept: validating LLM output against a set of checks before it's allowed
downstream.

This is **not** a fork of guardrails-ai. It's an independent, from-scratch
reimplementation of the *concept* — a `Guard` that checks output — with one
structural difference that changes everything downstream of it: **the
validation decision is not a boolean you trust, it's a signed artifact you
verify.**

## Before / after

| | Standard guardrails | RIG-enhanced guardrails |
|---|---|---|
| **What you get back** | `True` / `False` (or a raised exception) | A signed **ProofPacket**: status, per-check results, content hashes, timestamp, HMAC-SHA256 signature |
| **Who decides "it passed"** | The validator itself | The validator *claims* a status; an **independent Verifier** — a separate process/module that never imports the validator's logic — recomputes the claim from raw evidence and confirms or rejects it |
| **What happens if the result is altered downstream** | Nothing catches it — a boolean is just a boolean | Any single-byte change to the packet (status, a check's `passed` flag, a hash, the reason string) breaks the HMAC signature; the Verifier rejects it |
| **What happens if the validator has a logic bug** (checks fail internally but `status` gets set wrong) | Silent — you get the boolean the code produced, correct or not | Caught: the Verifier recomputes `status` from the raw `checks` dict independently of what the packet *claims*, and flags any mismatch even when the signature is cryptographically valid |
| **Can the output be swapped after validation and the "pass" reused?** | Yes — nothing binds the verdict to specific text | No — `output_hash` binds the packet to the exact output text; the Verifier recomputes the hash from independently-supplied text and rejects a mismatch |
| **A failed validation** | An exception, or a `False` with maybe a message | A `red` ProofPacket — still cryptographically signed, still independently verifiable as an *authentic record of failure* |
| **Auditability** | Whatever your logs happened to capture | The ProofPacket itself is the audit record — self-contained, tamper-evident, replayable |

## Architecture: Builder ≠ Verifier

Per [TAC doctrine](AGENTS.md), the Guard (Builder) and the Verifier are
kept structurally separate — the Verifier never imports or calls into the
Guard's validation logic:

```
LLM output
    |
    v
+----------+   seals verdict as    +--------------------+
|  Guard   | ---------------------> |    ProofPacket     |
| (Builder)|  signed HMAC-SHA256   | status + checks +   |
+----------+       JSON             | hashes + signature  |
                                    +--------------------+
                                              |
                                              v
                                    +--------------------+
                                    |     Verifier        |
                                    |  (independent)       |
                                    |  1. signature valid?  |
                                    |  2. status consistent |
                                    |     with raw checks?  |
                                    |  3. output hash        |
                                    |     matches supplied   |
                                    |     text?               |
                                    +--------------------+
                                              |
                                              v
                                  overall_valid: true / false
```

Four checks run inside `Guard.validate()` on every call:

1. **`json_schema`** — minimal recursive structural validator (type,
   required, properties, enum, items) run when a schema is supplied;
   skipped (and marked `passed: true`) when it isn't.
2. **`toxicity`** — lexicon/heuristic scorer: severe terms auto-fail,
   milder terms accumulate a score compared against a threshold. Real,
   deterministic logic — not a state-of-the-art classifier, and it says
   so.
3. **`factuality`** — an explicitly-labeled *placeholder* heuristic that
   flags unverified absolute claims (`always`, `guaranteed`, `100%`, …)
   with no adjacent evidence marker. True factuality checking needs
   retrieval against a knowledge base; this is a real, functioning,
   honestly-scoped stand-in for that pipeline stage.
4. **`format`** — non-empty, no null bytes, under a max length, balanced
   markdown code fences, no disallowed control characters.

## Quickstart

```bash
pip install -e .

export RIG_PROOF_HMAC_KEY="your-secret-key-here"

# Validate output and seal a ProofPacket
python3 -m src.guard --output "The forecast is mild with light wind." \
  --out packet.json

# Independently verify it — verify.py never imports guard.py
python3 -m src.verify packet.json
```

Programmatic use:

```python
from src.guard import Guard
from src.verify import Verifier

guard = Guard()          # loads RIG_PROOF_HMAC_KEY from the environment
verifier = Verifier()    # loads the same key independently

output = "The forecast is mild with light wind."
packet = guard.validate(output, input_text="what's the forecast?")

print(packet["status"])  # "green" or "red"

result = verifier.verify(packet, expected_output=output)
print(result.overall_valid)   # True only if signature + status + hash all check out
print(result.reasons)         # non-empty list explaining any failure
```

A failed validation still produces a fully signed, independently
verifiable packet — the point is not to guarantee green, it's to
guarantee **the record of what happened is authentic**:

```python
toxic_output = "You are such an idiot, shut up, you are worthless."
packet = guard.validate(toxic_output)
print(packet["status"])          # "red"
print(packet["reason"])          # "toxicity: toxicity score 0.30... "

result = verifier.verify(packet, expected_output=toxic_output)
print(result.overall_valid)      # True — the RED claim itself is authentic
```

## Verification layers

- **`.rig/smoke.sh`** — L10 self-evolving smoke test. Runs the Guard and
  Verifier as real subprocesses across 8 scenarios: valid output, toxic
  output, a tampered packet, a swapped-output attack, a wrong signing
  key, and a schema-invalid payload. Any failure is appended to
  `.rig/hardening-log.md` so the regression surface only grows across
  runs.
- **`.rig/verify.sh`** — L8 eight-layer verification: syntax → unit →
  integration → eval (checks demonstrably discriminate pass/fail, not
  just always-true/always-false) → proof (a genuine packet verifies, a
  tampered one doesn't) → gate (runs the full L10 smoke suite) → audit
  (required doctrine artifacts present) → sign-off (the L8 run itself is
  sealed as a ProofPacket at `.rig/last-l8-run.json`).
- **`spec/features/proof-gated-validation.feature`** — OpenSpec/Gherkin
  scenarios covering valid output, toxic output, and tampered packets as
  executable behavior specs.
- **`test/test_guard.py`** — pytest suite: 16 tests across valid,
  invalid (toxic / schema-violating / malformed), and tampered-packet
  scenarios, exercising the real cryptographic path (no mocking).

Run everything:

```bash
bash .rig/smoke.sh
bash .rig/verify.sh
python3 -m pytest test/test_guard.py -v
```

## Benchmark

Single-threaded, measured on the reference implementation's dev machine
(CPython 3.11, Apple Silicon), 2,000-call average after warmup. These
numbers describe *this reference implementation's* overhead — they are
illustrative, not a formal cross-platform benchmark suite:

| Operation | Latency (avg) | Notes |
|---|---|---|
| Four checks only (no proof sealing) | ~0.004 ms/call | What a standard "boolean" guardrails validator does |
| `Guard.validate()` — checks + hash + HMAC seal | ~0.010 ms/call | Full ProofPacket construction and signing |
| `Verifier.verify()` — signature + consistency + hash bind | ~0.005 ms/call | Independent re-check, no shared state beyond the key |
| Combined guard + verify round trip | ~0.015 ms/call | ~67,000 round trips/sec, single thread |
| ProofPacket size | ~750 bytes (JSON) | One packet per validated output; trivial to store/replay |

The cost of proof-gating over a bare boolean check is a small, constant
HMAC-SHA256 + two SHA-256 hashes per validation — dwarfed in any real
deployment by the cost of the LLM call the output came from. The payoff
is that "this output passed validation" becomes a claim a *different*
piece of code can check, rather than one you have to trust the validator
told the truth about.

## Repository layout

```
README.md                                  — this file
AGENTS.md                                   — TAC doctrine: Core Four, Builder≠Verifier, closed-loop architecture
LICENSE                                     — MIT
pyproject.toml                              — pip installable, `rig-guard` / `rig-verify` CLI entry points
src/
  proofpacket.py                            — shared crypto primitives ONLY (canonicalize, hash, sign, verify)
  guard.py                                  — Builder: 4 checks + ProofPacket sealing
  verify.py                                 — Verifier: independent signature + consistency + output-binding checks
.rig/
  smoke.sh                                  — L10 self-evolving smoke test
  verify.sh                                 — L8 eight-layer verification
  hardening-log.md                          — append-only regression log written by smoke.sh
spec/features/
  proof-gated-validation.feature            — OpenSpec/Gherkin behavior specs
test/
  test_guard.py                             — pytest suite (16 tests, real crypto path, no mocking)
```

## License

MIT — see [LICENSE](LICENSE).
