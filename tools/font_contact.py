"""Write out/contact/fonts.png: each font's glyph grid and sample lines.

    python tools/font_contact.py [INSTALL_DIR] [-o out/contact/fonts.png]

Rows per font: the 224 (or 64) glyph cells, 32 per row, then sample text
laid out with the game's rules (`.dat` advances, spacing 2, '~' underline).
.16 fonts use the 17i grey ramp
and the gold code ramp 0x620d90; font4 uses its embedded palette.
Transparent areas show a checkerboard. Output contains game data: out/ only.
"""

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from allods2 import graphics as gfx
from allods2.common import OUT, as_fs

SAMPLES = [b"The quick brown fox jumps over the lazy dog 0123456789",
           b"~Load game  ~~tilde~~  ~hotkey",
           b"Gold: 12,345  HP 100/100  [x] {y} (z) !?"]
SCALE = 2


def glyph_grid(font, colours):
    cw, ch = font.cell_width() + 2, font.cell_height() + 2
    n = len(font.sprites)
    cols = 32
    img = np.zeros((-(-n // cols) * ch, cols * cw, 4), np.uint8)
    for g in range(n):
        if font.is16a:
            pal = font.sprites.palette
        else:
            pal = np.zeros((256, 3), np.uint8)
            pal[:16] = gfx.unpack16(colours)
        rgba = gfx.to_rgba(font.sprites.decode(g), font.sprites.kind, pal)
        y, x = (g // cols) * ch, (g % cols) * cw
        img[y:y + rgba.shape[0], x:x + rgba.shape[1]] = rgba
        w = font.widths[g]
        if w < rgba.shape[1]:                  # mark the .dat width: one red pixel row
            img[y + rgba.shape[0], x:x + w + 1] = (255, 0, 0, 255)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("install", nargs="?")
    ap.add_argument("-o", "--out", default=os.path.join(OUT, "contact", "fonts.png"))
    a = ap.parse_args(argv)
    ramps = gfx.code_ramps16()
    grey, gold = gfx.pack16(ramps[0x61fa80]), gfx.pack16(ramps[0x620d90])
    label_font = ImageFont.load_default(11)
    blocks = []
    fs = as_fs(a.install)
    for dat in fs.glob("graphics/font*/font*.dat"):
        font = gfx.Font.load(dat[:-4], fs)
        name = dat.rpartition("/")[2][:-4]
        parts = [(name + " glyphs (red line = .dat width)", glyph_grid(font, gold))]
        for i, s in enumerate(SAMPLES):
            text = s.upper() if len(font.sprites) <= 64 else s
            parts.append(("%s sample %d" % (name, i + 1),
                          font.render(text, colours=grey if i != 1 else gold)))
        blocks += parts
    width = max(p.shape[1] for _, p in blocks) * SCALE + 20
    height = sum(p.shape[0] * SCALE + 18 for _, p in blocks) + 10
    sheet = Image.new("RGB", (width, height), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    y = 4
    for label, rgba in blocks:
        draw.text((6, y), label, fill=(230, 230, 230), font=label_font)
        y += 14
        tile = Image.fromarray(gfx.over_checker(rgba)).resize(
            (rgba.shape[1] * SCALE, rgba.shape[0] * SCALE), Image.NEAREST)
        sheet.paste(tile, (10, y))
        y += tile.height + 4
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sheet.save(a.out)
    print("%d blocks -> %s (%dx%d)" % (len(blocks), a.out, *sheet.size))


if __name__ == "__main__":
    main()
