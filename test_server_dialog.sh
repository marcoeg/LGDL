#!/bin/bash
# Test slot-filling with actual server

echo "Testing slot-filling dialog with live server..."
echo ""

CONV_ID="test_$(date +%s)"
API="http://localhost:9000/games/medical/move"

echo "Conversation ID: $CONV_ID"
echo "================================================"

echo ""
echo "[TURN 1] Patient: I'm in pain"
curl -s -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"user_id\": \"test_user\", \"input\": \"I'm in pain\"}" \
  | jq -r '"\nSystem: \(.response)\nAwaiting slot: \(.awaiting_slot // "none")"'

echo ""
echo "[TURN 2] Patient: My chest"
curl -s -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"user_id\": \"test_user\", \"input\": \"My chest\"}" \
  | jq -r '"\nSystem: \(.response)\nAwaiting slot: \(.awaiting_slot // "none")"'

echo ""
echo "[TURN 3] Patient: 8 out of 10"
curl -s -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"user_id\": \"test_user\", \"input\": \"8 out of 10\"}" \
  | jq -r '"\nSystem: \(.response)\nAwaiting slot: \(.awaiting_slot // "none")"'

echo ""
echo "[TURN 4] Patient: About an hour ago"
curl -s -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"user_id\": \"test_user\", \"input\": \"About an hour ago\"}" \
  | jq -r '"\nSystem: \(.response)\nSlots filled: \(.slots_filled // {})"'

echo ""
echo "================================================"
echo "✅ Dialog complete!"
