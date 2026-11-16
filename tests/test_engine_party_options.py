"""Party options at the game start (message 0x46 subs 1 / 2 / 3, docs/engine/ai.md 12.8, simulation.md 8.3a)."""
import pytest

pytest.importorskip("pygame")
from engine.audio.settings import Settings
from engine.backend_pygame.window import party_option_commands
from engine.sim import SetAutoCast, SetFormation, SetRetreatMode


def test_game_start_sends_all_three_in_exe_order_even_when_equal():
    s = Settings()                                   # first-run defaults: formation 1, retreat 0, autocasting 0x19
    cmds = party_option_commands(1, s, 1, 0, 0x19, always=True)
    assert [type(c) for c in cmds] == [SetRetreatMode, SetFormation, SetAutoCast]
    assert (cmds[0].mode, cmds[1].mode, cmds[2].flags) == (0, 1, 0x19)


def test_options_ok_sends_only_changes():
    s = Settings()
    assert party_option_commands(1, s, 1, 0, 0x19) == []
    assert [type(c) for c in party_option_commands(1, s, 2, 0, 0x08)] == [SetFormation, SetAutoCast]
