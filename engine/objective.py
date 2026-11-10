"""The objective run (phase K12): can the script of a campaign map reach "Mission Complete"?

A headless oracle, not a play-through.  It builds the map as `play` does, then works backwards from the triggers that run instant 4 ("Force Mission
Complete state"): a trigger pair that does not hold is traced to the check that feeds it, and the check's cause is produced by the world edit a
player would have to make: kill a group or a unit (check 1 / 5), bring the hero next to a unit or a point (2 / 3 / 6 / 7 / 15 / 16 / 27), put the quest
item in the hero's pack (12 / 17 / 16), set a switch's hit points (21).  Pairs fed by a script variable (check 19, 23, 24) are followed to the triggers
that write it.  Every edit goes through the real systems and the real trigger pass decides; the party never dies (hit points are refilled each round).

What it proves is that the **script side** of a mission can end (every instant and check on the path exists and behaves), not that a player can do
the edits: walking to a chest or killing a boss is the part only a play-through shows.  `stuck` names the check kinds the oracle has no edit for.
"""

import logging

from engine.sim import Simulation, triggers as T
from engine.sim import gear
from engine.sim.triggers import _holds

ROUND = 16                      # ticks per round = one script pass and one mission pass
MAX_ROUNDS = 160                # 2560 ticks, 160 s of game time
QUIET_ROUNDS = 40               # rounds without an edit before the run is called stuck (counters that climb with the passes need time)
HERO_HP = 300
GRIND_REACH = 24               # cells: how far a hero is sent after a foe in the grind phase
VAR_CHECKS = (19, 23, 24)       # fed by a script variable: follow it to the triggers that write it
WRITES = {3: 19, 8: 19, 35: 23, 36: 24}      # instant kind -> the check kind that reads what it writes
HANDLED = (1, 2, 3, 5, 6, 7, 8, 12, 14, 15, 16, 17, 21, 27)


def _slot_checks(script):
    return {c.index: c for c in script.checks}


def _writers(script, check):
    """The compiled triggers that write the variable the check reads (instants 3 / 8 for check 19, 35 / 36 for 23 / 24)."""
    var = check.nums[0]
    want = {19: (3, 8), 23: (35,), 24: (36,)}[check.type]
    out = []
    for t in script.triggers:
        for i in t.instants:
            if 0 <= i < len(script.instants):
                ins = script.instants[i]
                if ins.type in want and ins.nums[0] == var:
                    out.append(t)
                    break
    return out


def _phasers(script, units):
    """The compiled triggers whose instants phase one of `units` in again (17 unit, 18 polymorph target, 33 group)."""
    ids = {u.id for u in units}
    out = []
    for t in script.triggers:
        for i in t.instants:
            if 0 <= i < len(script.instants):
                ins = script.instants[i]
                who = (ins.unit,) if ins.type == 17 else (ins.second,) if ins.type == 18 else \
                    tuple(m for m, _ in ins.group.members) if ins.type == 33 and ins.group is not None else ()
                if any(getattr(m, "id", None) in ids for m in who):
                    out.append(t)
                    break
    return out


def _protected(script):
    """The units a defeat trigger (instant 5) watches with check 5 ("Ensure elder", "NecroFriend alive ?"): a player escorts them, the oracle keeps them
    at full health like the party."""
    slots, out = _slot_checks(script), []
    for t in script.triggers:
        if any(0 <= i < len(script.instants) and script.instants[i].type == 5 for i in t.instants):
            out += [slots[s].unit for pair in t.pairs for s in pair[:2] if s in slots and slots[s].type == 5]
    return out


def _is_win(script, t):
    return any(0 <= i < len(script.instants) and script.instants[i].type == 4 for i in t.instants)


def _pred(script, pair, c):
    """`f(value) -> bool`: does the pair hold when the check `c` reads `value`?"""
    a, b, op = pair
    vals = script.values
    if c.index == a:
        return lambda x: _holds({a: x, b: vals[b]}, a, b, op)
    return lambda x: _holds({a: vals[a], b: x}, a, b, op)


