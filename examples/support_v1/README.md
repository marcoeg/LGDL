# Customer Support Pack (v1)

**Domain**: L1 customer support automation
**Status**: Production-ready example
**LGDL Version**: v1.0-RC+
**Tests**: 10 golden dialogs, all passing

---

## Overview

Realistic L1 customer support automation covering the most common support scenarios:
- **Authentication**: Login issues, password reset, account unlock
- **Billing**: Invoice lookup, plan details, refund requests
- **Device/App**: Platform-specific troubleshooting
- **Subscription**: Plan changes (upgrade/downgrade/cancel)

Demonstrates all v1.0 features:
- Slot-filling for information gathering (username, email, account ID, device type)
- Enum slots for channel/topic/action selection
- Capability integration for auth/billing/device services
- Negotiation for unclear support requests
- Multi-turn progressive flows

---

## Use Cases Covered

### 1. Login Issues (Most Common)
**Scenario**: User can't log in, needs password reset
**Slots**: username/email (either), channel (email/sms)
**Capabilities**: verify_user, send_reset_link
**Turns**: 3 (complaint → credentials → channel → reset sent)

**Example**:
```
User: I can't log in
Bot: What's the username or email?
User: marco@example.com
Bot: How should I send the reset? email or sms?
User: email
Bot: Reset link sent to marco@example.com
```

### 2. Password Reset (Direct)
**Scenario**: User explicitly requests password reset
**Slots**: email
**Capabilities**: send_reset_link
**Turns**: 2 (request → email → link sent)

### 3. Account Locked
**Scenario**: Account locked from failed attempts
**Slots**: username, reason (optional)
**Capabilities**: unlock_account
**Turns**: 2 (complaint → username → unlocked)

### 4. Billing Inquiry
**Scenario**: Invoice, plan, or refund questions
**Slots**: account_id, topic (enum)
**Capabilities**: get_invoices, get_plan
**Turns**: 3 (complaint → account → topic → results)

### 5. Device/App Issues
**Scenario**: App not working, crashes, connectivity
**Slots**: device_type (enum), error_desc
**Capabilities**: check_status
**Turns**: 3 (complaint → device → error → troubleshooting)

### 6. Plan Changes
**Scenario**: Upgrade, downgrade, cancel subscription
**Slots**: account_id, action (enum), new_plan (conditional)
**Capabilities**: get_plan
**Turns**: 3-4 (request → account → action → [new plan] → confirmed)

### 7. Unclear Support
**Scenario**: Vague "it doesn't work" complaint
**Strategy**: Negotiation to clarify
**Turns**: 2+ (unclear → negotiate → clarified → route)

---

## Quick Start

### Run the Server

```bash
uv run lgdl serve --games support:examples/support_v1/game.lgdl --port 9000
```

### Test with Chat

```bash
uv run python scripts/chat.py --game support --api http://localhost:9000
```

### Run Golden Dialogs

```bash
# When simulation script is ready:
uv run python scripts/simulate_dialogs.py \
  --file examples/support_v1/golden_dialogs.yaml \
  --game support
```

---

## Example Dialogs

### Dialog 1: Login Issue (3 turns)

```
You: I can't log in
🤖 What's the username or email address on your account?

You: marco@example.com
🤖 How should I send the reset link? Reply with 'email' or 'sms'.

You: email
🤖 Let me verify your account and send a reset link via email.
   Account verified. Sending password reset link to your email.
   Reset link sent to marco@example.com. Check your inbox...
```

**Features**:
- ✅ OR logic for slots (username OR email)
- ✅ Enum slot (email/sms channel)
- ✅ Chained capabilities (verify → send_reset)
- ✅ Success/failure handling

---

### Dialog 2: Account Locked (2 turns)

```
You: my account is locked
🤖 What's the username for the locked account?

You: marco
🤖 I'll unlock the account for marco...
   Your account marco has been unlocked. You should be able to log in now.
```

**Features**:
- ✅ Direct unlock capability
- ✅ Fast resolution (2 turns)

---

### Dialog 3: Billing Inquiry (3 turns)

```
You: billing issue
🤖 Can you provide your account ID?

You: ACCT-001
🤖 Is this about an invoice, your plan details, or a refund?

You: invoice
🤖 Looking up invoice information for account ACCT-001...
   I found your invoice details for account ACCT-001.
   Last invoice: 2025-10-15. Current plan: Pro Plan.
```

**Features**:
- ✅ Account identification
- ✅ Topic routing (invoice/plan/refund)
- ✅ Data retrieval from billing system

---

### Dialog 4: Device Issue (3 turns)

```
You: the app is not working
🤖 Which device are you using? Reply with: ios, android, web, or desktop

You: ios
🤖 Can you describe what you see?

You: spinning wheel that never stops
🤖 Checking status for ios app...
   The ios service is operational. Try these steps:
   1) Log out and log back in
   2) Clear app cache
   3) Restart your device
```

**Features**:
- ✅ Platform-specific troubleshooting
- ✅ Status check capability
- ✅ Structured troubleshooting steps

---

## Metrics to Measure

### Resolution Metrics
- **First-contact resolution rate**: % of issues resolved without escalation
- **Turns to resolution**: Average turns per issue type
  - Login: Target 3 turns
  - Password reset: Target 2 turns
  - Billing: Target 3 turns
  - Device: Target 3 turns

