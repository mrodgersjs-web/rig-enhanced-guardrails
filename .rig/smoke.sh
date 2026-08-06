#!/usr/bin/env bash
# .rig/smoke.sh — L10 self-evolving smoke test.
#
# L10 doctrine: this harness does not just run a fixed script and report
# pass/fail. It runs a battery of real end-to-end scenarios against the
# actual Guard + Verifier CLIs, and any scenario that fails is captured
# and appended to .rig/hardening-log.md so the NEXT run of this script
# starts from a strictly larger regression set than the run before it.
# The harness is expected to grow monotonically harder over time.
#
# Usage: .rig/smoke.sh
# Exit code: 0 if every scenario behaves as expected, 1 otherwise.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

export RIG_PROOF_HMAC_KEY="${RIG_PROOF_HMAC_KEY:-smoke-test-key-$(date +%s)}"

HARDENING_LOG="$ROOT_DIR/.rig/hardening-log.md"
FAILURES=0
TOTAL=0

pass() { echo "  [PASS] $1"; }
fail() {
  echo "  [FAIL] $1"
  FAILURES=$((FAILURES + 1))
  {
    echo ""
    echo "## Regression case: $1"
    echo "- Discovered: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- This scenario must be kept in smoke.sh permanently going forward."
  } >> "$HARDENING_LOG"
}

check() {
  local desc="$1"
  local expected_exit="$2"
  local actual_exit="$3"
  TOTAL=$((TOTAL + 1))
  if [[ "$actual_exit" -eq "$expected_exit" ]]; then
    pass "$desc"
  else
    fail "$desc (expected exit $expected_exit, got $actual_exit)"
  fi
}

echo "=== L10 smoke: rig-enhanced-guardrails ==="
echo "Key material: ephemeral, scoped to this run"
echo ""

# ---------------------------------------------------------------------
# Scenario 1: valid output -> green packet -> verifies clean
# ---------------------------------------------------------------------
echo "[1/6] valid output produces a green, verifiable ProofPacket"
VALID_OUT="$WORKDIR/valid_output.txt"
echo -n "The forecast calls for mild temperatures and light wind." > "$VALID_OUT"

python3 -m src.guard --output-file "$VALID_OUT" --out "$WORKDIR/valid_packet.json" \
  > "$WORKDIR/valid_guard.log" 2>&1
GUARD_EXIT=$?
check "guard exits 0 on valid output" 0 "$GUARD_EXIT"

python3 -m src.verify "$WORKDIR/valid_packet.json" --output-file "$VALID_OUT" \
  > "$WORKDIR/valid_verify.log" 2>&1
VERIFY_EXIT=$?
check "verify exits 0 on genuine green packet" 0 "$VERIFY_EXIT"

# ---------------------------------------------------------------------
# Scenario 2: toxic output -> red packet -> Guard exits 1, but the
# packet is still a VALID (authentic, consistent) proof of failure.
# ---------------------------------------------------------------------
echo "[2/6] toxic output produces a red, still-verifiable ProofPacket"
TOXIC_OUT="$WORKDIR/toxic_output.txt"
echo -n "You are such an idiot, shut up, you are worthless." > "$TOXIC_OUT"

python3 -m src.guard --output-file "$TOXIC_OUT" --out "$WORKDIR/toxic_packet.json" \
  > "$WORKDIR/toxic_guard.log" 2>&1
GUARD_EXIT=$?
check "guard exits 1 on toxic output" 1 "$GUARD_EXIT"

python3 -m src.verify "$WORKDIR/toxic_packet.json" --output-file "$TOXIC_OUT" \
  > "$WORKDIR/toxic_verify.log" 2>&1
VERIFY_EXIT=$?
check "verify exits 0 confirming the red packet is authentic" 0 "$VERIFY_EXIT"

# ---------------------------------------------------------------------
# Scenario 3: tampered packet (status flipped, not re-signed) is caught
# ---------------------------------------------------------------------
echo "[3/6] tampered packet (status flip) is caught by the Verifier"
python3 - "$WORKDIR/toxic_packet.json" "$WORKDIR/tampered_status.json" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    packet = json.load(f)
packet["status"] = "green"
packet["reason"] = None
with open(sys.argv[2], "w") as f:
    json.dump(packet, f)
PYEOF

python3 -m src.verify "$WORKDIR/tampered_status.json" --output-file "$TOXIC_OUT" \
  > "$WORKDIR/tampered_status_verify.log" 2>&1
VERIFY_EXIT=$?
check "verify exits 1 on tampered status field" 1 "$VERIFY_EXIT"
if grep -q "signature mismatch" "$WORKDIR/tampered_status_verify.log"; then
  pass "tampered status is reported as a signature mismatch"
else
  fail "tampered status not reported as signature mismatch"
fi

# ---------------------------------------------------------------------
# Scenario 4: swapped-output attack (valid packet, different output text)
# ---------------------------------------------------------------------
echo "[4/6] swapped output is caught by output-hash binding"
DIFFERENT_OUT="$WORKDIR/different_output.txt"
echo -n "This is a totally different piece of text." > "$DIFFERENT_OUT"

python3 -m src.verify "$WORKDIR/valid_packet.json" --output-file "$DIFFERENT_OUT" \
  > "$WORKDIR/swap_verify.log" 2>&1
VERIFY_EXIT=$?
check "verify exits 1 when packet is checked against swapped output" 1 "$VERIFY_EXIT"
if grep -q "output_hash mismatch" "$WORKDIR/swap_verify.log"; then
  pass "swapped output is reported as an output_hash mismatch"
else
  fail "swapped output not reported as output_hash mismatch"
fi

# ---------------------------------------------------------------------
# Scenario 5: wrong signing key is caught
# ---------------------------------------------------------------------
echo "[5/6] verifying with the wrong key is caught"
RIG_PROOF_HMAC_KEY="a-completely-different-key" \
  python3 -m src.verify "$WORKDIR/valid_packet.json" --output-file "$VALID_OUT" \
  > "$WORKDIR/wrongkey_verify.log" 2>&1
VERIFY_EXIT=$?
check "verify exits 1 with the wrong signing key" 1 "$VERIFY_EXIT"

# ---------------------------------------------------------------------
# Scenario 6: schema-invalid JSON output is rejected
# ---------------------------------------------------------------------
echo "[6/6] schema-invalid JSON output fails the json_schema check"
SCHEMA_FILE="$WORKDIR/schema.json"
cat > "$SCHEMA_FILE" <<'EOF'
{"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
EOF
BAD_JSON_OUT="$WORKDIR/bad_json_output.txt"
echo -n '{"wrong_field": "value"}' > "$BAD_JSON_OUT"

python3 -m src.guard --output-file "$BAD_JSON_OUT" --schema "$SCHEMA_FILE" \
  --out "$WORKDIR/bad_schema_packet.json" > "$WORKDIR/bad_schema_guard.log" 2>&1
GUARD_EXIT=$?
check "guard exits 1 on schema-invalid JSON" 1 "$GUARD_EXIT"

echo ""
echo "=== L10 smoke summary: $((TOTAL - FAILURES))/$TOTAL scenarios passed ==="

if [[ "$FAILURES" -gt 0 ]]; then
  echo ""
  echo "New regression cases recorded in $HARDENING_LOG"
  echo "These MUST be folded into a permanent scenario before the next merge."
  exit 1
fi

exit 0
