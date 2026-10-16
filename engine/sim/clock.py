"""Tick rate by game speed.  CONFIRMED docs/formats/animation.md 3.1."""

TICK_RATES = (8, 10, 12, 14, 16, 20, 24, 28, 32)     # ticks/s for speed 0..8
DEFAULT_SPEED = 4


def tick_period_ms(speed=DEFAULT_SPEED):
    """Integer period in ms (1000 // rate): speed 4 = 62."""
    return 1000 // TICK_RATES[max(0, min(8, speed))]