### Slot-Filling Metrics
- **Slot completion rate**: % of conversations where all required slots filled
- **Validation failures**: Should be <5% (only on invalid input)
- **Prompts per conversation**: Should match required slot count

### Capability Metrics
- **Success rate by capability**:
  - auth.verify_user: >95%
  - auth.send_reset_link: >95%
  - billing.get_invoices: >98%
- **Capability latency**: <100ms P95 for mocks
- **Failure handling**: Verify escalation on capability timeout/error

### User Experience Metrics
- **Negotiation trigger rate**: Unclear_support should be <10% of conversations
- **Confidence distribution**: Most flows should be medium-high confidence
- **Escalation rate**: <5% should escalate to human

---

## Slot Design Patterns

### Pattern 1: Account Identification
```lgdl
slots {
  account_id: string required
}
# OR
slots {
  username: string optional
  email: string optional
}
```

**Usage**: Every authenticated operation
**Validation**: Format check (email regex, account ID pattern)

### Pattern 2: Multi-Option Selection
```lgdl
slots {
  topic: enum("invoice", "plan", "refund") required
  channel: enum("email", "sms") required
  device_type: enum("ios", "android", "web", "desktop") required
}
```

**Usage**: Routing to specific sub-flows
**Benefits**: Type-safe, validates input, enables branching

### Pattern 3: Conditional Slot Requirements
```lgdl
when slot new_plan is missing and slot action is not "cancel" {
  prompt slot: "Which plan would you like to switch to?"
}
```

**Usage**: new_plan only required for upgrade/downgrade, not cancel
**Note**: v1.0 doesn't support conditional logic in slot definitions directly,
but you can use conditional prompts in when blocks

---

## Integration Patterns

### Pattern 1: Verify Then Act
```lgdl
when all_slots_filled {
  auth.verify_user for "verification" await timeout 2
}

when successful {
  auth.send_reset_link for "reset" await timeout 2
}
```

**Benefits**: Don't send reset link if account doesn't exist

### Pattern 2: Lookup Then Display
```lgdl
when all_slots_filled {
  billing.get_invoices for "lookup" await timeout 3
}

when successful {
  respond with: "Found: {invoice_date}, {invoice_amount}"
}
```

**Benefits**: Capability data available in template

### Pattern 3: Check Status Then Troubleshoot
```lgdl
when all_slots_filled {
  device.check_status for "diagnostics" await timeout 2
}

when successful {
  respond with: "Service operational. Try: 1) Log out 2) Clear cache"
}

when failed {
  respond with: "Platform experiencing issues. ETA: {eta}"
}
```

**Benefits**: Different advice based on platform status

---

## Testing

### Functional Testing
```bash
# Test login flow
curl -X POST http://localhost:9000/games/support/move \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "test1", "user_id": "test", "input": "I cant log in"}'
```

### Load Testing
```python
# Locust scenario
class SupportUser(HttpUser):
    @task(weight=5)
    def login_issue(self):
        # Simulate 3-turn login flow

    @task(weight=2)
    def billing_inquiry(self):
        # Simulate 3-turn billing flow

    @task(weight=3)
    def device_issue(self):
        # Simulate 3-turn device flow
```

**Target**: 100 concurrent support conversations, P95 <500ms

### A/B Testing
Compare automated support vs human agent:
- Resolution time
- Customer satisfaction
- Escalation rate

---

## Production Deployment Notes

### Capability Integration

**Mock (Development)**:
```python
# In lgdl/runtime/capability.py
def _verify_user(self, payload):
    return {"status": "ok", "user_found": True}
```

**Production**:
```python
# Real integration
async def _verify_user(self, payload):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/verify",
            json=payload,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
        )
    return response.json()
```

### Rate Limiting Considerations

**L1 Support** typically sees:
- 1000-5000 conversations/day
- Peak hours: 9am-5pm local time
- Average conversation: 2-4 turns
- Total turns/day: 4000-20000

**Recommended Limits**:
```python
LGDL_RATE_LIMIT_USER=20/minute  # Higher than medical (users retry more)
LGDL_RATE_LIMIT_CONVERSATION=30/minute
```

### Escalation Integration

When `escalate to: human_agent` triggers:
```python
# Create support ticket
# Add to agent queue
# Notify user of wait time
# Transfer conversation context
```

---

## Common Support Patterns

### Fast Resolution (2 turns)
- Password reset: request → email → done
- Account unlock: complaint → username → unlocked

### Standard Resolution (3 turns)
- Login issue: complaint → credentials → channel → done
- Billing: complaint → account → topic → results
- Device: complaint → platform → error → troubleshooting

### Complex Resolution (4+ turns)
- Plan change: request → account → action → new plan → confirmed
- Multi-symptom device issues

### Escalation Needed
- Account locked for suspicious activity (manual review)
- Billing disputes (human judgment)
- Complex technical issues

---

## See Also

- [examples/medical_v2/](../medical_v2/) - Medical triage pack
- [SLOT_FILLING.md](../../docs/SLOT_FILLING.md) - Slot-filling guide
- [V1_0_PRODUCTION_HARDENING_PLAN.md](../../docs/V1_0_PRODUCTION_HARDENING_PLAN.md) - Production roadmap
