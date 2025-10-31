# Running Golden Dialog Tests

Golden dialog tests validate LGDL games against expected conversation flows.

## Quick Start

### 1. Start the Server

```bash
# Start with all games (recommended)
uv run lgdl serve --games \
  medical:examples/medical/game.lgdl,\
  greeting:examples/greeting/game.lgdl,\
  shopping:examples/shopping/game.lgdl,\
  support:examples/support/game.lgdl,\
  restaurant:examples/restaurant/game.lgdl \
  --port 9000
```

Server will be available at: `http://127.0.0.1:9000`

### 2. Run Golden Tests

**Basic (summary only)**:
```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml
```

**Verbose (show full conversations)**:
```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml \
  -v
```

## Test Individual Games

### Medical Game (✅ 4/4 passing)

```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml \
  -v
```

**Expected output**:
```
[OK]   doctor_name_present
[OK]   ambiguous_triggers_negotiation
[OK]   needs_name_negotiation
[OK]   capability_enforced

Summary: 4/4 passed
```

**Features demonstrated**:
- ✅ Parameter extraction (`{doctor}`)
- ✅ Confidence thresholds (high/medium)
- ✅ Uncertain block with clarification
- ✅ Capability calls with PolicyGuard
- ✅ Template fallbacks (`{doctor?any provider}`)

### Greeting Game (✅ 5/5 passing)

```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/greeting/move \
  --file examples/greeting/golden_dialogs.yaml \
  -v
```

**Expected output**:
```
[OK]   simple_greeting
[OK]   greeting_with_name
[OK]   farewell_simple
[OK]   farewell_casual
[OK]   small_talk_confident

Summary: 5/5 passed
```

**Features demonstrated**:
- ✅ Strict pattern matching
- ✅ Fuzzy pattern matching
- ✅ Parameter extraction with optional params (`{name?}`)
- ✅ Medium confidence threshold
- ✅ Multiple moves per game

### Shopping Game (⚠️ 0/12 passing - known issues)

```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/shopping/move \
  --file examples/shopping/golden_dialogs.yaml
```

**Known issues**:
- Template syntax errors (${var?fallback} not valid)
- PolicyGuard blocks capability calls ("Not allowed.")
- See `docs/PER_GAME_RUNTIME_ENHANCEMENT.md` for fix plan

### Support Game (⚠️ 11/18 passing)

```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/support/move \
  --file examples/support/golden_dialogs.yaml
```

**Passing tests**: Basic routing, password reset, escalation, ticket management
**Failing tests**: Capability calls blocked, some confidence mismatches

### Restaurant Game (⚠️ 9/25 passing)

```bash
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/restaurant/move \
  --file examples/restaurant/golden_dialogs.yaml
```

**Passing tests**: Reservations, menu inquiries, special requests
**Failing tests**: Arithmetic templates, capability calls, some pattern matches

## Run All Tests at Once

```bash
# Test all working games
for game in medical greeting; do
  echo "=== Testing $game ==="
  uv run python scripts/goldens.py \
    --api http://127.0.0.1:9000/games/$game/move \
    --file examples/$game/golden_dialogs.yaml
done
```

## Test with Stop-on-Fail

```bash
# Stop at first failure for debugging
uv run python scripts/goldens.py \
  --api http://127.0.0.1:9000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml \
  --stop-on-fail \
  -v
```

## Understanding Test Output

### Color Codes
- 🟢 **Green** - Test passed
- 🔴 **Red** - Test failed
- 🟡 **Yellow** - User input
- 🔵 **Cyan** - Assistant response

### Test Result Format

**Success**:
```
[OK]   test_name — input: 'user message'
```

**Failure**:
```
[FAIL] test_name — input: 'user message'
       - confidence 0.6 !>= 0.75
       - response missing 'expected text'
```

**HTTP Error**:
```
[FAIL] test_name: HTTP 500
```

### Verbose Output (`-v` flag)

Shows full JSON response for each test:
```json
{
  "move_id": "greeting",
  "confidence": 0.92,
  "response": "Hello! How can I help you today?",
  "action": null,
  "manifest_id": "...",
  "latency_ms": 0.05,
  "firewall_triggered": false
}
```

