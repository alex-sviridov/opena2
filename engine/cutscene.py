"""Cutscenes (m1, docs/engine/cutscenes.md): the chapter videos and the start-up chain as pure data + a frame source.  No pygame, no clock:
the shell's `Cutscene` screen asks for frames and decides what to show.

`video_paths(fs, code)`: `video\\<cutpaths.txt line code>\\NN.smk` for NN = 1, 2, ... while the file exists (CONFIRMED `0x48f919`, shell.md 6).
`Fades`: the `.reg` fade records and the exe's per-frame palette scaling (CONFIRMED `0x4c38d1` / `0x4c4561`, shell.md 6).
`Run`: one video, `step()` yields `CutFrame`s (pixels, the faded palette, the frame's audio) in order."""

from dataclasses import dataclass

import numpy as np

from allods2 import reg as regmod
from allods2.formats import smacker
from allods2.text import decode_text

CUTPATHS = "main/text/cutpaths.txt"
TITLES = "main/text/cutscene.txt"
LOGOS = ("video/logos/publisher.smk", "video/logos/nival.smk")       # the start-up chain: the intro (code 0) follows through `video_paths`
INTRO = 0


def cut_names(fs):
    """The directory names of the codes (`cutpaths.txt`, one per line)."""
    try:
        return [ln.strip() for ln in decode_text(fs.read(CUTPATHS)).splitlines() if ln.strip()]
    except (KeyError, OSError):
        return []


def cut_titles(fs):
    """The titles of the Cut Scenes list (`cutscene.txt`, one per code)."""
    try:
        return [ln.strip() for ln in decode_text(fs.read(TITLES)).splitlines() if ln.strip()]
    except (KeyError, OSError):
        return []


def video_paths(fs, code):
    """The files of chapter video `code`, in play order (NN = 1, 2, ... while the file exists)."""
    names = cut_names(fs)
    if not 0 <= code < len(names):
        return []
    out, n = [], 1
    while fs.exists("video/%s/%02d.smk" % (names[code], n)):
        out.append("video/%s/%02d.smk" % (names[code], n))
        n += 1
    return out


@dataclass(frozen=True)
class Fading:
    start: int
    end: int
    fade0: float
    fade1: float


def load_fadings(fs, path):
    """The `Fading<n>` records of the `.reg` next to `path` (`video/x/01.smk` -> `video/x/01.reg`); none when the file is missing."""
    rp = path[:-4] + ".reg"
    if not fs.exists(rp):
        return []
    r = regmod.load_reg(rp, fs)
    n = int(r.get("Common/nFadings", 0) or 0)
    out = []
    for i in range(1, n + 1):
        sec = "Fading%d/" % i
        out.append(Fading(int(r[sec + "startframe"]), int(r[sec + "endframe"]), float(r[sec + "startfade"]), float(r[sec + "endfade"])))
    return out


class Fades:
    """The fade engine of `0x4c399a`: per frame, a record whose `start` equals the frame starts (`fade = fade0`, `step = (fade1 - fade0) / len`,
    `len = end - start`); an active record then does `fade += step` (float32), `len -= 1` and the palette is `trunc(byte * fade)`; at 0 it stops and
    the last palette stays (nothing sets the raw one again until the Smacker palette changes)."""

    def __init__(self, fadings):
        self.fadings = list(fadings)
        self.active = False
        self.fade = np.float32(1.0)
        self.step = np.float32(0.0)
        self.left = 0
        self.held = None            # the palette a finished fade leaves on screen (None = the raw one)

    def palette(self, frame, raw, changed):
        """The palette to show on `frame` (0-based) when the Smacker palette is `raw` ((256, 3) uint8) and `changed` says whether this frame carried a new one."""
        for f in self.fadings:
            if f.start == frame:
                ln = f.end - f.start
                self.fade = np.float32(f.fade0)
                self.step = np.float32((np.float32(f.fade1) - np.float32(f.fade0)) / np.float32(ln)) if ln else np.float32(0.0)
                self.left = ln
                self.active = True
                self.held = None
        if self.active:
            self.fade = np.float32(self.fade + self.step)
            self.left -= 1
            out = (raw.astype(np.float32) * self.fade).astype(np.uint8)         # trunc toward zero; fade stays in 0..1
            if self.left <= 0:
                self.active = False
                self.held = out
            return out
        if self.held is not None and not changed:
            return self.held
        self.held = None
        return raw


@dataclass
class CutFrame:
    index: int
    pixels: np.ndarray                  # (h, w) uint8 palette indices
    palette: np.ndarray                 # (256, 3) uint8, after the fade
    audio: np.ndarray = None            # (n, 2) int16 at `Run.sample_rate`


class Run:
    """One video being played: `step()` decodes the next frame (the delta frames need every one in order), None at the end."""

    def __init__(self, fs, path):
        self.path = path
        self.video = smacker.load(path, fs)
        self.fades = Fades(load_fadings(fs, path))
        self._it = self.video.decode()
        self._pal = None
        self.frame = 0

    @property
    def width(self):
        return self.video.width

    @property
    def height(self):
        return self.video.height

    @property
    def frame_ms(self):
        return self.video.frame_ms

    @property
    def sample_rate(self):
        return self.video.sample_rate

    @property
    def frames(self):
        return self.video.frames

    def step(self):
        f = next(self._it, None)
        if f is None:
            return None
        changed = self._pal is None or not np.array_equal(f.palette, self._pal)
        self._pal = f.palette
        pal = self.fades.palette(f.index, f.palette, changed)
        self.frame = f.index + 1
        return CutFrame(f.index, f.pixels, pal, f.audio)
