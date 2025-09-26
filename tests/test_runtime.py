import asyncio, os
from lgdl.runtime.engine import load_compiled_game, LGDLRuntime

async def _run():
    compiled = load_compiled_game("examples/medical/game.lgdl")
    rt = LGDLRuntime(compiled)
    r = await rt.process_turn("c1","u1","I need to see Dr. Smith",{})
    assert r["move_id"] == "appointment_request"
    assert r["confidence"] >= 0.6  # allow for embedding/fallback variance

def test_runtime_smoke():
    asyncio.run(_run())
