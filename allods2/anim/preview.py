"""Preview images of animation sets, to check animations by eye.

Animated GIFs (one per action and facing, at the game's tick period, or in
real milliseconds for ms-clocked sets such as cursors) and a still grid
(rows = actions, columns = facings).  Frames are drawn with the set's own
draw (the game's blit modes, mirrored in place) on a checkerboard; a cross
marks the anchor.  While a unit walks, the checkerboard scrolls by its real
displacement (8 map units per pixel), so feet that stay planted move with
the ground.  Output contains game data: write it to out/ or outside the repo.
"""

import os

from PIL import Image, ImageDraw, ImageFont

from .. import units as U
from ..graphics import Canvas, checker
from .base import DEFAULT_SPEED, period_ms

MARK = {None: (255, 0, 255), "impact": (255, 40, 40), "release": (255, 220, 0)}
MARGIN = 8


def bounds(aset, clips=None):
    """Box (w, h) and anchor (x, y) holding every previewed frame."""
    x0 = y0 = x1 = y1 = 0
    if clips is None:
        clips = [aset.preview_clip(a, d) for a in aset.actions for d in aset.preview_facings]
    for clip in clips:
        for ref, _ in clip:
            e = aset.extent(ref)
            x0, y0, x1, y1 = min(x0, e[0]), min(y0, e[1]), max(x1, e[2]), max(y1, e[3])
    return (x1 - x0 + 2 * MARGIN, y1 - y0 + 2 * MARGIN), (MARGIN - x0, MARGIN - y0)


def render(aset, ref, box, anchor, shift=(0, 0), mark=True):
    """RGB array of one frame on the checkerboard, anchor cross on top.
    shift: ground displacement in pixels (the checkerboard scrolls with it)."""
    w, h = box
    cv = Canvas(w, h)
    cv.pix[...] = checker(h, w, ox=shift[0], oy=shift[1])
    aset.draw(cv, ref, anchor[0], anchor[1])
    if mark:
        colour = MARK.get(ref.events[0] if ref.events else None, MARK[None])
        x, y = anchor
        cv.pix[y, max(x - 3, 0):x + 4] = colour
        cv.pix[max(y - 3, 0):y + 4, x] = colour
    return cv.pix


def durations(n, speed=DEFAULT_SPEED, step_ms=None):
    """GIF delays (10 ms steps) whose running sum tracks n steps of
    `step_ms` (default: the game tick period)."""
    p = period_ms(speed) if step_ms is None else step_ms
    out, prev = [], 0
    for k in range(1, n + 1):
        t = round(k * p, -1)
        out.append(max(int(t - prev), 10))
        prev = t
    return out


def write_gifs(aset, dest, speed=DEFAULT_SPEED, mark=True):
    """dest/<action>_d<facing>.gif for every action and preview facing."""
    os.makedirs(dest, exist_ok=True)
    clips = {(a, d): aset.preview_clip(a, d) for a in aset.actions for d in aset.preview_facings}
    box, anchor = bounds(aset, clips.values())
    step = aset.preview_step_ms if aset.clock == "ms" else None
    paths = []
    for (name, d), clip in clips.items():
        frames = [Image.fromarray(render(aset, ref, box, anchor, shift, mark))
                  for ref, shift in clip]
        if not frames:
            continue
        suffix = "_d%02d" % d if len(aset.preview_facings) > 1 else ""
        path = os.path.join(dest, "%s%s.gif" % (name, suffix))
        frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                       duration=durations(len(frames), speed, step), disposal=1)
        paths.append(path)
    return paths


def grid(aset, mark=True):
    """Still grid: rows = actions, columns = preview facings, first frame."""
    facings = aset.preview_facings
    first = {(a, d): aset.preview_clip(a, d)[:1] for a in aset.actions for d in facings}
    box, anchor = bounds(aset, first.values())
    font = ImageFont.load_default(10)
    left, top = 64, 14
    img = Image.new("RGB", (left + len(facings) * box[0], top + len(aset.actions) * box[1]),
                    (40, 40, 40))
    dr = ImageDraw.Draw(img)
    flip = getattr(getattr(aset, "t", None), "Flip", 0)
    for c, d in enumerate(facings):
        if len(facings) > 1:
            mirrored = U.dir8(d, flip)[1] if aset.kind == "units" else False
            dr.text((left + c * box[0] + 2, 1), "d=%d%s" % (d, " m" if mirrored else ""),
                    fill=(230, 230, 230), font=font)
    for r, name in enumerate(aset.actions):
        y = top + r * box[1]
        dr.text((2, y + 2), name, fill=(230, 230, 230), font=font)
        for c, d in enumerate(facings):
            clip = first[(name, d)]
            if clip:
                img.paste(Image.fromarray(render(aset, clip[0][0], box, anchor, mark=mark)),
                          (left + c * box[0], y))
    return img
