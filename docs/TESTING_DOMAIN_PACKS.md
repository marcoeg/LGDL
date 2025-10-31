# Testing Domain Packs - Command Reference

**Domain Packs**: medical_v2, support_v1
**LGDL Version**: v1.0-RC
**Status**: Ready to test

---

## Quick Start

### Prerequisites
```bash
# Ensure dependencies installed
uv sync --extra dev

# Verify LGDL works
uv run lgdl --help
```

---

## Test Medical Stress Triage Pack (medical_v2)

### 1. Compile and Validate

```bash
# Validate grammar
uv run lgdl validate examples/medical_v2/game.lgdl

# Compile to IR
uv run lgdl compile examples/medical_v2/game.lgdl -o medical_v2.ir.json

# Inspect compiled moves
cat medical_v2.ir.json | jq '.moves[] | {id, slots: .slots | keys}'
```

**Expected Output**:
```json
{
  "id": "pain_assessment",
  "slots": ["location", "severity", "onset", "associated_symptoms"]
}
{
  "id": "chest_pain_followup",
  "slots": ["shortness_of_breath", "nausea", "sweating", "radiating_pain"]
}
...
```

### 2. Start Server

```bash
# Start on port 9001 (different from main medical example)
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9001

# Server should show:
# ✓ Validated: medical_v2 -> examples/medical_v2/game.lgdl
# Starting LGDL API server on port 9001...
# Health check: http://127.0.0.1:9001/healthz
```

### 3. Test with Interactive Chat

```bash
# In a new terminal
uv run python scripts/chat.py --game medical_v2 --api http://localhost:9001
```

**Try These Dialogs**:

#### Dialog 1: Basic Pain Assessment
```
You: I have pain
Bot: Where exactly is the pain located?
You: in my lower back
Bot: On a scale from 1 to 10, how severe is the pain?
You: 7
Bot: When did this pain start?
You: since yesterday
Bot: Thank you. You reported 7/10 pain in your lower back...
```

#### Dialog 2: Chest Pain High-Risk
```
You: I have chest pain
Bot: Chest pain can be serious. I need to check a few important things...
You: yes
Bot: Are you short of breath right now? (yes/no)
You: yes
Bot: Are you also feeling nauseous or vomiting? (yes/no)
You: no
Bot: Are you sweating or feeling cold and clammy? (yes/no)
You: yes
Bot: Does the pain radiate to your arm, jaw, or back? (yes/no)
You: no
Bot: Based on your chest pain symptoms... please call 911...
```

#### Dialog 3: Breathing Difficulty
```
You: short of breath
Bot: How long have you been short of breath?
You: 2 hours
Bot: Does it happen at rest, when walking, or only when exercising?
You: at rest
Bot: Do you also have a cough? (yes/no)
You: no
Bot: You've been short of breath for 2 hours, happening at rest...
```

#### Dialog 4: Medication Check
```
You: what meds am I on
Bot: What's your patient ID or date of birth for verification?
You: DOB 01/15/1980
Bot: Would you like to check medications, allergies, or both?
You: medications
Bot: Let me pull up your medications from the system...
    I found your records...
```

### 4. Test with cURL

```bash
# Turn 1
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "test1", "user_id": "patient1", "input": "I have pain"}' \
  | jq '.response, .awaiting_slot'

# Should show: "Where exactly is the pain located?" and "location"

# Turn 2
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "test1", "user_id": "patient1", "input": "my back"}' \
  | jq '.response, .awaiting_slot'

# Should show: "On a scale from 1 to 10..." and "severity"
```

### 5. Check Slot Persistence

```bash
# Query SQLite database directly
sqlite3 ~/.lgdl/conversations.db "
SELECT conversation_id, move_id, slot_name, slot_value
FROM slots
WHERE conversation_id LIKE 'test%'
ORDER BY conversation_id, move_id, slot_name;
"

# Should show filled slots from your conversation
```

---

## Test Customer Support Pack (support_v1)

### 1. Compile and Validate

```bash
# Validate
uv run lgdl validate examples/support_v1/game.lgdl

# Compile
uv run lgdl compile examples/support_v1/game.lgdl -o support_v1.ir.json

# Inspect moves and slots
cat support_v1.ir.json | jq '.moves[] | {id, slots: .slots | keys}'
```

### 2. Start Server

```bash
# Start on port 9002
uv run lgdl serve --games support:examples/support_v1/game.lgdl --port 9002
```

