"""
Game registry for multi-game LGDL runtime.

Manages loading, compiling, and serving multiple LGDL games
with metadata tracking and runtime caching.

Copyright (c) 2025 Graziano Labs Corp.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any

from ..parser.parser import parse_lgdl
from ..parser.ir import compile_game
from .engine import LGDLRuntime


class GameRegistry:
    """
    Registry for managing multiple LGDL games.

    Each game has:
    - Unique identifier (game_id)
    - Compiled IR and metadata
    - Dedicated runtime instance
    - File hash for cache invalidation
    """

    def __init__(self):
        """Initialize empty registry."""
        self.games: Dict[str, Dict[str, Any]] = {}
        self.runtimes: Dict[str, LGDLRuntime] = {}

    def register(self, game_id: str, path: str, version: str = "0.1"):
        """
        Load and compile a game with per-game capability configuration.

        Args:
            game_id: Unique identifier for this game
            path: Path to .lgdl file
            version: Grammar version (default: "0.1")

        Raises:
            ValueError: If game_id already registered
            FileNotFoundError: If path doesn't exist
            CompileError: If game fails to compile

        Note:
            Automatically locates capability_contract.json in the same directory
            as the .lgdl file. If found, enables per-game capabilities.
        """
        if game_id in self.games:
            raise ValueError(f"Game '{game_id}' already registered")

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Game file not found: {path}")

        # Compute file hash for cache invalidation
        content = path_obj.read_text()
        file_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

        # Parse and compile
        game_ast = parse_lgdl(path)
        compiled = compile_game(game_ast)

        # Auto-locate capability_contract.json in same directory
        contract_path = path_obj.parent / "capability_contract.json"
        capability_contract_path = None
        if contract_path.exists():
            capability_contract_path = str(contract_path.absolute())

        self.games[game_id] = {
            "path": str(path_obj.absolute()),
            "version": version,
            "compiled": compiled,
            "name": compiled["name"],
            "file_hash": file_hash,
            "last_compiled": path_obj.stat().st_mtime,
            "capability_contract_path": capability_contract_path
        }

        # Create per-game runtime with auto-extracted allowlist and capability contract
        self.runtimes[game_id] = LGDLRuntime(
            compiled=compiled,
            capability_contract_path=capability_contract_path
        )

    def get_runtime(self, game_id: str) -> LGDLRuntime:
        """
        Get runtime for a specific game.

        Args:
            game_id: Game identifier

        Returns:
            LGDLRuntime instance for this game

        Raises:
            KeyError: If game not found
        """
        if game_id not in self.runtimes:
            available = list(self.runtimes.keys())
            raise KeyError(
                f"Game '{game_id}' not found. Available: {available}"
            )
        return self.runtimes[game_id]

    def get_metadata(self, game_id: str) -> dict:
        """
        Get metadata for a specific game.

        Args:
            game_id: Game identifier

        Returns:
            Dictionary with game metadata

        Raises:
            KeyError: If game not found
        """
        if game_id not in self.games:
            raise KeyError(f"Game '{game_id}' not found")
        meta = self.games[game_id]
        return {
            "id": game_id,
            "name": meta["name"],
            "version": meta["version"],
            "path": meta["path"],
            "file_hash": meta["file_hash"]
        }

    def list_games(self) -> list[dict]:
        """List all registered games with metadata."""
        return [self.get_metadata(gid) for gid in self.games.keys()]

    def reload(self, game_id: str):
        """
        Reload a game from disk (for hot reload in dev mode).

        Args:
            game_id: Game to reload

        Raises:
            KeyError: If game not registered
            CompileError: If reload fails
        """
        if game_id not in self.games:
            raise KeyError(f"Game '{game_id}' not found")

        meta = self.games[game_id]
        path = meta["path"]
        version = meta["version"]

        # Re-register (will overwrite)
        del self.games[game_id]
        del self.runtimes[game_id]
        self.register(game_id, path, version)
