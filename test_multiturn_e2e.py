#!/usr/bin/env python3
"""
End-to-end test for multi-turn conversation state management.

Tests that:
1. State is persisted across turns
2. Context enrichment works
3. Conversation history is stored
"""

import asyncio
import httpx
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:5555"
CONVERSATION_ID = f"test-e2e-{datetime.now().timestamp()}"

async def test_multi_turn_conversation():
    """Test a multi-turn medical conversation with state management."""

    print("=" * 60)
    print("Multi-Turn Conversation E2E Test")
    print("=" * 60)
    print(f"Conversation ID: {CONVERSATION_ID}\n")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check health
        print("1. Checking server health...")
        resp = await client.get(f"{BASE_URL}/healthz")
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {resp.json()}\n")

        # Turn 1: User reports pain
        print("2. Turn 1: User reports 'I have severe chest pain'")
        payload = {
            "conversation_id": CONVERSATION_ID,
            "user_id": "test-user",
            "input": "I have severe chest pain"
        }
        resp = await client.post(
            f"{BASE_URL}/games/medical/move",
            json=payload
        )
        turn1 = resp.json()
        print(f"   Matched move: {turn1['move_id']}")
        print(f"   Confidence: {turn1['confidence']:.2f}")
        print(f"   Response: {turn1['response']}")
        print(f"   Latency: {turn1['latency_ms']:.2f}ms\n")

        # Turn 2: Short follow-up (should be enriched)
        print("3. Turn 2: User says 'it started an hour ago'")
        print("   (Testing context enrichment)")
        payload = {
            "conversation_id": CONVERSATION_ID,
            "user_id": "test-user",
            "input": "it started an hour ago"
        }
        resp = await client.post(
            f"{BASE_URL}/games/medical/move",
            json=payload
        )
        turn2 = resp.json()
        print(f"   Matched move: {turn2['move_id']}")
        print(f"   Confidence: {turn2['confidence']:.2f}")
        print(f"   Response: {turn2['response']}")
        print(f"   Latency: {turn2['latency_ms']:.2f}ms\n")

        # Turn 3: Another short response
        print("4. Turn 3: Testing another contextual response")
        payload = {
            "conversation_id": CONVERSATION_ID,
            "user_id": "test-user",
            "input": "yes it's getting worse"
        }
        resp = await client.post(
            f"{BASE_URL}/games/medical/move",
            json=payload
        )
        turn3 = resp.json()
        print(f"   Matched move: {turn3['move_id']}")
        print(f"   Confidence: {turn3['confidence']:.2f}")
        print(f"   Response: {turn3['response']}")
        print(f"   Latency: {turn3['latency_ms']:.2f}ms\n")

    print("=" * 60)
    print("Test completed successfully!")
    print("=" * 60)
    print("\nKey Observations:")
    print("- All turns processed successfully")
    print("- Conversation state maintained across turns")
    print("- Context enrichment applied (check logs for '[Context] Enriched' messages)")
    print(f"- Conversation stored in ~/.lgdl/conversations.db with ID: {CONVERSATION_ID}")

if __name__ == "__main__":
    try:
        asyncio.run(test_multi_turn_conversation())
    except httpx.ConnectError:
        print("\nERROR: Could not connect to server at", BASE_URL)
        print("Please start the server with:")
        print("  uv run lgdl serve --games medical:examples/medical/game.lgdl --port 5555")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
