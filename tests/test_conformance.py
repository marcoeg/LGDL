from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game

def test_parse_and_compile():
    game = parse_lgdl("examples/medical/game.lgdl")
    ir = compile_game(game)
    assert ir["name"] == "medical_scheduling"
    assert len(ir["moves"]) >= 2
    mv = next(m for m in ir["moves"] if m["id"]=="appointment_request")
    assert mv["threshold"] >= 0.8
