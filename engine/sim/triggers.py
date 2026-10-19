"""Scenario triggers: the map script (section 7) compiled at map start and run in the group pass.

Spec: docs/engine/triggers.md (T§ in the comments; routine addresses there), file layout docs/formats/map.md part 6.
Layer 4: reads and writes `engine.world` only.  Off unless `enable(world, map)` was called: `world.script` is None, no
system runs, the dump is unchanged.

Pass (T§1): `ai.ai_system` calls `run_pass` at `tick & 15 == 6` after `ai.wake`, before the squad handlers: every check
without a variable reference is evaluated into `values`, then every trigger in file order.  `mission_system` (the last
system of a step) runs the victory / defeat test (T§6) when the step's counter after the increment is 15 mod 16.
"""

from collections import Counter
from dataclasses import dataclass, field

from allods2.formats import scenario as S
from engine.world import DEAD, OrderGroup

from . import ai
from .pathfinding import chebyshev

SLOTS = 1000                        # S+0xc784 values (4000 bytes) and S+0xe6c4 fired flags (1000 bytes), FUN_0057468d
HERO_TYPE = 0x15                    # FUN_00562518: hero k = the unit with (u16)(+0x14c) - 0x15 == k
SUBOBJECTIVE_BASE = 0x2F0           # Scenario.dll variable of sub-objective n (instant 36, check 24)
MSG_SUB_DONE, MSG_SUB_FAILED = 0xFD, 0xFE   # messages of instant 36 (FUN_00577b16)
MISSION_PHASE = 15                  # FUN_004f8967 when (tick + 1) & 15 == 15 (end of the step)
STATE_COMPLETE, STATE_HERO = 1, 2   # player +0x40 after message 0xb5 / after the hero test


def _i32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


@dataclass(frozen=True)
class ScriptMessage:
    """Event (`World.events`): server message 0xb6 with value `number` (instant 2; 0xfd / 0xfe from instant 36)."""
    tick: int
    number: int


@dataclass(frozen=True)
class MissionComplete:
    """Event: message 0xb5 (T§6): the client opens the "mission complete" dialog (text 0x8c) or leaves at once."""
    tick: int
    player_id: int


@dataclass(frozen=True)
class MissionFailed:
    """Event: message 0xb4 with `cause` (T§6; 2 = no main hero / the main hero is dying): the defeat dialog."""
    tick: int
    player_id: int
    cause: int


class TriggerGroup:
    """The squad a group argument names (T§2.1: the group map keyed by squad number).  `members` = the squad's units at map start
    in creation order with the command group each had then; a member counts while it is not removed (state 0x10), still in that
    group (a player command or an owner change makes a new group) and still of the owner (FUN_0044fc20 = the list count)."""

    def __init__(self, key, members, ai_group=None, order_group=None):
        self.key = key
        self.members = members              # [(Unit, order_group id at map start)]
        self.ai_group = ai_group            # the AiGroup of a computer squad (orders, keep-awake)
        self.order_group = order_group      # the OrderGroup of a human squad (ai._stand_squads)

    @property
    def owner(self):
        return self.key[0]

    def live(self):
        return [u for u, og in self.members if u.state != DEAD and u.order_group == og and u.owner == self.key[0]]

    def target(self):
        """The group object the scripted orders act on."""
        return self.ai_group if self.ai_group is not None else self.order_group


@dataclass
class Compiled:
    """The runtime record of an instant or check (T§2.2)."""
    index: int
    type: int
    name: str
    nums: list                              # +0x08 packed numeric arguments (10)
    unit: object = None                     # +0x5c
    group: object = None                    # +0x60 TriggerGroup
    player: object = None                   # +0x64
    second: object = None                   # +0x68
    item: int = 0                           # +0x6c u16
    building: object = None                 # +0x70 MapObject
    var_refs: int = 0                       # +0x58


@dataclass
class CompiledTrigger:
    position: int                           # element index (the fired flag)
    name: str
    pairs: list                             # [(slot a, slot b, op)]
    instants: list                          # runtime instant indices
    once: int