### 3. Test with Interactive Chat

```bash
uv run python scripts/chat.py --game support --api http://localhost:9002
```

**Try These Dialogs**:

#### Dialog 1: Login Issue
```
You: I can't log in
Bot: What's the username or email address on your account?
You: marco@example.com
Bot: How should I send the reset link? Reply with 'email' or 'sms'.
You: email
Bot: Let me verify your account...
    Account verified. Sending password reset link...
    Reset link sent to your email.
```

#### Dialog 2: Password Reset
```
You: reset my password
Bot: What's the email address on your account?
You: user@test.com
Bot: Sending password reset link to user@test.com...
    Reset link sent. Check your inbox...
```

#### Dialog 3: Account Locked
```
You: my account is locked
Bot: What's the username for the locked account?
You: marco
Bot: I'll unlock the account for marco...
    Your account marco has been unlocked. You should be able to log in now.
```

#### Dialog 4: Billing Inquiry
```
You: billing issue
Bot: Can you provide your account ID?
You: ACCT-001
Bot: Is this about an invoice, your plan details, or a refund?
You: invoice
Bot: Looking up invoice information...
    I found your invoice details for account ACCT-001...
```

#### Dialog 5: Device Issue
```
You: the app is not working
Bot: Which device are you using? Reply with: ios, android, web, or desktop
You: ios
Bot: Can you describe what you see?
You: spinning wheel
Bot: Checking status for ios app...
    The ios service is operational. Try these steps: 1) Log out...
```

### 4. Test Multi-Turn with cURL

```bash
CONV="support_test_$(date +%s)"

# Turn 1
curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"customer1\", \"input\": \"I cant log in\"}" \
  | jq '{move, confidence, response, awaiting_slot}'

# Turn 2
curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"customer1\", \"input\": \"marco@test.com\"}" \
  | jq '{move, response, awaiting_slot}'

# Turn 3
curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"customer1\", \"input\": \"email\"}" \
  | jq '{move, response, action}'
```

---

## Run Both Servers Simultaneously

### Terminal 1: Medical
```bash
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9001
```

### Terminal 2: Support
```bash
uv run lgdl serve --games support:examples/support_v1/game.lgdl --port 9002
```

### Terminal 3: Test Medical
```bash
uv run python scripts/chat.py --game medical_v2 --api http://localhost:9001
```

### Terminal 4: Test Support
```bash
uv run python scripts/chat.py --game support --api http://localhost:9002
```

---

## Automated Testing

### Test All Moves Compile

```bash
# Count moves in each domain
uv run python -c "
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game

games = [
    ('medical_v2', 'examples/medical_v2/game.lgdl'),
    ('support_v1', 'examples/support_v1/game.lgdl')
]

for name, path in games:
    game = parse_lgdl(path)
    ir = compile_game(game)
    moves_with_slots = sum(1 for m in ir['moves'] if 'slots' in m)
    total_slots = sum(len(m.get('slots', {})) for m in ir['moves'])
    print(f'{name}: {len(ir[\"moves\"])} moves, {moves_with_slots} with slots, {total_slots} total slots')
"
```

**Expected Output**:
```
medical_v2: 7 moves, 6 with slots, 17 total slots
support_v1: 7 moves, 6 with slots, 14 total slots
```

### Test Slot Types

```bash
# Check that range, enum, timeframe slots compile correctly
uv run python -c "
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game
import json

game = parse_lgdl('examples/medical_v2/game.lgdl')
ir = compile_game(game)

pain_move = next(m for m in ir['moves'] if m['id'] == 'pain_assessment')
print('Pain assessment slots:')
print(json.dumps(pain_move['slots'], indent=2))
"
```

### Test Golden Dialogs (Manual for now)

Since the golden runner needs updates for multi-turn slot dialogs, test manually:

```bash
# Follow the dialogs in:
cat examples/medical_v2/golden_dialogs.yaml
cat examples/support_v1/golden_dialogs.yaml

# Execute each turn via chat.py or cURL
# Verify responses match expectations
```

---

## Metrics to Collect

### During Testing, Track:

**Slot-Filling Metrics**:
```bash
# Count slots in database after test
sqlite3 ~/.lgdl/conversations.db "
SELECT move_id, COUNT(*) as slot_count
FROM slots
GROUP BY move_id;
"
```

