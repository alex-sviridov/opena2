"""Write a contact sheet of the first sprite of ~100 files per sprite type.

    python tools/sprite_contact.py [INSTALL_DIR] [-o out/contact] [-n 100]

Writes out/contact/256.png, b.256.png, 16a.png and 16.png. Files are picked
evenly across the sorted list, so every folder is represented. Palette: the
embedded one, else the first .pal in the sprite's folder (unit palettes),
else human.pal[0] for humans, else grey. b.256 overlays use their main
sprite's palette. Transparent pixels show a checkerboard. The output contains
game data, so it belongs in the gitignored out/.
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

from allods2 import graphics as gfx
from allods2.common import OUT, as_fs
from allods2.units import HUMAN_PAL

TYPES = {"256": "256", "b.256": "smooth", "16a": "16a", "16": "16"}


def files_of(fs, label):
    return [p for p in fs.files("graphics")
            if p.lower().endswith("." + label.split(".")[-1])
            and gfx.guess_kind(p) == TYPES[label] and len(fs.read(p)) > 4]


def pick(paths, n):
    if len(paths) <= n:
        return paths
    return [paths[round(i * (len(paths) - 1) / (n - 1))] for i in range(n)]


def folder_palette(path, fs):
    d = path.rpartition("/")[0]
    pals = sorted(n for n in fs.listdir(d) if n.lower().endswith(".pal"))
    if pals:
        return gfx.load_palettes(d + "/" + pals[0], fs)[0].rgb
    if "humans" in path and fs.isfile(HUMAN_PAL):
        return gfx.load_human_palettes(HUMAN_PAL, fs)[0]
    return None


def palette_for(path, sf, fs):
    if sf.kind == "smooth":
        main = path[:-len("b.256")] + ".256"
        if fs.isfile(main):
            msf = gfx.SpriteFile.load(main, fs)
            if msf.palette is not None:
                return msf.palette
            return folder_palette(main, fs)
    if sf.palette is not None:
        return sf.palette
    return folder_palette(path, fs)


def sheet(entries, cols=10, cell=128, label_h=26):
    font = ImageFont.load_default(10)
    rows = -(-len(entries) // cols)
    img = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    for i, (label, rgba) in enumerate(entries):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        tile = Image.fromarray(gfx.over_checker(rgba)) if rgba.size else None
        if tile is not None:
            tile.thumbnail((cell - 4, cell - 4))
            img.paste(tile, (x + (cell - tile.width) // 2, y + (cell - tile.height) // 2))
        for j, line in enumerate((label[-40:-20], label[-20:]) if len(label) > 20 else ("", label)):
            draw.text((x + 2, y + cell + j * 12), line, fill=(230, 230, 230), font=font)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("install", nargs="?")
    ap.add_argument("-o", "--out", default=os.path.join(OUT, "contact"))
    ap.add_argument("-n", type=int, default=100)
    a = ap.parse_args(argv)
    fs = as_fs(a.install)
    os.makedirs(a.out, exist_ok=True)
    for label in TYPES:
        all_files = files_of(fs, label)
        entries = []
        for path in pick(all_files, a.n):
            rel = path.partition("/")[2]
            sf = gfx.SpriteFile.load(path, fs)
            if not len(sf):
                continue
            entries.append(("%s (%d)" % (rel, len(sf)), sf.to_rgba(0, palette_for(path, sf, fs))))
        out = os.path.join(a.out, label + ".png")
        sheet(entries).save(out)
        print("%-6s %4d of %4d files -> %s" % (label, len(entries), len(all_files), out))


if __name__ == "__main__":
    main()
