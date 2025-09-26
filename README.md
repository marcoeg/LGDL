# LGDL MVP (v0.1) — Full Skeleton

This repository contains a *working* MVP for LGDL:
- Lark grammar (`lgdl/spec/grammar_v0_1.lark`)
- Parser + Transformer → typed AST
- IR compiler
- Runtime with `POST /move`
- Matcher with **OpenAI embeddings** (if `OPENAI_API_KEY` set) or offline fallback
- CLI (`validate`, `compile`)
- Examples + golden dialogs
- Basic tests

## Install

Create & sync the environment
### new venv managed by uv
uv venv .venv

### install runtime deps only
uv sync

### …or include extras and dev tools:
uv sync --extra openai --extra dev

Run things with uv (no manual activation needed)
### start API
uv run uvicorn lgdl.runtime.api:app --reload

### run CLI
uv run lgdl validate examples/medical/game.lgdl
uv run lgdl compile examples/medical/game.lgdl -o out.ir.json

### run tests
uv run pytest

Enable embeddings
export OPENAI_API_KEY=sk-...
uv sync --extra openai
> now the runtime will use cosine similarity over OpenAI embeddings;
without the key (or without the extra), it falls back to token overlap.



```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or
pip install lark fastapi uvicorn pydantic jsonschema click numpy openai pytest
```

## Run API

```bash
export OPENAI_API_KEY=sk-...   # optional; enables embedding-based matching
uvicorn lgdl.runtime.api:app --reload
curl -s -X POST localhost:8000/move -H 'content-type: application/json'   -d '{"conversation_id":"c1","user_id":"u1","input":"I need to see Dr. Smith"}' | jq
```

## CLI

```bash
python -m lgdl.cli.main validate examples/medical/game.lgdl
python -m lgdl.cli.main compile  examples/medical/game.lgdl -o out.ir.json

uv run python scripts/goldens.py --file examples/medical/golden_dialogs.yaml --api http://localhost:8000/move -v

Tests

- uv run lgdl validate examples/medical/game.lgdl
- uv run pytest -q
- uv run bash scripts/run_goldens.sh

(Use uv run uvicorn lgdl.runtime.api:app --reload --port 8000 before running uv run python scripts/goldens.py, since it assumes the API is already up.)



```

## Tests

```bash
pip install pytest
pytest -q
```
