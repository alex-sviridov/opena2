"""The unit slots of the exe's cell records: occupant and stamp, first come first served.

Spec: docs/engine/simulation.md 7.4 "Cell record" (CONFIRMED, GOG allods2.exe).  The path finder keeps a 60-byte record per
cell that carries a unit, with two pairs of unit slots; this module is those slots and the routines that fill and clear them,
written from the spec (not from decompiler output).  Layer 3: knows only `Unit` fields (`id`, `x`, `y`, `move_type`, `stats`,
`mover.stamp_cell`).

- occupant slot rec+4 (ground classes 1, 2) / rec+8 (class 3): `place` (`FUN_0055020a` -> `FUN_005503af`, taken only when
  empty, any holder, a failure stops the footprint loop and skips the final stamp) and `lift` (`FUN_00550697` ->
  `FUN_0055073f`, clears the slot WHATEVER unit holds it; an empty slot stops the loop).  Read by `FUN_00551edb`.
- stamp slot rec+0x2c (every class but 3) / rec+0x30 (class 3): `be86` (`FUN_0055be86(unit, cell, mode)`) over the
  `(size + 2)^2` ring around the unit's cell; a stamp (`FUN_0055c2ce`) is taken when the slot is empty or already the unit's,
  a release (`FUN_0055c1fe`) clears it only when the unit holds it.  Read by the live layer (bit 0x40 / 0x80).
"""

AIR = 3                         # movement class 3 (flyer): the second slot of each pair
RELEASE, STAMP_NEXT, STAMP_OWN = 1, 2, 3        # the marks of the ring table


def _size(u):
    """Footprint side in cells (token size, vtable +0x1c)."""
    return max(1, int(getattr(u.stats, "token_size", 1) or 1)) if u.stats is not None else 1


def movement_class(u):
    """`FUN_0055f330` (vtable +0x20, creature +0x4a): the data.bin movementType; -1 ("keep the constructor default", the 605 humans)
    stays at the constructor's 1 (`0x50e1e0`)."""
    return 1 if u.move_type == -1 else u.move_type


def pack(x, y):
    """The 16-bit cell word `y << 8 | x`."""
    return ((y & 0xFF) << 8) | (x & 0xFF)


class CellSlots:
    """Occupant and stamp slots of every cell, keyed by the 16-bit cell index (the record hash key)."""

    def __init__(self):
        self.stamp = ({}, {})       # [ground, air]: idx -> unit id   (rec+0x2c, rec+0x30)
        self.occ = ({}, {})         # [ground, air]: idx -> unit id   (rec+4, rec+8)

    # --- stamps ----------------------------------------------------------------------------------------

    def take(self, u, idx):
        """`FUN_0055c2ce`: the slot is taken when empty or already this unit's (first come, first served)."""
        d = self.stamp[movement_class(u) == AIR]
        h = d.get(idx)
        if h is None or h == u.id:
            d[idx] = u.id

    def free(self, u, idx):
        """`FUN_0055c1fe`: the slot is cleared only when this unit holds it."""
        d = self.stamp[movement_class(u) == AIR]
        if d.get(idx) == u.id:
            del d[idx]

    def be86(self, u, cell, mode):
        """`FUN_0055be86(unit, cell, mode)` (mode 0: stamp the footprint at `cell` and at the own cell; 1: the own cell; 2: nothing):
        every cell of the ring that is not stamped is released, so the unit ends up holding exactly the cells it stamps among
        those of the ring, then `mover+0x80` := `cell` (0), the own cell (1) or 0 (2).  `cell` is a 16-bit word."""
        n = _size(u)
        table = [0] * 64                                    # 8 x 8 bytes, index x * 8 + y; the original overflows silently
        for i in range(n + 2):
            for j in range(n + 2):
                table[i * 8 + j] = RELEASE
        if mode == 0:
            dx, dy = (cell & 0xFF) - u.x, ((cell >> 8) & 0xFF) - u.y
            for i in range(1, n + 1):
                for j in range(1, n + 1):
                    k = (i + dx) * 8 + (j + dy)
                    if 0 <= k < 64:
                        table[k] = STAMP_NEXT
        if mode != 2:
            for i in range(1, n + 1):
                for j in range(1, n + 1):
                    table[i * 8 + j] = STAMP_OWN
        ox, oy = u.x - 1, u.y - 1
        for i in range(n + 2):
            for j in range(n + 2):
                mark = table[i * 8 + j]
                if not mark:
                    continue
                idx = (((j + oy) << 8) + (i + ox)) & 0xFFFF
                if mark == RELEASE:
                    self.free(u, idx)
                else:
                    self.take(u, idx)
        u.mover.stamp_cell = cell if mode == 0 else pack(u.x, u.y) if mode == 1 else 0

    # --- occupants -------------------------------------------------------------------------------------

    def place(self, u):
        """`FUN_0055020a`: the `size x size` footprint at the unit's own cell, row by row (x inner).  A non-empty slot (any unit, the
        caller included) stops the loop at once and the final `be86(unit, own cell, 1)` is skipped: returns False.  A unit of no
        known movement class places nothing."""
        if movement_class(u) not in (1, 2, 3):
            return False
        d = self.occ[movement_class(u) == AIR]
        n = _size(u)
        for j in range(n):
            for i in range(n):
                idx = pack(u.x + i, u.y + j)
                if idx in d:
                    return False
                d[idx] = u.id
        self.be86(u, pack(u.x, u.y), 1)
        return True

    def lift(self, u):
        """`FUN_00550697`: clears the footprint slots at the unit's own cell, whatever unit holds them; an empty slot stops the
        loop (returns False)."""
        if movement_class(u) not in (1, 2, 3):
            return False
        d = self.occ[movement_class(u) == AIR]
        n = _size(u)
        for j in range(n):
            for i in range(n):
                if d.pop(pack(u.x + i, u.y + j), None) is None:
                    return False
        return True

    def occupant(self, idx):
        """`FUN_00551edb(cell)`: the ground occupant slot only (rec+4), a unit id or None."""
        return self.occ[0].get(idx)

    # --- bookkeeping -----------------------------------------------------------------------------------

    def holders(self):
        """Every unit id that holds a slot (for the consistency check)."""
        return {h for t in (*self.stamp, *self.occ) for h in t.values()}
