"""Using a structure (command `0x24`, order `0xf`, Brain mode 15, state `0xf`): docs/engine/structures.md, design 2026-11-09-use-structure-design.md.

Built: the walk to the structure and the effect of every usable class, as data (`USE_A`, `WELLS`) plus one handler per behaviour: the toggle of the
switches 1 / 2 and the altars 1 / 2 (types 28, 29, 76, 77: `+0x42 = (+0x42 == 0) ? 1 : 0`, which check 21 reads), the signposts 70-75 (run the
instant `+0x6c` when it is > 0), the wells 15 / 16 (lookup B: 3 charges, a Potion Big Healing / Mana drunk through `gear.use_item`); graves and
houses do nothing (structures.md 3, 7).  The multiplayer shops / inns end the case like the exe (their messages are out of scope).  Layer 4: reads
and writes `engine.world` only.

The effect is not the clicked structure's: state `0xf` looks for the first structure of the list within Chebyshev 2 of `(x - 1, y - 1)` of the unit's
cell (`FUN_0052c129` -> `FUN_0052bfe7`, CONFIRMED, structures.md 3); `World.use_clicked` (debug) uses the clicked one instead.
"""

from dataclasses import dataclass

from .pathfinding import Foot, chebyshev, foot

USE_ORDER, USE_STATE = 0xF, 0xF         # unit order `+0x50` and state `+0x54`
TOGGLE_TYPES = frozenset((28, 29, 76, 77))      # switches 1 / 2, altars 1 / 2 (type word `+0xe`, `0x50f9d4`-`0x50f9fe`)
LOOKUP_RANGE = 2                        # `FUN_0054fb7f` Chebyshev distance of the position lookup
FLAG_DESTROYED = 1                      # engine.world.FLAG_DESTROYED
POINTER_TYPES = frozenset(range(70, 76))        # "Usable Pointer" 1-6, class "Pointer" `0x5f90b0` (structure ctor by type 0x46-0x4b, `FUN_00561422`)
SHOP_INN_TYPES = frozenset((0x22, 0x23, 0x5D, 0x5E, 0x5F, 0x69, 0x6A, 0x6B, 0x43, 0x44, 0x45, 0x63, 0x64, 0x65, 0x6F, 0x70, 0x71))  # multiplayer: the case ends (0x83 / 0x84)
WELLS = {0xF: "Potion Big Healing", 0x10: "Potion Big Mana"}   # lookup B by the type byte `+0x40`: the potion made per charge (`0x5fe2dc`, `0x5fe2f0`)


@dataclass(frozen=True)
class StructureState:
    """Event: server message `0x82` (`FUN_00503672`: structure id, its `+0x42` word) sent to the clients.  The client stores it and posts the info-panel
    refresh; **no sound, no text** (structures.md 4.1).  Lives in `World.events`, never in the dump or the hash."""
    tick: int
    uid: int
    hp: int


def approach(obj):
    """`FUN_0056d22b`: (destination cell, range) by the footprint width: 1-2 -> the cell, 1; 3-4 -> +(1, 1), 2; 5 and more -> +(2, 2), 3."""
    w = max((dx for dx, _, _ in obj.footprint), default=0) + 1 if obj.size is None else obj.size[0]
    if w <= 2:
        return (obj.x, obj.y), 1
    if w <= 4:
        return (obj.x + 1, obj.y + 1), 2
    return (obj.x + 2, obj.y + 2), 3


def set_use(world, u, obj):
    """`FUN_0056d22b`: cancel, order `0xf`, the structure, its approach cell and range, Brain mode 0 (the group pass starts it)."""
    from . import movement as mv
    mv.cancel(u, world)
    u.order = USE_ORDER
    u.use_obj = obj.id
    u.use_dest, u.use_dist = approach(obj)
    u.use_goal = u.use_dest                           # the planner target is the destination cell itself (FUN_00555411 gets dest + range; structures.md 2.1)
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_follow = u.mode_look = u.mode_use = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False
    u.mover.arrived = False


def command_use(world, u, object_id):
    """Command `0x24` after the intake: an unknown id or an object that is not a structure drops the command (`FUN_0052bfa3` over the building list).
    No test of class, owner, hero, distance or items (CONFIRMED).  Returns False when dropped."""
    obj = world.objects.get(object_id)
    if obj is None or obj.kind == "object":
        return False
    set_use(world, u, obj)
    return True


def refresh_use(world, u):
    """`FUN_0056af23` (order `0xf` in the group-pass executor): Brain mode 15 towards the approach cell."""
    if u.use_dest is None:
        return
    from .movement import live_cells
    u.mode_use = True
    if u.use_goal in live_cells(world, u):              # another unit stands on the walk's goal: pick again (DECISION, `walk_goal`)
        u.use_goal = u.use_dest                           # the planner target is the destination cell itself (FUN_00555411 gets dest + range; structures.md 2.1)
    m = u.mover
    if m.goal != u.use_goal:
        m.goal = u.use_goal
        m.arrived = m.failed = False
        m.waiting = m.parked = False


