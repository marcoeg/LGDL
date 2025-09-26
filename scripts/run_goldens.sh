#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure env is ready
uv venv "$ROOT_DIR/.venv" >/dev/null 2>&1 || true
source "$ROOT_DIR/.venv/bin/activate"
# Ensure we have dev extras (requests, PyYAML) available for the inline runner
uv sync --extra dev >/dev/null

# Start API
uv run uvicorn lgdl.runtime.api:app --port 8000 --reload &
API_PID=$!
sleep 2

# Run goldens (inline python uses requests + PyYAML; installed via dev extra)
uv run python - <<'EOF'
import yaml, requests, sys
g = yaml.safe_load(open("examples/medical/golden_dialogs.yaml"))
failures = 0
for d in g["dialogs"]:
    for t in d["turns"]:
        r = requests.post("http://localhost:8000/move", json={
            "conversation_id":"c1","user_id":"u1","input":t["input"]
        })
        if r.status_code != 200:
            print(f"[FAIL] {d['name']}: HTTP {r.status_code}")
            failures += 1
            continue
        data = r.json()
        exp = t["expect"]
        ok = True
        if "move" in exp and data["move_id"] != exp["move"]:
            print(f"[FAIL] {d['name']}: move {data['move_id']} != {exp['move']}")
            ok = False
        if "confidence" in exp:
            op, thr = exp["confidence"][:2], float(exp["confidence"][2:])
            if op == ">=" and data["confidence"] < thr: ok = False
            if op == "<=" and data["confidence"] > thr: ok = False
            if not ok:
                print(f"[FAIL] {d['name']}: confidence {data['confidence']} vs {exp['confidence']}")
        if "response_contains" in exp:
            for s in exp["response_contains"]:
                if s.lower() not in data["response"].lower():
                    print(f"[FAIL] {d['name']}: missing '{s}' in response")
                    ok = False
        print(f"[{'OK' if ok else 'FAIL'}] {d['name']}")
        if not ok: failures += 1
sys.exit(1 if failures else 0)
EOF

kill $API_PID