**Conversation Metrics**:
```bash
# Turns per conversation
sqlite3 ~/.lgdl/conversations.db "
SELECT conversation_id, COUNT(*) as turn_count
FROM turns
GROUP BY conversation_id
ORDER BY turn_count DESC
LIMIT 10;
"
```

**Move Distribution**:
```bash
# Which moves are matched most
sqlite3 ~/.lgdl/conversations.db "
SELECT matched_move, COUNT(*) as match_count
FROM turns
GROUP BY matched_move
ORDER BY match_count DESC;
"
```

---

## Debugging Commands

### Check Server Health

```bash
# Health check
curl http://localhost:9001/healthz | jq

# List games
curl http://localhost:9001/games | jq

# Check specific game
curl http://localhost:9001/games/medical_v2 | jq '.moves[] | .id'
```

### View Conversation State

```bash
# After having a conversation, check the database
sqlite3 ~/.lgdl/conversations.db "
SELECT id, created_at, turns_history_count,
       awaiting_response, awaiting_slot_for_move
FROM (
  SELECT c.id, c.created_at,
         COUNT(t.id) as turns_history_count,
         c.awaiting_response,
         c.awaiting_slot_for_move
  FROM conversations c
  LEFT JOIN turns t ON c.id = t.conversation_id
  GROUP BY c.id
)
ORDER BY created_at DESC
LIMIT 5;
"
```

### View Filled Slots

```bash
# See what slots were filled
sqlite3 ~/.lgdl/conversations.db "
SELECT s.conversation_id, s.move_id, s.slot_name, s.slot_value, s.slot_type
FROM slots s
JOIN conversations c ON s.conversation_id = c.id
ORDER BY c.created_at DESC, s.move_id, s.slot_name
LIMIT 20;
"
```

### Check Logs

```bash
# Server logs show slot-filling activity
# Look for lines like:
# [Slot] Filled 'location' = chest
# [Slot] Missing required slot 'severity', prompting user
# [Slot] All slots filled: {'location': 'chest', 'severity': 8.0, ...}
```

---

## Performance Testing

### Single Conversation Latency

```bash
# Time a single turn
time curl -s -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "perf1", "user_id": "test", "input": "I have pain"}' \
  > /dev/null

# Should be <100ms for first turn
```

### Concurrent Conversations

```bash
# Simple concurrent test (requires GNU parallel)
seq 1 10 | parallel -j 10 'curl -s -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"concurrent_{}\", \"user_id\": \"user{}\", \"input\": \"I have pain\"}" \
  > /dev/null'

# Check that all 10 conversations were created
sqlite3 ~/.lgdl/conversations.db "SELECT COUNT(*) FROM conversations WHERE id LIKE 'concurrent_%';"
```

---

## Comparison Testing

### Compare medical vs medical_v2

**Original** (examples/medical/game.lgdl):
- 7 moves (pain, cardiac, respiratory, trauma, fall, fever, appointment)
- pain_assessment has 4 slots
- Demonstrates basic slot-filling

**medical_v2** (examples/medical_v2/game.lgdl):
- 7 moves (pain, chest_pain_risk, chest_pain_followup, breathing, medication, fever, unclear)
- Specialized high-risk pathways
- EHR capability integration
- More enum slots (yes/no, multiple choice)

**Test Both**:
```bash
# Terminal 1
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 9000

# Terminal 2
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9001

# Compare responses for same input:
curl -X POST http://localhost:9000/games/medical/move -H "Content-Type: application/json" -d '{"conversation_id": "cmp1", "user_id": "test", "input": "chest pain"}' | jq .response

curl -X POST http://localhost:9001/games/medical_v2/move -H "Content-Type: application/json" -d '{"conversation_id": "cmp2", "user_id": "test", "input": "chest pain"}' | jq .response
```

---

## Feature-Specific Tests

### Test Range Validation

```bash
# medical_v2: severity slot has range(1, 10)
CONV="range_test"

# Turn 1
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"I have pain\"}"

# Turn 2
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"my back\"}"

# Turn 3 - Valid (within range)
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"8\"}"

# Should accept and move to next slot

# Try invalid (>10) - starts new conversation
curl -X POST http://localhost:9001/games/medical_v2/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"range_test2\", \"user_id\": \"test\", \"input\": \"15\"}"

# Should fail validation, re-prompt for severity
```

### Test Enum Slots

