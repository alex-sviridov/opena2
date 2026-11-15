"""Smacker 2 decoder (docs/engine/cutscenes.md 2): synthetic bit streams (always run) and the install's eight videos (skipped without them)."""

import struct

import numpy as np
import pytest

from allods2.formats import smacker as S

from helpers import GFS, needs


def pack_bits(bits):
    out = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        out[i >> 3] |= b << (i & 7)
    return bytes(out)


def num(v, n):
    return [(v >> i) & 1 for i in range(n)]


def test_bits_are_lsb_first():
    b = S._Bits(bytes([0b00000101, 0xFF]))
    assert [b.bit() for _ in range(4)] == [1, 0, 1, 0]
    assert b.bits(8) == 0b11110000
    with pytest.raises(S.SmackerError):
        b.bits(8)


def test_small_tree_and_walk():
    # node(leaf 7, node(leaf 9, leaf 200)): 1, 0 + 7, 1, 0 + 9, 0 + 200
    bits = [1] + [0] + num(7, 8) + [1] + [0] + num(9, 8) + [0] + num(200, 8)
    tree = S._small_tree(S._Bits(pack_bits(bits)))
    assert tree == (7, (9, 200))
    assert S._walk(S._Bits(pack_bits([0])), tree) == 7
    assert S._walk(S._Bits(pack_bits([1, 0])), tree) == 9
    assert S._walk(S._Bits(pack_bits([1, 1])), tree) == 200


def test_palette_chunk_skip_copy_and_colours():
    old = np.zeros((256, 3), np.uint8)
    old[5] = (1, 2, 3)
    old[6] = (4, 5, 6)
    # colour (63, 32, 16), skip 2, copy 2 colours from index 5, skip the rest
    buf = bytes([63, 32, 16, 0x81, 0x40 | 1, 5, 0x80 | 0x7F, 0x80 | 0x7F])
    pal = S.Smacker._palette(buf, old)
    assert tuple(pal[0]) == (255, 0x82, 0x41)
    assert (pal[1:3] == old[1:3]).all()
    assert tuple(pal[3]) == (1, 2, 3) and tuple(pal[4]) == (4, 5, 6)


def test_palette_six_bit_table_ends_at_255():
    assert S.PAL6[0] == 0 and S.PAL6[16] == 0x41 and S.PAL6[63] == 255 and len(S.PAL6) == 64


def test_run_table():
    assert len(S.RUNS) == 64 and S.RUNS[0] == 1 and S.RUNS[58] == 59 and S.RUNS[63] == 2048


def test_bad_signature_refused():
    with pytest.raises(S.SmackerError):
        S.Smacker(b"SMK4" + bytes(200))


@needs("video", "intro", "01.smk")
def test_intro_header_and_first_frames():
    v = S.load("video/intro/01.smk", GFS)
    assert (v.width, v.height, v.frames) == (640, 360, 773)
    assert abs(v.fps - 15.0) < 0.01 and v.sample_rate == 22050 and v.audio_tracks() == [0]
    frames = []
    for f in v.decode():
        frames.append(f)
        if f.index >= 2:
            break
    f0 = frames[0]
    assert f0.pixels.shape == (360, 640) and f0.palette.shape == (256, 3)
    assert f0.audio.shape == (23520, 2) and frames[1].audio.shape[1] == 2     # the first frame carries a second of audio
    assert frames[2].pixels.max() > 0                                          # frame 0 is black: the intro fades in


@needs("video", "intro", "01.smk")
def test_native_and_python_block_loops_agree():
    from allods2 import native
    if native.smk() is None:
        pytest.skip("no C compiler")
    import types
    a = S.load("video/intro/01.smk", GFS)
    b = S.load("video/intro/01.smk", GFS)
    b._video = types.MethodType(S.Smacker._video_py, b)
    for fa, fb in zip(a.decode(), b.decode()):
        assert (fa.pixels == fb.pixels).all() and (fa.palette == fb.palette).all()
        if fa.index >= 40:
            break


@needs("video", "teleport", "01.smk")
@pytest.mark.parametrize("name", ["logos/nival", "teleport/01", "crown/01"])
def test_whole_video_decodes_and_audio_matches_length(name):
    v = S.load("video/%s.smk" % name, GFS)
    n = samples = 0
    for f in v.decode():
        n += 1
        samples += 0 if f.audio is None else len(f.audio)
    assert n == v.frames
    assert abs(samples / v.sample_rate - v.frames / v.fps) < 0.01
