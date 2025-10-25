"""
FastAPI runtime for LGDL games.

Multi-game support with registry, health checks, and metadata endpoints.

Copyright (c) 2025 Graziano Labs Corp.
"""

from fastapi import FastAPI, HTTPException, Path as PathParam
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
import time, uuid, os
from pathlib import Path
from .registry import GameRegistry

app = FastAPI(title="LGDL Runtime", version="0.2")

# Global registry
REGISTRY = GameRegistry()
DEV_MODE = os.getenv("LGDL_DEV_MODE", "0") == "1"


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


@app.on_event("startup")
async def load_games():
    """Load games specified in LGDL_GAMES env var or default."""
    games_spec = os.getenv("LGDL_GAMES")
    if games_spec:
        # Format: "medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl"
        for pair in games_spec.split(","):
            game_id, path = pair.split(":")
            REGISTRY.register(game_id.strip(), path.strip(), version="0.1")
    else:
        # Default: load medical example
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        REGISTRY.register(
            "medical_scheduling",
            str(examples_dir / "medical" / "game.lgdl"),
            version="0.1"
        )


@app.get("/healthz")
async def healthz():
    """
    Health check endpoint with registry status.

    Returns:
        Status info: healthy status, game count, loaded game IDs
    """
    return {
        "status": "healthy",
        "games_loaded": len(REGISTRY.list_games()),
        "games": [g["id"] for g in REGISTRY.list_games()]
    }


@app.get("/games")
async def list_games():
    """
    List all available games with metadata.

    Returns:
        List of games with id, name, version, file_hash
    """
    return {"games": REGISTRY.list_games()}


@app.get("/games/{game_id}")
async def get_game_metadata(game_id: str = PathParam(...)):
    """
    Get metadata for a specific game.

    Args:
        game_id: Game identifier

    Returns:
        Game metadata including path and file hash

    Raises:
        404: If game not found
    """
    try:
        return REGISTRY.get_metadata(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/games/{game_id}/move", response_model=MoveResponse)
async def move(
    req: MoveRequest,
    game_id: str = PathParam(..., description="Game identifier")
):
    """
    Execute a move in a specific game.

    Args:
        game_id: Game identifier
        req: Move request with conversation_id, user_id, input

    Returns:
        Move response with move_id, confidence, response, action, etc.

    Raises:
        404: If game not found
        500: On runtime error
    """
    try:
        runtime = REGISTRY.get_runtime(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e))

    t0 = time.perf_counter()
    result = await runtime.process_turn(
        req.conversation_id, req.user_id, req.input, req.context or {}
    )

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


@app.post("/move", response_model=MoveResponse, deprecated=True)
async def move_legacy(req: MoveRequest):
    """
    Legacy endpoint (routes to default game).

    DEPRECATED: Use /games/{game_id}/move instead.

    Returns:
        Same as /games/{game_id}/move
    """
    return await move(req, "medical_scheduling")


# Deprecation header middleware
class DeprecationHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path == "/move":
            response.headers["X-Deprecation-Warning"] = (
                "Use /games/{game_id}/move instead. "
                "This endpoint will be removed in v2.0."
            )
        return response


app.add_middleware(DeprecationHeaderMiddleware)


# Hot reload endpoint (dev mode only)
if DEV_MODE:
    @app.post("/games/{game_id}/reload")
    async def reload_game(game_id: str):
        """
        Reload game from disk (dev mode only).

        Args:
            game_id: Game to reload

        Returns:
            Status message

        Raises:
            404: If game not found
            500: If reload fails
        """
        try:
            REGISTRY.reload(game_id)
            return {"status": "reloaded", "game_id": game_id}
        except KeyError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(500, f"Reload failed: {e}")
