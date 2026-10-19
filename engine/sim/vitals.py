"""Regeneration and corpse decay: the 16-tick job (`FUN_0052bbb7` at `tick & 15 == 12`, which runs before the commands and the creatures).

Spec: docs/engine/combat.md 12.5 (`FUN_0050fc5a`, vtable slot `+0x14` of the creature classes) and 12.6.  The counter the slot tests is the
16-tick block (`tick >> 4` at the job), not the tick.  Layer 4: reads and writes `engine.world` only.
"""

from engine.world import DEAD

from . import spells
from .death import decay_corpses

JOB_PHASE = 12                  # tick & 15 at which the job runs
REST_TICKS = 80                 # more than this many ticks since the last step ended: regeneration x3 (`FUN_0050fc3e`)


def regen_rates(u):
    """(HP regeneration `+0x98`, mana regeneration `+0x9e`) of a unit: data.bin p5 / p7 for monsters (see `human_regen` for humans)."""
    st = u.stats
    if st is None:
        return 0, 0
    if u.human:
        return human_regen(u)
    return st.get("hp_regen", 0) or 0, st.get("mana_regen", 0) or 0


def human_regen(u):
    """Humans have no regeneration columns in data.bin: the creature base constructor sets 100 and 50 (`FUN_0050ec60`, combat.md 12.5b)."""
    return 100, 50


def regen(world, u, block):
    """One call of `FUN_0050fc5a`: the HP < 0 drain (every 4th block), HP regeneration for the units whose id matches the block, mana every block."""
    if u.state == DEAD:
        return
    if u.hp < 0:
        if block & 3 == 0:
            u.hp -= 1
        return
    if u.hp == 0:
        return
    k = 3 if world.tick - u.step_end > REST_TICKS else 1
    hp_regen, mana_regen = regen_rates(u)
    if hp_regen and u.hp < u.hp_max and block & 3 == u.id & 3:
        t = u.hp * 100 + u.hp_acc + (u.hp_max * 2 * 100 * k) // hp_regen        # bonus +0xde = 0 (no effects yet)
        u.hp_acc = t % 100
        u.hp = min(t // 100, u.hp_max)
    if mana_regen and u.mana < u.mana_max:
        t = u.mana * 100 + u.mana_acc + (u.mana_max * 100 * k) // mana_regen    # bonus +0xe2 = 0
        u.mana_acc = t % 100
        u.mana = min(t // 100, u.mana_max)


def vitals_system(world, commands):
    if world.tick & 15 != JOB_PHASE:
        return
    block = world.tick >> 4
    for u in list(world.units.values()):
        regen(world, u, block)
    decay_corpses(world)
    spells.minion_job(world)                # the rest of FUN_0052bbb7: the summon cap (docs/data/spells.md 9b)