## Golden Dialog File Format

**Example**: `examples/medical/golden_dialogs.yaml`

```yaml
game: medical_scheduling
version: 0.1
dialogs:
  - name: doctor_name_present
    turns:
      - input: "I need to see Dr. Smith"
        expect:
          move: appointment_request
          confidence: ">=0.80"
          response_contains: ["availability", "Smith"]
          action: check_availability
```

### Expectation Operators

**Confidence**:
- `>=0.80` - Greater than or equal
- `<=0.70` - Less than or equal
- `0.75` - Exact (with tolerance)

**Response**:
- `response_contains: ["text1", "text2"]` - Must contain all strings
- `response_exact: "exact text"` - Exact match

**Move**:
- `move: appointment_request` - Expected move ID

**Action**:
- `action: check_availability` - Expected capability action
- `action: null` - No action expected

## Troubleshooting

### Connection Refused
```
[FAIL] test: HTTP error ... Connection refused
```

**Solution**: Start the server first:
```bash
uv run lgdl serve --games medical:examples/medical/game.lgdl --port 9000
```

### Wrong Port
```
[FAIL] test: HTTP error ... Connection refused
```

**Check port**: Server might be on different port. Check server output:
```
Starting LGDL API server on port 9000...
```

Then use matching port in API URL:
```bash
--api http://127.0.0.1:9000/games/medical/move
```

### Game Not Found (404)
```
[FAIL] test: HTTP 404
```

**Solution**: Verify game is loaded. Check `/healthz`:
```bash
curl http://127.0.0.1:9000/healthz
```

Should show game in list:
```json
{
  "status": "healthy",
  "games": ["medical", "greeting", ...]
}
```

### Template Errors (500)
```
[FAIL] test: HTTP 500
```

**Common causes**:
1. Invalid template syntax (e.g., `${var?fallback}`)
2. Undefined variables
3. Arithmetic errors

Check server logs for error details.

## Performance Benchmarks

**Typical latencies** (offline TF-IDF embeddings):
- Medical game: ~50ms per turn
- Greeting game: ~5ms per turn
- Pattern matching: <1ms
- Template rendering: <0.1ms

**With OpenAI embeddings**:
- First call: ~200-500ms (API latency)
- Cached: ~5-10ms (SQLite cache hit)

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Golden Dialog Tests
  run: |
    # Start server in background
    uv run lgdl serve --games medical:examples/medical/game.lgdl --port 9000 &
    SERVER_PID=$!

    # Wait for server to start
    sleep 3

    # Run tests
    uv run python scripts/goldens.py \
      --api http://127.0.0.1:9000/games/medical/move \
      --file examples/medical/golden_dialogs.yaml \
      --stop-on-fail

    # Cleanup
    kill $SERVER_PID
```

### Docker Example

```bash
# Start containerized server
docker run -d -p 9000:9000 lgdl-server

# Run tests against container
uv run python scripts/goldens.py \
  --api http://localhost:9000/games/medical/move \
  --file examples/medical/golden_dialogs.yaml
```

## Current Test Status

See `docs/GOLDEN_TEST_BASELINE.txt` for full results.

**Summary**:
- ✅ Medical: 4/4 (100%)
- ✅ Greeting: 5/5 (100%)
- ⚠️ Support: 11/18 (61%)
- ⚠️ Restaurant: 9/25 (36%)
- ❌ Shopping: 0/12 (0%)

**Overall**: 29/64 (45.3%)

**Next steps**:
1. Implement per-game runtime enhancement (P1-3)
2. Fix template syntax in new games
3. Calibrate golden test expectations

---

## Related Documentation

- [GOLDEN_TEST_BASELINE.txt](GOLDEN_TEST_BASELINE.txt) - Current test results
- [PER_GAME_RUNTIME_ENHANCEMENT.md](PER_GAME_RUNTIME_ENHANCEMENT.md) - Fix plan for capability issues
- [P0_P1_CRITICAL_FIXES.md](P0_P1_CRITICAL_FIXES.md) - Implementation history
