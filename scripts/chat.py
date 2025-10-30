#!/usr/bin/env python3
"""
Interactive LGDL chat REPL for manual testing.

Features:
- Color-coded output (user/assistant/system)
- Shows confidence, move_id, negotiation rounds
- Multi-game support
- Conversation history tracking
- JSON export option

Usage:
    uv run python scripts/chat.py --game shopping
    uv run python scripts/chat.py --games medical,shopping,support
    uv run python scripts/chat.py --game restaurant --export conversation.json
"""

import argparse
import json
import sys
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: uv sync --extra dev")
    sys.exit(1)


# Color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Text colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Background colors
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"


def color(text: str, color_code: str, bold: bool = False) -> str:
    """Apply color to text."""
    prefix = Colors.BOLD if bold else ""
    return f"{prefix}{color_code}{text}{Colors.RESET}"


def format_confidence(conf: float) -> str:
    """Format confidence with color coding."""
    if conf >= 0.85:
        return color(f"{conf:.2f}", Colors.GREEN, bold=True)
    elif conf >= 0.70:
        return color(f"{conf:.2f}", Colors.YELLOW)
    else:
        return color(f"{conf:.2f}", Colors.RED)


def format_negotiation(neg_data: Dict[str, Any]) -> str:
    """Format negotiation metadata."""
    if not neg_data:
        return ""

    rounds = neg_data.get("rounds", [])
    reason = neg_data.get("reason", "unknown")
    final_conf = neg_data.get("final_confidence", 0.0)

    if not rounds:
        return ""

    # Format rounds summary
    round_summary = []
    for r in rounds:
        delta = r.get("delta", 0.0)
        delta_str = f"{delta:+.2f}" if delta >= 0 else f"{delta:.2f}"
        delta_color = Colors.GREEN if delta > 0.05 else Colors.YELLOW if delta > 0 else Colors.RED
        round_summary.append(
            f"    R{r['n']}: {r['before']:.2f} → {r['after']:.2f} "
            f"({color(delta_str, delta_color)})"
        )

    result_color = Colors.GREEN if reason == "threshold_met" else Colors.YELLOW
    header = color(f"  [Negotiation: {len(rounds)} rounds, {reason}]", result_color)

    return "\n".join([header] + round_summary)


