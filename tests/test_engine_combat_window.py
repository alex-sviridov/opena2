"""The backend side of combat (I1): fight log -> floating numbers, Ctrl+L option, a short headless session.
Needs the install (sprite sets, human.pal, fonts)."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from allods2.assets import AssetCache
from engine.sim import AttackUnit
from engine.ui import DebugFlags
from engine.view import Camera, DrawOptions
from engine.view.damage import FloatingDamage
from engine.world import UNIT_ID_BASE, Damage, Died, Player, Unit, World
from helpers import GFS, needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


def world_with(assets, type_id):
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8), "arena")
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 3)
    a = Unit(UNIT_ID_BASE + 1, type_id, 1, 10, 10, hp=50, hp_max=50)
    b = Unit(UNIT_ID_BASE + 2, type_id, 2, 12, 10, hp=50, hp_max=50)
    w.add_unit(a)
    w.add_unit(b)
    return w, a, b


def a_type(assets):
    for tid in range(1, 400):
        s = assets.unit_set(tid)
        if s is not None and "attack" in s.actions:
            return tid
    raise AssertionError("no unit set")


def test_blows_that_took_hp_become_numbers_in_the_victims_colour_and_misses_do_not(assets):
    from engine.backend_pygame import window
    w, a, b = world_with(assets, a_type(assets))
    w.fight_log += [Damage(5, a.id, b.id, 7, 43, 12, True), Damage(5, a.id, b.id, 0, 43, -50, False),
                    Damage(5, a.id, b.id, 3, 40, 80, True), Died(6, b.id, a.id)]
    f = FloatingDamage()
    window.feed_fight_log(w, f, assets, 1, DrawOptions(), DebugFlags(), 1000)
    assert w.fight_log == []                                                   # drained
    assert [(n.unit, n.value, n.foreign) for n in f.numbers] == [(b.id, 10, True)]    # 7 + 3 merged, same unit and tick
    assert f.numbers[0].colour == 3
    cam = Camera(480, 480, 40, 40, 0, 0)
    out = window.floating_entries(w, f, cam, assets, assets.fs, 1100)
    assert len(out) == 1 and out[0][0] == "10" and len(out[0][1]) == 16


def test_the_option_off_makes_no_numbers_but_the_console_line_still_prints(assets, capsys):
    from engine.backend_pygame import window
    w, a, b = world_with(assets, a_type(assets))
    w.fight_log.append(Damage(9, a.id, b.id, 7, 43, 12, True))
    f = FloatingDamage()
    window.feed_fight_log(w, f, assets, 1, DrawOptions(flying_damage=False), DebugFlags(combat=True), 0)
    assert f.numbers == []
    assert "damage 7 hp 43" in capsys.readouterr().out


def test_a_headless_session_fights_and_draws_the_numbers(assets):
    from engine.backend_pygame import window
    from engine.view import TerrainView
    w, a, b = world_with(assets, a_type(assets))
    a.speed_mod = 24                                                        # a unit without a template has speed 0 (1/256 cell per tick)
    from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
    a.combat = CombatStats(AttackRecord(skill=500, lo=3, sp=0), ArmourBlock(), windup=4, recovery=2)
    b.combat = CombatStats(AttackRecord(), ArmourBlock())
    lay = window.Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, 8 * 32, 8 * 32, border=256)
    tv = TerrainView(w, assets.tileset())
    sim = window.run(w, tv, cam, lay, speed=8, assets=assets, options=DrawOptions(), commands=[AttackUnit(1, (a.id,), b.id)],
                     max_frames=120)
    assert b.hp < 50                                                        # blows landed during the session
    pygame.display.quit()
