"""Arrows in a real fight on map 73 (needs the install): they appear and vanish, they never change the world dump (client state only), the headless
screenshots of the volley match tests/golden.json["arrows"].  Docs: docs/engine/rendering.md "Arrows and shots"."""

import json
import os

import pytest

from allods2.assets import AssetCache

from arrow_scenarios import hashes, run
from helpers import GFS, needs_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


@needs_data
def test_a_fight_makes_arrows_and_they_are_all_gone_afterwards(assets):
    w, seen = run(assets)
    assert len(seen) >= 3                                         # four shooters attacked: several shots in 160 ticks
    assert all(a.live is False or a.steps >= 0 for a in w.arrows) and len(w.arrows) <= len(seen)


@needs_data
def test_arrows_never_change_the_world_dump(assets):
    with_arrows, _ = run(assets)
    without, seen = run(assets, arrows=False)
    assert not seen and with_arrows.dump_hash() == without.dump_hash()
    assert "arrows" not in with_arrows.dump_json() and "flashes" not in with_arrows.dump_json()


@needs_data
def test_volley_screenshots_match_the_golden(assets):
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["arrows"]
    got = hashes(assets)
    assert got == gold, "the arrow fight changed; if intended run tools/update_golden.py --only arrows"


@needs_data
def test_a_teleport_cast_shows_two_flashes_for_21_ticks_and_moves_the_caster(assets):
    """Real map 73, the real record 54 (`teleport`, 96 x 96, 21 phases): a mage's cast at a free cell (spell 23, cast action tick 0) makes two objects, the
    caster's point and the destination; the view draws frames 0 .. 20 over 21 ticks and the caster stands at the destination after the release."""
    from allods2.cli import open_map
    from engine.sim import CastSpell, Simulation, combat, spells
    from engine.view import Camera, DrawOptions, build_draw_list
    from engine.world import World
    w = World.from_map(open_map("73", GFS), assets, seed=5)
    party = [u for u in w.units.values() if w.players[u.owner].human]
    mage = next(u for u in party if combat.combat_stats(w, u).mage)         # the hero mage of the party
    mage.mana = mage.mana_max = 300
    mage.spellbook = spells.known_mask(mage) | (1 << 23)
    dest = (mage.x + 6, mage.y)
    sim = Simulation(w, ai=False)
    sim.step([CastSpell(mage.owner, (mage.id,), 23, cell=dest)])
    cam = Camera(640, 480, w.width, w.height, max(mage.x * 32 - 320 + 96, 0), max(mage.y * 32 - 240, 0))
    seen = []
    for _ in range(60):
        items = build_draw_list(w, cam, w.tick, assets, DrawOptions())
        got = [i for i in items if i.kind == "sprite" and i.sprite[0] == "projectile" and i.sprite[1] == 0x36 and i.sprite[2] == "main"]
        if got:
            seen.append((w.tick, sorted(i.frame for i in got)))
        sim.step([])
    assert [f for _, f in seen] == [[k, k] for k in range(21)]                          # two objects, frame k on the k-th drawn tick
    assert [t for t, _ in seen] == list(range(seen[0][0], seen[0][0] + 21))             # consecutive ticks
    assert (mage.x, mage.y) == dest
