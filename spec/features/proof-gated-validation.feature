Feature: Proof-gated LLM output validation
  As a system operator relying on an LLM in a production pipeline
  I want every output validation decision to be independently, cryptographically
  auditable
  So that "the Guard said it passed" is never accepted on its own word

  Background:
    Given a Guard sealed with a known HMAC key
    And an independent Verifier holding the same key material
    And the Verifier never imports or calls the Guard's check logic directly

  Scenario: Valid output passes and produces a verifiable green ProofPacket
    Given an LLM output "The forecast calls for mild temperatures and light wind."
    When the Guard validates the output
    Then the ProofPacket status is "green"
    And the ProofPacket reason is empty
    And every check in the ProofPacket reports "passed": true
    And the ProofPacket carries a 64-character HMAC-SHA256 signature
    When the Verifier independently verifies the ProofPacket against the original output
    Then the verification result is "overall_valid": true
    And the verification reports "signature_valid": true
    And the verification reports "status_consistent": true
    And the verification reports "output_matches": true

  Scenario: Toxic output fails and produces a verifiable red ProofPacket
    Given an LLM output "You are such an idiot, shut up, you are worthless."
    When the Guard validates the output
    Then the ProofPacket status is "red"
    And the ProofPacket reason mentions "toxicity"
    And the "toxicity" check in the ProofPacket reports "passed": false
    When the Verifier independently verifies the ProofPacket against the original output
    Then the verification result is "overall_valid": true
    # A correctly-signed RED packet is itself a valid proof: the failure
    # claim is authentic and internally consistent, even though the
    # underlying validation did not pass.

  Scenario: Tampered ProofPacket is caught even when only one field is changed
    Given a sealed ProofPacket produced by the Guard for a toxic output
    And the packet's original status is "red"
    When an attacker rewrites the packet's "status" field to "green" without
      re-signing it
    And the Verifier independently verifies the tampered packet against the
      original output
    Then the verification result is "overall_valid": false
    And the verification reports "signature_valid": false
    And the verification reasons mention "signature mismatch"

  Scenario: Tampered check outcome plus status is still caught by the signature
    Given a sealed ProofPacket produced by the Guard for a toxic output
    When an attacker flips the "toxicity" check's "passed" field to true
      and sets "status" to "green" without re-signing
    And the Verifier independently verifies the tampered packet
    Then the verification result is "overall_valid": false
    And the verification reports "signature_valid": false

  Scenario: Internally inconsistent but validly signed packet is flagged
    Given a ProofPacket payload whose raw "checks" would recompute to
      status "red"
    But whose "status" field was set to "green" before sealing
    When that payload is sealed with a valid signature
    And the Verifier independently verifies the packet
    Then the verification reports "signature_valid": true
    But the verification reports "status_consistent": false
    And the verification result is "overall_valid": false

  Scenario: Verification against a swapped output is caught by output binding
    Given a sealed, valid green ProofPacket produced for output A
    When the Verifier is asked to verify that packet against a different
      output B
    Then the verification reports "output_matches": false
    And the verification result is "overall_valid": false

  Scenario: Verification with the wrong signing key is caught
    Given a sealed, valid ProofPacket produced with key K1
    When a Verifier holding a different key K2 verifies the packet
    Then the verification reports "signature_valid": false
    And the verification result is "overall_valid": false