```bash
# support_v1: channel enum("email", "sms")
CONV="enum_test"

curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"I cant log in\"}"

curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"marco@test.com\"}"

# Try valid enum value
curl -X POST http://localhost:9002/games/support/move \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV\", \"user_id\": \"test\", \"input\": \"email\"}" \
  | jq '.response'

# Should accept "email"
```

### Test Timeframe Parsing

```bash
# Test various timeframe formats
for timeframe in "2 hours ago" "yesterday" "recently" "this morning" "an hour ago"; do
  echo "Testing: $timeframe"
  curl -s -X POST http://localhost:9001/games/medical_v2/move \
    -H "Content-Type: application/json" \
    -d "{\"conversation_id\": \"tf_$(echo $timeframe | tr ' ' '_')\", \"user_id\": \"test\", \"input\": \"$timeframe\"}" \
    | jq -r '.response' | head -1
done
```

---

## Troubleshooting

### Issue: "Sorry, I didn't catch that"

**Cause**: Pattern not matching

**Debug**:
```bash
# Check what patterns exist
uv run python -c "
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game

game = parse_lgdl('examples/medical_v2/game.lgdl')
ir = compile_game(game)

for move in ir['moves']:
    print(f'\n{move[\"id\"]}:')
    for trigger in move.get('triggers', []):
        for pattern in trigger['patterns'][:5]:  # First 5
            print(f'  - {pattern[\"text\"][:50]}')
"
```

### Issue: Slots not persisting

**Debug**:
```bash
# Check state manager is enabled
curl http://localhost:9001/healthz | jq '.state_enabled'

# Should be true

# Check database exists
ls -lh ~/.lgdl/conversations.db

# Check schema has slots table
sqlite3 ~/.lgdl/conversations.db ".schema slots"
```

### Issue: Capability not working

**Debug**:
```bash
# Check capability is registered
curl http://localhost:9001/games/medical_v2 | jq '.capabilities'

# Check capability contract loaded
ls -l examples/medical_v2/capability_contract.json

# Check server logs for capability errors
# Look for: "Capabilities not configured" or timeout errors
```

---

## Advanced: Compare All 3 Medical Examples

You now have 3 medical examples at different evolution stages:

| Example | Slots | Moves | Features |
|---------|-------|-------|----------|
| **medical** (original) | 4 | 7 | Basic slot-filling, original demo |
| **medical_v2** | 17 | 7 | High-risk pathways, EHR integration, enum slots |
| **(future) medical_v3** | TBD | TBD | Learning pipeline, propose-only |

**Test Side-by-Side**:
```bash
# Start all 3 (need 3 terminals)
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 9000
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9001
# medical_v3 when ready

# Same input to all 3
for port in 9000 9001; do
  echo "Port $port:"
  curl -s -X POST http://localhost:$port/games/*/move \
    -H "Content-Type: application/json" \
    -d '{"conversation_id": "compare", "user_id": "test", "input": "chest pain"}' \
    | jq -r '.response' | head -2
  echo ""
done
```

---

## Next Steps

### 1. Manual Testing (Now)
- Start servers for medical_v2 and support_v1
- Run through 2-3 dialogs in each
- Verify slot-filling works
- Check capabilities execute

### 2. Create Automated Test Runner (Future)
- Update `scripts/simulate_dialogs.py` to run golden dialogs
- Add support for multi-turn expectations
- Report pass/fail for each dialog

### 3. Load Testing (Production Hardening)
- Use Locust to stress test both packs
- Measure P95 latency with slot-filling
- Test 100+ concurrent conversations

---

## Quick Reference

```bash
# MEDICAL_V2
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9001
uv run python scripts/chat.py --game medical_v2 --api http://localhost:9001

# SUPPORT_V1
uv run lgdl serve --games support:examples/support_v1/game.lgdl --port 9002
uv run python scripts/chat.py --game support --api http://localhost:9002

# VALIDATE
uv run lgdl validate examples/medical_v2/game.lgdl
uv run lgdl validate examples/support_v1/game.lgdl

# COMPILE
uv run lgdl compile examples/medical_v2/game.lgdl -o medical_v2.ir.json
uv run lgdl compile examples/support_v1/game.lgdl -o support_v1.ir.json

# INSPECT DATABASE
sqlite3 ~/.lgdl/conversations.db "SELECT * FROM slots ORDER BY updated_at DESC LIMIT 10;"
```

---

**Ready to test!** Start with the commands above.
