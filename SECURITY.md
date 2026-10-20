# Security Policy

## Supported versions

| Version | Supported |
| :-- | :-: |
| `main` branch | yes |
| latest tagged release | yes |
| older releases | best effort |

`rig-enhanced-guardrails` is stdlib-only Python with no runtime
dependencies. The signing primitive is `hmac.compare_digest` from the
standard library.

## Threat model in scope

The library exists so that an LLM validation decision is a signed,
independently-verifiable record. The signer (Guard) and the verifier
(Verifier) are designed to be used by separate processes that share
only the signing key. The verifier does NOT import the guard's
validation logic.

The library is in scope for:

- secret strength of the HMAC key
- secret leakage into logs, packets, or error messages
- HMAC key rotation
- algorithm choice (HMAC-SHA256, hex-encoded)

The library is OUT of scope for:

- the semantic correctness of the heuristic checks (toxicity,
  factuality placeholder). Those are documented placeholders that need
  domain-specific tuning.

## Reporting a vulnerability

Please email **security@rodgersintelligence.com** with:

- a description of the issue and impact
- the commit SHA or tag you reproduced against
- a minimal reproduction

We aim to acknowledge within 3 business days. Please do not file a
public issue for a security report.

## Secret handling

The signing key is passed in as `bytes` and never logged. Do not write
the key to disk, do not print it, do not pass it through a logging
formatter. Production deployments should read it from an environment
variable or a secrets manager and pass it directly to the Guard or
Verifier constructor.
