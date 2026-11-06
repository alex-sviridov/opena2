"""The random jagged line of the Lightning / Prismatic Spray bolts (projectiles 28 / 30), a port of `FUN_004c8863` (build), `FUN_004c819d` (control
points + smoothing + retry) and `FUN_004c8069` (quadratic through three points).  CONFIRMED asm (docs/engine/effects.md 11).  Pure: no pygame.

The exe works in doubles on the x87 stack (80-bit intermediates; here 64-bit), so a point can differ by one pixel in a rare rounding case.  The
random source is the C runtime `rand` (`FUN_00583290`: `holdrand = holdrand * 214013 + 2531011`, result `(holdrand >> 16) & 0x7fff`) of the one
thread, seeded once with `timeGetTime` (`srand` at `0x45ae54`): so the exe's lines are not reproducible; `CrtRand` keeps the generator and the caller
picks a seed (the engine derives it from the bolt and the tick, never touching `world.rng`)."""

import math


class CrtRand:
    """`FUN_00583290`: the MSVC `rand`."""

    def __init__(self, seed=1):
        self.state = seed & 0xFFFFFFFF

    def __call__(self):
        self.state = (self.state * 214013 + 2531011) & 0xFFFFFFFF
        return (self.state >> 16) & 0x7FFF


RETRY_LIMIT = 200       # DECISION: the exe recurses without a limit (`FUN_004c819d` calls itself); a stack-deep retry never happens in practice


def _div(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return math.copysign(math.inf, a) if a else math.nan


def spline(x1, y1, x2, y2, x3, y3, xs, ys):
    """`FUN_004c8069`: the quadratic `(A x + B) x + C` through the three points, sampled from `x1` in steps of 6.0 while `x < x3`, appended to
    `xs` / `ys` (the exe's lists `+0x90` / `+0xa4`).  The determinant and the three coefficients are evaluated in the exe's order."""
    s1, s2, s3 = x1 * x1, x2 * x2, x3 * x3
    d = (x3 - x2) * s1 + (x1 - x3) * s2 + (x2 - x1) * s3
    a = _div(-((y3 - y2) * x1 + (y1 - y3) * x2 + (y2 - y1) * x3), d)
    b = _div((y3 - y2) * s1 + (y1 - y3) * s2 + (y2 - y1) * s3, d)
    c = _div(-((x2 * y3 - x3 * y2) * s1 + (x3 * y1 - x1 * y3) * s2 + (x1 * y2 - x2 * y1) * s3), d)
    x = x1
    while x < x3:
        xs.append(x)
        ys.append((a * x + b) * x + c)
        x += 6.0


def control_line(x1, y1, x2, y2, length, rand):
    """`FUN_004c819d`: the jagged line from `(x1, y1)` towards `(x2, y2)` (the exe calls it with a horizontal line of `length`), returned as
    `(xs, ys)` sample lists.  Steps: a lateral sign by `rand & 1`; draws `rand % 7 * sign` and `rand % 50 * 0.01` until the running step sum
    reaches 0.7, a draw counting when `|jump| > 2` and the step `> 0.15` (the running offset is clamped to +-3, the sign flips); the control points
    sit at `x1 + t * dx` with the offset `* 0.03 * length` added to y, smoothed by the midpoints, closed with `(x2, y2)` and splined.  The line is
    thrown away and rebuilt when a sample strays from `y1` by more than `0.15 * length`."""
    dx, dy = x2 - x1, y2 - y1
    limit = length * 0.15
    scale = length * 0.03
    for attempt in range(RETRY_LIMIT):
        sign = 1.0 if rand() & 1 else -1.0
        t, off = [0.0], [0.0]
        acc = cum = 0.0
        while True:
            jump = (rand() % 7) * sign
            step = (rand() % 50) * 0.01
            if abs(jump) > 2.0 and step > 0.15:
                cum += jump
                if cum > 3.0:
                    cum = 3.0
                if cum < -3.0:
                    cum = -3.0
                off.append(cum)
                acc += step
                t.append(acc)
                sign = -sign
            if not acc < 0.7:
                break
        if t[-1] >= 1.0:
            del t[-1], off[-1]
        t.append(1.0)
        off.append(0.0)
        px = [x1, t[1] * dx + x1]
        py = [y1, off[1] * scale + (t[1] * dy + y1)]
        for i in range(2, len(t) - 1):
            x = t[i] * dx + x1
            y = off[i] * scale + (t[i] * dy + y1)
            px.append((x - px[-1]) / 2.0 + px[-1])
            py.append((y - py[-1]) / 2.0 + py[-1])
            px.append(x)
            py.append(y)
        px.append(x2)
        py.append(y2)
        xs, ys = [], []
        for i in range(2, len(px), 2):
            spline(px[i - 2], py[i - 2], px[i - 1], py[i - 1], px[i], py[i], xs, ys)
        if not any(abs(y - y1) > limit for y in ys):
            return xs, ys
    return xs, ys


def build(x1, y1, x2, y2, rand):
    """`FUN_004c8863`: the integer points `[(x, y)]` of one bolt line from `(x1, y1)` to `(x2, y2)`: the control line is made along a horizontal of the
    same length (`length = hypot(dx, dy)`) and rotated about its first sample onto the real direction, each coordinate truncated (`FUN_00582c0c` =
    `fistp` with round-toward-zero).  A zero-length line has no points."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    xs, ys = control_line(x1, y1, x1 + length, y1, length, rand)
    ux, uy = dx / length, dy / length
    if not xs:
        return []
    x0, y0 = xs[0], ys[0]
    out = []
    for x, y in zip(xs, ys):
        px = (x - x0) * ux + x0 - (y - y0) * uy
        py = (y - y0) * ux + ((x - x0) * uy + y0)
        out.append((int(px), int(py)))
    return out
