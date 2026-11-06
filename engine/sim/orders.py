"""Order system: the player's commands become unit orders, and the group pass.

Spec: docs/engine/simulation.md "Orders (H3)", docs/engine/click-to-move-research.md (R section numbers in the
comments; routine addresses there).  Layer 4: reads and writes `engine.world` only.  Runs first in
`Simulation.systems`: at the start of a step the group pass (when `world.tick & 15 == 6`), then the command drain.
"""

from engine.world import OrderGroup

from .commands import (AttackUnit, CastScroll, CastSpell, DropGold, Guard, MoveItem, MoveUnits, PickUp, Retreat, SetAutoCast, SetAutoSpell, SetFormation, SetRetreatMode, StandStill, Stop,
                       Swarm)
from .combat import can_order_attack, find_target, refresh_attack, set_attack
from .movement import (ATTACK_ORDER, CENTRE, RETREAT_ORDER, MoveTo, _in_map, _set_action, IDLE, cancel, fail_stop, live_cells, path_grid,
                       set_guard, set_move, set_retreat, set_stand, set_still, stop_unit, unit_size, unit_speed)
from .pathfinding import chebyshev
from . import ai, follow, gear, spells

MAX_IDS = 253                       # FUN_0050bbb8 stops appending at 253 (R 2)
FORMATION_LIMIT = 2                 # server+0xa724: Chebyshev distance an Auto group may be spread over (R 3.2)
SERVER_FORMATION = (0, 2, 1)        # client mode 0 off, 1 auto, 2 on -> server 0 off, 2 auto, 1 on (0x4f688c..0x4f68f8)
BORDER = 8                          # clamp margin of FUN_0056d032
GROUP_ORDERS, GROUP_MOVE, GROUP_STAND = 0, 4, 3      # group order (record+0x20): 0 = every member runs its own order executor
PASS_PHASE = 6                      # group pass runs when the tick counter before its increment has & 15 == 6


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _lookup(world, player_id, uid):
    """`FUN_004f3a19`: the unit in the claimed player's own set, living.  (A unit with HP <= 0 is refused here;
    the exe accepts it and resets the order on its death tick, which is not implemented yet: DECISION.)"""
    u = world.units.get(uid)
    return u if u is not None and u.owner == player_id and u.hp > 0 else None


def _new_group(world, owner):
    """`FUN_0052b06f`: delete the owner's empty groups, allocate a fresh one."""
    for gid in [gid for gid, g in world.groups.items() if g.owner == owner and not g.members]:
        del world.groups[gid]
    g = OrderGroup(world._next_group, owner)
    world._next_group += 1
    world.groups[g.id] = g
    return g


def _join(world, g, u):
    """`FUN_0052af8c`: leave the old group, append at the tail of the new one."""
    old = world.groups.get(u.order_group)
    if old is not None and u.id in old.members:
        old.members.remove(u.id)
    g.members.append(u.id)
    u.order_group = g.id


def intake(world, player_id, unit_ids):
    """`FUN_004f515d` up to the dispatch (R 3.1): the command needs a known player and >= 1 id whose FIRST id is a
    living unit of that player; later invalid ids are skipped silently.  A new group per command.  Returns the
    group or None."""
    if player_id not in world.players:
        return None
    ids = list(unit_ids)[:MAX_IDS]
    if not ids or _lookup(world, player_id, ids[0]) is None:
        return None
    g = _new_group(world, player_id)
    for i in ids:
        u = _lookup(world, player_id, i)
        if u is not None:
            _join(world, g, u)
    return g


