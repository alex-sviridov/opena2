"""Write a contact sheet of every distinct palette the game uses.

    python tools/palette_contact.py [DATA_DIR] [-o out/contact/palettes.png]

Each palette is a 16x16 swatch (entry i at row i // 16, column i % 16),
labelled with its source file and how many other files carry the same
colours. Palettes built in code (FUN_00463d30) come first. The output
contains game data, so it belongs in the gitignored out/.
"""

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from allods2 import graphics as gfx
from allods2.common import DATA, OUT

ORDER = ["code", "human.pal", ".pal", ".bmp", ".256", "*b.256", ".16a"]


def collect(data_dir):
    """[(kind, label, rgb)] with identical colours merged per first source."""
    entries = [("code", p.name, p.rgb) for p in gfx.code_palettes()]
    for rel, kind, pals in gfx.find_palettes(data_dir):
        rel = rel.replace(os.sep, "/").removeprefix("graphics/")
        for i, p in enumerate(pals):
            entries.append((kind, rel if len(pals) == 1 else "%s[%d]" % (rel, i), p.rgb))
    entries.sort(key=lambda e: ORDER.index(e[0]))
    seen = {}
    out = []
    for kind, label, rgb in entries:
        key = rgb.tobytes()
        if key in seen:
            seen[key][1] += 1
            continue
        seen[key] = item = [kind, 0, label, rgb]
        out.append(item)
    return out


def wrap(text, width):
    return [text[i:i + width] for i in range(0, len(text), width)] or [""]


def sheet(items, ramps, cols=24, cell=4):
    font = ImageFont.load_default(10)
    sw = 16 * cell
    tw, th = sw + 170, sw + 8
    n = len(items) + 1
    rows = -(-n // cols)
    img = Image.new("RGB", (cols * tw, rows * th), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    tiles = [(f"{k} {lab}" + (f" (+{dup} same)" if dup else ""),
              np.repeat(np.repeat(rgb.reshape(16, 16, 3), cell, 0), cell, 1))
             for k, dup, lab, rgb in items]
    ramp = np.stack(list(ramps.values()))                     # (14, 16, 3)
    ramp_img = np.zeros((16 * cell, 16 * cell, 3), np.uint8)
    ramp_img[:len(ramp) * cell] = np.repeat(np.repeat(ramp, cell, 0), cell, 1)
    tiles.insert(len(gfx.code_palettes()),
                 ("code 16-colour ramps (rows: " + " ".join("%x" % a for a in ramps) + ")", ramp_img))
    for i, (label, sw_img) in enumerate(tiles):
        x, y = (i % cols) * tw + 4, (i // cols) * th + 4
        img.paste(Image.fromarray(sw_img), (x, y))
        for j, line in enumerate(wrap(label, 30)[:5]):
            draw.text((x + sw + 4, y + j * 12), line, fill=(230, 230, 230), font=font)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", nargs="?", default=DATA)
    ap.add_argument("-o", "--out", default=os.path.join(OUT, "contact", "palettes.png"))
    a = ap.parse_args(argv)
    items = collect(a.data)
    img = sheet(items, gfx.code_ramps16())
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    img.save(a.out)
    print("%d distinct palettes + code ramps -> %s (%dx%d)" % (len(items), a.out, *img.size))


if __name__ == "__main__":
    main()
