"""Tick rate by game speed.  CONFIRMED docs/formats/animation.md 3.1."""

TICK_RATES = (8, 10, 12, 14, 16, 20, 24, 28, 32)     # ticks/s for speed 0..8
DEFAULT_SPEED = 4


def tick_period_ms(speed=DEFAULT_SPEED):
    """Integer period in ms (1000 // rate): speed 4 = 62."""
    return 1000 // TICK_RATES[max(0, min(8, speed))]


class TickClock:
    """The exe's tick scheduler (`FUN_00488aa1`, docs/engine/architecture.md 4; CONFIRMED).

    A 16-tick block: the tick with block counter `count` is due at `base + period * (count + 1)`; the tick that
    starts a block (count 0) sets `base = now` (the re-base), then the counter wraps `& 15`.  There is no
    cap: after a stall the due ticks run back to back up to the wrap and the tick at count 0 (so `17 - count`,
    at most 16, with count 1) and the stale lag is dropped at that re-base.
    A closed dialog / resume only zeroes the counter (`resume`), the base stays stale: exactly one tick runs at once.
    """

    def __init__(self, period, now=0):
        self.period, self.base, self.count = period, now, 0

    def advance(self, now):
        """Ticks to run at time `now` (ms)."""
        n = 0
        while now >= self.base + self.period * (self.count + 1):
            if self.count == 0:
                self.base = now
            self.count = (self.count + 1) & 15
            n += 1
        return n

    def resume(self):
        """After a modal window closed (`FUN_004891d8`: `+0x40c = 0`; `+0x414` untouched)."""
        self.count = 0
