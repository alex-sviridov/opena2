"""Preview images of an AnimationSet, to check animations by eye.

Animated GIFs (one per action and facing, at the game's tick period) and a
still grid (rows = actions, columns = facings).  Frames are drawn with
AnimationSet.draw (sprite + b.256 overlay, mirrored in place) on a
checkerboard; a cross marks the anchor (the object position).  While
walking, the checkerboard scrolls by the unit's real displacement (8 map
units per pixel), so feet that stay planted move with the ground.
Output contains game data: write it to out/ or outside the repo.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import anim as A
from . import units as U
from .graphics import Canvas

CHECK = 8                                   # checker square, pixels
CHECK_COLOURS = ((150, 150, 150), (110, 110, 110))
MARK = {None: (255, 0, 255), "impact": (255, 40, 40), "release": (255, 220, 0)}
MARGIN = 8
IDLE_TAIL = 6                               # ticks of idle shown after a once-action
CORPSE_TAIL = 8                             # ticks of corpse after dying


def checker(h, w, ox=0, oy=0):
    yy = (np.arange(h)[:, None] + oy) // CHECK
    xx = (np.arange(w)[None, :] + ox) // CHECK
    out = np.empty((h, w, 3), np.uint8)
    out[...] = CHECK_COLOURS[0]
    out[(xx + yy) % 2 == 1] = CHECK_COLOURS[1]
    return out


def bounds(aset):
    """Box (w, h) and anchor (x, y) holding every frame of the set."""
    x0 = y0 = x1 = y1 = 0
    for name in aset.actions:
        for d in A.FACINGS:
            for source, i, m in aset.frames(name, d):
                sf = aset.sprites(source)
                if i >= len(sf):
                    continue
                hx, hy = aset.hotspot(source, i)
                x0, y0 = min(x0, -hx), min(y0, -hy)
                x1, y1 = max(x1, sf[i].width - hx), max(y1, sf[i].height - hy)
    return (x1 - x0 + 2 * MARGIN, y1 - y0 + 2 * MARGIN), (MARGIN - x0, MARGIN - y0)


def render(aset, ref, box, anchor, shift=(0, 0), palettes=None, smoothing=True):
    """RGB array of one frame on the checkerboard, anchor cross on top.
    shift: ground displacement in pixels (the checkerboard scrolls with it)."""
    w, h = box
    cv = Canvas(w, h)
    cv.pix[...] = checker(h, w, *shift)
    pal = (palettes or {}).get(ref.source)
    aset.draw(cv, ref, anchor[0], anchor[1], palette=pal, smoothing=smoothing)
    colour = MARK[ref.events[0] if ref.events else None]
    x, y = anchor
    cv.pix[y, max(x - 3, 0):x + 4] = colour
    cv.pix[max(y - 3, 0):y + 4, x] = colour
    return cv.pix


def clip(aset, action, facing):
    """[(FrameRef, (dx, dy) shift in pixels)] for one pass of the action."""
    a = aset.actions[action]
    if action == "move":
        per_cell = A.CELL_UNITS * (1.41 if facing & 2 else 1)
        cells = max(1, -(-a.ticks * A.MOVE_UNITS_PER_ELEMENT // int(per_cell)))
        tpc = A.walk_ticks_per_cell(diagonal=bool(facing & 2))
        out = []
        for k in range(cells * tpc):
            _, (px, py) = A.walk_odometer(facing, k, tpc)
            out.append((aset.frame_at("move", facing, k, ticks_per_cell=tpc),
                        (px // A.UNITS_PER_PIXEL, py // A.UNITS_PER_PIXEL)))
        return out
    n = a.ticks
    if a.end == "idle":
        n += IDLE_TAIL
    elif action == "dying":
        n += CORPSE_TAIL
    return [(aset.frame_at(action, facing, k), (0, 0)) for k in range(n)]


def durations(n, speed=A.DEFAULT_SPEED):
    """GIF delays (10 ms steps) whose running sum tracks n game ticks."""
    p = A.period_ms(speed)
    out, prev = [], 0
    for k in range(1, n + 1):
        t = round(k * p, -1)
        out.append(max(int(t - prev), 10))
        prev = t
    return out


def write_gifs(aset, dest, speed=A.DEFAULT_SPEED, palettes=None, smoothing=True,
               facings=A.COMPASS):
    """dest/<action>_d<facing>.gif for every action and facing."""
    os.makedirs(dest, exist_ok=True)
    box, anchor = bounds(aset)
    paths = []
    for name in aset.actions:
        for d in facings:
            frames = [Image.fromarray(render(aset, ref, box, anchor, (sx, sy),
                                             palettes, smoothing))
                      for ref, (sx, sy) in clip(aset, name, d)]
            path = os.path.join(dest, "%s_d%02d.gif" % (name, d))
            frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                           duration=durations(len(frames), speed), disposal=1)
            paths.append(path)
    return paths


def grid(aset, palettes=None, smoothing=True, facings=A.COMPASS):
    """Still grid: rows = actions, columns = facings, first phase of each."""
    box, anchor = bounds(aset)
    font = ImageFont.load_default(10)
    left, top = 64, 14
    img = Image.new("RGB", (left + len(facings) * box[0], top + len(aset.actions) * box[1]),
                    (40, 40, 40))
    dr = ImageDraw.Draw(img)
    for c, d in enumerate(facings):
        mirrored = U.dir8(d, aset.t.Flip)[1]
        dr.text((left + c * box[0] + 2, 1), "d=%d%s" % (d, " m" if mirrored else ""),
                fill=(230, 230, 230), font=font)
    for r, (name, a) in enumerate(aset.actions.items()):
        y = top + r * box[1]
        dr.text((2, y + 2), name, fill=(230, 230, 230), font=font)
        for c, d in enumerate(facings):
            ref = aset.ref(name, d, a.phases[0])
            img.paste(Image.fromarray(render(aset, ref, box, anchor, palettes=palettes,
                                             smoothing=smoothing)),
                      (left + c * box[0], y))
    return img
