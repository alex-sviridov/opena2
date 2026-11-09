"""Scripted scenarios on small synthetic worlds (no game files) that collect `World.sound_events`: the source of `tests/golden.json["audio"]`
(`tools/update_golden.py --only audio`) and of `tests/test_engine_audio_events.py` (docs/engine/audio.md 8).  Each returns the event list."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np

from allods2.formats.unitstats import HUMAN, UnitType
from engine.sim import AttackUnit, CastSpell, PickUp, Simulation, UseStructure
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.world import UNIT_ID_BASE, MapObject, Player, Unit, World

SOUNDS = [100, 200, 220, 221, 240]          # units.reg Sound: attack, blow, easy, hard, dead
EAST = 64
N = 40


class FakeAssets:
    """What `sim/sounds.py` asks of the AssetCache: the units.reg records' `Sound` list of type 1."""

    def unit_types(self):
        return {1: SimpleNamespace(values={"Sound": SOUNDS})}


def world(seed=3):
    w = World(np.zeros((N, N), np.uint16), np.zeros((N, N), np.int8), "audio", seed=seed)
    w._cost = np.full((N, N), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    w.assets = FakeAssets()
    return w


def hero_stats(name="Start_MF"):
    return UnitType(HUMAN, 1, name, 1, 1, {"token_size": 1, "mana_max": -1, "dying_time": 1}, (), ())


def fighter(w, uid, x, y, owner, hp=40, lo=6, bank=None, **kw):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=EAST, speed_mod=24, **kw)
    u.mover.turn_rate = 32
    u.combat = CombatStats(AttackRecord(skill=500, lo=lo, sp=0), ArmourBlock(), windup=5, recovery=4, range=1)
    if bank:
        u.human, u.server_id, u.stats = True, 10210, hero_stats(bank)
    w.add_unit(u)
    return u


def run(sim, ticks):
    for _ in range(ticks):
        sim.step()


def melee():
    """A monster fighter attacks a 40 HP monster until it dies: swings, wound sounds (easy then hard at half HP), the death sound."""
    w = world()
    a, b = fighter(w, 1, 10, 10, 1, lo=6), fighter(w, 2, 11, 10, 2)
    sim = Simulation(w, keep_sound_events=True)
    sim.step([AttackUnit(1, (a.id,), b.id)])
    run(sim, 160)
    return list(w.sound_events)


def hero_melee():
    """The victim is hero Aldor (`Start_MF`): its wounds and death come from the voice bank, on the speech bus."""
    w = world()
    a, b = fighter(w, 1, 10, 10, 2, lo=9), fighter(w, 2, 11, 10, 1, hp=30, bank="Start_MF")
    sim = Simulation(w, keep_sound_events=True)
    sim.step([AttackUnit(2, (a.id,), b.id)])
    run(sim, 120)
    return list(w.sound_events)


def cast():
    """A mage casts Fire Arrow at a target: the cast message's spell object, the cast frame, then the wound."""
    from spell_helpers import FIRE_ARROW, spell_table
    w = world()
    w.spell_table = spell_table()
    m = fighter(w, 1, 10, 15, 1, hp=60)
    m.combat = CombatStats(AttackRecord(skill=300, lo=3, sp=2), ArmourBlock(), windup=5, recovery=4, range=7, mage=True, human=True)
    m.mana = m.mana_max = 30
    m.spellbook = 1 << FIRE_ARROW
    t = fighter(w, 2, 17, 15, 2, hp=500)
    sim = Simulation(w, keep_sound_events=True)
    sim.step([CastSpell(1, (m.id,), FIRE_ARROW, t.id)])
    run(sim, 80)
    return list(w.sound_events)


def pickup():
    """A hero picks up a sack: no sound event (docs/engine/audio.md 2.1)."""
    from gear_helpers import code_of, world_with_hero
    w, u = world_with_hero()
    w.place_pile(24, 20, 0, [code_of("Boots")])
    sim = Simulation(w, keep_sound_events=True)
    sim.step([PickUp(1, (u.id,), (24, 20))])
    run(sim, 200)
    assert not w.items
    return list(w.sound_events)


def switch():
    """A hero uses a switch: no sound event (structures.md 4)."""
    from gear_helpers import world_with_hero
    w, u = world_with_hero()
    s = MapObject(0x6001, "structure", 28, 26, 20, uid=1, hp=1, hp_max=3, owner=0)
    w.add_object(s)
    sim = Simulation(w, keep_sound_events=True)
    sim.step([UseStructure(1, (u.id,), s.id)])
    run(sim, 300)
    assert s.hp == 0
    return list(w.sound_events)


SCENARIOS = {"melee": melee, "hero_melee": hero_melee, "cast": cast, "pickup": pickup, "switch": switch}


def digest(events):
    blob = json.dumps([[e.tick, e.kind, e.uid, e.x, e.y, e.sound, e.bus, e.hero, e.k, e.owner] for e in events])
    return {"count": len(events), "sha256": hashlib.sha256(blob.encode("ascii")).hexdigest()}


def all_hashes():
    return {k: digest(f()) for k, f in SCENARIOS.items()}