@dataclass
class Script:
    """`world.script`: the compiled scenario and its state (the exe's S+0xc784.., T§1)."""
    instants: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    values: list = field(default_factory=lambda: [0] * SLOTS)
    fired: bytearray = field(default_factory=lambda: bytearray(SLOTS))
    stage: int = 0                          # S+0xc710 (instant 1)
    stage2: int = 0                         # S+0xd59c (instant 1)
    complete: int = 0                       # S+0xbe0c (instant 4)
    fail: int = 0                           # S+0xbe14 (instant 5, check 18)
    passes: int = 0                         # S+0xd720 (FUN_0057485b)
    drops: list = field(default_factory=list)           # "Drop Location" cells (x, y) (CWordArray this+0x28)
    gold: dict = field(default_factory=dict)            # player id -> server player +0x3c added by instant 23
    scenario_vars: dict = field(default_factory=dict)   # Scenario.dll ScenarioGetVar / SetVar array (0 until set)
    phased: dict = field(default_factory=dict)          # unit id -> Unit phased out (instants 16, 32)
    errors: list = field(default_factory=list)          # compile messages ("Can't resolve unit 5", ...)
    unsupported: Counter = field(default_factory=Counter)   # ("check" | "instant" | "group", kind) not implemented
    trace: list = field(default_factory=list)           # (tick, "trigger" | "instant", index): debug, not dumped
    strict: bool = False                    # raise NotImplementedError instead of counting

    def dump(self):
        return {"values": [[i, v] for i, v in enumerate(self.values) if v],
                "fired": [i for i, f in enumerate(self.fired) if f],
                "counters": [self.stage, self.stage2, self.complete, self.fail, self.passes],
                **({"gold": sorted(self.gold.items())} if self.gold else {}),
                **({"vars": sorted(self.scenario_vars.items())} if self.scenario_vars else {}),
                **({"phased": sorted(self.phased)} if self.phased else {}),
                **({"unsupported": sorted("%s:%d" % k for k in self.unsupported)} if self.unsupported else {})}


# --- compilation (T§2) ----------------------------------------------------------------------------------------------------------

