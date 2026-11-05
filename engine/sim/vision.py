"""The player's fog of war (docs/engine/vision.md): the viewer's own units and structures reveal cells in the world's tile words.

Client state in the exe, nothing in the simulation reads it; the system only keeps `World.fog` current.  Integer math, no RNG.
"""

from allods2 import vision as v

from . import ai, combat, combatstats
from ..world import death_stage

REFRESH_MASK = 0x1F             # `FUN_0040bcd8` `0x40bd37`: the full refresh when clock & 0x1f == 0
_MASK_CACHE_LIMIT = 8192


def enable(world, viewer=1):
    """Start with every cell never seen; the first `vision_system` pass reveals around the viewer's units (VERIFY IN GAME 1)."""
    world.fog = v.new_fog(world.width, world.height)
    world.fog_viewer = viewer
    world.fog_cells = {}
    world.fog_rev += 1


def reveal_all(world):
    """`#show map`: every tile in sight (the refresh is skipped while set in the exe; the engine's refresh would clear 0x4000, so `hide_all` is the
    only way back and this is for debugging)."""
    world.fog[:] = v.IN_SIGHT
    world.fog_rev += 1


def hide_all(world):
    """`#hide map` (value 0): clear the flag only, the tiles keep EXPLORED (everything explored)."""
    world.fog |= v.EXPLORED
    world.fog_rev += 1


def unit_sight(world, u):
    """The client sight word `obj+0x10a` of a unit: a human's recompute, else `scan << 8` with the effects' scan changes."""
    if u.human:
        st = combat.combat_stats(world, u)
        if st.attrs is not None:
            return combatstats.human_sight_word(u, st)
    return ai._scan_range(u, world) << 8


def _mask(world, x, y, sight):
    key = (x, y, sight)
    got = world._fog_masks.get(key)
    if got is None:
        if len(world._fog_masks) >= _MASK_CACHE_LIMIT:
            world._fog_masks.clear()
        got = world._fog_masks[key] = v.sight_mask(world.heights, world.width, world.height, x, y, sight)
    return got


def _observers(world):
    """(id, cell x, cell y, sight word) of everything of the viewer's that reveals: units and corpses of death stage < 3 (`FUN_0046df20`),
    structures with a scan range (`FUN_00460b76` centre = cell + half the footprint)."""
    me = world.fog_viewer
    for u in list(world.units.values()) + list(world.corpses.values()):
        if u.owner == me and death_stage(u.hp) < 3:
            yield u.id, u.x, u.y, unit_sight(world, u)
    for ob in world.objects.values():
        if ob.kind == "structure" and ob.owner == me and ob.sight:
            w = max(dx for dx, _, _ in ob.footprint) + 1
            h = max(dy for _, dy, _ in ob.footprint) + 1
            yield ob.id, ob.x + w // 2, ob.y + h // 2, ob.sight


def vision_system(world, commands):
    """After movement: (1) a viewer's observer whose cell differs from the one it last revealed reveals at once (`FUN_00460ae0`); (2) every 32 ticks
    (clock `tick + 1`) clear SEEN everywhere and reveal for every observer (`FUN_0040c129`)."""
    fog = world.fog
    if fog is None:
        return
    before = None
    full = (world.tick + 1) & REFRESH_MASK == 0
    if full:
        before = fog.copy()
        v.begin_refresh(fog)
    for eid, x, y, sight in _observers(world):
        if full or world.fog_cells.get(eid) != (x, y):
            if sight:
                if before is None:
                    before = fog.copy()
                v.reveal(fog, _mask(world, x, y, sight))
            world.fog_cells[eid] = (x, y)
    if before is not None and (fog != before).any():
        world.fog_rev += 1
    _drop_hidden_selection(world)


def _drop_hidden_selection(world):
    """`FUN_00468762`: a foreign unit with S = 1 (none of its four tiles in sight) that is selected (`obj+0x80`) is deselected the same view tick
    (info-panel selection of a monster that walks into the fog).  Own units have S = 0 always."""
    p = world.players.get(world.fog_viewer)
    if p is None or not p.selection:
        return
    keep = tuple(i for i in p.selection
                 if (u := world.units.get(i)) is None or u.owner == world.fog_viewer or v.cell_in_sight(world.fog, u.x, u.y))
    if keep != p.selection:
        p.selection = keep