def in_range(u):
    """`FUN_0055539a`: the unit's cell is within `use_dist` (Chebyshev) of the destination and its facing is the facing to it (`FUN_00556b2c`)."""
    from . import combat
    d = u.use_dest
    return chebyshev((u.x, u.y), d) <= u.use_dist and u.facing == combat.octant(foot(u), Foot(d[0], d[1])) and not u.mover.turning


def use_mode(world, u):
    """Brain mode 15 (`FUN_0056ecbc`), every tick the unit is at a cell centre: state `0xf` already -> stop (`FUN_0056dbc6`: the effect ran once in the
    tick that set it); in range and facing -> state `0xf`; in range -> turn to the destination; else the move driver (the stop distance is the
    range test above, made at every centre).  A walk that ends out of range ends the order."""
    from . import combat, movement as mv
    if u.state == USE_STATE:
        mv.stop_unit(world, u)
        return
    d = u.use_dest
    if chebyshev((u.x, u.y), d) <= u.use_dist:
        if in_range(u):
            u.state = USE_STATE
            return
        face = combat.octant(foot(u), Foot(d[0], d[1]))
        if u.facing != face or u.mover.turning:
            mv._set_action(world, u, mv.TURN)
        mv._turn_toward(u, face)
        return
    mv.go_tick(world, u)
    if u.mover.arrived:                                 # the plan ended short of the range (`mover+0x90`): the order ends
        mv.stop_unit(world, u)


def find_structure(world, point):
    """Lookup A (`FUN_0052bfe7`): the first structure in creation order (= map file order) within Chebyshev 2 of `point`; the position is the footprint's
    top-left cell.  Type and owner are not tested."""
    for o in world.objects.values():
        if o.kind != "object" and chebyshev((o.x, o.y), point) <= LOOKUP_RANGE:
            return o
    return None


def toggle(world, obj):
    """`+0x42 = (+0x42 == 0) ? 1 : 0`, then message `0x82`; the client draws the destroyed art for `hp < 1` (structures.md 4)."""
    obj.hp = 0 if obj.hp else 1
    if obj.hp < 1:
        obj.flags |= FLAG_DESTROYED
    else:
        obj.flags &= ~FLAG_DESTROYED
    world.events.append(StructureState(world.tick, obj.uid, obj.hp))


def run_pointer(world, obj):
    """Class "Pointer": `if (+0x6c > 0) FUN_00574f3f(+0x6c)`: the instant runs at every use (no flag); the runtime index 0 is never reachable
    (quirk, map.md part 6); a signpost without a record keeps `-1`."""
    index = world.pointers.get(obj.uid, -1)
    if index > 0 and world.script is not None:
        from . import triggers
        triggers.run_instant(world, world.script, index)


def potion_item(world, name):
    """`FUN_00522fab(name)`: the item object of the data.bin special item of that name (its effects from the modifier text), and its resolved record;
    None when the table has no such name (the exe logs "no such ID" and goes on with id 0: not a game case)."""
    from . import gear
    from allods2.formats import saves as S
    for d in getattr(world.item_table, "defs", ()):
        if d.name == name and d.kind == "special":
            item = S.Item(14 << 8 | d.index, 1, d.price, ())
            return item, gear.resolve(world.item_table, item)
    return None


def use_well(world, u, obj):
    """Lookup B, type byte 0xf / 0x10: while `+0x42 > 0` one charge goes (message `0x82`) **before** and independently of the potion, which is made and
    drunk by the unit (`FUN_00523613`: effects applied, item destroyed; a full pack, a full unit, class, owner: never tested)."""
    if obj.hp <= 0:
        return
    obj.hp -= 1
    world.events.append(StructureState(world.tick, obj.uid, obj.hp))
    made = potion_item(world, WELLS[obj.type_id])
    if made is not None and made[1] is not None:
        from . import gear
        gear.use_item(world, u, made[0], made[1])


USE_A = {28: toggle, 29: toggle, 76: toggle, 77: toggle}       # lookup A, by the type word `+0xe`: handler(world, obj); then lookup B always runs


def use_tick(world, u):
    """The state switch case `0xf` (`FUN_0050f12c`, `0x50f896`, CONFIRMED): lookup A at `(x - 1, y - 1)`: a shop / inn or a Pointer ends the case (a
    Pointer runs its instant first), a switch / altar toggles; then lookup B at the unit's own cell: a well gives its potion.  Graves, houses and the
    multiplayer church: nothing."""
    obj = world.objects.get(u.use_obj) if world.use_clicked else None
    if obj is None:
        obj = find_structure(world, (u.x - 1, u.y - 1))
    if obj is not None and obj.kind == "structure":
        if obj.type_id in SHOP_INN_TYPES:
            return
        if obj.type_id in POINTER_TYPES:
            run_pointer(world, obj)
            return
        handler = USE_A.get(obj.type_id)
        if handler is not None:
            handler(world, obj)
    obj = find_structure(world, (u.x, u.y))
    if obj is not None and obj.kind == "structure" and obj.type_id in WELLS:
        use_well(world, u, obj)
