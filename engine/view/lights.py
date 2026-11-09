"""The dynamic light map (`view+0xa8`, rebuilt every frame by `FUN_0040403b`; docs/mechanics/lighting.md section 3): vertex -> value, 0xFF = no light.

Sources built: structures with `LightRadius` (`FUN_00462386`) and missile projectiles (`FUN_0046d0ef`: firebolt / icemissile / meteorit radius 0, fireball
radius 1, value 16, stamped at the projectile's cell).  Burning cells (Wall of Fire flag on a cell whose map object has a DeadObject, `World.burn_start`) are built.  Fire explosions (projectile 13, `World.explosions`, `explosion_phases`) and their burning-list entries (`World.burn_fx`) are built, and the Lightning / Prismatic Spray bolts (`World.bolts`, `bolt_cells` -> `bolt_vertices`).  Pure: no pygame."""


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
    for a in getattr(world, "arrows", ()):                         # the client flights (cast action): the light follows the sprite
        if a.live and a.pid in MISSILE_IDS:
            light = lt.projectile_light(a.pid)
            if light is not None:
                _stamp(out, a.x >> 8, a.y >> 8, *light)
    for b in getattr(world, "bolts", ()):                          # projectiles 28 / 30: `phase * 10` over each segment point's 2 x 2 vertices
        age = bolt_age(b, tick)
        if age is not None:
            out.update(bolt_vertices(bolt_cells(world, b, tick), bolt_phase(age)))
    for e, age, phase in explosion_phases(world, assets, tick):     # projectile 13 (`FUN_0046d0ef` case 0xd): radius and value by the phase `+0x74`
        light = lt.projectile_light(13, phase)
        _stamp(out, e.x, e.y, *light)
    for x, y, counter in burning_entries(world, assets, tick):      # `FUN_0040403b` step 3, after the object lights: overwrites them
        _stamp(out, x, y, 1, lt.BURNING_LIGHT_PHASES[counter >> 1])
    return out


def explosion_phases(world, assets, tick):
    """`[(explosion, age, phase)]` of the live fire explosions: age `obj+0x9c` = -1 at creation and 0 after the first tick of the creation step, so the frame
    after step `born` (`tick = born + 1`) shows age 0 and the last one (`born + life`) age `life - 1`; phase `obj+0x74` = `(age / 2) mod Phases`
    (`FUN_0046c1d0` case 0xd, CONFIRMED; the record's Phases, 11 when the set is unknown)."""
    out = []
    pset = None
    for e in getattr(world, "explosions", ()):
        age = tick - e.born - 1
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


def bolt_age(b, tick):
    """The age `obj+0x9c` the bolt is drawn at on `tick`, None while it does not exist (before its first draw or after its 13 steps).  The object is made in
    step `born` and ticked once in it (server step -> message loop -> view tick, `FUN_00488aa1`), so the frame after that step (`tick = born + 1`) shows
    age 1 (the cast action's bolt, `age0 = 0`) or age 0 (the message-made 0x8c form, `age0 = -1`), and the 13 steps are drawn on `born + 1 .. born + 13`."""
    n = tick - b.born
    if 1 <= n <= b.life:
        return n + b.age0
    return None


def bolt_phase(age):
    """`obj+0x74` of projectile 28 / 30 at age 1 .. 13 (`FUN_0046c1d0` cases 0x1c / 0x1e, table `0x46cb47`, index `age - 1` above 0xc leaves the
    phase alone): 4 3 2 1 0 1 2 1 0 1 2 3 4; age 0 (the 0x8c form's first tick) keeps the constructor's phase 0 (INFERRED: zeroed by `FUN_0045fa00`)."""
    from allods2.anim.projectiles import PING_PONG
    return PING_PONG[age - 1] if age >= 1 else 0


def bolt_seed(b, tick, i):
    """The generator seed of line `i` of bolt `b` on `tick`: the exe's lines come from the thread's `rand` seeded by `timeGetTime` (not reproducible),
    so the engine draws a repeatable stream per line, scrambled so that nearby ticks do not give similar lines (never `world.rng`)."""
    import random
    return random.Random(hash((b.born, b.caster, tick, i)) & 0xFFFFFFFF).getrandbits(32)


