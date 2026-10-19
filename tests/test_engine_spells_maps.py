"""A party with a mage fights on a real campaign map with melee and Fire Arrow (I4c; game files, skipped without the install).

Map 73 is the one with a human party of four knights (fighter, archer, mage, healer).  Commands only: the fighters and the archer attack the nearest
hostile unit, the mage alternates `CastSpell` (Fire Arrow, which the script adds to its book: the campaign teaches it later) and the staff attack.
The run ends when the party or the enemy group is dead.  Checks: it ends, it is deterministic, the cast / carrier / damage chain ran, the world's
indexes stay consistent, no unit hangs mid-step, and the world hash is the same when the same command log is driven at 30 and at 60 frames per second
with the draw list built every frame (the view never touches the world).
"""

import math

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import DEFAULT_SPEED, AttackUnit, CastSpell, Simulation, tick_period_ms
from engine.sim import combat, spells, xp
from engine.view import Camera, DrawOptions, build_draw_list
from engine.world import CastReleased, CastStarted, Damage, Died, World

from helpers import GFS, needs_graphics

pytestmark = needs_graphics
FIRE_ARROW = 1
MAX_TICKS = 3000
ENEMIES = 6


def build():
    a = AssetCache(GFS)
    w = World.from_map(open_map("73"), a, seed=5)
    party = [u for u in w.units.values() if w.players[u.owner].human]
    mage = next(u for u in party if combat.combat_stats(w, u).mage)
    mage.spellbook = spells.known_mask(mage) | (1 << FIRE_ARROW)
    enemies = sorted((u for u in w.units.values() if xp.hostile(w, mage, u)),
                     key=lambda u: math.hypot(u.x - mage.x, u.y - mage.y))[:ENEMIES]
    return a, w, party, mage, enemies


def nearest(w, u, group):
    live = [e for e in group if e.id in w.units and e.hp > 0]
    return min(live, key=lambda e: (math.hypot(e.x - u.x, e.y - u.y), e.id), default=None)


def commands(w, party, mage, enemies):
    """The script: every 32 ticks each living party member is (re)ordered at the nearest living enemy; the mage casts on every other round."""
    if w.tick % 32:
        return []
    out = []
    for i, u in enumerate(party):
        if u.hp <= 0 or u.id not in w.units:
            continue
        t = nearest(w, u, enemies)
        if t is None:
            continue
        if u is mage and (w.tick // 32) % 2 == 0 and u.mana >= 3:
            out.append(CastSpell(u.owner, (u.id,), FIRE_ARROW, t.id))
        else:
            out.append(AttackUnit(u.owner, (u.id,), t.id))
    return out


def finished(w, party, enemies):
    return (all(e.hp <= 0 or e.id not in w.units for e in enemies) or all(u.hp <= 0 or u.id not in w.units for u in party))


def play(fps=None):
    """Run the fight; `fps` None: one step per loop; else a render-clock driver that builds the draw list every frame."""
    a, w, party, mage, enemies = build()
    sim = Simulation(w, ai=True)
    cam = Camera(640, 480, w.width, w.height, max(mage.x * 32 - 320, 0), max(mage.y * 32 - 240, 0))
    if fps is None:
        while w.tick < MAX_TICKS and not finished(w, party, enemies):
            sim.step(commands(w, party, mage, enemies))
    else:
        period, frame, acc = tick_period_ms(DEFAULT_SPEED), 1000.0 / fps, 0.0
        while w.tick < MAX_TICKS and not finished(w, party, enemies):
            acc += frame
            while acc >= period and w.tick < MAX_TICKS and not finished(w, party, enemies):
                sim.step(commands(w, party, mage, enemies))
                acc -= period
            build_draw_list(w, cam, w.tick, a, DrawOptions())
    return w, party, enemies, sim


def kinds(w, cls):
    return [e for e in w.fight_log if isinstance(e, cls)]


def test_the_party_fights_to_the_end_with_melee_and_spells():
    w, party, enemies, sim = play()
    assert w.tick < MAX_TICKS, "neither side died within %d ticks" % MAX_TICKS
    assert kinds(w, CastStarted) and kinds(w, CastReleased) and kinds(w, Died)
    assert any(isinstance(e, Damage) and e.roll != 0 for e in w.fight_log) and len(kinds(w, Damage)) > len(kinds(w, CastReleased))
    assert w.check_consistency() == []


def test_the_fight_is_deterministic():
    a, b = play()[0], play()[0]
    assert a.dump_hash() == b.dump_hash() and a.tick == b.tick


@pytest.mark.parametrize("fps", [30, 60])
def test_the_same_fight_at_30_and_60_fps_gives_the_same_world(fps):
    ref = play()[0]
    got = play(fps)[0]
    assert got.tick == ref.tick and got.dump_hash() == ref.dump_hash()


def test_combat_on_keeps_the_indexes_consistent_and_nobody_hangs_mid_step():
    """The H integration check with the fight on: the AI plays, the party fights, a long run after the fight; the indexes stay consistent every
    32 ticks and no unit sits mid-step without progress between samples 8 ticks apart (`Mover.steps` always advances)."""
    a, w, party, mage, enemies = build()
    sim = Simulation(w, ai=True)
    prev = {}
    for n in range(1, 1501):
        sim.step(commands(w, party, mage, enemies) if not finished(w, party, enemies) else [])
        if n % 32 == 0:
            assert w.check_consistency() == [], "tick %d" % n
        if n % 8 == 0:
            cur = {u.id: (u.x, u.y, u.sub_x, u.sub_y, u.mover.steps) for u in w.units.values() if u.mover.step_ticks and u.hp > 0}
            stuck = [i for i, k in cur.items() if prev.get(i) == k]
            assert not stuck, "tick %d: mid-step without progress: %s" % (n, [hex(i) for i in stuck[:5]])
            prev = cur