def _reduced_id(u):
    """+0x14c: a human's server id above 10000 is stored as (v / 10) % 1000 (docs/data/units.md)."""
    v = u.server_id
    return (v // 10) % 1000 if u.human and v > 10000 else v


class _Resolver:
    def __init__(self, world, script):
        self.world, self.script = world, script
        self.units = {}
        for u in world.units.values():                  # creature map keyed by +8 (scenario uid); a later equal uid wins
            self.units[u.uid] = u
        self.groups = {}
        for pid in sorted(world.players):               # players in list order; a later player's equal squad number wins
            seen = {}
            for u in world.units.values():
                if u.owner == pid:
                    seen.setdefault(u.squad, []).append(u)
            for squad, mem in seen.items():
                key = (pid, squad)
                order_group = world.groups.get(mem[0].order_group)
                self.groups[squad] = TriggerGroup(key, [(u, u.order_group) for u in mem], world.ai_groups.get(key), order_group)

    def fail(self, text):
        self.script.errors.append(text)
        return None

    def unit(self, v):
        if v < S.HERO_BASE:
            u = self.units.get(v)
            return u if u is not None else self.fail("Can't resolve unit %d" % v)
        if v < S.NAMED_BASE:
            k = v - S.HERO_BASE
            pl = next((p for _, p in sorted(self.world.players.items()) if p.human), None)
            if pl is not None and pl.main_hero:
                for u in self.world.units.values():     # the owner's unit list, creation order (the filtered second loop: T§2.1)
                    if u.owner == pl.id and (_reduced_id(u) - HERO_TYPE) & 0xFFFF == k:
                        return u
            return self.fail("Can't resolve hero %d" % v)
        return self.fail("Can't resolve hero %d (units by name are not implemented)" % v)

    def group(self, v):
        g = self.groups.get(v)
        return g if g is not None else self.fail("Can't resolve group %d" % v)

    def player(self, v):
        p = self.world.players.get(v)
        return p if p is not None else self.fail("Can't resolve player %d" % v)

    def building(self, v):
        ob = self.world.objects.get(0x6000 + v)
        return ob if ob is not None and ob.kind != "object" else self.fail("Can't resolve building %d." % v)


def _compile(rec, index, res, check):
    """FUN_00562745's argument loop for one record; returns (Compiled, ok)."""
    c = Compiled(index, rec.type, rec.name, [0] * S.ARGS)
    ok, packed, first = True, 0, {}
    for k, v in zip(rec.kinds, rec.values):
        if S.VAR_LOW <= v <= S.VAR_HIGH and k in S.OBJECT_KINDS:
            c.var_refs += 1                             # T§2.3: resolved at run time from S+0xd724 (never written)
            continue
        if k == S.K_GROUP:
            obj = res.group(v)
            slot = "group"
        elif k == S.K_PLAYER:
            obj = res.player(v)
            slot = "player"
        elif k == S.K_UNIT:
            obj = res.unit(v)
            slot = "unit"
        elif k == S.K_ITEM:
            c.item = (v + S.ITEM_BASE) & 0xFFFF
            continue
        elif k == S.K_BUILDING:
            c.building = res.building(v)
            ok = ok and c.building is not None
            continue
        else:
            c.nums[packed] = v
            packed += 1
            continue
        if obj is None:
            ok = False
        if slot in first:
            c.second = obj
        else:
            first[slot] = True
            setattr(c, slot, obj)
    # keep-awake side effect (T§2.2): the first resolved group, else the second; the squad of the first unit, else the second
    if not (check and rec.type == 1):
        g = c.group if c.group is not None else (c.second if isinstance(c.second, TriggerGroup) else None)
        if g is not None and g.ai_group is not None:
            g.ai_group.keep_awake = True
        u = c.unit if c.unit is not None else (c.second if c.second is not None and hasattr(c.second, "squad") else None)
        if u is not None:
            ag = res.world.ai_groups.get((u.owner, u.squad))
            if ag is not None and u.id in ag.members:
                ag.keep_awake = True
    return c, ok


def compile_scenario(world, scenario):
    """T§2 on a world whose squads exist (`ai.enable` ran): returns the `Script`."""
    script = Script()
    res = _Resolver(world, script)
    imap = {}
    for rec in scenario.instants:
        if rec.type > S.CONSTANT - 1:
            if rec.type == S.CONSTANT:
                script.drops.append((rec.values[0] & 0xFF, rec.values[1] & 0xFF))      # CWordArray::Add(y << 8 | x)
            continue
        c, ok = _compile(rec, len(script.instants), res, False)
        if ok:
            imap[rec.id] = c.index
            script.instants.append(c)
        else:
            script.errors.append("Failed to create instant %d %s" % (rec.id, rec.name))
    cmap, slot = {}, 0
    for rec in scenario.checks:
        cmap[rec.id] = slot
        if rec.type < S.CONSTANT:
            c, ok = _compile(rec, slot, res, True)
            if ok:
                script.checks.append(c)
                slot += 1
            else:
                cmap[rec.id] = 0
                script.errors.append("Failed to create check %d %s" % (rec.id, rec.name))
        elif rec.type == S.CONSTANT:
            if slot < SLOTS:
                script.values[slot] = _i32(rec.values[0])
            slot += 1
    for pos, t in enumerate(scenario.triggers):
        if not t.active:
            continue
        pairs = [(cmap.get(a, 0), cmap.get(b, 0), op) for (a, b), op in zip(t.pairs, t.ops) if a and b]
        inst = []
        for i in t.instants:
            if i:
                if i > 5000:
                    script.errors.append("Reference to suspicsious instant (%d) from pattern %d." % (i, pos))
                inst.append(imap.get(i, 0))             # a missing / failed instant: the CMap default 0 (T§2.4)
        script.triggers.append(CompiledTrigger(pos, t.name, pairs, inst, t.once))
    return script


def enable(world, m, strict=False, assets=None, party=0):
    """Compile `m.scenario` (an `allods2.formats.Map`) into `world.script`; enables the AI first (the squads and their map-start
    orders are part of the compiler, T§2.1).  `strict`: unimplemented kinds raise NotImplementedError instead of being counted.

    With `assets`, a map that has "Drop Location" cells and a human player without a main hero gets a fresh campaign party
    (`engine.party.place_party`, T§9: `party` heroes, the main hero first; 0 = as many as the script names, 1..3, DECISION: the save
    that would carry the recruited heroes is not read) before the script is compiled, so the hero references resolve; a world
    that already holds the main hero is left alone."""
    scenario = m.scenario if hasattr(m, "scenario") else m
    if assets is not None:
        drops = [(r.values[0] & 0xFF, r.values[1] & 0xFF) for r in scenario.instants if r.type == S.CONSTANT]
        if drops:
            from engine.party import place_party
            named = [v - S.HERO_BASE + 1 for r in list(scenario.instants) + list(scenario.checks) for k, v in r.args()
                     if k == S.K_UNIT and S.HERO_BASE <= v < S.NAMED_BASE]
            place_party(world, assets, drops, count=party or min(3, max(named + [1])))
    if not world.ai_on:
        ai.enable(world)
    world.script = compile_scenario(world, scenario)
    world.script.strict = strict
    return world.script


# --- run time --------------------------------------------------------------------------------------------------------------------

def _unsupported(script, what, kind):
    if script.strict:
        raise NotImplementedError("%s kind %#x is not implemented (docs/engine/triggers.md)" % (what, kind))
    script.unsupported[(what, kind)] += 1


def _cell(u):
    return u.x, u.y


def _units_of(world, script, pid):
    """The members of all groups of player `pid` (every creature is in a group until its removal): living and dying units plus the
    phased-out ones (they stay in their group)."""
    out = [u for u in world.units.values() if u.owner == pid]
    out += [u for u in script.phased.values() if u.owner == pid and u.state != DEAD]
    return out


def _has_item(u, code):
    """FUN_00529ee5 over the unit's inventory: the engine's inventory is the section 8 pack (`Unit.carried`)."""
    return any((c & 0xFFFF) == code for c in u.carried)


def eval_check(world, script, c):
    """FUN_00574955 for one compiled check (T§3)."""
    vals, n, u, kind = script.values, c.nums, c.unit, c.type
    if kind == 1:
        vals[c.index] = len(c.group.live())
    elif kind == 2:
        vals[c.index] = int(n[0] <= u.x <= n[2] and n[1] <= u.y <= n[3])
    elif kind == 3:
        vals[c.index] = int(chebyshev(_cell(u), (n[0] & 0xFF, n[1] & 0xFF)) <= n[2])
    elif kind == 4:
        if n[0] == 6:
            vals[c.index] = _s16(u.hp)
    elif kind == 5:
        vals[c.index] = 0 if u.state == DEAD else 1
    elif kind == 6:
        u2 = c.second
        vals[c.index] = 0xFF if DEAD in (u.state, u2.state) else chebyshev(_cell(u), _cell(u2)) & 0xFF
    elif kind == 7:
        vals[c.index] = chebyshev(_cell(u), (n[0] & 0xFF, n[1] & 0xFF)) & 0xFF
    elif kind == 8:
        vals[c.index] = len(_units_of(world, script, c.player.id))
    elif kind == 9:
        t = world.find_unit(u.target) if u.mode_attack and u.target is not None else None
        vals[c.index] = t.uid if t is not None else 0
    elif kind == 10:
        p1, p2 = c.player, c.second
        vals[c.index] = (p1.relations[p2.id - 1] & 3) if 0 < p2.id <= len(p1.relations) else 0
    elif kind in (11, 13):
        pass
    elif kind in (12, 17):
        vals[c.index] = int(_has_item(u, c.item))
    elif kind == 14:
        vals[c.index] = int(bool(world.items_at(n[0] & 0xFF, n[1] & 0xFF)))
    elif kind == 15:
        ds = [chebyshev((n[0] & 0xFF, n[1] & 0xFF), _cell(m)) & 0xFF for m in _units_of(world, script, c.player.id)]
        vals[c.index] = min(ds + [0xFF])
    elif kind == 16:
        vals[c.index] = chebyshev(_cell(u), (n[0] & 0xFF, n[1] & 0xFF)) & 0xFF if _has_item(u, c.item) else 0xFF
    elif kind == 18:
        if u.state == DEAD:
            script.fail = _i32(script.fail + 1)
    elif kind == 19:
        vals[c.index] = vals[n[0]] if 0 <= n[0] < SLOTS else 0
    elif kind == 20:
        vals[c.index] = sum(1 for ob in world.objects.values()
                            if ob.kind != "object" and ob.owner == c.player.id and _s16(ob.hp) > 0)
    elif kind == 21:
        vals[c.index] = _s16(c.building.hp)
    elif kind == 23:
        vals[c.index] = script.scenario_vars.get(n[0], 0)
    elif kind == 24:
        vals[c.index] = script.scenario_vars.get(n[0] + SUBOBJECTIVE_BASE, 0)
    elif kind == 26 and n[0] == 12:
        vals[c.index] = int(u.hidden)                   # +0x144 bit 12: Invisibility (the only effect bit the engine has)
    elif kind == 27:
        vals[c.index] = int(u.x == (n[1] & 0xFF) and u.y == (n[2] & 0xFF) and (u.sub_x, u.sub_y) == (128, 128))
    else:
        _unsupported(script, "check", kind)


def _set_var(script, i, v):
    if 0 <= i < SLOTS:
        script.values[i] = _i32(v)


def _set_group_order(world, script, g, sub, n):
    orders = {1: (ai.G_GUARD, n[1]), 2: (ai.G_HOLD, (n[1] & 0xFF, n[2] & 0xFF)), 3: (ai.G_STAND, None),
              4: (ai.G_MOVE, (n[1] & 0xFF, n[2] & 0xFF)), 5: (ai.G_SWARM, (n[1] & 0xFF, n[2] & 0xFF)),
              17: (ai.G_WANDER, None), 18: (ai.G_COMPUTER, n[1] & 0xFF)}
    if sub not in orders:
        _unsupported(script, "group", sub)
        return
    target = g.target()
    if target is None or not [i for i in target.members if i in world.units]:
        return                                          # an empty group: every setter only loops over the members
    order, arg = orders[sub]
    ai.set_group_order(world, target, order, arg)


def change_owner(world, u, pid):
    """FUN_004f0568: leave the group and the owner list, new owner, a new group (no deletion of empty ones) under stand ground
    (`FUN_00570f2b` = cancel + `FUN_00570b8b`), out of the other players' selections (INFERRED: the client update)."""
    from . import orders
    old = world.groups.get(u.order_group)
    if old is not None and u.id in old.members:
        old.members.remove(u.id)
    for g in world.ai_groups.values():
        if u.id in g.members:
            g.members.remove(u.id)
    u.owner = pid
    g = OrderGroup(world._next_group, pid)
    world._next_group += 1
    world.groups[g.id] = g
    orders._join(world, g, u)
    orders.stop_group(world, g)
    for p in world.players.values():
        if u.id in p.selection:
            p.selection = tuple(i for i in p.selection if i != u.id)


def phase_out(world, script, u):
    """FUN_005102a3 (T§4 16): off the map and out of the update list, still a member of its squad."""
    if u.id in script.phased or u.id not in world.units:
        return
    world._index_del(world._ucells, u)
    del world.units[u.id]
    world.release(u)                                    # FUN_005102a3 -> FUN_00553891: the stamps and the occupant slots
    g = world.groups.get(u.order_group)
    if g is not None and u.id in g.members:
        g.members.remove(u.id)
    for ag in world.ai_groups.values():
        if u.id in ag.members:
            ag.members.remove(u.id)
    for p in world.players.values():
        if u.id in p.selection:
            p.selection = tuple(i for i in p.selection if i != u.id)
    script.phased[u.id] = u


def _free(world, u, x, y):
    """FUN_005563ca (INFERRED: the cell is inside the map, not blocked for the unit's mover and holds no unit)."""
    if not (0 <= x < world.width and 0 <= y < world.height):
        return False
    return not world.blocked(x, y, u.move_type if u.move_type in (1, 2, 3) else 1) and not world.units_at(x, y)


def find_place(world, u, x, y, r):
    """FUN_00510089(x, y, r): up to r*r/2 + 2 random tries in the square [-r/2, r - r/2] (y drawn first), then (r > 0) a scan
    x-major over [-r/2, r/2]; None when no cell is free."""
    rng, h = world.rng, r // 2
    for _ in range((r * r) // 2 + 2):
        cy = (y - h + rng.rand(r)) & 0xFF
        cx = (x - h + rng.rand(r)) & 0xFF
        if _free(world, u, cx, cy):
            return cx, cy
    if r:
        for cx in range(x - h, x + h + 1):
            for cy in range(y - h, y + h + 1):
                if _free(world, u, cx & 0xFF, cy & 0xFF):
                    return cx & 0xFF, cy & 0xFF
    return None


def _enter(world, script, u, cell):
    """Back into the world at `cell` (centre), appended to the update order (FUN_0052b22a), back into its squad in creation order."""
    del script.phased[u.id]
    m = u.mover
    m.step_target = m.step_from = None
    m.steps = m.step_ticks = 0
    u.x, u.y, u.sub_x, u.sub_y = cell[0], cell[1], 128, 128
    world.units[u.id] = u
    world._index_add(world._ucells, u)
    world.slots.place(u)                                # FUN_00510089: occupant slots (first come) and the own stamp
    groups = [world.groups.get(u.order_group)] if u.order_group else [world.ai_groups.get((u.owner, u.squad))]
    for g in groups:
        if g is not None and u.id not in g.members:
            g.members.append(u.id)
            g.members.sort(key=lambda i: world.units[i].seq if i in world.units else 0)


def phase_in(world, script, u, cell=None, radius=None):
    """FUN_005103ae (own cell, r = 0 then 3) or, with `cell`, FUN_00510318(cell, r = 3).  A unit on the map is left alone (the exe
    inserts it into the creature list a second time: not modelled, DECISION)."""
    if u.id not in script.phased:
        script.errors.append("phase in of unit %d which is on the map (not modelled)" % u.uid)
        return False
    if cell is None:
        spot = find_place(world, u, u.x, u.y, 0) or find_place(world, u, u.x, u.y, 3)
    else:
        spot = find_place(world, u, cell[0], cell[1], 3)
    if spot is None:
        script.errors.append("Unit can't return to map - no free place" if cell is None else "Unit can't enter map - no free place")
        return False
    _enter(world, script, u, spot)
    return True


def run_instant(world, script, index):
    """FUN_00574f3f (T§4)."""
    if not 0 <= index < len(script.instants):
        return
    c = script.instants[index]
    script.trace.append((world.tick, "instant", index))
    kind, n, u = c.type, c.nums, c.unit
    if c.var_refs:
        _unsupported(script, "instant", kind)           # T§2.3: S+0xd724 is never written
        return
    if kind == 1:
        script.stage = _i32(script.stage + 1)
        script.stage2 = _i32(script.stage2 + 1)
    elif kind == 2:
        world.events.append(ScriptMessage(world.tick, n[0]))
    elif kind == 3:
        _set_var(script, n[0], n[1])
    elif kind == 4:
        script.complete = _i32(script.complete + 1)
    elif kind == 5:
        script.fail = _i32(n[0])
    elif kind == 6:
        _set_group_order(world, script, c.group, n[0], n)
    elif kind == 8:
        if 0 <= n[0] < SLOTS:
            _set_var(script, n[0], script.values[n[0]] + 1)
    elif kind == 9:
        pass
    elif kind == 10:
        a, b = world.players.get(n[0]), n[1]
        if a is not None and 0 < b <= len(a.relations):
            rel = list(a.relations)
            rel[b - 1] = ((rel[b - 1] & 0xFC) + n[2]) & 0xFF
            a.relations = tuple(rel)
    elif kind == 16:
        phase_out(world, script, u)
    elif kind == 17:
        phase_in(world, script, u)
    elif kind == 18:
        phase_out(world, script, u)
        phase_in(world, script, c.second, cell=(u.x, u.y))
    elif kind == 19:
        change_owner(world, u, c.player.id)
    elif kind == 22:
        for m in c.group.live():
            change_owner(world, m, c.player.id)
    elif kind == 23:
        pid = c.player.id
        script.gold[pid] = _i32(script.gold.get(pid, 0) + n[0])
    elif kind == 26:
        c.building.hp = _s16(n[0])
    elif kind in (32, 33):
        for m in c.group.live():
            (phase_out if kind == 32 else phase_in)(world, script, m)
    elif kind == 34 and n[0] == 6:
        u.hp = _s16(n[1])
    elif kind == 35:
        script.scenario_vars[n[0]] = _i32(n[1])
    elif kind == 36:
        _subobjective(world, script, n[0] + SUBOBJECTIVE_BASE, n[1])
    elif kind == 39:
        g = c.group.ai_group
        if g is not None:
            g.keep_awake = False
    elif kind in (7, 11, 12, 13, 14, 15, 20, 21, 24, 25, 27, 28, 29, 30, 31, 34, 38):
        _unsupported(script, "instant", kind)
    else:
        script.errors.append("Script: Bad instant %d." % kind)


def _subobjective(world, script, var, value):
    """FUN_00577b16."""
    get = script.scenario_vars.get(var, 0)
    if value == 1:
        if get == 0:
            script.scenario_vars[var] = 1
    elif value == 2:
        if get != 4:
            if get & 2 == 0:
                world.events.append(ScriptMessage(world.tick, MSG_SUB_DONE))
            script.scenario_vars[var] = 3
    elif value == 4:
        world.events.append(ScriptMessage(world.tick, MSG_SUB_FAILED))
        script.scenario_vars[var] = 5
    else:
        script.scenario_vars[var] = _i32(value)


def _holds(vals, a, b, op):
    x, y = vals[a], vals[b]
    return (x == y, x != y, x > y, x < y, x >= y, x <= y)[op] if 0 <= op < 6 else False


def run_pass(world):
    """FUN_0057485b: the counter, every check (FUN_00574899), every trigger (FUN_00574ba1)."""
    script = world.script
    script.passes = _i32(script.passes + 1)
    for c in script.checks:
        if not c.var_refs:
            eval_check(world, script, c)
    vals = script.values
    for t in script.triggers:
        if t.once and script.fired[t.position]:
            continue
        script.fired[t.position] = 0
        if all(_holds(vals, a, b, op) for a, b, op in t.pairs):
            script.fired[t.position] = 1
            script.trace.append((world.tick, "trigger", t.position))
            for i in t.instants:
                run_instant(world, script, i)


def mission_pass(world):
    """FUN_004f856a for every human player (T§6); `Player.death_code` is the +0x40 byte."""
    script = world.script
    for _, p in sorted(world.players.items()):
        if not p.human or p.death_code >= 2:
            continue
        hero = world.find_unit(p.main_hero) if p.main_hero else None
        if p.main_hero and hero is None:
            hero = script.phased.get(p.main_hero)
        if not p.main_hero or hero is None or hero.death_seen:
            p.death_code = STATE_HERO
            p.defeat_dialog = True
            world.events.append(MissionFailed(world.tick, p.id, STATE_HERO))
        elif script.fail >= 1:
            p.death_code = script.fail & 0xFF
            p.defeat_dialog = True
            world.events.append(MissionFailed(world.tick, p.id, script.fail))
        elif script.complete != 0 and p.death_code != STATE_COMPLETE:
            p.death_code = STATE_COMPLETE
            world.events.append(MissionComplete(world.tick, p.id))


def mission_system(world, commands):
    """The per-player pass at the end of the step whose counter after the increment is 15 mod 16 (`FUN_004f08c0` `0x4f0aa7`)."""
    if world.script is not None and (world.tick + 1) & 15 == MISSION_PHASE:
        mission_pass(world)
