from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import time, uuid
from pathlib import Path
from .engine import LGDLRuntime, load_compiled_game

app = FastAPI(title="LGDL Runtime (MVP)", version="0.1")

class MoveRequest(BaseModel):
    conversation_id: str
    user_id: str
    input: str
    context: Optional[Dict[str, Any]] = None

class MoveResponse(BaseModel):
    move_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    response: str
    action: Optional[str] = None
    manifest_id: str
    latency_ms: float = Field(ge=0.0)
    firewall_triggered: bool = False

COMPILED = load_compiled_game(str(Path(__file__).resolve().parents[2] / "examples" / "medical" / "game.lgdl"))
RUNTIME = LGDLRuntime(compiled=COMPILED)

@app.post("/move", response_model=MoveResponse)
async def move(req: MoveRequest):
    t0 = time.perf_counter()
    result = await RUNTIME.process_turn(req.conversation_id, req.user_id, req.input, req.context or {})
    if not result:
        raise HTTPException(500, "Runtime error")
    latency = round((time.perf_counter() - t0) * 1000, 2)
    return MoveResponse(
        move_id=result["move_id"],
        confidence=result["confidence"],
        response=result["response"],
        action=result.get("action"),
        manifest_id=result.get("manifest_id", str(uuid.uuid4())),
        latency_ms=latency,
        firewall_triggered=result.get("firewall_triggered", False),
    )
