"""
proofpacket.py — shared cryptographic primitives for RIG ProofPackets.

This module contains ONLY mechanical infrastructure (canonicalization,
hashing, HMAC signing/verification). It contains NO validation logic and
NO trust decisions — those live in guard.py (the Builder) and verify.py
(the Verifier) respectively, and the two are intentionally kept separate
per TAC doctrine (Builder != Verifier).

A ProofPacket is a flat JSON-serializable dict. Every field except
`signature` is considered "payload"; the signature covers the canonical
JSON encoding of the payload only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

PACKET_TYPE_GUARD_VALIDATION = "rig.guard.validation"
PACKET_SCHEMA_VERSION = "1"
SIGNATURE_FIELD = "signature"
KEY_ID_FIELD = "key_id"

# Insecure fallback key used ONLY when RIG_PROOF_HMAC_KEY is unset, so the
# reference implementation is runnable out of the box. Any real deployment
# MUST set RIG_PROOF_HMAC_KEY to a secret value.
_DEMO_FALLBACK_KEY = b"rig-demo-fallback-key-DO-NOT-USE-IN-PRODUCTION"
_DEMO_KEY_ID = "demo-fallback-v1"


def load_key(env_var: str = "RIG_PROOF_HMAC_KEY") -> tuple[bytes, str]:
    """Load the HMAC signing/verification key and a stable key_id label.

    Returns (key_bytes, key_id). key_id is never secret and is embedded in
    the packet so a Verifier knows which key material to load — it is not
    itself sufficient to verify anything.
    """
    raw = os.environ.get(env_var)
    if raw:
        key_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return raw.encode("utf-8"), key_id
    print(
        f"[proofpacket] WARNING: {env_var} not set — using insecure demo "
        "fallback key. Set RIG_PROOF_HMAC_KEY before relying on this in "
        "any non-demo context.",
        file=sys.stderr,
    )
    return _DEMO_FALLBACK_KEY, _DEMO_KEY_ID


def sha256_hex(text: str) -> str:
    """SHA-256 hex digest of a UTF-8 string. Deterministic content hash."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_timestamp() -> str:
    """RFC 3339 / ISO 8601 UTC timestamp with second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonicalize(payload: Mapping[str, Any]) -> bytes:
    """Deterministic byte encoding of a payload dict for signing.

    Sorted keys, no whitespace, ensure_ascii — the same payload always
    canonicalizes to the same bytes regardless of dict insertion order.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sign_payload(payload: Mapping[str, Any], key: bytes) -> str:
    """HMAC-SHA256 over the canonical payload encoding. Returns hex digest."""
    return hmac.new(key, canonicalize(payload), hashlib.sha256).hexdigest()


def split_packet(packet: Mapping[str, Any]) -> tuple[dict, str | None]:
    """Split a packet into (payload_without_signature, signature_or_None)."""
    payload = dict(packet)
    signature = payload.pop(SIGNATURE_FIELD, None)
    return payload, signature


def seal(payload: Mapping[str, Any], key: bytes, key_id: str) -> dict:
    """Attach key_id + signature to a payload, producing a finished packet.

    `payload` MUST NOT already contain a `signature` field — that field is
    exclusively computed here, over everything else including `key_id`.
    """
    if SIGNATURE_FIELD in payload:
        raise ValueError("payload must not pre-contain a signature field")
    full_payload = dict(payload)
    full_payload[KEY_ID_FIELD] = key_id
    signature = sign_payload(full_payload, key)
    full_payload[SIGNATURE_FIELD] = signature
    return full_payload


def recompute_signature(packet: Mapping[str, Any], key: bytes) -> str:
    """Recompute what the signature SHOULD be for a packet's current payload.

    Does not compare — callers use hmac.compare_digest against the packet's
    stored signature. Exposed separately so verify.py can report both
    values for debugging without ever short-circuiting the constant-time
    comparison itself.
    """
    payload, _ = split_packet(packet)
    return sign_payload(payload, key)


def signature_valid(packet: Mapping[str, Any], key: bytes) -> bool:
    """Constant-time check that packet['signature'] matches the payload."""
    payload, signature = split_packet(packet)
    if not signature or not isinstance(signature, str):
        return False
    expected = sign_payload(payload, key)
    return hmac.compare_digest(expected, signature)