def bolt_segments(world, b, tick):
    """The segments of a bolt at `tick` as `[(variant, [(px, py)])]`, px in world pixels, y with the ground relief and the unit's altitude removed
    (`FUN_0046d46a`, CONFIRMED: the polyline of `boltline.build` from `(obj+0x54, obj+0x58 - obj+0x6c - obj+0x10)` of the projectile = its origin
    (`Bolt.origin`: the caster's ShootOffset point, `effects.shoot_origin`; altitude 0) to `(view+0x64, view+0x68 - view+0x6c - view+0x10)` of each
    target = the footprint centre of the unit, its ground relief and its altitude (flyers 16, `FLYER_ALTITUDE`), no chest height).  Lightning has
    one segment, the Spray one per list entry with `index % 7` as the variant that picks the sprite row.  A target that is gone (the view lookup
    fails) has no segment."""
    from . import boltline
    from .drawlist import CELL, FLYER_ALTITUDE
    from allods2.formats import objects as fobj

    def screen(pos, size, alt):
        x, y = pos[0] + ((size - 1) << 7), pos[1] + ((size - 1) << 7)
        return ((x * CELL) >> 8, ((y * CELL) >> 8) - fobj.ground_height(world.heights, pos[0], pos[1], size, size) - alt)
    p0 = screen(b.origin, 1, 0)
    out = []
    for i, tid in enumerate(b.targets):
        t = world.find_unit(tid)
        if t is None:
            continue
        p1 = screen((t.x * 256 + t.sub_x, t.y * 256 + t.sub_y), tile_size(world, t), FLYER_ALTITUDE if unit_flies(world, t) else 0)
        rand = boltline.CrtRand(bolt_seed(b, tick, i))
        out.append((i % 7 if b.pid == 30 else 0, boltline.build(p0[0], p0[1], p1[0], p1[1], rand)))
    return out


def tile_size(world, u):
    """units.reg `TileSize` of a unit (the view's footprint side; the engine `Unit` has no size attribute); 1 when the unit set is unknown."""
    assets = getattr(world, "assets", None)
    aset = assets.unit_set(u.type_id) if assets is not None and hasattr(assets, "unit_set") else None
    return max(int(getattr(aset.t, "TileSize", 1)), 1) if aset is not None else 1


def unit_flies(world, u):
    """units.reg `Z != 0` (the flyer view class, altitude `U+0x10` = 16); False when the unit set is unknown."""
    assets = getattr(world, "assets", None)
    aset = assets.unit_set(u.type_id) if assets is not None and hasattr(assets, "unit_set") else None
    return bool(aset is not None and aset.t.Z)


def bolt_cells(world, b, tick):
    """The light cells of a bolt: for each point `(x >> 5, FUN_00417f31(x, y))` inside the map (`pick_row`)."""
    cells = []
    for _, pts in bolt_segments(world, b, tick):
        for x, y in pts:
            cx, cy = int(x) >> 5, pick_row(world, int(x), int(y))
            if cy is not None and 0 <= cx < world.width - 1 and 0 <= cy < world.height - 1:
                cells.append((cx, cy))
    return cells


def pick_row(world, mx, my):
    """`FUN_00417f31(mx, my)` in world pixels (CONFIRMED asm, docs/engine/click-to-move-research.md 9): the first row `r` whose terrain strip at column
    `mx >> 5` holds the pixel row `my`: vertex screen y `32 * r - int8(height)`, interpolated across the cell by `mx & 31`; `None` = no match (the
    exe's `H + 4`)."""
    col, fx = mx >> 5, mx & 31
    hs = world.heights
    rows, cols = hs.shape
    if not 0 <= col < cols - 1:
        return None

    def v(r):
        r = min(max(r, 0), rows - 1)
        a = 32 * r - int(hs[r, col])
        b = 32 * r - int(hs[r, col + 1])
        return a + int((b - a) * fx / 32)
    for r in range(max((my >> 5) - 6, 0), min((my >> 5) + 7, rows - 1)):
        if v(r) <= my <= v(r + 1):
            return r
    return None


def bolt_vertices(points, phase):
    """Lightning / prismatic spray (`FUN_0046d0ef` cases 0x1c, 0x1e): at each segment point's cell `(cx, cy)` (x `>> 5`, row by `FUN_00417f31`) the 2 x 2
    vertices get `phase * 10` (a byte), with no Lighting-option gate.  Fed by `bolt_cells` (the bolt's polyline points) in `light_map`."""
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
