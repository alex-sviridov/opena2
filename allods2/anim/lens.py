"""The screen lens of projectile 7 (bat and succubus missiles).

Spec: docs/formats/animation.md §4.4 (CONFIRMED).  Projectile ID 7 draws no
sprite: FUN_004a6b4b moves screen pixels around its anchor through a table
built once (global 0x621454, FUN_004a6840(R = 20, d = 16) -> FUN_004a695f):

    n    = trunc(sqrt(R^2 - (R - d)^2))                     = 19
    k(0) = 1;  k(r) = r / (R * sin(atan(r / (R - d))))       r = 1 .. n-1
    for i, j in 0 .. n-1:
        r = trunc(sqrt(i^2 + j^2) + 0.5)
        T[i][j] = (trunc(i k(r) + 0.5), trunc(j k(r) + 0.5)) if r < n else (i, j)

k(r) = sqrt(r^2 + 16) / 20 < 1, so each pixel copies one nearer the centre:
a magnifying bulge of radius 19 px.  The draw walks i, then j, from n-1
down to 0 and for each (i, j) copies, in place on the frame buffer,
(x+a, y+b) <- (x+sa, y+sb) for the quadrants (+,+), (+,-), (-,+), (-,-),
skipping pixels whose source or target is off screen.
"""

import math

import numpy as np

LENS_R, LENS_D = 20, 16


def _ftol(v):
    return int(v)           # __ftol truncates toward zero


def lens_table(R=LENS_R, d=LENS_D):
    n = _ftol(math.sqrt(R * R - (R - d) * (R - d)))
    k = [1.0] + [r / (R * math.sin(math.atan(r / (R - d)))) for r in range(1, n)]
    t = np.empty((n, n, 2), np.int32)
    for i in range(n):
        for j in range(n):
            r = _ftol(math.sqrt(i * i + j * j) + 0.5)
            t[i, j] = (_ftol(i * k[r] + 0.5), _ftol(j * k[r] + 0.5)) if r < n else (i, j)
    return t


TABLE = lens_table()
LENS_SIZE = TABLE.shape[0]


def apply_lens(pix, x, y, table=TABLE):
    """Apply the lens centred at (x, y) to an (h, w, c) array, in place."""
    h, w = pix.shape[:2]
    n = table.shape[0]
    for i in range(n - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            si, sj = table[i, j]
            for a, b, sa, sb in ((i, j, si, sj), (i, -j, si, -sj), (-i, j, -si, sj), (-i, -j, -si, -sj)):
                tx, ty, fx, fy = x + a, y + b, x + sa, y + sb
                if 0 <= tx < w and 0 <= ty < h and 0 <= fx < w and 0 <= fy < h:
                    pix[ty, tx] = pix[fy, fx]
    return pix
