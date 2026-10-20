"""The placement search `FUN_00510089(x, y, r)` and its free-cell test (docs/engine/triggers.md section 10; CONFIRMED in the GOG exe).

`FUN_005563ca(creature)` = `FUN_0055c5a0(creature, cell, 0)` and then `(creature, cell, 1)`: the `size x size` footprint (vtable `+0x1c`) whose
top-left cell is the creature's position (`x + i`, `y + j`, both masked to a byte: the grids are 256 x 256 and wrap) must show no bit of the
mover mask (`brain+5`: 0x41 walker, 0x44 ghost, 0x82 flyer) in the live layer (`+0x20000`: static + unit stamps) and in the static layer
(`+0x10000`).  There is no occupant test: a unit that holds no stamp (a lost first-come race) does not block.  Layer 3: reads `World` only.
"""

from allods2.formats import passability as pas

from .pathfinding import unit_size

STAMP = {0: 0x40, 1: 0x80}            # live-layer bit of the stamp slot (ground classes / flyers)


def clamp(world, x, y):
    """`FUN_00510089` -> `FUN_0054fca8`: the (byte) position is clamped into the playable rectangle [8, width - 9] x [8, height - 9]
    before every test (the search never leaves it, whatever the draw gave)."""
    return min(max(x & 0xFF, 8), world.width - 9), min(max(y & 0xFF, 8), world.height - 9)


def mover_class(u):
    """The mover class used for the mask: the data.bin movementType, -1 (humans) counts as a walker (map.md part 3)."""
    return u.move_type if u.move_type in pas.MOVE_MASK else 1


def cell_free(world, u, x, y):
    """`FUN_0055c5a0` for both layers of `FUN_005563ca`: True when the footprint of `u` anchored at (x, y) is clear."""
    mt = mover_class(u)
    mask = pas.MOVE_MASK[mt]
    n = unit_size(u)
    stamps = world.slots.stamp
    for i in range(n):
        for j in range(n):
            cx, cy = (x + i) & 0xFF, (y + j) & 0xFF
            if cx >= world.width or cy >= world.height:
                return False                # unreachable from the search (clamped); the exe reads 0 / 0x1f here
            if world.blocked(cx, cy, mt):
                return False
            idx = (cy << 8) | cx
            for air in (0, 1):
                if idx in stamps[air] and STAMP[air] & mask:
                    return False
    return True


def find_place(world, u, x, y, r):
    """`FUN_00510089(x, y, r)`: up to `r*r/2 + 2` random tries in the square [x - r/2, x - r/2 + r] (the y draw comes first; `rand(r)` is
    0..r), then (r > 0) a scan x-major over [-r/2, +r/2]; the first free cell, or None.  Cells are bytes."""
    rng, h = world.rng, r // 2
    for _ in range((r * r) // 2 + 2):
        cy = (y - h + rng.rand(r)) & 0xFF
        cx = (x - h + rng.rand(r)) & 0xFF
        cx, cy = clamp(world, cx, cy)
        if cell_free(world, u, cx, cy):
            return cx, cy
    if r:
        for cx in range(x - h, x + h + 1):
            for cy in range(y - h, y + h + 1):
                px, py = clamp(world, cx, cy)
                if cell_free(world, u, px, py):
                    return px, py
    return None
