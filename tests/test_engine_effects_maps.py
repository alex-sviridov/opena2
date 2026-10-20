"""Spell effects with the install's spell table and a real party (phase K2; game files, skipped without the install).

Map 73 (four human knights, a mage among them): the handlers' values from data.bin, the human stat hooks (protection, Shield absorption through
the recompute, Haste on the speed and the turn rate, Darkness on the scan) and expiry.  Spec: docs/engine/effects.md.
"""

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import ai, combat, effects, movement
from engine.world import World

from helpers import GFS, needs_data

pytestmark = needs_data


def party():
    a = AssetCache(GFS)
    w = World.from_map(open_map("73"), a, seed=1)
    return w, [u for u in w.units.values() if w.players[u.owner].human]


def give(w, u, n, level):
    e = effects.make_effect(w, w.spell_table.get(n), level, True, u)
    effects.apply(w, u, e)
    return e


def test_install_values_of_the_handlers():
    w, ps = party()
    u = ps[0]
    t = w.spell_table
    assert (effects.make_effect(w, t.get(27), 40, True, u).value, effects.make_effect(w, t.get(27), 40, True, u).ticks) == (7, 14482)
    p = effects.make_effect(w, t.get(6), 30, True, u)
    assert (p.kind, p.flags, p.value, p.ticks) == (6, 2, -3, 128)
    s = effects.make_effect(w, t.get(18), 50, False, u) or effects.Effect(18, kind=16, value=5)
    assert (s.kind, s.value) == (16, 5)                                         # absorption +5, the first term of the text
    assert effects.make_effect(w, t.get(14), 30, True, u).value == -2 and effects.make_effect(w, t.get(15), 30, True, u).value == 2


def test_human_hooks_protection_shield_haste_darkness_and_expiry():
    w, ps = party()
    u = ps[0]
    st0 = combat.combat_stats(w, u)
    prot0, absorb0, speed0, scan0 = st0.block.prot[1], st0.block.absorb, movement.unit_speed(u), ai._scan_range(u)
    give(w, u, 4, 40)                                                           # Protection from Fire: +20 through the recompute (capped)
    from allods2.formats import progression as prog
    cap = prog.attributes(u.stats)[3] // 2 + 70                                 # the recompute caps a protection at spirit / 2 + 70 and 100
    assert combat.combat_stats(w, u).block.prot[1] == min(100, cap, prot0 + 20) > prot0
    give(w, u, 27, 40)                                                          # Shield: the bonus word +0x100
    assert combat.combat_stats(w, u).block.absorb == absorb0 + 7
    give(w, u, 21, 30)                                                          # Haste: the bonus word +0xd8; the turn rate follows the speed
    assert movement.unit_speed(u) == speed0 + 3 and movement.turn_rate(u) == (speed0 + 3) & 255
    give(w, u, 14, 30)                                                          # Darkness: twice until the next recompute
    assert ai._scan_range(u) == (scan0 - 4) & 0xFF
    give(w, u, 20, 30)                                                          # a kind-0 effect runs the recompute: the direct part is dropped
    assert ai._scan_range(u) == (scan0 - 2) & 0xFF
    for e in u.effects:
        if e.id in (21, 27):
            e.ticks = 1
    movement._tick_unit(w, u)
    assert movement.unit_speed(u) == speed0 and combat.combat_stats(w, u).block.absorb == absorb0
