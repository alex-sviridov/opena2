"""Find every palette in the install, parse it the way the game does, and
check the rules in docs/formats/palettes.md.

    python tools/validate_palettes.py [DATA_DIR]

Exit status 0 when every rule holds on every file.
"""

import collections
import glob
import os
import struct
import sys

import numpy as np

from allods2 import graphics as gfx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "samples", "Allods2_en_251005", "Allods2_en", "data")
EXTS = (".pal", ".256", ".16a", ".16", ".bmp")


def source_kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pal":
        return "human.pal" if os.path.basename(path).lower() == "human.pal" else ".pal"
    if ext == ".256" and path.lower().endswith("b.256"):
        return "*b.256"
    return ext


def find_palettes(data_dir):
    """Yield (relative path, kind, [Palette]) for every file that has palettes."""
    for path in sorted(glob.glob(os.path.join(data_dir, "**", "*"), recursive=True)):
        if not path.lower().endswith(EXTS) or not os.path.isfile(path):
            continue
        pals = gfx.load_palettes(path)
        if pals:
            yield os.path.relpath(path, data_dir), source_kind(path), pals


def check_file(path, kind, pals):
    """Return the list of rule violations for one file."""
    with open(path, "rb") as f:
        data = f.read()
    bad = []
    if kind == "human.pal":
        if len(data) != gfx.palette.HUMAN_PALETTES * gfx.palette.PALETTE_BYTES:
            bad.append("human.pal is %d bytes, not 0x4000" % len(data))
        if b"".join(p.to_bytes() for p in pals) != data:
            bad.append("round trip differs")
    elif kind == ".pal":
        off, hsize = struct.unpack_from("<II", data, 10)
        bpp, = struct.unpack_from("<H", data, 28)
        if data[:2] != b"BM" or hsize != 40 or bpp != 8 or off != 0x36 + 0x400:
            bad.append("not an 8-bit BMP with its colour table at 0x36")
        if pals[0].to_bytes() != data[0x36:0x436]:
            bad.append("round trip differs")
    elif kind in (".256", "*b.256", ".16a"):
        if pals[0].to_bytes() != data[:0x400]:
            bad.append("round trip differs")
    for p in pals:
        if p.rgb.shape != (256, 3) or p.rgb.dtype != np.uint8:
            bad.append("bad palette shape")
    if kind in (".pal", "human.pal", ".bmp") and any(p.reserved.any() for p in pals):
        bad.append("non-zero reserved byte")
    return bad


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data_dir = argv[0] if argv else DEFAULT_DATA
    files = collections.Counter()
    count = collections.Counter()
    distinct = collections.defaultdict(set)
    zero = collections.Counter()
    reserved = collections.Counter()
    problems = []
    for rel, kind, pals in find_palettes(data_dir):
        files[kind] += 1
        for p in pals:
            count[kind] += 1
            distinct[kind].add(p.rgb.tobytes())
            zero[kind] += not p.rgb.any()
            reserved[kind] += bool(p.reserved.any())
        problems += ["%s: %s" % (rel, b) for b in check_file(os.path.join(data_dir, rel), kind, pals)]
    print("%-10s %6s %9s %9s %9s %9s" % ("source", "files", "palettes", "distinct", "all-zero", "rsvd!=0"))
    for kind in sorted(files):
        print("%-10s %6d %9d %9d %9d %9d" % (kind, files[kind], count[kind], len(distinct[kind]),
                                            zero[kind], reserved[kind]))
    every = set().union(*distinct.values()) if distinct else set()
    print("total      %6d %9d %9d" % (sum(files.values()), sum(count.values()), len(every)))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
