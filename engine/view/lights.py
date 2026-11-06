"""The dynamic light map (`view+0xa8`, rebuilt every frame by `FUN_0040403b`; docs/mechanics/lighting.md section 3): vertex -> value, 0xFF = no light.

Sources built: structures with `LightRadius` (`FUN_00462386`) and missile projectiles (`FUN_0046d0ef`: firebolt / icemissile / meteorit radius 0, fireball
radius 1, value 16, stamped at the projectile's cell).  Burning cells (Wall of Fire flag on a cell whose map object has a DeadObject, `World.burn_start`) are built.  Fire explosions (projectile 13, `World.explosions`, `explosion_phases`) and their burning-list entries (`World.burn_fx`) are built.  Not built: the lightning segments of 28 / 30 (`bolt_vertices`
is the formula; no sim object feeds it, see docs/engine/rendering.md).  Pure: no pygame."""

from allods2.graphics import lighting as lt

NO_LIGHT = 0xFF
MISSILE_IDS = {10, 18, 40, 12}            # `projectiles.reg` ids that stamp (lighting.md); the engine's missile id is 2 * spell + 8


def light_map(world, assets, tick):
    """{(vx, vy): value} of the lit vertices at animation clock `tick` (`view+0xa88`); empty = nothing lit (the common case).  Later sources
    overwrite earlier ones (the exe writes in view-list order; INFERRED here: structures, then missiles)."""
    out = {}
    for ent in world.objects.values():
        if ent.kind != "structure" or ent.hp <= 0:
            continue
        aset = assets.structure_set(ent.type_id, None)
        rec = None if aset is None else aset.rec
        radius = 0 if rec is None else rec.get("LightRadius") or 0
        if not radius:
            continue
        value = lt.structure_light_value(rec.get("LightPulse") or 0, tick)
        for v in lt.structure_light_vertices(ent.x, ent.y, ent.x + aset.W - 1, ent.y + aset.TH - 1, radius):
            out[v] = value
    for c in getattr(world, "carriers", ()):
        if c.kind != "missile" or c.spell * 2 + 8 not in MISSILE_IDS:
            continue
        light = lt.projectile_light(c.spell * 2 + 8)
        cell = missile_cell(world, c, tick)
        if light is not None and cell is not None:
            _stamp(out, cell[0], cell[1], *light)
    for e, age, phase in explosion_phases(world, assets, tick):     # projectile 13 (`FUN_0046d0ef` case 0xd): radius and value by the phase `+0x74`
        light = lt.projectile_light(13, phase)
        _stamp(out, e.x, e.y, *light)
    for x, y, counter in burning_entries(world, assets, tick):      # `FUN_0040403b` step 3, after the object lights: overwrites them
        _stamp(out, x, y, 1, lt.BURNING_LIGHT_PHASES[counter >> 1])
    return out


def explosion_phases(world, assets, tick):
    """`[(explosion, age, phase)]` of the live fire explosions: age = ticks since creation (0 .. life - 1), phase `obj+0x74` = `(age / 2) mod Phases`
    (`FUN_0046c1d0` case 0xd, CONFIRMED; the record's Phases, 11 when the set is unknown)."""
    out = []
    pset = None
    for e in getattr(world, "explosions", ()):
        age = tick - e.born
        if 0 <= age < e.life:
            if pset is None and assets is not None:
                pset = assets.projectile_set(13)
            phases = max(pset.rec["Phases"], 1) if pset is not None else 11
            out.append((e, age, (age // 2) % phases))
    return out


def burning_entries(world, assets, tick):
    """The live burning-list entries `(x, y, counter)` (`view+0xa94`; counter = ticks since the flag, `< 22`) of the cells that qualify (`burns`).
    Fire explosion entries (`world.burn_fx`, queued at age 4: map object or water) join the Wall of Fire ones; the later `SetAt` of a cell wins."""
    out = {}
    for (x, y), born in world.burn_start.items():
        if 0 <= tick - born < lt.BURN_TICKS and burns(world, assets, x, y):
            out[(x, y)] = tick - born
    for (x, y), (born, water) in getattr(world, "burn_fx", {}).items():
        if 0 <= tick - born < lt.BURN_TICKS and (water or burns(world, assets, x, y)):
            out[(x, y)] = min(out.get((x, y), 99), tick - born)
    return [(x, y, c) for (x, y), c in out.items()]


def burns(world, assets, x, y):
    """`FUN_0041c18c` flag 3: the cell enters the burning list only when its map object has a `DeadObject` (`objects.reg` `+0x44 != -1`)."""
    for i in world.objects_at(x, y):
        ent = world.objects[i]
        if ent.kind == "object":
            aset = assets.object_set(ent.type_id)
            return aset is not None and aset.rec["DeadObject"] != -1
    return False


def missile_cell(world, c, tick):
    from .drawlist import missile_position      # the same position the sprite is drawn at
    t = world.find_unit(c.target)
    tpos = None if t is None else ((t.x << 8) | t.sub_x, (t.y << 8) | t.sub_y)
    pos = missile_position(c, tpos, max(tick - c.born, 0))
    return pos[0] >> 8, pos[1] >> 8


def bolt_vertices(points, phase):
    """Lightning / prismatic spray (`FUN_0046d0ef` cases 0x1c, 0x1e): at each segment point's cell `(cx, cy)` (x `>> 5`, row by `FUN_00417f31`) the 2 x 2
    vertices get `phase * 10` (a byte), with no Lighting-option gate.  Pure formula: no sim object feeds it yet (the point list comes from message 0x8a)."""
    value = (phase * 10) & 0xFF
    return {(cx + i, cy + j): value for cx, cy in points for i in (0, 1) for j in (0, 1)}


def _stamp(out, cx, cy, radius, value):
    """`FUN_0040631e`: every vertex with dx^2 + dy^2 < r (r + 1) (r = 0: the centre)."""
    limit = radius * (radius + 1) or 1
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy < limit:
                out[(cx + dx, cy + dy)] = value


def corner_lights(lights, base, x, y):
    """The four corners of cell (x, y), `FUN_00405cf4`: min(terrain light, light) where lit, else the terrain light; None when no corner is lit."""
    vs = ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))
    if not any(v in lights for v in vs):
        return None
    return tuple(min(int(base[vy, vx]), lights[(vx, vy)]) if (vx, vy) in lights else int(base[vy, vx]) for vx, vy in vs)


def cell_row(lights, x, y, ambient):
    """Object light row of cell (x, y) (`FUN_00404a2a` step 3), None = the default row."""
    return lt.object_light_row_lit([lights.get(v, NO_LIGHT) for v in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))], ambient)
