"""AI casting on a real campaign map (phase K; game files, skipped without the install).

Map 73: the party of four knights walks to the nearest computer-owned spell user; with the AI on, the computer's mages (`2M_Knight3_73`
with Lightning / Poison Cloud / Shield) and special-attack monsters cast on their own.  Checks: computer-owned units start casts, a damage
spell of theirs lands, their buffs become effects (Shield once per mage: an active Shield ends the idle recast, ai.md 12.5; Bless on their
friends), the run is deterministic and the world stays consistent.  Spec: docs/engine/ai.md 12, docs/engine/effects.md.
"""

import math
from collections import Counter

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import MoveUnits, Simulation, spells
from engine.world import CastReleased, CastStarted, Damage, World

from helpers import GFS, needs_data

pytestmark = needs_data
TICKS = 1500


def play(seed=3):
    a = AssetCache(GFS)
    w = World.from_map(open_map("73"), a, seed=seed)
    party = [u for u in w.units.values() if w.players[u.owner].human]
    casters = [u for u in w.units.values() if not w.players[u.owner].human and spells.known_mask(u)]
    goal = min(casters, key=lambda c: (min(math.hypot(c.x - h.x, c.y - h.y) for h in party), c.id))
    sim = Simulation(w, ai=True)
    sim.step([MoveUnits(party[0].owner, tuple(u.id for u in party), (goal.x, goal.y))])
    for _ in range(TICKS - 1):
        sim.step()
    return w, sim


def test_computer_casters_cast_on_their_own_and_their_buffs_are_effects():
    w, sim = play()
    computer = {e.caster for e in w.fight_log if isinstance(e, CastStarted) and not w.players[_owner(w, e.caster)].human}
    assert computer, "no computer-owned unit started a cast"
    released = [e for e in w.fight_log if isinstance(e, CastReleased) and e.caster in computer]
    assert released or w.unbuilt_casts
    assert any(isinstance(e, Damage) and e.attacker in computer for e in w.fight_log)
    shields = Counter(e.caster for e in w.fight_log if isinstance(e, CastStarted) and e.spell == spells.SHIELD and e.caster in computer)
    assert shields and max(shields.values()) == 1                # the Shield effect bit stops the idle recast (FUN_0057a999)
    assert any(u.effect_mask & 1 << spells.SHIELD for u in w.units.values())
    assert any(e.id == 20 for u in w.units.values() for e in u.effects)    # Bless on a friend at full mana
    assert not w.unbuilt_casts
    assert any(getattr(c, "ai", False) and c.__class__.__name__ == "CastSpell" for _, c in sim.log)
    assert w.check_consistency() == []


def _owner(w, uid):
    u = w.units.get(uid) or w.corpses.get(uid)
    return u.owner


def test_the_casting_run_is_deterministic():
    a, _ = play()
    b, _ = play()
    assert a.dump_hash() == b.dump_hash() and a.unbuilt_casts == b.unbuilt_casts
