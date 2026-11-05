"""The dynamic light map (`view+0xa8`, rebuilt every frame by `FUN_0040403b`; docs/mechanics/lighting.md section 3): vertex -> value, 0xFF = no light.

Sources built: structures with `LightRadius` (`FUN_00462386`) and missile projectiles (`FUN_0046d0ef`: firebolt / icemissile / meteorit radius 0, fireball
radius 1, value 16, stamped at the projectile's cell).  Not built (the engine has no such objects): the burning-cell list (fire explosions, server
message), the explosion phases of projectile 13 and the lightning segments of 28 / 30.  Pure: no pygame."""

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
    return out


def missile_cell(world, c, tick):
    from .drawlist import missile_position      # the same position the sprite is drawn at
    t = world.find_unit(c.target)
    tpos = None if t is None else ((t.x << 8) | t.sub_x, (t.y << 8) | t.sub_y)
    pos = missile_position(c, tpos, max(tick - c.born, 0))
    return pos[0] >> 8, pos[1] >> 8


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
