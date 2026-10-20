"""The server's free-id bitmap (`DAT_006c9628`, 0xc00 bytes = 0x6000 bits; docs/engine/combat.md 12.11 item 1).

`FUN_004f8d90` hands out the lowest clear bit and sets it (`FUN_004f8cec`, ids >= 0x6000 are never recorded), `FUN_004f8d3d` clears one; the
initialiser `FUN_004f8cc9` (server start `0x4eb37a`, load `0x4ec994`) zeroes the table and sets bit 0, so id 0 is never issued.  The ids go to
the objects created at run time: ground piles (`FUN_0052a780`, also at map load), a new main hero (`FUN_004f254b`), a recruited hero
(`FUN_004f312a`), units made by `FUN_004f89d1` (the Summon / Control Spirit spells, `FUN_00519db8`); map units and structures use `0x6000 + uid`
(`FUN_0052b281`) and never touch the table.  The summon cap job keys its `CMap` by these ids.
"""

LIMIT = 0x6000


class NetIds:
    def __init__(self):
        self.used = {0}

    def alloc(self):
        """`FUN_004f8d90`: the lowest free id."""
        i = 0
        while i in self.used:
            i += 1
        if i < LIMIT:
            self.used.add(i)
        return i

    def free(self, i):
        """`FUN_004f8d3d` (ids >= 0x6000 are ignored)."""
        if 0 < i < LIMIT:
            self.used.discard(i)
