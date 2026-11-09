"""Using a structure (command `0x24`, order `0xf`, Brain mode 15, state `0xf`): docs/engine/structures.md, design 2026-11-09-use-structure-design.md.

Built: the walk to the structure and the toggle of the switches 1 / 2 and the altars 1 / 2 (types 28, 29, 76, 77: `+0x42 = (+0x42 == 0) ? 1 : 0`, which
check 21 reads).  The wells, signposts and graves are K8 (structures.md 7): the lookup finds them and nothing happens.  Layer 4: reads and writes
`engine.world` only.

The effect is not the clicked structure's: state `0xf` looks for the first structure of the list within Chebyshev 2 of `(x - 1, y - 1)` of the unit's
cell (`FUN_0052c129` -> `FUN_0052bfe7`, CONFIRMED, structures.md 3); `World.use_clicked` (debug) uses the clicked one instead.
"""

from .pathfinding import Foot, chebyshev, foot

USE_ORDER, USE_STATE = 0xF, 0xF         # unit order `+0x50` and state `+0x54`
TOGGLE_TYPES = frozenset((28, 29, 76, 77))      # switches 1 / 2, altars 1 / 2 (type word `+0xe`, `0x50f9d4`-`0x50f9fe`)
LOOKUP_RANGE = 2                        # `FUN_0054fb7f` Chebyshev distance of the position lookup
FLAG_DESTROYED = 1                      # engine.world.FLAG_DESTROYED


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
    u.use_goal = walk_goal(world, u)
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_follow = u.mode_look = u.mode_use = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False
    u.mover.arrived = False


def walk_goal(world, u):
    """The cell the walk plans to.  The exe's planner call takes the range (`FUN_00555411(unit, dest, dist)`); ours plans to a cell, and the static search
    to a blocked target is bounded (pathfinding.md: unbounded only to a free cell), so a far unit would find "unreachable" at the structure's own cell.
    DECISION: the free cell (static layer and no unit on it) within the range of the destination that is nearest to the unit (Chebyshev, then Euclid, then row-major); the destination itself
    when the unit is already in range or no cell is free."""
    from .movement import live_cells, path_grid
    d = u.use_dest
    if chebyshev((u.x, u.y), d) <= u.use_dist:
        return (u.x, u.y)
    grid, live = path_grid(world, u.move_type), live_cells(world, u)
    cells = [(x, y) for y in range(d[1] - u.use_dist, d[1] + u.use_dist + 1) for x in range(d[0] - u.use_dist, d[0] + u.use_dist + 1)
             if 0 <= x < world.width and 0 <= y < world.height and not grid.is_blocked(x, y) and (x, y) not in live]
    if not cells:
        return d
    return min(cells, key=lambda c: (chebyshev((u.x, u.y), c), (c[0] - u.x) ** 2 + (c[1] - u.y) ** 2, c[1], c[0]))


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
        u.use_goal = walk_goal(world, u)
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
    """`+0x42 = (+0x42 == 0) ? 1 : 0`; the client stores the HP of message `0x82` and draws the destroyed art for `hp < 1` (structures.md 4)."""
    obj.hp = 0 if obj.hp else 1
    if obj.hp < 1:
        obj.flags |= FLAG_DESTROYED
    else:
        obj.flags &= ~FLAG_DESTROYED


def use_tick(world, u):
    """The state switch case `0xf` (`FUN_0050f12c`, `0x50f896`): lookup A at `(x - 1, y - 1)` and the switch / altar toggle."""
    obj = world.objects.get(u.use_obj) if world.use_clicked else None
    if obj is None:
        obj = find_structure(world, (u.x - 1, u.y - 1))
    if obj is not None and obj.kind == "structure" and obj.type_id in TOGGLE_TYPES:
        toggle(world, obj)
