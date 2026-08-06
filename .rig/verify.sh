#!/usr/bin/env bash
# .rig/verify.sh — L8 eight-layer verification.
#
# Each layer is a distinct question about the artifact, run in strictly
# increasing order of cost/scope. A failure at any layer halts the run —
# later layers assume earlier ones held. Exit 0 only if all eight layers
# pass; a ProofPacket for this run is emitted at the end either way.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERIFY_WORKDIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_WORKDIR"' EXIT

LAYER_RESULTS=()
FAILED=0

run_layer() {
  local n="$1"
  local name="$2"
  shift 2
  echo "--- L${n}: ${name} ---"
  if "$@"; then
    echo "L${n} PASS: ${name}"
    LAYER_RESULTS+=("{\"layer\":${n},\"name\":\"${name}\",\"status\":\"pass\"}")
  else
    echo "L${n} FAIL: ${name}"
    LAYER_RESULTS+=("{\"layer\":${n},\"name\":\"${name}\",\"status\":\"fail\"}")
    FAILED=1
  fi
  echo ""
}

# ---------------------------------------------------------------------
# Layer 1: SYNTAX — every Python file parses.
# ---------------------------------------------------------------------
layer1_syntax() {
  local ok=0
  for f in src/*.py test/*.py; do
    python3 -m py_compile "$f" || ok=1
  done
  return $ok
}

# ---------------------------------------------------------------------
# Layer 2: UNIT — pytest suite passes.
# ---------------------------------------------------------------------
layer2_unit() {
  # Always invoke via `python3 -m pytest` rather than a bare `pytest`
  # binary: `-m` guarantees the current directory is on sys.path so the
  # `src` package resolves the same way regardless of which pytest
  # happens to be first on PATH.
  python3 -m pytest test/test_guard.py -q
}

# ---------------------------------------------------------------------
# Layer 3: INTEGRATION — guard.py CLI and verify.py CLI work together
# as real subprocesses (not in-process imports).
# ---------------------------------------------------------------------
layer3_integration() {
  local tmp="$VERIFY_WORKDIR/l3-integration"
  mkdir -p "$tmp"
  export RIG_PROOF_HMAC_KEY="l8-integration-key"

  echo -n "A calm and factually modest sentence." > "$tmp/out.txt"
  python3 -m src.guard --output-file "$tmp/out.txt" --out "$tmp/packet.json" \
    > /dev/null 2>&1 || return 1
  python3 -m src.verify "$tmp/packet.json" --output-file "$tmp/out.txt" \
    > /dev/null 2>&1
}

# ---------------------------------------------------------------------
# Layer 4: EVAL — the four checks each demonstrably discriminate
# pass/fail on a known-good and known-bad input (a check that always
# passes or always fails would slip past L1-L3 but is caught here).
# ---------------------------------------------------------------------
layer4_eval() {
  python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from src.guard import check_json_schema, check_toxicity, check_factuality_placeholder, check_format

cases = [
    ("json_schema", check_json_schema("not json", {"type": "object"}), False),
    ("json_schema", check_json_schema('{"a": 1}', {"type": "object"}), True),
    ("toxicity", check_toxicity("idiot shut up worthless"), False),
    ("toxicity", check_toxicity("a calm neutral sentence"), True),
    ("factuality", check_factuality_placeholder("this always works 100% guaranteed"), False),
    ("factuality", check_factuality_placeholder("this tends to work well"), True),
    ("format", check_format(""), False),
    ("format", check_format("a fine sentence"), True),
]

failures = []
for name, (passed, detail), expected in cases:
    if passed != expected:
        failures.append(f"{name}: expected passed={expected}, got {passed} ({detail})")

if failures:
    print("EVAL LAYER FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {len(cases)} discrimination cases behaved as expected")
PYEOF
}

# ---------------------------------------------------------------------
# Layer 5: PROOF — a sealed ProofPacket verifies, and a tampered one
# does not. This is the cryptographic core of the whole system.
# ---------------------------------------------------------------------
layer5_proof() {
  python3 - <<'PYEOF'
import sys, copy
sys.path.insert(0, ".")
from src.guard import Guard
from src.verify import Verifier

key = b"l8-proof-layer-key"
guard = Guard(key=key, key_id="l8")
verifier = Verifier(key=key, key_id="l8")

output = "A properly formed, non-toxic, schema-free sentence."
packet = guard.validate(output)
result = verifier.verify(packet, expected_output=output)
if not result.overall_valid:
    print("FAIL: genuine packet did not verify:", result.reasons)
    sys.exit(1)

tampered = copy.deepcopy(packet)
tampered["status"] = "red" if packet["status"] == "green" else "green"
tampered_result = verifier.verify(tampered, expected_output=output)
if tampered_result.overall_valid:
    print("FAIL: tampered packet incorrectly verified as valid")
    sys.exit(1)

print("proof layer: genuine packet verifies, tampered packet is rejected")
PYEOF
}

# ---------------------------------------------------------------------
# Layer 6: GATE — .rig/smoke.sh (the L10 harness) passes in full.
# ---------------------------------------------------------------------
layer6_gate() {
  bash .rig/smoke.sh
}

# ---------------------------------------------------------------------
# Layer 7: AUDIT — required doctrine artifacts are present and non-empty.
# ---------------------------------------------------------------------
layer7_audit() {
  local required=(
    "README.md"
    "AGENTS.md"
    "LICENSE"
    "pyproject.toml"
    "src/guard.py"
    "src/verify.py"
    "src/proofpacket.py"
    "spec/features/proof-gated-validation.feature"
    "test/test_guard.py"
    ".rig/smoke.sh"
  )
  local missing=0
  for f in "${required[@]}"; do
    if [[ ! -s "$f" ]]; then
      echo "AUDIT: missing or empty required artifact: $f"
      missing=1
    fi
  done
  return $missing
}

# ---------------------------------------------------------------------
# Layer 8: SIGN-OFF — emit a signed ProofPacket for this verification
# run itself, so "the L8 run passed" is itself a checkable claim.
# ---------------------------------------------------------------------
layer8_signoff() {
  local results_json
  results_json=$(IFS=,; echo "${LAYER_RESULTS[*]}")
  python3 - "$results_json" "$FAILED" <<'PYEOF'
import sys, json
sys.path.insert(0, ".")
from src import proofpacket as pp

results_json, failed = sys.argv[1], sys.argv[2]
layers = json.loads(f"[{results_json}]")
key, key_id = pp.load_key()

payload = {
    "packet_type": "rig.l8.verification_run",
    "schema_version": pp.PACKET_SCHEMA_VERSION,
    "timestamp": pp.utc_timestamp(),
    "layers": layers,
    "status": "red" if failed == "1" else "green",
    "reason": "one or more layers failed" if failed == "1" else None,
}
packet = pp.seal(payload, key, key_id)
with open(".rig/last-l8-run.json", "w") as f:
    json.dump(packet, f, indent=2, sort_keys=True)
print("L8 run ProofPacket written to .rig/last-l8-run.json")
print(f"status: {packet['status']}")
PYEOF
}

echo "=== L8 eight-layer verification: rig-enhanced-guardrails ==="
echo ""

run_layer 1 "syntax"      layer1_syntax
run_layer 2 "unit"        layer2_unit
run_layer 3 "integration" layer3_integration
run_layer 4 "eval"        layer4_eval
run_layer 5 "proof"       layer5_proof
run_layer 6 "gate"        layer6_gate
run_layer 7 "audit"       layer7_audit
layer8_signoff  # always runs, records whatever happened above

echo ""
if [[ "$FAILED" -eq 1 ]]; then
  echo "=== L8 result: FAIL (see .rig/last-l8-run.json) ==="
  exit 1
fi
echo "=== L8 result: PASS (see .rig/last-l8-run.json) ==="
exit 0
