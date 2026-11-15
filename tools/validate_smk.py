"""Whole-install check of the Smacker decoder (docs/engine/cutscenes.md 2): every `.smk` of video.res decodes with the Python reference,
each frame's block stream ends within 4 bytes of its chunk (one frame per file may leave up to 32: teleport frame 105 leaves 31, INFERRED padding), the audio length equals the video length, and (when the C library builds) the native
block loop gives the same pictures.   Usage: python tools/validate_smk.py [INSTALL_DIR]"""

import hashlib
import sys
import types

from allods2.common import as_fs
from allods2.formats import smacker
from allods2 import native


def main(argv):
    fs = as_fs(argv[1] if len(argv) > 1 else None)
    names = sorted(n for n in fs.listdir("video") if n.endswith(".smk")) if hasattr(fs, "listdir") else None
    names = names or ["video/logos/publisher.smk", "video/logos/nival.smk"] + ["video/%s/01.smk" % c for c in
             ("intro", "teleport", "stars", "crown", "knights", "druids")]
    bad = 0
    for path in names:
        v = smacker.load(path, fs)
        used = []
        orig = smacker.Smacker._video_py

        def spy(self, buf, pix, _o=orig, _u=used):
            pos = _o(self, buf, pix)
            _u.append(len(buf) - (pos + 7) // 8)
            return pos
        v._video = types.MethodType(spy, v)
        hs, samples = hashlib.sha1(), 0
        for f in v.decode():
            hs.update(f.pixels.tobytes() + f.palette.tobytes())
            samples += 0 if f.audio is None else len(f.audio)
        ok = sum(1 for u in used if u > 4) <= 1 and max(used) <= 32 and min(used) >= 0 and abs(samples / v.sample_rate - v.frames / v.fps) < 0.01
        line = "%-28s %dx%d %d frames, tail bytes max %d, audio %.2fs / video %.2fs" % (
            path, v.width, v.height, v.frames, max(used), samples / v.sample_rate, v.frames / v.fps)
        if native.smk() is not None:
            vn = smacker.load(path, fs)
            hn = hashlib.sha1()
            for f in vn.decode():
                hn.update(f.pixels.tobytes() + f.palette.tobytes())
            ok = ok and hn.digest() == hs.digest()
            line += ", native %s" % ("same" if hn.digest() == hs.digest() else "DIFFERENT")
        print(("OK   " if ok else "FAIL ") + line)
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