class ChatSession:
    """Interactive chat session with LGDL runtime."""

    def __init__(self, api_url: str, game_id: str, export_path: Optional[str] = None):
        self.api_url = api_url
        self.game_id = game_id
        self.export_path = export_path
        self.conversation_id = str(uuid.uuid4())
        self.user_id = "chat_user"
        self.history: List[Dict[str, Any]] = []
        self.turn_count = 0

    def send_message(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Send message to LGDL runtime."""
        payload = {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "input": user_input
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(color(f"\nError communicating with API: {e}", Colors.RED, bold=True))
            return None

    def display_response(self, response: Dict[str, Any]):
        """Display assistant response with formatting."""
        move_id = response.get("move_id", "unknown")
        confidence = response.get("confidence", 0.0)
        message = response.get("response", "")
        action = response.get("action")
        firewall = response.get("firewall_triggered", False)
        negotiation = response.get("negotiation")

        # Format move and confidence
        move_str = color(move_id, Colors.CYAN, bold=True)
        conf_str = format_confidence(confidence)

        # Build status line
        status_parts = [f"({move_str}, conf={conf_str}"]
        if action:
            status_parts.append(color(f"action={action}", Colors.MAGENTA))
        if firewall:
            status_parts.append(color("FIREWALL", Colors.BG_RED))
        status_parts.append(")")

        status_line = " ".join(status_parts)

        # Print response
        print(f"\n{color('Assistant', Colors.GREEN, bold=True)} {status_line}:")
        print(f"  {message}")

        # Print negotiation details if present
        if negotiation:
            neg_info = format_negotiation(negotiation)
            if neg_info:
                print(neg_info)

    def run(self):
        """Run interactive chat loop."""
        # Print header
        game_name = color(self.game_id, Colors.CYAN, bold=True)
        print(f"\n{'='*70}")
        print(f"  {color('LGDL Interactive Chat', Colors.BOLD)} - {game_name}")
        print(f"  API: {color(self.api_url, Colors.DIM)}")
        print(f"  Conversation ID: {color(self.conversation_id[:8], Colors.DIM)}")
        print(f"{'='*70}")
        print(f"\nType {color('quit', Colors.YELLOW)} or {color('exit', Colors.YELLOW)} to end session.\n")

        # Chat loop
        while True:
            try:
                # Get user input
                user_input = input(f"{color('You', Colors.BLUE, bold=True)}: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print(color("\nGoodbye!", Colors.YELLOW, bold=True))
                    break

                # Send to API
                self.turn_count += 1
                response = self.send_message(user_input)

                if response:
                    # Record in history
                    self.history.append({
                        "turn": self.turn_count,
                        "timestamp": datetime.now().isoformat(),
                        "user_input": user_input,
                        "response": response
                    })

                    # Display response
                    self.display_response(response)
                else:
                    print(color("\n⚠ No response from server", Colors.YELLOW))

                print()  # Blank line for readability

            except KeyboardInterrupt:
                print(color("\n\nInterrupted. Exiting...", Colors.YELLOW, bold=True))
                break
            except Exception as e:
                print(color(f"\nUnexpected error: {e}", Colors.RED, bold=True))
                continue

        # Export conversation if requested
        if self.export_path and self.history:
            self.export_conversation()

        # Print summary
        print(f"\n{color('Session Summary:', Colors.BOLD)}")
        print(f"  Turns: {self.turn_count}")
        print(f"  Conversation ID: {self.conversation_id}")
        if self.export_path:
            print(f"  Exported to: {color(self.export_path, Colors.GREEN)}")

    def export_conversation(self):
        """Export conversation history to JSON."""
        export_data = {
            "game_id": self.game_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "turn_count": self.turn_count,
            "api_url": self.api_url,
            "history": self.history
        }

        try:
            with open(self.export_path, 'w') as f:
                json.dump(export_data, f, indent=2)
            print(color(f"\n✓ Conversation exported to {self.export_path}", Colors.GREEN))
        except Exception as e:
            print(color(f"\n✗ Export failed: {e}", Colors.RED))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive LGDL chat REPL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single game
  uv run python scripts/chat.py --game shopping

  # Custom API URL
  uv run python scripts/chat.py --game medical --api http://localhost:8000

  # With conversation export
  uv run python scripts/chat.py --game restaurant --export my_conversation.json
        """
    )

    parser.add_argument(
        "--game",
        required=True,
        help="Game ID to chat with (e.g., medical, shopping, support, restaurant, greeting)"
    )

    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="Base API URL (default: %(default)s)"
    )

    parser.add_argument(
        "--export",
        metavar="FILE",
        help="Export conversation to JSON file"
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Construct game-specific API URL
    api_url = f"{args.api.rstrip('/')}/games/{args.game}/move"

    # Check if server is reachable
    try:
        healthz_url = f"{args.api.rstrip('/')}/healthz"
        response = requests.get(healthz_url, timeout=2)
        response.raise_for_status()
        health_data = response.json()

        # Verify game is loaded
        if args.game not in health_data.get("games", []):
            print(color(f"Error: Game '{args.game}' not loaded on server", Colors.RED, bold=True))
            print(f"Available games: {', '.join(health_data.get('games', []))}")
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(color(f"Error: Cannot reach LGDL server at {args.api}", Colors.RED, bold=True))
        print(f"Details: {e}")
        print(f"\nMake sure the server is running:")
        print(color(f"  uv run lgdl serve --games {args.game}:examples/{args.game}/game.lgdl", Colors.CYAN))
        sys.exit(1)

    # Start chat session
    session = ChatSession(api_url, args.game, args.export)
    session.run()


if __name__ == "__main__":
    main()