def _adjacent(world, u, x, y, radius=3):
    for r in range(0, radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r and T.teleport(world, u, (x + dx) & 0xFF, (y + dy) & 0xFF):
                    return True
    return False


def _hero(world):
    p = world.players[1]
    return world.find_unit(p.main_hero) if p.main_hero else None


def _kill(u):
    u.hp = -30


def _wanted(world, script, c):
    """The units a check is about that are still phased out (the map's own script has to bring them in first)."""
    if c.type == 1 and c.group is not None:
        return [m for m in c.group.live() if m.id in script.phased]
    if c.type == 8:
        return [m for m in script.phased.values() if m.owner == c.player.id and m.state != T.DEAD]
    if c.type == 5:
        return [c.unit] if c.unit.id in script.phased else []
    return []                                       # a phased-out unit is a position marker for the distance checks (map 93: unit 2027)


def satisfy(world, script, pair, c):
    """Make the pair's check true by one world edit.  Returns the edit's name, or None when the oracle has no edit for it."""
    ok = _pred(script, pair, c)
    kind, n, u, hero = c.type, c.nums, c.unit, _hero(world)
    if kind == 1:
        live = c.group.live()
        for k in range(1, len(live) + 1):
            if ok(len(live) - k):
                for m in live[:k]:
                    _kill(m)
                return "kill %d of group %s" % (k, c.group.key,)
        return None
    if kind == 8:
        mine = [m for m in T._units_of(world, script, c.player.id) if m.state != T.DEAD and m.hp > 0]
        for k in range(1, len(mine) + 1):
            if ok(len(mine) - k):
                for m in mine[:k]:
                    _kill(m)
                return "kill %d units of player %d" % (k, c.player.id)
        return None
    if kind == 14:
        piles = [world.items[i] for i in world.items_at(n[0] & 0xFF, n[1] & 0xFF)]
        if piles and hero is not None and ok(0):
            for p in piles:
                gear.pick_up(world, hero, p)
            return "take the sack at (%d, %d)" % (n[0] & 0xFF, n[1] & 0xFF)
        return None
    if kind == 4 and n[0] == 6:                         # "Get unit parameter" 6 = the hit points (map 50: the ogre hostage's health)
        for hp in (1, 5, 10, 25, 50, 100, 300, 0):
            if ok(hp):
                u.hp = hp
                return "unit %d hp %d" % (u.server_id, hp)
        return None
    if kind == 5:
        if u.state != T.DEAD and ok(0):
            _kill(u)
            return "kill unit %d" % u.server_id
        return None
    if kind in (2, 3, 7, 27, 16):
        if kind == 16 and not T._has_item(u, c.item):
            gear.give_item(world, u, c.item)
        x, y = (n[1], n[2]) if kind == 27 else (n[0], n[1])
        if kind == 2:
            x, y = (n[0] + n[2]) // 2, (n[1] + n[3]) // 2
        return "move unit to (%d, %d)" % (x & 0xFF, y & 0xFF) if u is not None and _adjacent(world, u, x & 0xFF, y & 0xFF) else None
    if kind == 15:
        return "hero to (%d, %d)" % (n[0] & 0xFF, n[1] & 0xFF) if hero is not None and _adjacent(world, hero, n[0] & 0xFF, n[1] & 0xFF) else None
    if kind == 6:
        u2 = c.second
        mover, other = (u2, u) if u2 is hero else (u, u2)
        if mover.state != T.DEAD and other.state != T.DEAD and _adjacent(world, mover, other.x, other.y, 2):
            return "bring unit %d next to unit %d" % (mover.server_id, other.server_id)
        return None
    if kind in (12, 17):
        if not T._has_item(u, c.item):
            gear.give_item(world, u, c.item)
        return "give item %#x" % c.item
    if kind == 21:
        for hp in (0, 1, 100):
            if ok(hp):
                c.building.hp = hp
                return "building hp %d" % hp
        return None
    return None


def _plan(world, script, t, slots, seen, stuck):
    """Depth first from a trigger: returns `(trigger, [(pair, check)])` of the first trigger whose script-variable pairs all hold and whose
    physical pairs do not (the next thing a player has to bring about), else None."""
    if t.position in seen or (t.once and script.fired[t.position]):
        return None
    seen.add(t.position)
    physical, deferred = [], []
    for pair in t.pairs:
        a, b, op = pair
        if _holds(script.values, a, b, op):
            continue
        for s in (a, b):
            c = slots.get(s)
            if c is None:
                continue
            if c.type in VAR_CHECKS:
                deferred.append(c)
                break
            away = _wanted(world, script, c)
            if away:
                deferred.extend(("phase", m) for m in away)
                stuck.append((t.position, c.type, "phased out"))
                break
            physical.append((pair, c))
            break
    for c in deferred:
        writers = _phasers(script, [c[1]]) if isinstance(c, tuple) else _writers(script, c)
        for w in writers:
            r = _plan(world, script, w, slots, seen, stuck)
            if r:
                return r
    if deferred:
        return None
    return (t, physical) if physical else None


def _side_writers(script, side):
    """The compiled triggers whose instant 35 (ScenarioSetVar) writes one of the campaign variables `side` that is still 0: the optional goals
    of a campaign mission (map 20 "Get mission 21" = Var 0x304, map 50 "Give 52 mission" = Var 0x30c), tried before the win."""
    out = []
    for t in script.triggers:
        for i in t.instants:
            if 0 <= i < len(script.instants):
                ins = script.instants[i]
                if ins.type == 35 and ins.nums[0] in side and not script.scenario_vars.get(ins.nums[0]):
                    out.append(t)
                    break
    return out


def _round(world, sim, side=()):
    """One edit round: the next trigger on the way to the goal (a `side` variable's writer first, then the win) and the world edits that make its
    conditions true."""
    script = world.script
    slots, seen, stuck = _slot_checks(script), set(), []
    for t in _side_writers(script, side) + [t for t in script.triggers if _is_win(script, t)]:
        r = _plan(world, script, t, slots, seen, stuck)
        if r:
            t, physical = r
            edits = []
            for pair, c in physical:
                e = satisfy(world, script, pair, c)
                if e:
                    edits.append((t.position, c.type, e))
                else:
                    stuck.append((t.position, c.type))
            return edits, stuck
    return [], stuck


def at_war(world, a, b):
    """Relation bit 1 of player `a` towards `b` (map section 5): a unit the human may attack without breaking a peace the mission script cares about."""
    p = world.players.get(a)
    return p is not None and len(p.relations) >= b and bool(p.relations[b - 1] & 1)


def grind_commands(world, assigned, reach=GRIND_REACH):
    """The orders of the fight-crediting phase: a hero of the human player whose last target is gone (`assigned`: hero id -> target id, kept by the caller)
    attacks the nearest living hostile unit within `reach` cells (Chebyshev), so the carried XP comes from real blows, kills and the kill credit of
    `sim.xp`; the oracle keeps the party's HP up."""
    from engine.sim import AttackUnit
    from engine.sim import xp as XP
    cmds = []
    for h in world.units.values():
        if h.owner != 1 or h.hp <= 0 or not XP.is_hero(h):
            continue
        t = world.units.get(assigned.get(h.id))
        if t is not None and t.hp > 0:
            continue
        foes = [(max(abs(u.x - h.x), abs(u.y - h.y)), u.id) for u in world.units.values()
                if u.hp > 0 and u.owner != h.owner and at_war(world, h.owner, u.owner)]
        foes = [f for f in foes if f[0] <= reach]
        if foes:
            assigned[h.id] = min(foes)[1]
            cmds.append(AttackUnit(h.owner, (h.id,), assigned[h.id]))
    return cmds


def run(name, install=None, seed=1, world=None, side=(), grind=0):
    """One objective run (`grind`: ticks at the start in which the party's heroes fight the nearest hostile units, so the run earns XP like a player who clears the map; 0 = none; `side`: campaign variables whose writer triggers are tried before the win; on `world` when given: a campaign mission built by `CampaignGame.start_mission`, else the map as `play` builds it).  Returns `{"result": "won" | "lost" | "stuck" | "timeout" | "crash", "tick", "edits", "stuck", "triggers"}`."""
    from engine.session import build_game
    out = {"map": name, "result": "timeout", "tick": 0, "edits": [], "stuck": [], "wins": 0}
    logging.disable(logging.WARNING)
    try:
        if world is None:
            world, _ = build_game(name, install, seed=seed)
        sim = Simulation(world, triggers=True)
        script = world.script
        out["wins"] = sum(1 for t in script.triggers if _is_win(script, t))
        if not out["wins"]:
            out["result"] = "stuck"
            out["stuck"] = [("no trigger runs instant 4", 0)]
            return out
        quiet, guarded, assigned = 0, _protected(script), {}
        for _ in range(MAX_ROUNDS):
            fight = grind_commands(world, assigned) if world.tick < grind else []
            for _ in range(ROUND):
                for u in list(world.units.values()) + guarded:
                    if (u.owner == 1 or u in guarded) and u.hp > 0:
                        u.hp = HERO_HP
                sim.step(fight)
                fight = []
            r = T.result(world)
            if r:
                out["result"], out["tick"] = r, world.tick
                return out
            if world.tick < grind:                         # the fight phase: no edits yet, the heroes earn their XP first
                continue
            edits, stuck = _round(world, sim, side)
            out["edits"] += [(world.tick,) + e for e in edits]
            out["stuck"] = stuck
            quiet = 0 if edits else quiet + 1
            if quiet >= QUIET_ROUNDS:
                out["result"] = "stuck"
                break
        out["tick"] = world.tick
        return out
    except Exception as e:
        out["result"], out["crash"] = "crash", "%s: %s" % (type(e).__name__, e)
        return out
    finally:
        logging.disable(logging.NOTSET)
