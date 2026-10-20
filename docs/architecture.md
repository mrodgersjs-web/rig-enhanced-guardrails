# Architecture

`rig-enhanced-guardrails` separates validation from verification. The
Guard is the only module that decides if an output passes; the Verifier
checks that the packet the Guard produced is authentic and internally
consistent.

## Why two modules

A self-reporting guardrail can be tampered with. If the Guard both
decides and verifies its own decision, an attacker (or a buggy upgrade)
can flip a red packet to green without anyone noticing. Splitting the
two roles means the verifier never re-runs the guard's checks; it only
checks the cryptographic signature, the output binding, and the
internal consistency of the packet.

## Public surface

| Class / function | Purpose |
| :-- | :-- |
| `Guard.validate(output, ...)` | Run all four checks and sign the result |
| `Verifier.verify(packet, expected_output)` | Check signature, output binding, status consistency |
| `proofpacket.sign(payload, key)` | Low-level HMAC-SHA256 hex signer |
| `proofpacket.verify(payload, signature, key)` | Constant-time signature check |
| `validators.check_json_schema(value, schema)` | Standalone JSON-schema check |
| `validators.check_toxicity_callable(text)` | Standalone toxicity check |
| `validators.check_factuality(text)` | Standalone factuality placeholder |
| `validators.check_format_callable(text, max_length)` | Standalone format check |
| `validators.run_checks(text, schema, max_length, only)` | Run a named subset of the four checks |
| `validators.balanced_code_fences(text)` | True if triple-backtick fences are even |

The four `validators.check_*` functions are pure re-exports of the
helpers used inside `Guard.validate`, kept under a stable import path so
downstream tooling does not depend on the internal `src.guard` module.

## Packet shape

The ProofPacket is a JSON document with these fields:

| Field | Type | Notes |
| :-- | :-- | :-- |
| `status` | `"green" \| "red"` | Overall verdict across the four checks |
| `reason` | `string \| null` | Human-readable reason when red, `None` when green |
| `checks` | object | Per-check result with `passed` and `detail` |
| `output_hash` | string | SHA-256 hex digest of the validated output |
| `signature` | string | HMAC-SHA256 hex over the canonical payload |
| `key_id` | string | Optional identifier for the signing key |
| `ts` | string | ISO-8601 timestamp the packet was produced |
| `packet_type` | string | Constant `"rig.guard.validation"` for this library |

The verifier recomputes `hash(raw_output) == output_hash`, recomputes
`signature` from the packet's fields, and flags the packet as invalid if
either check fails.

## When the verifier says a packet is invalid

| Verifier field | Reason |
| :-- | :-- |
| `signature_valid=False` | signature mismatch (payload edited or wrong key) |
| `output_matches=False` | `output_hash` mismatch (the output text was swapped) |
| `status_consistent=False` | `status` disagrees with the per-check `passed` flags |

Any of those flags makes `overall_valid=False`. A red packet that
verifies green is the failure mode; an incomplete verifier signature is
also a failure.

## Threat model in scope

- secret strength of the HMAC key (recommend 32+ random bytes)
- secret leakage into logs, packets, or error messages (the library
  never logs the key)
- HMAC key rotation (a `key_id` field is provided so a Verifier can
  reject a packet signed by a retired key)

## Out of scope

- semantic correctness of the heuristic checks. The toxicity and
  factuality checks are intentionally simple; production deployments
  should tune them or replace them with domain-specific models.
