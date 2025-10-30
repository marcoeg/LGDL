"""Tests for per-game runtime enhancements (Phase 1-6)."""

import pytest
from pathlib import Path
from lgdl.parser.ir import extract_capability_allowlist
from lgdl.runtime.engine import LGDLRuntime
from lgdl.runtime.registry import GameRegistry


def test_extract_capability_allowlist_empty():
    """Test extraction from IR with no capabilities."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "greet",
                "threshold": 0.8,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "respond",
                                "data": {"text": "Hello!"}
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    assert allowlist == set()


def test_extract_capability_allowlist_single():
    """Test extraction from IR with single capability."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "search",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "respond",
                                "data": {"text": "Searching..."}
                            },
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "catalog",
                                        "function": "search_products",
                                        "intent": "search",
                                        "await": False,
                                        "timeout": 3.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    assert allowlist == {"search_products"}


def test_extract_capability_allowlist_multiple():
    """Test extraction from IR with multiple capabilities."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "search",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "catalog",
                                        "function": "search_products",
                                        "intent": "search",
                                        "await": False,
                                        "timeout": 3.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            {
                "id": "add_to_cart",
                "threshold": 0.8,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "cart",
                                        "function": "add_item",
                                        "intent": "cart update",
                                        "await": False,
                                        "timeout": 2.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    assert allowlist == {"search_products", "add_item"}


def test_extract_capability_allowlist_if_chain():
    """Test extraction from IR with if_chain blocks."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "technical_issue",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "if_chain",
                        "chain": [
                            {
                                "condition": {"special": "uncertain"},
                                "actions": [
                                    {
                                        "type": "respond",
                                        "data": {"text": "Clarifying..."}
                                    }
                                ]
                            },
                            {
                                "condition": {"expr": "severity = 'critical'"},
                                "actions": [
                                    {
                                        "type": "escalate",
                                        "data": {"target": "engineering"}
                                    },
                                    {
                                        "type": "capability",
                                        "data": {
                                            "call": {
                                                "service": "ticketing",
                                                "function": "create_urgent_ticket",
                                                "intent": "urgent",
                                                "await": False,
                                                "timeout": 2.0
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    assert allowlist == {"create_urgent_ticket"}


def test_extract_capability_allowlist_duplicates():
    """Test that duplicate capabilities are deduplicated."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "search1",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "catalog",
                                        "function": "search_products",
                                        "intent": "search",
                                        "await": False,
                                        "timeout": 3.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            {
                "id": "search2",
                "threshold": 0.8,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "catalog",
                                        "function": "search_products",
                                        "intent": "search",
                                        "await": False,
                                        "timeout": 3.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    # Should only have one copy despite appearing in two moves
    assert allowlist == {"search_products"}


def test_extract_capability_allowlist_mixed_blocks():
    """Test extraction from IR with mixed block types (when, if_chain)."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "move1",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "service1",
                                        "function": "func1",
                                        "intent": "intent1",
                                        "await": False,
                                        "timeout": 2.0
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "kind": "if_chain",
                        "chain": [
                            {
                                "condition": {"expr": "x > 5"},
                                "actions": [
                                    {
                                        "type": "capability",
                                        "data": {
                                            "call": {
                                                "service": "service2",
                                                "function": "func2",
                                                "intent": "intent2",
                                                "await": False,
                                                "timeout": 3.0
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    allowlist = extract_capability_allowlist(ir)
    assert allowlist == {"func1", "func2"}


# Phase 2: LGDLRuntime Constructor Tests


def test_runtime_auto_extract_allowlist():
    """Test that runtime auto-extracts allowlist when not provided."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "search",
                "threshold": 0.5,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "capability",
                                "data": {
                                    "call": {
                                        "service": "catalog",
                                        "function": "search_products",
                                        "intent": "search",
                                        "await": False,
                                        "timeout": 3.0
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }

    runtime = LGDLRuntime(ir)
    assert runtime.policy.allowlist == {"search_products"}


def test_runtime_explicit_allowlist():
    """Test that runtime accepts explicit allowlist."""
    ir = {"name": "test_game", "moves": []}
    custom_allowlist = {"func1", "func2", "func3"}

    runtime = LGDLRuntime(ir, allowlist=custom_allowlist)
    assert runtime.policy.allowlist == custom_allowlist


def test_runtime_no_capability_contract():
    """Test that runtime works without capability contract (cap disabled)."""
    ir = {"name": "test_game", "moves": []}

    runtime = LGDLRuntime(ir)
    assert runtime.cap is None


def test_runtime_with_capability_contract():
    """Test that runtime accepts capability contract path."""
    ir = {"name": "test_game", "moves": []}
    contract_path = str(
        Path(__file__).resolve().parents[1] / "examples" / "medical" / "capability_contract.json"
    )

    runtime = LGDLRuntime(ir, capability_contract_path=contract_path)
    assert runtime.cap is not None


def test_runtime_backward_compatible():
    """Test that existing code without parameters still works."""
    ir = {
        "name": "test_game",
        "moves": [
            {
                "id": "greet",
                "threshold": 0.8,
                "triggers": [],
                "blocks": [
                    {
                        "kind": "when",
                        "condition": {"special": "confident"},
                        "actions": [
                            {
                                "type": "respond",
                                "data": {"text": "Hello!"}
                            }
                        ]
                    }
                ]
            }
        ]
    }

    # Old code: just pass compiled IR
    runtime = LGDLRuntime(ir)

    # Should work with empty allowlist (no capabilities in game)
    assert runtime.policy.allowlist == set()
    assert runtime.cap is None


# Phase 3: GameRegistry Tests


def test_registry_loads_capability_contract():
    """Test that registry loads capability_contract.json when present."""
    reg = GameRegistry()
    reg.register("medical", "examples/medical/game.lgdl")

    runtime = reg.get_runtime("medical")

    # Medical game has capability contract
    assert runtime.cap is not None
    # Allowlist should be extracted from IR
    assert "check_availability" in runtime.policy.allowlist


def test_registry_no_capability_contract():
    """Test that registry handles games without capability_contract.json."""
    reg = GameRegistry()
    reg.register("greeting", "examples/greeting/game.lgdl")

    runtime = reg.get_runtime("greeting")

    # Greeting game has no capability contract
    assert runtime.cap is None
    # Allowlist should be empty (no capabilities in game)
    assert runtime.policy.allowlist == set()


def test_registry_shopping_capability_contract():
    """Test that shopping game loads its own capability contract."""
    reg = GameRegistry()
    reg.register("shopping", "examples/shopping/game.lgdl")

    runtime = reg.get_runtime("shopping")
    meta = reg.games["shopping"]

    # Shopping game has capability contract
    assert runtime.cap is not None
    assert meta["capability_contract_path"] is not None
    assert "capability_contract.json" in meta["capability_contract_path"]

    # Allowlist should be extracted from shopping IR
    expected_funcs = {"search_products", "get_price", "add_item", "process_payment"}
    assert expected_funcs.issubset(runtime.policy.allowlist)


def test_registry_per_game_isolation():
    """Test that different games have isolated runtimes and allowlists."""
    reg = GameRegistry()
    reg.register("medical", "examples/medical/game.lgdl")
    reg.register("shopping", "examples/shopping/game.lgdl")

    medical_runtime = reg.get_runtime("medical")
    shopping_runtime = reg.get_runtime("shopping")

    # Different runtime instances
    assert medical_runtime is not shopping_runtime

    # Different allowlists
    assert medical_runtime.policy.allowlist != shopping_runtime.policy.allowlist

    # Medical has check_availability, shopping doesn't
    assert "check_availability" in medical_runtime.policy.allowlist
    assert "check_availability" not in shopping_runtime.policy.allowlist

    # Shopping has search_products, medical doesn't
    assert "search_products" in shopping_runtime.policy.allowlist
    assert "search_products" not in medical_runtime.policy.allowlist
