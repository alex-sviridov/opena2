"""Scripted combat scenarios with spell casts on small synthetic worlds (no game files): the source of `tests/golden.json["casts"]`
(`tools/update_golden.py`) and of `tests/test_engine_spells_golden.py`.  Each returns a summary dict: the world dump hash after the run, the tick
the fight ended, the final HP and mana, and the counts of the fight log's cast / damage events."""

import numpy as np

from engine.sim import AttackUnit, CastSpell, Simulation
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.world import UNIT_ID_BASE, CastReleased, CastStarted, Damage, Died, Player, Unit, World
from spell_helpers import FIRE_ARROW, spell_table

EAST, WEST = 64, 192
N = 40


def world(seed=7):
    w = World(np.zeros((N, N), np.uint16), np.zeros((N, N), np.int8), "casts-golden", seed=seed)
    w._cost = np.full((N, N), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    w.spell_table = spell_table()
    return w


def unit(w, uid, x, y, owner, hp=60, mage=False, mana=0, book=None, wspell=None, rng=1, lo=3, sp=2, windup=5, recovery=4, facing=EAST):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=facing, speed_mod=24)
    u.mover.turn_rate = 32
    u.combat = CombatStats(AttackRecord(skill=300, lo=lo, sp=sp), ArmourBlock(), windup=windup, recovery=recovery, range=rng, mage=mage,
                           human=mage, has_weapon=wspell is not None, weapon_spell=wspell)
    u.mana = u.mana_max = mana
    u.spellbook = book
    w.add_unit(u)
    return u


def run(w, script, ticks, done):
    """Steps until `done(w)` or `ticks`; returns (tick of the end or None)."""
    sim, ended = Simulation(w), None
    for _ in range(ticks):
        sim.step(script.get(w.tick, ()))
        if done(w):
            ended = w.tick
            break
    return ended


def summary(w, ended):
    log = w.fight_log
    return {"hash": w.dump_hash(), "ended": ended, "hp": {str(u.uid): u.hp for u in w.units.values()},
            "mana": {str(u.uid): u.mana for u in w.units.values() if u.mana_max},
            "started": sum(isinstance(e, CastStarted) for e in log), "released": sum(isinstance(e, CastReleased) for e in log),
            "damage": [e.amount for e in log if isinstance(e, Damage)], "died": [e.unit for e in log if isinstance(e, Died)]}


def staff_kill():
    """(a) A mage whose staff has `castSpell=Fire_Arrow:1` is ordered to attack a 30 HP target 7 cells away: it casts for free until the target dies."""
    w = world()
    mage = unit(w, 1, 10, 15, 1, mage=True, wspell=(FIRE_ARROW, 1), rng=7)
    foe = unit(w, 2, 17, 15, 2, hp=30)
    ended = run(w, {0: [AttackUnit(1, (mage.id,), foe.id)]}, 600, lambda w: foe.hp <= 0)
    return summary(w, ended)


def mana_runs_out():
    """(b) A mage that knows Fire Arrow (3 mana) has 7 mana: two casts start, the third never does (a silent retry loop), the target survives."""
    w = world()
    mage = unit(w, 1, 10, 15, 1, mage=True, mana=7, book=1 << FIRE_ARROW)
    foe = unit(w, 2, 17, 15, 2, hp=500)
    script = {0: [CastSpell(1, (mage.id,), FIRE_ARROW, foe.id)], 40: [CastSpell(1, (mage.id,), FIRE_ARROW, foe.id)],
              80: [CastSpell(1, (mage.id,), FIRE_ARROW, foe.id)]}
    ended = run(w, script, 300, lambda w: False)
    return summary(w, ended)


def melee_and_cast():
    """(c) A fighter attacks in melee while a mage casts from range at the same target; the target (an enemy fighter ordered to attack the fighter)
    dies or the fighter does."""
    w = world()
    fighter = unit(w, 1, 14, 15, 1, hp=80, lo=5, sp=3)
    mage = unit(w, 2, 9, 15, 1, mage=True, mana=30, book=1 << FIRE_ARROW)
    foe = unit(w, 3, 18, 15, 2, hp=70, lo=4, sp=3, facing=WEST)
    script = {0: [AttackUnit(1, (fighter.id,), foe.id), CastSpell(1, (mage.id,), FIRE_ARROW, foe.id), AttackUnit(2, (foe.id,), fighter.id)],
              45: [CastSpell(1, (mage.id,), FIRE_ARROW, foe.id)], 90: [CastSpell(1, (mage.id,), FIRE_ARROW, foe.id)]}
    ended = run(w, script, 900, lambda w: foe.hp <= 0 or fighter.hp <= 0)
    return summary(w, ended)


SCENARIOS = {"staff_kill": staff_kill, "mana_runs_out": mana_runs_out, "melee_and_cast": melee_and_cast}


def all_summaries():
    return {name: fn() for name, fn in sorted(SCENARIOS.items())}
