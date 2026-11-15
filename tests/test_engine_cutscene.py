"""Cutscene frame source (docs/engine/cutscenes.md 3): the fade engine (shell.md 6) on synthetic palettes, the code -> files mapping and one real run."""

import numpy as np

from engine import cutscene as C

from helpers import GFS, needs

RAW = np.tile(np.array([[200, 100, 50]], np.uint8), (256, 1))


def shown(fades, frames):
    return [int(fades.palette(f, RAW, f == 0)[0, 0]) for f in frames]


def test_fade_in_factors_on_frames_0_to_4():
    f = C.Fades([C.Fading(0, 5, 0.0, 1.0)])
    assert shown(f, range(7)) == [40, 80, 120, 160, 200, 200, 200]          # 0.2 .. 1.0, then the full palette stays


def test_fade_out_leaves_the_black_palette():
    f = C.Fades([C.Fading(161, 166, 1.0, 0.0)])
    out = [int(f.palette(i, RAW, i == 0)[0, 0]) for i in range(160, 168)]
    assert out == [200, 160, 120, 80, 40, 0, 0, 0]                      # 0.8 .. 0.0 on 161-165; 166 keeps it


def test_no_fadings_is_the_raw_palette():
    f = C.Fades([])
    assert shown(f, range(3)) == [200, 200, 200]


class FakeFS:
    def __init__(self, files):
        self.files = files

    def exists(self, p):
        return p in self.files

    def read(self, p):
        return self.files[p]


def test_video_paths_walk_nn_while_the_file_exists():
    fs = FakeFS({C.CUTPATHS: b"intro\r\nteleport\r\n", "video/teleport/01.smk": b"", "video/teleport/02.smk": b"", "video/teleport/04.smk": b""})
    assert C.video_paths(fs, 1) == ["video/teleport/01.smk", "video/teleport/02.smk"]
    assert C.video_paths(fs, 0) == [] and C.video_paths(fs, 9) == [] and C.video_paths(fs, -1) == []


@needs("main", "text", "cutpaths.txt")
def test_install_codes():
    names = C.cut_names(GFS)
    assert names == ["intro", "teleport", "stars", "crown", "knights", "druids"]
    assert [len(C.video_paths(GFS, c)) for c in range(6)] == [1] * 6
    assert len(C.cut_titles(GFS)) == 6


@needs("video", "logos", "nival.smk")
def test_nival_logo_fades_out_on_its_last_frames():
    run = C.Run(GFS, "video/logos/nival.smk")
    assert run.fades.fadings == [C.Fading(159, 164, 1.0, 0.0)]
    last = None
    while True:
        f = run.step()
        if f is None:
            break
        last = f
    assert last.index == 164 and int(last.palette.max()) == 0
