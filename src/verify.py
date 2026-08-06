"""
verify.py — the Verifier. Independently re-checks a ProofPacket's
signature. Per TAC doctrine (Builder != Verifier), this module
deliberately does NOT import guard.py or re-run any of its checks.

The Verifier trusts nothing the packet *claims* about itself:

  1. Cryptographic integrity — recompute the HMAC signature over the
     packet's own payload and compare (constant-time) against the stored
     signature. This is what catches tampering: change ANY field after
     sealing (status, a check's `passed` bit, a hash, the reason string)
     and the signature no longer matches.

  2. Logical consistency — independently recompute what `status` SHOULD
     be from the raw `checks` dict (green iff every check's `passed` is
     true) and compare that to the `status` field the packet asserts.
     This catches a *correctly signed but internally inconsistent*
     packet — e.g. a Guard bug that flips `status` to "green" while a
     check actually failed. A valid signature alone is NOT sufficient;
     the Verifier still audits the claim against its own evidence.

  3. Output binding (optional) — if the original output text is supplied
     independently, recompute its hash and compare against the packet's
     `output_hash`. This catches a swapped-output attack: presenting a
     genuinely-signed packet alongside a *different* piece of text than
     the one it was actually issued for.

A packet is only `overall_valid` when all checks that were run pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from src import proofpacket as pp


@dataclass
class VerificationResult:
    signature_valid: bool
    status_consistent: bool
    output_matches: bool | None  # None when no output was supplied to check
    reasons: list[str] = field(default_factory=list)

    @property
    def overall_valid(self) -> bool:
        checks = [self.signature_valid, self.status_consistent]
        if self.output_matches is not None:
            checks.append(self.output_matches)
        return all(checks)

    def to_dict(self) -> dict:
        return {
            "signature_valid": self.signature_valid,
            "status_consistent": self.status_consistent,
            "output_matches": self.output_matches,
            "overall_valid": self.overall_valid,
            "reasons": self.reasons,
        }


class Verifier:
    """Independent re-checker. Holds signing-key material only — never
    the Guard's validation logic."""

    def __init__(self, key: bytes | None = None, key_id: str | None = None):
        if key is None or key_id is None:
            loaded_key, loaded_key_id = pp.load_key()
            key = key if key is not None else loaded_key
            key_id = key_id if key_id is not None else loaded_key_id
        self.key = key
        self.key_id = key_id

    def verify(
        self, packet: dict[str, Any], expected_output: str | None = None
    ) -> VerificationResult:
        reasons: list[str] = []

        # 1. Cryptographic integrity — never trust the packet's own claim.
        sig_ok = pp.signature_valid(packet, self.key)
        if not sig_ok:
            reasons.append(
                "signature mismatch: packet payload does not match its "
                "signature — packet has been tampered with, corrupted, "
                "or was signed with a different key"
            )

        # Cross-check key_id, purely informational (signature check above
        # is what actually matters cryptographically).
        packet_key_id = packet.get(pp.KEY_ID_FIELD)
        if packet_key_id is not None and packet_key_id != self.key_id:
            reasons.append(
                f"key_id mismatch: packet claims key_id={packet_key_id!r}, "
                f"verifier is using key_id={self.key_id!r}"
            )

        # 2. Logical consistency — recompute status from raw checks,
        # independent of what the packet's `status` field asserts.
        checks = packet.get("checks", {})
        if not isinstance(checks, dict) or not checks:
            status_consistent = False
            reasons.append("packet has no usable `checks` dict to audit")
        else:
            all_checks_passed = all(
                isinstance(c, dict) and c.get("passed") is True
                for c in checks.values()
            )
            recomputed_status = "green" if all_checks_passed else "red"
            claimed_status = packet.get("status")
            status_consistent = recomputed_status == claimed_status
            if not status_consistent:
                reasons.append(
                    f"status inconsistency: packet claims status="
                    f"{claimed_status!r} but raw checks recompute to "
                    f"status={recomputed_status!r}"
                )

        # 3. Output binding — only if the caller supplied the original
        # output independently (i.e. is NOT just trusting the packet).
        output_matches: bool | None = None
        if expected_output is not None:
            recomputed_hash = pp.sha256_hex(expected_output)
            claimed_hash = packet.get("output_hash")
            output_matches = recomputed_hash == claimed_hash
            if not output_matches:
                reasons.append(
                    "output_hash mismatch: the supplied output text does "
                    "not hash to the value recorded in the packet — this "
                    "packet does not attest to this output"
                )

        return VerificationResult(
            signature_valid=sig_ok,
            status_consistent=status_consistent,
            output_matches=output_matches,
            reasons=reasons,
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.verify",
        description="Independently verify a RIG ProofPacket.",
    )
    parser.add_argument("packet", help="path to a ProofPacket JSON file, or '-' for stdin")
    parser.add_argument(
        "--output-file",
        help="path to the original output text, to bind-check against output_hash",
    )
    args = parser.parse_args(argv)

    if args.packet == "-":
        packet = json.load(sys.stdin)
    else:
        with open(args.packet, "r", encoding="utf-8") as f:
            packet = json.load(f)

    expected_output = None
    if args.output_file:
        with open(args.output_file, "r", encoding="utf-8") as f:
            expected_output = f.read()

    verifier = Verifier()
    result = verifier.verify(packet, expected_output=expected_output)

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.overall_valid else 1


if __name__ == "__main__":
    raise SystemExit(_main())
