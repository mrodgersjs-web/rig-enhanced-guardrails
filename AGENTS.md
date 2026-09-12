# AGENTS.md — rig-enhanced-guardrails

Tactical Agentic Coding (TAC) doctrine for this repository. This file is
the hierarchical context root: any agent (human or LLM) touching this repo
reads this before touching `src/`.

## What this repo is

A reference implementation of **proof-gated LLM output validation**. It
takes the guardrails-ai/guardrails concept — run a set of checks over an
LLM's output, decide pass/fail — and adds the missing piece: the pass/fail
decision itself is a claim, and claims from the system under test are not
proof. This repo makes the validation step produce **evidence** (a signed
ProofPacket) instead of just a boolean, and makes checking that evidence
**someone else's job**.

## The Core Four

Every change to this repo is evaluated against four questions, in order:

1. **Does it work?** Run it. `python3 -m src.guard --output "..."` must
   produce a real, signed ProofPacket — not a mock, not a `TODO`.
2. **Can it be verified independently?** If a check, a field, or a claim
   can only be confirmed by asking the component that made the claim, it
   is not verified — it's an assertion. Everything load-bearing in this
   repo routes through `verify.py`, which never imports `guard.py`.
3. **Does it fail loudly and specifically?** A red ProofPacket carries a
   `reason` naming the exact failing check and the exact evidence. Silent
   failure, generic "validation failed" messages, and swallowed
   exceptions are bugs.
4. **Is the loop closed?** `.rig/smoke.sh` and `.rig/verify.sh` must both
   exit 0 before any change here is considered done. A green pytest run
   alone is not the bar — see L10/L8 below.

## Builder ≠ Verifier (non-negotiable)

This is the single most important structural rule in this codebase:

- `src/guard.py` is the **Builder**. It owns all four validation checks
  (`json_schema`, `toxicity`, `factuality`, `format`) and seals its
  verdict into a ProofPacket, signed with an HMAC key.
- `src/verify.py` is the **Verifier**. It is a *separate module* that
  **does not import `guard.py`**, does not re-run its checks, and does
  not trust its `status` field. It only:
  1. recomputes the HMAC signature over the packet's payload and
     compares it (constant-time) against the stored signature,
  2. independently recomputes what `status` *should* be from the raw
     `checks` dict and compares that to what the packet *claims*, and
  3. (optionally) recomputes the output's hash from independently
     supplied text and compares it to `output_hash`.
- `src/proofpacket.py` is shared **infrastructure only** — canonicalization,
  hashing, HMAC sign/verify primitives. It contains zero validation logic
  and zero trust decisions. Both Guard and Verifier depend on it; neither
  depends on the other.

If you ever find yourself importing `from src.guard import Guard` inside
`verify.py` (or vice versa) to "simplify" something, stop — you are about
to collapse the Builder/Verifier boundary that makes the ProofPacket mean
anything. The whole point is that an attacker who can make the Guard lie
still can't make the Verifier agree, because the Verifier never asks the
Guard.

## Closed-loop architecture

```
   LLM output
       |
       v
  +----------+     seals verdict as        +------------------+
  |  Guard   | --------------------------> |   ProofPacket     |
  | (Builder)|   signed HMAC-SHA256 JSON   | (status + checks  |
  +----------+                              |  + hashes + sig)  |
                                             +------------------+
                                                      |
                                                      v
                                             +------------------+
                                             |    Verifier      |
                                             | (independent)    |
                                             |  1. sig valid?   |
                                             |  2. status       |
                                             |     consistent   |
                                             |     with checks? |
                                             |  3. output hash  |
                                             |     matches?     |
                                             +------------------+
                                                      |
                                                      v
                                          overall_valid: true/false
```

The loop closes at two independent levels:

- **Per-artifact**: every `Guard.validate()` call produces a packet that
  `Verifier.verify()` can check without any shared state beyond the
  signing key. Tamper with one field after sealing and the signature
  breaks; tamper with `status` alone and the recomputed-from-checks
  consistency check breaks too.
- **Per-change to this repo**: `.rig/smoke.sh` (L10) runs the Guard and
  Verifier as real subprocesses across six scenarios — including two
  tamper attempts — and appends any failure to `.rig/hardening-log.md` so
  the regression surface only grows. `.rig/verify.sh` (L8) wraps that
  plus syntax, unit, integration, eval-discrimination, and artifact-audit
  layers, and seals its own run result as a ProofPacket in
  `.rig/last-l8-run.json` — so "the L8 run passed" is itself a checkable
  claim, not a self-report.

## Working in this repo

- Never add a check to `Guard` that can only ever return `passed: True`
  (or only `False`) — every check must be shown to discriminate, and L4
  of `.rig/verify.sh` enforces this with real known-good/known-bad pairs.
- Never let `Verifier` accept a packet on the strength of its `status`
  field alone. Signature validity and logical consistency are separate,
  both-required checks — see `test_status_forged_to_green_without_editing_checks_still_caught`
  in `test/test_guard.py` for why.
- `RIG_PROOF_HMAC_KEY` must be set for any non-demo use. The fallback key
  in `src/proofpacket.py` exists only so this repo runs out of the box;
  it prints a warning every time it's used and must never ship in a real
  deployment.
- Before committing: `bash .rig/smoke.sh && bash .rig/verify.sh`. Both
  must exit 0.

## RIG lattice contract (stamped)

This repository runs the shared RIG lattice: loops in `.rig/loop.yaml`, pre-tool
hooks in `.rig/hooks/`, CI gate in `.github/workflows/rig-lattice.yml`, execution
owner routing in `.rig/work-routing.yaml` (operator standard 2026-09-11), and a
results-driven MCP server at `mcp/server.py` returning verified results only.
D85 rules apply: every outward action needs a Gate-D request + typed approval;
durable builds need four ratios >= 0.85 and a sealed proof. Done-claims need TAC
close-gate sealed evidence. Shared agent substrate lives in Supabase schema
`rig_shared` (see PROGRAM.md in rig-lattice-retrofit).