def centroid(world, g):
    """`FUN_0056f850`: truncating division of the sums of the 16-bit positions (cell * 256 + sub-cell, mid-step
    offsets count); returns the centroid cell."""
    us = [world.units[i] for i in g.members]
    n = len(us)
    if not n:
        return None
    sx = sum((u.x << 8) | u.sub_x for u in us)
    sy = sum((u.y << 8) | u.sub_y for u in us)
    return (sx // n) >> 8, (sy // n) >> 8


def _clamp(world, x, y):
    """`FUN_0056d032`: `& 0xff` first (a negative target wraps to the far edge), then per axis into [8, size - 9]."""
    x, y = x & 0xFF, y & 0xFF
    return (max(BORDER, min(world.width - 1 - BORDER, x)), max(BORDER, min(world.height - 1 - BORDER, y)))


def _cancel_group(world, g):
    """`FUN_00570e83`: cancel every member, group order := 0 (record `+0x20`) and the group speed byte := 0 (`+0x44`, `0x570e6f`)."""
    for i in g.members:
        cancel(world.units[i], world)
    g.order = 0
    g.speed = 0


def move_group(world, g, x, y, raw=False, swarm=False):
    """`FUN_005703c0` (R 3.2, 4.1, 4.3).  `raw` (debug `MoveTo`): the target is used as given, no wrap or clamp.  `swarm`: `FUN_0057063e`, the same
    code with group order 5 at the end (cmd 0x1a)."""
    x, y = x & 0xFF, y & 0xFF
    formation, minspeed = True, 250
    _cancel_group(world, g)
    player = world.players.get(g.owner)                 # synthetic worlds may lack the player: default option
    mode = SERVER_FORMATION[player.formation if player else 1]
    c = None
    if mode == 2:
        c = centroid(world, g)
        if any(chebyshev((world.units[i].x, world.units[i].y), c) > FORMATION_LIMIT for i in g.members):
            formation = False
    elif mode != 0:
        c = centroid(world, g)
    else:
        formation = False
    _cancel_group(world, g)
    for i in g.members:
        u = world.units[i]
        if formation:
            tx, ty = x + (u.x - c[0]), y + (u.y - c[1])
            sp = _s16(unit_speed(u))
            if sp < minspeed:
                minspeed = sp & 0xFF
        else:
            tx, ty = x, y
        set_move(world, u, *((tx, ty) if raw else _clamp(world, tx, ty)))
    if formation:
        g.speed = minspeed
    g.order = ai.G_SWARM if swarm else GROUP_MOVE
    g.target = (x, y)


def stop_group(world, g):
    """`FUN_00570b8b` (cmd 0x18, stand ground): every member order 0xc with the anchor on its own cell; group order 3."""
    _cancel_group(world, g)
    for i in g.members:
        set_stand(world, world.units[i])
    g.order = GROUP_STAND


def guard_group(world, g, radius=0, computer=False):
    """`FUN_005709d9(group, radius)` (cmd 0x17 G with radius 0; the scripted guard with the radius byte) and `FUN_00570aba` (`computer`: the squads'
    group order 0x12): every member `FUN_0056d4ba` (order 0xb, anchor), the group order, `FUN_0057026e` (centroid stats, pool radius := reach), then
    a given radius raises the pool radius to it, else the floor applies: G -> `MinimalGuardRange` (10), 0x12 -> 20 (when the reach is below 10)."""
    _cancel_group(world, g)
    mem = [world.units[i] for i in g.members]
    for u in mem:
        set_guard(world, u)
    g.order = ai.G_COMPUTER if computer else ai.G_GUARD
    if mem:
        ai.record_stats(world, g, mem)
    if radius:
        if g.radius < radius:
            g.radius = g.base = radius
    elif g.radius < ai.MIN_GUARD_RANGE:
        g.radius = g.base = ai.DEFAULT_RADIUS if computer else ai.MIN_GUARD_RANGE


def still_group(world, g):
    """`FUN_00570bde` (cmd 0x12 L): every member `FUN_0056d572` (order 0x17, anchor on the own cell), group order 0x13."""
    _cancel_group(world, g)
    for i in g.members:
        set_still(world, world.units[i])
    g.order = ai.G_STILL


def retreat_group(world, g):
    """`FUN_00570c31` (cmd 0x14 R): cancel every member (group order 0), each `FUN_0056da4f` (order 0x16, Brain mode 0).  The executor runs in the group
    pass of order 0 (`ai.retreat_exec`)."""
    _cancel_group(world, g)
    for i in g.members:
        set_retreat(world, world.units[i])


def hold_group(world, g, x, y):
    """`FUN_005708bc` (scripted sub-command 2): cancel, group order 2, destination `y << 8 | x`; the members keep their order."""
    _cancel_group(world, g)
    g.order = ai.G_HOLD
    g.target = (x & 0xFF, y & 0xFF)


def wander_group(world, g):
    """`FUN_005708ff` (scripted sub-command 17): cancel, group order 0x11, destination := the first member's cell, counter := 0."""
    _cancel_group(world, g)
    g.order = ai.G_WANDER
    first = world.units[g.members[0]] if g.members else None
    g.target = (first.x, first.y) if first is not None else (0, 0)
    g.counter = 0


def _target_free(world, u, cell):
    """`FUN_0055cd50`: the unit's footprint at `cell` is free in the live layer (static block plus the other units'
    stamps, INFERRED to exclude the unit's own)."""
    grid, live = path_grid(world, u.move_type), live_cells(world, u)
    n = unit_size(u)
    return all(not grid.is_blocked(cell[0] + i, cell[1] + j) and (cell[0] + i, cell[1] + j) not in live
               for j in range(n) for i in range(n))


def group_pass(world):
    """`FUN_0056fe4d` (R 4.4): per player in id order, each group in creation order: the group orders 0 and 4 always, 3 (stand ground, `57309d`),
    1, 2, 0x11, 0x12, 0x13 and 0xff when the AI is on, 5 (swarm) and 0x11 (wander) also with the AI off (an empty pool: they walk); the
    handlers are in `ai.run_group` (docs/engine/ai.md 14)."""
    for pid in sorted({g.owner for g in world.groups.values()}):
        for g in [g for g in world.groups.values() if g.owner == pid]:
            if g.members and g.order == GROUP_MOVE:
                _pass_move(world, g)
                _post_steps(world, g)
            elif g.members and g.order == GROUP_ORDERS:
                _pass_orders(world, g)
                _post_steps(world, g)
            elif g.members and g.order == GROUP_STAND and world.ai_on:
                ai.stand_pass(world, g)         # FUN_0057309d; behind the AI switch (the original always runs it)
                _post_steps(world, g)
            elif g.members and g.order in ai.PASS_ORDERS and (world.ai_on or g.order in (ai.G_SWARM, ai.G_WANDER)):
                ai.run_group(world, g)


def _post_steps(world, g):
    """`FUN_00573713` on every member after the handler (ai.md 9).  Only a unit with retreat-mode thresholds is visited; the
    run_group path of the other group orders calls it itself, behind the AI switch (its enemies exist only then)."""
    for i in list(g.members):
        u = world.units.get(i)
        if u is not None and u.wimpy_hp is not None:        # DECISION: only the retreat-mode thresholds; a player-owned monster's data.bin ones stay inert (as before)
            ai.post_step(world, g, u)


def _pass_move(world, g):
    """`FUN_00573198`, per member in list order."""
    for i in list(g.members):
        u = world.units[i]
        m = u.mover
        cell = (u.x, u.y)
        at_centre = (u.sub_x, u.sub_y) == (CENTRE, CENTRE)
        if m.goal is None:
            m.goal, m.arrived, m.failed = (0, 0), False, False     # brain+0xa of a member that never got a destination (a wander group): cell word 0
        if m.goal is not None and cell == m.goal and at_centre and not u.stopped:
            stop_unit(world, u)                         # arrived (FUN_0056dbc6)
            m.arrived = False
        elif m.arrived and m.tail == cell:
            stop_unit(world, u)                         # arrived at the end of its plan (a fallback cell)
            m.arrived = False
        if u.stopped:
            if world.ai_on:
                ai.guard_scan(world, u)                 # FUN_0056afac(u, 0) = FUN_0056a1fb; AI-off sims have no enemies to scan
            continue
        # FUN_0056c8af: brain mode := 1, destination := brain+0xa.  No test of the unit's order: it restarts a
        # parked unit (order 1) and a unit whose order the failure turned into 0xc (`stopped` still 0)
        u.mode_go = True
        u.mode_attack = u.mode_cast = False
        u.mode_follow = False
        m.waiting = m.parked = False
        if (not _target_free(world, u, g.target) and m.goal == g.target
                and chebyshev(cell, g.target) < 2):
            # FUN_0056a1fb -> FUN_0056afd9 -> FUN_0056b025: no target in range, mode 0 (DECISION: also for
            # ranged and computer-player units, whose branches 56bc7b / mode 0xb are phase I)
            m.parked = True
            if not m.step_ticks:
                _set_action(world, u, IDLE)


def _pass_orders(world, g):
    """Group order 0: `FUN_00569321` for every member, list order.  The attack (3), cast (0xd, 0xe), defend (8), patrol (0xa) and follow (0x11)
    orders have an effect here (combat.md 2.3, spells.md 9c, ai.md 14.2); the executors of the other orders are no-ops for what the engine
    models (guard scan, state := 0).  A leader in state 0x10 stops its follower inside the executors (`follow._leader`)."""
    for i in list(g.members):
        u = world.units[i]
        if u.order == ATTACK_ORDER:
            refresh_attack(world, u)
        elif u.order == spells.CAST_ORDER:
            spells.refresh_cast(world, u)               # FUN_0056c72b: Brain mode 8
        elif u.order == spells.CELL_ORDER:
            spells.refresh_cell(world, u)               # FUN_0056969c: Brain mode 9
        elif u.order == follow.DEFEND_ORDER:
            follow.exec_defend(world, u)                # FUN_005696e8
        elif u.order == follow.FOLLOW_ORDER:
            follow.exec_follow(world, u)                # FUN_00569857
        elif u.order == follow.PATROL_ORDER:
            follow.exec_patrol(world, u)                # FUN_00569b62
        elif u.order == RETREAT_ORDER:
            ai.retreat_exec(world, u)                   # FUN_0056c9bc
        elif u.order == gear.PICK_ORDER:
            gear.refresh_pickup(world, u)               # FUN_0056c8da: order 2, go to the sack / Brain mode 7


def attack_group(world, g, target):
    """`FUN_00570946` (combat.md 2.1): cancel every member (group order 0), then per member the attack matrix; a refused member stands
    (`FUN_0056dba1`), the others get order 3 (a member that is the target stops)."""
    _cancel_group(world, g)
    for i in g.members:
        u = world.units[i]
        if can_order_attack(world, u, target):
            set_attack(world, u, target)
        else:
            fail_stop(world, u)


def orders_system(world, commands):
    """Group pass (before the drain), then the drain in log order."""
    if (world.tick & 15) == PASS_PHASE:
        group_pass(world)
    for cmd in commands:
        if getattr(cmd, "ai", False):               # an AI command from a log: the brain-level executor, no group (docs/engine/ai.md 10)
            ai.apply(world, cmd)
        elif isinstance(cmd, MoveUnits):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                move_group(world, g, *cmd.cell)
        elif isinstance(cmd, AttackUnit):
            g = intake(world, cmd.player_id, cmd.unit_ids)      # the group exists before the target is looked up (0x4f5283)
            target = find_target(world, cmd.target_id)   # a corpse or a structure is a legal target (combat.md 12.2, 5.5)
            if g is not None and target is not None:
                attack_group(world, g, target)
        elif isinstance(cmd, CastSpell) and cmd.cell is not None:
            g = intake(world, cmd.player_id, cmd.unit_ids)      # command 0x1f (docs/engine/ai.md 12.6)
            if g is not None and world.spell_table is not None:
                spells.cell_cast_group(world, g, cmd.spell_id, cmd.cell, _cancel_group)
        elif isinstance(cmd, CastSpell):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            target = world.find_unit(cmd.target_id)     # a corpse is a legal target, as for an attack (spells.md 9c.3)
            if g is not None and target is not None and world.spell_table is not None:
                spells.cast_group(world, g, cmd.spell_id, target, _cancel_group)
        elif isinstance(cmd, Stop):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                stop_group(world, g)
        elif isinstance(cmd, Guard):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                guard_group(world, g, 0)                # cmd 0x17: FUN_005709d9(group, 0)
        elif isinstance(cmd, StandStill):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                still_group(world, g)
        elif isinstance(cmd, Retreat):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                retreat_group(world, g)
        elif isinstance(cmd, SetRetreatMode):           # message 0x46 sub 1 (0x4f67d5): FUN_0057393c (withdraw := 0) and FUN_00573b38 (wimpy := maxHP * x / 100)
            if cmd.player_id in world.players:
                x = {1: 10, 2: 30}.get(cmd.mode, 0)
                for u in world.units.values():
                    if u.owner == cmd.player_id:
                        u.wimpy_hp, u.withdraw_hp = u.hp_max * x // 100, 0
        elif isinstance(cmd, Swarm):
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None:
                move_group(world, g, *cmd.cell, swarm=True)
        elif isinstance(cmd, PickUp):                   # message 0x21: the last unit of the intake gets the pickup order (FUN_004f515d)
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None and g.members:
                _cancel_group(world, g)
                gear.command_pickup(world, world.units[g.members[-1]], cmd.cell, cmd.index)
        elif isinstance(cmd, MoveItem):                 # message 0x22: hero container moves (sim/gear.py)
            u = _lookup(world, cmd.player_id, cmd.unit_id) if cmd.player_id in world.players else None
            if u is not None:
                gear.move_item(world, u, cmd.src_kind, cmd.dst_kind, cmd.src_index, cmd.dst_index, cmd.count)
        elif isinstance(cmd, DropGold):                 # message 0x23
            g = intake(world, cmd.player_id, cmd.unit_ids)
            if g is not None and g.members:
                gear.drop_gold(world, world.players[cmd.player_id], world.units[g.members[0]], cmd.amount, cmd.cell)
        elif isinstance(cmd, SetFormation):
            if cmd.player_id in world.players and cmd.mode in (0, 1, 2):
                world.players[cmd.player_id].formation = cmd.mode
        elif isinstance(cmd, CastScroll):               # messages 0x25 / 0x26: a scroll of the unit's pack
            g = intake(world, cmd.player_id, (cmd.unit_id,))
            target = world.find_unit(cmd.target_id) if cmd.cell is None else None
            if g is not None and world.spell_table is not None and (cmd.cell is not None or target is not None):
                spells.scroll_cast(world, g, world.units[cmd.unit_id], cmd.index, target, cmd.cell, _cancel_group)
        elif isinstance(cmd, SetAutoCast):              # message 0x46 sub 3 (0x4f6945): the byte is stored as sent
            if cmd.player_id in world.players:
                world.players[cmd.player_id].autocast = cmd.flags & 0xFF
        elif isinstance(cmd, SetAutoSpell):             # message 0x46 sub 4 (0x4f694d): toggle brain+0x78
            u = _lookup(world, cmd.player_id, cmd.unit_id) if cmd.player_id in world.players else None
            if u is not None:
                u.auto_spell = 0 if u.auto_spell == (cmd.spell & 0xFF) else cmd.spell & 0xFF
        elif isinstance(cmd, MoveTo):
            u = world.units.get(cmd.unit_id)
            if u is not None and u.hp > 0 and _in_map(world, (cmd.x, cmd.y)):
                g = _new_group(world, u.owner)
                _join(world, g, u)
                move_group(world, g, cmd.x, cmd.y, raw=True)
