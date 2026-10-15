"""Write a contact sheet of the first sprite of ~100 files per sprite type.

    python tools/sprite_contact.py [DATA_DIR] [-o out/contact] [-n 100]

Writes out/contact/256.png, b.256.png, 16a.png and 16.png. Files are picked
evenly across the sorted list, so every folder is represented. Palette: the
embedded one, else the first .pal in the sprite's folder (unit palettes),
else human.pal[0] for humans, else grey. b.256 overlays use their main
sprite's palette. Transparent pixels show a checkerboard. The output contains
game data, so it belongs in the gitignored out/.
"""

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from allods2 import graphics as gfx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_sprites import DEFAULT_DATA, ROOT  # noqa: E402

TYPES = {"256": "256", "b.256": "smooth", "16a": "16a", "16": "16"}


def files_of(data_dir, label):
    paths = sorted(glob.glob(os.path.join(data_dir, "**", "*"), recursive=True))
    return [p for p in paths if os.path.isfile(p) and os.path.getsize(p) > 4
            and gfx.guess_kind(p) == TYPES[label]
            and os.path.splitext(p)[1].lower() == "." + label.split(".")[-1]]


def pick(paths, n):
    if len(paths) <= n:
        return paths
    return [paths[round(i * (len(paths) - 1) / (n - 1))] for i in range(n)]


def folder_palette(path, data_dir):
    d = os.path.dirname(path)
    pals = sorted(glob.glob(os.path.join(d, "*.pal")))
    if pals:
        return gfx.load_palettes(pals[0])[0].rgb
    human = os.path.join(data_dir, "graphics", "units", "humans", "human.pal")
    if "humans" in path and os.path.exists(human):
        return gfx.load_human_palettes(human)[0]
    return None


def palette_for(path, sf, data_dir):
    if sf.kind == "smooth":
        main = path[:-len("b.256")] + ".256"
        if os.path.exists(main):
            msf = gfx.SpriteFile.load(main)
            if msf.palette is not None:
                return msf.palette
            return folder_palette(main, data_dir)
    if sf.palette is not None:
        return sf.palette
    return folder_palette(path, data_dir)


def checker(h, w, size=4):
    yy, xx = np.indices((h, w))
    on = ((yy // size + xx // size) % 2).astype(bool)
    out = np.empty((h, w, 3), np.uint8)
    out[on] = (200, 200, 200)
    out[~on] = (150, 150, 150)
    return out


def over_checker(rgba):
    h, w = rgba.shape[:2]
    a = rgba[..., 3:4].astype(np.uint16)
    bg = checker(h, w).astype(np.uint16)
    return ((rgba[..., :3] * a + bg * (255 - a)) // 255).astype(np.uint8)


def sheet(entries, cols=10, cell=128, label_h=26):
    font = ImageFont.load_default(10)
    rows = -(-len(entries) // cols)
    img = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    for i, (label, rgba) in enumerate(entries):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        tile = Image.fromarray(over_checker(rgba)) if rgba.size else None
        if tile is not None:
            tile.thumbnail((cell - 4, cell - 4))
            img.paste(tile, (x + (cell - tile.width) // 2, y + (cell - tile.height) // 2))
        for j, line in enumerate((label[-40:-20], label[-20:]) if len(label) > 20 else ("", label)):
            draw.text((x + 2, y + cell + j * 12), line, fill=(230, 230, 230), font=font)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", nargs="?", default=DEFAULT_DATA)
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "out", "contact"))
    ap.add_argument("-n", type=int, default=100)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    for label in TYPES:
        all_files = files_of(a.data, label)
        entries = []
        for path in pick(all_files, a.n):
            sf = gfx.SpriteFile.load(path)
            if not len(sf):
                continue
            rel = os.path.relpath(path, os.path.join(a.data, "graphics")).replace(os.sep, "/")
            entries.append(("%s (%d)" % (rel, len(sf)), sf.to_rgba(0, palette_for(path, sf, a.data))))
        out = os.path.join(a.out, label + ".png")
        sheet(entries).save(out)
        print("%-6s %4d of %4d files -> %s" % (label, len(entries), len(all_files), out))


if __name__ == "__main__":
    main()
