"""The simulation's random number generator: the exe's own (MSVC CRT `rand`).

Spec: docs/engine/simulation.md section 10.  `FUN_00583290` is `rand()`, `FUN_00583280` is `srand`, `FUN_0051fa25(n)` is the
game's `rand(n)`.  One instance is owned by the `World`; every system in `engine/sim/` draws from it in update order and nowhere
else (a test scans the imports).  Our stream equals the original algorithm's for the same seed; it cannot equal a recorded original
session (the exe seeds from the clock and shares the stream with its client).
"""

DEFAULT_SEED = 1                    # a fresh CRT thread block holds 1 (FUN_0058a910)
_MUL, _ADD, _MASK = 0x343FD, 0x269EC3, 0xFFFFFFFF


class Rng:
    """CRT linear congruential generator.  `state` is the 32-bit word the exe keeps at `ptd+0x14`."""

    __slots__ = ("state",)

    def __init__(self, seed=DEFAULT_SEED):
        self.state = seed & _MASK

    def srand(self, seed):
        self.state = seed & _MASK

    def rand15(self):
        """`rand()`: advance, return bits 16..30 (0..0x7fff)."""
        self.state = (self.state * _MUL + _ADD) & _MASK
        return (self.state >> 16) & 0x7FFF

    def rand(self, n):
        """`FUN_0051fa25(n)`: uniform on `0..n` inclusive; `n == 0` returns 0 and draws nothing."""
        if n == 0:
            return 0
        return (self.rand15() * (n + 1)) >> 15
