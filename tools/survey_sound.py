"""Survey every audio candidate of the install: RIFF chunk layout, wFormatTag,
rate / channels / bits, size ranges per folder, byte accounting.

    python tools/survey_sound.py [INSTALL_DIR]
"""

import collections
import os
import struct
import sys

from allods2.common import as_fs

AUDIO_EXT = (".wav", ".mp3", ".ogg", ".mid", ".midi", ".mod", ".xm", ".s3m", ".it", ".snd", ".voc", ".raw", ".mus")


def chunks(b):
    """[(id, offset, size)] of a RIFF/WAVE file; raises ValueError if malformed."""
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("not RIFF/WAVE")
    riff = struct.unpack_from("<I", b, 4)[0]
    out, i = [], 12
    while i + 8 <= len(b):
        t, s = struct.unpack_from("<4sI", b, i)
        out.append((t, i + 8, s))
        i += 8 + s + (s & 1)
    return riff, out, i


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    fmts = collections.Counter()
    layouts = collections.Counter()
    sizes = collections.defaultdict(list)
    exts = collections.Counter()
    problems = []
    for p in fs.files():
        ext = os.path.splitext(p)[1].lower()
        if ext in AUDIO_EXT:
            exts[ext] += 1
        if ext != ".wav":
            continue
        b = bytes(fs.read(p))
        folder = p.split("/")[0]
        try:
            riff, ch, end = chunks(b)
        except ValueError as e:
            problems.append("%s: %s" % (p, e))
            continue
        layouts[tuple(c[0].decode("latin1") for c in ch)] += 1
        if riff + 8 != len(b):
            problems.append("%s: RIFF size %d + 8 != file %d" % (p, riff, len(b)))
        if end != len(b):
            problems.append("%s: chunks end at %d, file %d" % (p, end, len(b)))
        fmt = next(c for c in ch if c[0] == b"fmt ")
        f = struct.unpack_from("<HHIIHH", b, fmt[1])
        extra = fmt[2] - 16
        fmts[(folder, f[0], f[1], f[2], f[5], fmt[2])] += 1
        sizes[folder].append(len(b))
    print("audio extensions:", dict(exts))
    print("%-8s %4s %3s %6s %4s %5s %6s" % ("folder", "tag", "ch", "rate", "bits", "fmtsz", "files"))
    for k, v in sorted(fmts.items()):
        print("%-8s %4d %3d %6d %4d %5d %6d" % (k + (v,)))
    print("chunk layouts:")
    for k, v in layouts.most_common():
        print("  %5d  %s" % (v, " ".join(k)))
    for f, s in sorted(sizes.items()):
        print("%-8s n=%d bytes min=%d max=%d total=%.1f MB" % (f, len(s), min(s), max(s), sum(s) / 1e6))
    for p in problems:
        print("PROBLEM", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
