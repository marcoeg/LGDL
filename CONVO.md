# Conversation Walkthrough: `examples/medical/golden_dialogs.yaml`

This note explains how each dialog in `examples/medical/golden_dialogs.yaml` maps to the runtime behaviour captured by running:

```bash
uv run python scripts/goldens.py --file examples/medical/golden_dialogs.yaml -v
```

The command output (ANSI colour removed for readability) was:

```
User: I need to see Dr. Smith
LGDL: I can check availability for Smith. Availability for Smith: Tue 10:00, Wed 14:00
[RESP JSON] doctor_name_present
{
  "move_id": "appointment_request",
  "confidence": 0.92,
  "response": "I can check availability for Smith. Availability for Smith: Tue 10:00, Wed 14:00",
  "action": "check_availability",
  "manifest_id": "afdc3c48-09f0-4956-9a62-5ec9dae46168",
  "latency_ms": 51.16,
  "firewall_triggered": false
}
[OK]   doctor_name_present — input: 'I need to see Dr. Smith'

User: I need help
LGDL: I can help with appointments or general info.
[RESP JSON] ambiguous_triggers_negotiation
{
  "move_id": "general_inquiry",
  "confidence": 0.75,
  "response": "I can help with appointments or general info.",
  "action": null,
  "manifest_id": "cf0b708c-0b69-40ea-ab12-e9f7031edb3a",
  "latency_ms": 0.03,
  "firewall_triggered": false
}
[OK]   ambiguous_triggers_negotiation — input: 'I need help'

User: I need to see a doctor
LGDL: Is this for a specific doctor or any provider?
[RESP JSON] needs_name_negotiation
{
  "move_id": "appointment_request",
  "confidence": 0.6000000000000001,
  "response": "Is this for a specific doctor or any provider?",
  "action": null,
  "manifest_id": "a545b52f-5804-47e8-a8a3-1353ce152b34",
  "latency_ms": 0.03,
  "firewall_triggered": false
}
[OK]   needs_name_negotiation — input: 'I need to see a doctor'

User: Book appointment with Dr. Lee
LGDL: Attempting to book Dr. Lee. Not allowed.
[RESP JSON] capability_enforced
{
  "move_id": "book_intent",
  "confidence": 0.92,
  "response": "Attempting to book Dr. Lee. Not allowed.",
  "action": null,
  "manifest_id": "4c9e884b-8cdb-4f30-b438-628649b566cc",
  "latency_ms": 0.04,
  "firewall_triggered": false
}
[OK]   capability_enforced — input: 'Book appointment with Dr. Lee'


Summary: 4/4 passed in 55 ms
```

The API was running with the preloaded medical scheduling game (`examples/medical/game.lgdl`) while the script issued each turn. Each numbered dialog in the YAML is meant to prove a distinct behaviour:

---

## 1. doctor_name_present
- **YAML turn:** `"I need to see Dr. Smith"`
- **Intent:** Demonstrate the "happy path"—a confident match when the user provides a specific doctor name.
- **Expectation:** `appointment_request`, `confidence >= 0.80`, response containing `"availability"` and `"Smith"`.
- **Runtime:**
  - Best trigger: `"I need to see Dr. {doctor}"` (strict).
  - Captured slot `{doctor}` ⇒ `Smith` → confident path.
  - Response: “I can check availability for Smith. Availability for Smith: Tue 10:00, Wed 14:00.”
  - Confidence: `0.92` (≥ required). Action: `check_availability` (allowed by policy guard).
  - The transcript shows the user line followed by the LGDL response; the JSON block confirms move ID, confidence, action, manifest ID, latency, and firewall status.

---

## 2. ambiguous_triggers_negotiation
- **YAML turn:** `"I need help"`
- **Intent:** Cover a generic help request that should route to the fallback move instead of the booking intent.
- **Expectation:** `general_inquiry`, `confidence >= 0.30`, response mentioning `"appointments"` and `"general info"`.
- **Runtime:**
  - Trigger: `"I need help"` under `general_inquiry` move.
  - Confidence level: medium (`0.75`), meeting the threshold.
  - Confident branch response: “I can help with appointments or general info.”
  - No capability executed. The JSON confirms move, confidence, null action, and success.

---

## 3. needs_name_negotiation
- **YAML turn:** `"I need to see a doctor"`
- **Intent:** Ensure the system negotiates when the request lacks a specific doctor—confidence should drop below the high threshold and trigger the clarification.
- **Expectation:** Same move (`appointment_request`), `confidence <= 0.70`, response prompting for specifics.
- **Runtime:**
  - Token-overlap matching of fuzzy pattern creates a match but with lower score (`0.60`).
  - The `if uncertain` block fires, generating “Is this for a specific doctor or any provider?”
  - Action remains `null`, as only a respond action is executed.
  - JSON output shows the lower confidence and the fallback response, meeting the expectation.

---

## 4. capability_enforced
- **YAML turn:** `"Book appointment with Dr. Lee"`
- **Intent:** Verify that policy enforcement blocks the `book` capability even when the trigger matches with high confidence.
- **Expectation:** `book_intent`, `confidence >= 0.50`, response containing “Attempting to book” and “Not allowed”, `action: null`.
- **Runtime:**
  - Strict `book` patterns capture `{doctor}` ⇒ `Dr. Lee` and reach high confidence (`0.92`).
  - Move attempts capability call `appointment_system.book`, but `PolicyGuard` disallows it.
  - Engine returns scripted response “Attempting to book Dr. Lee. Not allowed.” with no action value (null), consistent with expectation.
  - JSON block corroborates the denial (no action executed) and high confidence.

---

### Summary
All four dialogs satisfied their expectations, yielding a green `[OK]` and the final summary `4/4 passed`. The transcript emitted by the golden runner matches the YAML-defined scenarios: confident doctor match, generic help response, negotiation for specificity, and enforced capability denial. Latencies remained sub-millisecond except for the first turn (due to capability invocation).
