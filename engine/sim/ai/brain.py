"""brain: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

from ..commands import AttackUnit, CastSpell, MoveUnits, Stop
from .. import combat as cb, movement as mv, spells
from .perception import _scan_range, sight, unword


# --- command emission --------------------------------------------------------------------------------------------------------

def emit(world, cmd):
    """Log the command (`Simulation.step` drains `ai_emitted` into the session log) and apply it at once, as the group pass does."""
    world.ai_emitted.append(cmd)
    apply(world, cmd)


def go(world, m, w):
    """`FUN_0056c8af(m, cell word)`: brain mode 1 towards the cell."""
    emit(world, MoveUnits(m.owner, (m.id,), unword(w), ai=True))


def attack(world, m, t):
    """`FUN_0056acc8` / `FUN_0056c840`: brain mode 5 / 6 on the target (a melee unit: the same driver)."""
    emit(world, AttackUnit(m.owner, (m.id,), t.id, ai=True))


def _human(world, m):
    pl = world.players.get(m.owner)
    return pl is not None and pl.human


# --- brain-level executors of the AI commands ------------------------------------------------------------------------------

def apply(world, cmd):
    """Execute an `ai=True` command: the Brain mode changes of `FUN_0056c8af` (1), `FUN_0056acc8` (5), `FUN_0056afd9` (0xb).  The unit's
    order, anchor, stopped flag and squad are untouched (the exe writes the Brain, not the order)."""
    for uid in cmd.unit_ids:
        u = world.units.get(uid)
        if u is None or u.hp <= 0:
            continue
        m = u.mover
        if isinstance(cmd, MoveUnits):
            cell = cmd.cell                                     # CONFIRMED: the exe feeds the raw cell to its planner (ai.md 3)
            u.set_mode(go=True)
            if m.goal != cell:
                m.goal = cell
                m.arrived = m.failed = False
            m.waiting = m.parked = False
        elif isinstance(cmd, AttackUnit):
            t = world.find_unit(cmd.target_id)
            if t is None:
                continue
            u.target = t.id
            u.range = cb.attack_range(world, u)
            u.set_mode(attack=True)
            m.waiting = m.parked = False
        elif isinstance(cmd, CastSpell):
            apply_cast(world, u, cmd)
        elif isinstance(cmd, Stop):
            u.set_mode(look=not _human(world, u))


def apply_cast(world, u, cmd):
    """The AI cast (`brain+0x60 := 1`, then `FUN_0056c72b` or `FUN_0056969c`): Brain mode 8 at the unit (target, wrapper, range = wrapper `+9`, the
    target's `brain+0xa4/+0xa8` := spell number / tick) or Brain mode 9 at the cell.  Order, anchor and group untouched."""
    if world.spell_table is None or world.spell_table.get(cmd.spell_id) is None:
        return
    w = spells.Wrapper(cmd.spell_id)
    sp = world.spell_table.get(cmd.spell_id)
    if cmd.cell is None:
        t = world.find_unit(cmd.target_id)
        if t is None:
            return
        u.set_mode(cast=True)
        u.cast_target = t.id
        t.ai.spell_mark, t.ai.spell_tick = cmd.spell_id, world.tick
    else:
        u.set_mode(cell=True)
        u.cast_cell = tuple(cmd.cell)
    u.cast_wrapper = w
    u.range = spells.wrapper_range(sp, w, spells.unit_level(u, sp))
    u.ai_cast = True
    u.mover.waiting = u.mover.parked = False


def look_around(world, u):
    """Brain mode 0xb (`FUN_0056e5bc`), every tick: an idle computer-owned unit turns to a random direction now and then.  A settled unit
    turns on `rand() <= 0xcc` (about 0.6 % of the ticks) or at once after a hit; a turn in progress continues."""
    m = u.mover
    if u.facing == m.target_facing:
        if u.ai.alerted == 0 and world.rng.rand15() > 0xCC:
            u.state = mv.IDLE_STATE
            mv._set_action(world, u, mv.IDLE)
            return
        new = (u.facing + 0x21 + world.rng.rand(0xBD)) & 0xFF
        m.target_facing = new
        u.ai.alerted = 0
    face = m.target_facing
    if u.facing != face or m.turning:
        mv._set_action(world, u, mv.TURN)
    mv._turn_toward(u, face)
    u.state = mv.MOVE_STATE


def mode_name(u):
    """The Brain mode of a unit as the debug overlay names it."""
    if u.hp <= 0:
        return "dead"
    for flag, name in ((u.mode_attack, "attack"), (u.mode_go, "go"), (u.mode_look, "look")):
        if flag:
            return name
    return "idle"


def overlay(world, u):
    """What the `ai` debug overlay draws for unit `u` (None when it is not in a squad): its sight (the aggro area), the ring at the
    squad's pool radius round the centroid, the post, the target's cell and a label with the mode."""
    g = next((g for g in world.ai_groups.values() if u.id in g.members), None)
    if g is None:
        return None
    cx, cy = unword(g.centre)
    r = g.radius
    ring = {(x, y) for x in range(cx - r, cx + r + 1) for y in (cy - r, cy + r) if 0 <= x < world.width and 0 <= y < world.height}
    ring |= {(x, y) for y in range(cy - r, cy + r + 1) for x in (cx - r, cx + r) if 0 <= x < world.width and 0 <= y < world.height}
    t = world.units.get(u.ai.target) if u.ai.target is not None else None
    label = "%s order %#x t=%s R=%d stamp=%d" % (mode_name(u), u.order, "-" if t is None else t.uid, r, u.ai.stamp)
    return {"sight": set(sight(world, u.x, u.y, _scan_range(u, world))), "ring": ring, "post": u.anchor,
            "target": (t.x, t.y) if t is not None else None, "label": label}
