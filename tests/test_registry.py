"""
Tests for game registry and multi-game API.

Copyright (c) 2025 Graziano Labs Corp.
"""

import pytest
import pytest_asyncio
from pathlib import Path
from lgdl.runtime.registry import GameRegistry
from lgdl.runtime.engine import LGDLRuntime


# Registry unit tests

def test_register_game():
    """Register a game successfully."""
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    assert "test" in reg.games
    assert "test" in reg.runtimes


def test_duplicate_registration_fails():
    """Cannot register the same game_id twice."""
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    with pytest.raises(ValueError, match="already registered"):
        reg.register("test", "examples/medical/game.lgdl")


def test_missing_file_raises():
    """Registration fails with FileNotFoundError for missing files."""
    reg = GameRegistry()
    with pytest.raises(FileNotFoundError):
        reg.register("missing", "nonexistent.lgdl")


def test_get_runtime():
    """Get runtime for registered game."""
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    runtime = reg.get_runtime("test")
    assert isinstance(runtime, LGDLRuntime)


def test_get_runtime_not_found():
    """Get runtime raises KeyError for unregistered game."""
    reg = GameRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.get_runtime("nonexistent")


def test_get_metadata():
    """Get metadata for registered game."""
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    meta = reg.get_metadata("test")

    assert meta["id"] == "test"
    assert meta["name"] == "medical_scheduling"
    assert "file_hash" in meta
    assert len(meta["file_hash"]) == 8
    assert "path" in meta
    assert "version" in meta


def test_list_games():
    """List all registered games."""
    reg = GameRegistry()
    reg.register("game1", "examples/medical/game.lgdl")
    games = reg.list_games()

    assert len(games) == 1
    assert games[0]["id"] == "game1"
    assert all(key in games[0] for key in ["id", "name", "version", "file_hash"])


def test_list_games_multiple():
    """List multiple registered games."""
    reg = GameRegistry()
    reg.register("game1", "examples/medical/game.lgdl")
    reg.register("game2", "examples/medical/game.lgdl")  # Same file, different ID

    games = reg.list_games()
    assert len(games) == 2
    game_ids = [g["id"] for g in games]
    assert "game1" in game_ids
    assert "game2" in game_ids


def test_reload_game():
    """Reload a game from disk."""
    reg = GameRegistry()
    reg.register("test", "examples/medical/game.lgdl")
    original_hash = reg.get_metadata("test")["file_hash"]

    # Reload (should succeed)
    reg.reload("test")

    # Should still be registered
    assert "test" in reg.games
    assert "test" in reg.runtimes

    # Hash should be the same (file unchanged)
    reloaded_hash = reg.get_metadata("test")["file_hash"]
    assert reloaded_hash == original_hash


def test_reload_not_found():
    """Reload raises KeyError for unregistered game."""
    reg = GameRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.reload("nonexistent")


# API Integration Tests

@pytest_asyncio.fixture
async def test_client():
    """Create test client for FastAPI app."""
    from httpx import AsyncClient, ASGITransport
    import lgdl.runtime.api as api_module
    from lgdl.runtime.registry import GameRegistry
    from pathlib import Path

    # Initialize registry for testing (simulating startup event)
    api_module.REGISTRY = GameRegistry(state_manager=None)  # Stateless for tests

    # Manually load the medical game for testing
    examples_dir = Path(__file__).resolve().parents[1] / "examples"
    api_module.REGISTRY.register(
        "medical_scheduling",
        str(examples_dir / "medical" / "game.lgdl"),
        version="0.1"
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_module.app),
        base_url="http://test"
    ) as client:
        yield client

    # Cleanup: reset registry after tests
    api_module.REGISTRY = None


@pytest.mark.asyncio
async def test_api_healthz(test_client):
    """Test /healthz endpoint."""
    response = await test_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "games_loaded" in data
    assert "games" in data
    assert isinstance(data["games"], list)


@pytest.mark.asyncio
async def test_api_list_games(test_client):
    """Test GET /games endpoint."""
    response = await test_client.get("/games")
    assert response.status_code == 200
    games = response.json()["games"]
    assert len(games) >= 1
    assert all("id" in g and "name" in g and "file_hash" in g for g in games)


@pytest.mark.asyncio
async def test_api_get_game_metadata(test_client):
    """Test GET /games/{id} endpoint."""
    response = await test_client.get("/games/medical_scheduling")
    assert response.status_code == 200
    meta = response.json()
    assert meta["id"] == "medical_scheduling"
    assert meta["name"] == "medical_scheduling"
    assert "file_hash" in meta
    assert "path" in meta


@pytest.mark.asyncio
async def test_api_get_game_not_found(test_client):
    """Test GET /games/{id} with nonexistent game."""
    response = await test_client.get("/games/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_move_with_game_id(test_client):
    """Test POST /games/{id}/move endpoint."""
    response = await test_client.post(
        "/games/medical_scheduling/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["move_id"] == "appointment_request"
    assert data["confidence"] > 0.8


@pytest.mark.asyncio
async def test_api_move_game_not_found(test_client):
    """Test POST /games/{id}/move with nonexistent game."""
    response = await test_client.post(
        "/games/nonexistent/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "test"
        }
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_move_legacy(test_client):
    """Test legacy /move endpoint (deprecated)."""
    response = await test_client.post(
        "/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )
    assert response.status_code == 200
    assert "X-Deprecation-Warning" in response.headers
    assert "removed in v2.0" in response.headers["X-Deprecation-Warning"]

    data = response.json()
    assert data["move_id"] == "appointment_request"
    assert data["confidence"] > 0.8


@pytest.mark.asyncio
async def test_api_move_legacy_routes_to_default(test_client):
    """Verify legacy /move routes to medical_scheduling game."""
    # Test legacy endpoint
    legacy_response = await test_client.post(
        "/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )

    # Test new endpoint with same game
    new_response = await test_client.post(
        "/games/medical_scheduling/move",
        json={
            "conversation_id": "c1",
            "user_id": "u1",
            "input": "I need to see Dr. Smith"
        }
    )

    # Should return same results (minus deprecation header)
    assert legacy_response.status_code == new_response.status_code
    assert legacy_response.json()["move_id"] == new_response.json()["move_id"]
