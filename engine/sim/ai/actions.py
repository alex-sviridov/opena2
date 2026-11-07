"""actions: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__.

The top of the executor layering (perception -> targeting -> brain -> casting -> autocast -> actions -> reaction -> groups): the two
entry points `engage` (`FUN_0056acc8`) and `idle` (`FUN_0056afd9`) that choose between the brain executors, the caster routines and the
player's auto-cast scans."""

from ..commands import Stop
from .. import spells
from ..pathfinding import chebyshev
from .autocast import human_attack, human_scan, mode0
from .brain import _human, attack, emit
from .casting import CLEVER_MELEE, CLEVER_MIND, OWN_SPELLS, _divide, _wrapper_ok, cast_at, is_mage, mage_idle, special_attack


def engage(world, m, t):
    """`FUN_0056acc8(m, t)` (docs/engine/ai.md 12.2): the special-attack roll over the monster's three slots (one `rand15` per used slot, the last
    slot whose `rand15 < probability * 0x147` wins; Teleport only when the target is more than 2 cells away), else a computer-owned mage tries
    `FUN_0057a769` (`caster_attack`), else brain mode 5 on the target.  A human-owned unit runs `human_attack` (`FUN_0056b059` with the selected
    spell, mode 5, the caster scan `FUN_0056bc7b`; ai.md 12.8).  The target flag `+0x4c & 8` (off the map) and
    the `m == t` branch (`FUN_00567988`) are never reached from the pools (§10)."""
    pick = 0
    if not m.human:
        for n, p in spells.monster_slots(m.stats):
            if n and world.rng.rand15() < p:            # FUN_0057afc0 = rand(); only used slots draw
                pick = n
    if pick and (pick != spells.TELEPORT or chebyshev((t.x, t.y), (m.x, m.y)) > 2):
        special_attack(world, m, t, pick)
        return
    if m is t:
        return
    if _human(world, m):
        human_attack(world, m, t)
        return
    if is_mage(world, m) and caster_attack(world, m, t):
        return
    attack(world, m, t)


def caster_attack(world, m, t):
    """`FUN_0057a769(m, t)` (ai.md 12.4): a computer-owned mage picks a random offensive spell it can pay (n = 1..28) and casts it at the target;
    with mind >= 60 it first draws `rand(100)` and on <= 29 runs the whole decision again and reports 0 (the caller then sets mode 5)."""
    if spells.mind_of(m) >= CLEVER_MIND and _divide(world.rng, 100) <= CLEVER_MELEE:
        engage(world, m, t)
        return False
    cands = [n for n in range(1, OWN_SPELLS) if _wrapper_ok(world, m, n, False)]
    k = _divide(world.rng, len(cands))
    if not cands:
        return False
    cast_at(world, m, t, cands[k])
    return True


def idle(world, m):
    """`FUN_0056afd9`: a computer-owned unit with nothing to do looks around (brain mode 0xb) and a computer-owned mage then runs
    `FUN_0056c592` (`mage_idle`: heal, Shield, friends; ai.md 12.5); a human's unit gets brain mode 0 (`FUN_0056b025`), a human mage runs the
    caster scan `FUN_0056bc7b` (`human_scan`, ai.md 12.8).  Already in that mode = a no-op in the exe (the mode is set to the value it has),
    so the command is not issued again (log size)."""
    if _human(world, m):
        if world.ai_on and is_mage(world, m):
            human_scan(world, m)                        # FUN_0056b025: a mage runs the caster scan FUN_0056bc7b
        else:
            mode0(world, m)
        return
    if not m.idle_mode:
        emit(world, Stop(m.owner, (m.id,), ai=True))
    if is_mage(world, m):
        mage_idle(world, m)
