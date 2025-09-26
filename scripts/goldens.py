#!/usr/bin/env python3
"""
Run LGDL golden dialogs against a live runtime.

Assumptions:
- FastAPI runtime is already running on http://localhost:8000
- Golden file defaults to examples/medical/golden_dialogs.yaml
- Requires: PyYAML, requests  (install via: uv sync --extra dev)
"""

from __future__ import annotations
import argparse
import sys
import time
import re
from typing import Any, Dict, List

import requests
import yaml


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run LGDL golden dialogs against a live runtime.")
    p.add_argument(
        "--api",
        default="http://localhost:8000/move",
        help="Runtime /move endpoint (default: %(default)s)",
    )
    p.add_argument(
        "--file",
        default="examples/medical/golden_dialogs.yaml",
        help="Path to golden dialogs YAML (default: %(default)s)",
    )
    p.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop after the first failure (default: continue).",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (print responses).",
    )
    return p.parse_args()


def color(s: str, c: str) -> str:
    codes = {"red": "31", "green": "32", "yellow": "33", "cyan": "36"}
    return f"\x1b[{codes.get(c,'0')}m{s}\x1b[0m"


def load_goldens(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "dialogs" not in data:
        raise ValueError("Golden file missing top-level 'dialogs' key.")
    return data


def parse_confidence_expr(expr: str) -> tuple[str, float]:
    """
    Parse expressions like '>=0.80', '<=0.5', '>0.7', '==0.9'
    Returns (op, value). Defaults to '>=', float(value) if it looks like a bare number.
    """
    expr = str(expr).strip()
    m = re.match(r"^(>=|<=|==|>|<)\s*([0-9]*\.?[0-9]+)$", expr)
    if m:
        return m.group(1), float(m.group(2))
    # bare number => '>=' that number
    try:
        return ">=", float(expr)
    except ValueError:
        raise ValueError(f"Unrecognized confidence expression: {expr!r}")


def check_confidence(op: str, expected: float, actual: float) -> bool:
    if op == ">=":
        return actual >= expected
    if op == "<=":
        return actual <= expected
    if op == ">":
        return actual > expected
    if op == "<":
        return actual < expected
    if op == "==":
        # float equality is harsh; give a tiny epsilon
        return abs(actual - expected) <= 1e-6
    return False


def run_dialogs(api: str, goldens: Dict[str, Any], verbose: bool, stop_on_fail: bool) -> int:
    total_turns = 0
    total_fail = 0
    start_time = time.time()

    for dialog in goldens.get("dialogs", []):
        dname = dialog.get("name", "<unnamed>")
        turns: List[Dict[str, Any]] = dialog.get("turns", [])
        for t in turns:
            total_turns += 1
            user_input = t.get("input", "")
            expect = t.get("expect", t.get("expected", {}))  # support 'expect' or legacy 'expected'

            try:
                r = requests.post(api, json={
                    "conversation_id": "golden",
                    "user_id": "tester",
                    "input": user_input
                }, timeout=10)
                ok_http = (r.status_code == 200)
            except requests.RequestException as e:
                print(color(f"[FAIL] {dname}: HTTP error {e}", "red"))
                total_fail += 1
                if stop_on_fail:
                    return total_fail
                continue

            if not ok_http:
                print(color(f"[FAIL] {dname}: HTTP {r.status_code}", "red"))
                if verbose:
                    print(r.text)
                total_fail += 1
                if stop_on_fail:
                    return total_fail
                continue

            data = r.json()
            if verbose:
                print(color(f"[RESP] {dname}", "cyan"), data)

            # Assertions
            ok = True
            details: List[str] = []

            # move
            exp_move = expect.get("move")
            if exp_move is not None:
                if data.get("move_id") != exp_move:
                    ok = False
                    details.append(f"move_id={data.get('move_id')} != {exp_move}")

            # confidence
            exp_conf = expect.get("confidence")
            if exp_conf is not None:
                try:
                    op, val = parse_confidence_expr(str(exp_conf))
                    if not check_confidence(op, val, float(data.get("confidence", 0.0))):
                        ok = False
                        details.append(f"confidence {data.get('confidence')} !{op} {val}")
                except Exception as e:
                    ok = False
                    details.append(f"confidence parse error: {e}")

            # action
            if "action" in expect:
                exp_action = expect.get("action")
                actual_action = data.get("action")
                if exp_action != actual_action:
                    ok = False
                    details.append(f"action {actual_action} != {exp_action}")

            # response_contains
            exp_contains = expect.get("response_contains", [])
            resp_text = str(data.get("response", ""))
            for needle in exp_contains:
                if str(needle).lower() not in resp_text.lower():
                    ok = False
                    details.append(f"response missing '{needle}'")

            if ok:
                print(color(f"[OK]   {dname} — input: {user_input!r}", "green"))
            else:
                print(color(f"[FAIL] {dname} — input: {user_input!r}", "red"))
                if details:
                    for d in details:
                        print("       -", d)
                total_fail += 1
                if stop_on_fail:
                    return total_fail

    dur_ms = int((time.time() - start_time) * 1000)
    passed = total_turns - total_fail
    print()
    print(color(f"Summary: {passed}/{total_turns} passed in {dur_ms} ms", "yellow" if total_fail else "green"))
    return total_fail


def main() -> int:
    args = parse_args()
    try:
        goldens = load_goldens(args.file)
    except Exception as e:
        print(color(f"Failed to load goldens: {e}", "red"))
        return 2

    failures = run_dialogs(api=args.api, goldens=goldens, verbose=args.verbose, stop_on_fail=args.stop_on_fail)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
