"""Survey the graphics files in the install: per-extension statistics and
hex dumps of small and large samples.

    python tools/gfx_survey.py [DATA_DIR] [-o out/gfx]

Writes OUT/stats.txt and OUT/dumps/<ext>/<name>.txt. Each dump holds the
first 128 and last 32 bytes, since sprite containers keep their frame count
in a trailer. Dumps contain game bytes, so OUT must stay in the gitignored
out/.
"""

import argparse
import collections
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "samples", "Allods2_en_251005", "Allods2_en", "data")

# Graphics extensions; "b.256" separates smoothing overlays from plain .256.
KINDS = (".256", "b.256", ".16a", ".16", ".pal", ".bmp", ".png", ".dat")


def kind_of(path):
    """Extension class; "b.256" is a smoothing overlay: x b.256 next to x.256."""
    low = path.lower()
    ext = os.path.splitext(low)[1]
    if low.endswith("b.256") and os.path.exists(path[:-5] + path[-4:]):
        return "b.256"
    if ext == ".dat" and "graphics" not in low.replace("\\", "/").split("/"):
        return None
    return ext if ext in KINDS else None


def hexdump(data, base=0):
    out = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join("%02x" % c for c in chunk)
        asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
        out.append("%08x  %-47s  %s" % (base + i, hx, asc))
    return "\n".join(out)


def collect(data_dir):
    files = collections.defaultdict(list)
    for dp, _, names in os.walk(data_dir):
        for n in names:
            p = os.path.join(dp, n)
            k = kind_of(p)
            if k:
                files[k].append((os.path.getsize(p), os.path.relpath(p, data_dir)))
    return files


def folder_of(rel):
    parts = rel.replace("\\", "/").split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", nargs="?", default=DEFAULT_DATA)
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "out", "gfx"))
    a = ap.parse_args(argv)
    files = collect(a.data)
    lines = []
    for k in KINDS:
        entries = sorted(files.get(k, []))
        if not entries:
            continue
        sizes = [s for s, _ in entries]
        folders = collections.Counter(folder_of(r) for _, r in entries)
        lines.append("%-6s files=%d size min=%d median=%d max=%d total=%d" % (
            k, len(entries), sizes[0], int(statistics.median(sizes)), sizes[-1], sum(sizes)))
        for f, n in folders.most_common():
            lines.append("         %5d  %s" % (n, f))
        nonempty = [e for e in entries if e[0] > 0]
        picks = nonempty[:5] + nonempty[-5:] if len(nonempty) > 10 else nonempty
        ddir = os.path.join(a.out, "dumps", k.lstrip("."))
        os.makedirs(ddir, exist_ok=True)
        for size, rel in picks:
            with open(os.path.join(a.data, rel), "rb") as fh:
                data = fh.read()
            name = rel.replace("\\", "/").replace("/", "__") + ".txt"
            with open(os.path.join(ddir, name), "w") as out:
                out.write("%s  (%d bytes)\n\nfirst 128 bytes:\n%s\n" % (rel, size, hexdump(data[:128])))
                if size > 128:
                    tail = data[-32:]
                    out.write("\nlast 32 bytes:\n%s\n" % hexdump(tail, size - len(tail)))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "stats.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
