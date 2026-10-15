"""Synthetic tests for docs/formats/terrain.md and the .alm container."""

import glob
import os
import struct

import numpy as np
import pytest

from allods2.alm import load_alm, parse_alm
from allods2.graphics import terrain as tr

BASE = os.environ.get("ALLODS2_INSTALL", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples", "Allods2_en_251005", "Allods2_en"))
MAPS = sorted(glob.glob(os.path.join(BASE, "maps", "*.alm")))


# --- .alm container ----------------------------------------------------------

def alm(width, height, tiles, extra_sections=()):
    general = struct.pack("<II", width, height) + bytes(636)
    secs = [(0, general), (1, struct.pack("<%dH" % len(tiles), *tiles)),
            (2, bytes(width * height))] + list(extra_sections)
    body = b""
    for k, (sid, data) in enumerate(secs):
        body += struct.pack("<5I", 7, 20, len(data), sid, 0) + data
        if k == 0:
            body += bytes(16)                      # quirk: pad after section 0
    head = b"M7R\0" + struct.pack("<4I", 20, width * height * 4 + 72, len(secs), 0x640)
    return head + body


def test_alm_walks_to_eof_and_exposes_tiles():
    m = parse_alm(alm(2, 1, [0x0041, 0x2302]))
    assert (m.width, m.height) == (2, 1)
    assert m.tiles.tolist() == [[0x0041, 0x2302]]


def test_alm_rejects_trailing_bytes():
    with pytest.raises(ValueError):
        parse_alm(alm(1, 1, [0]) + b"x")


# --- cell value --------------------------------------------------------------

def test_decode_cell_fields():
    c = tr.decode_cell((5 << 6) | (2 << 4) | 9 | 0x2000)
    assert (c.set, c.strip, c.row, c.dirt) == (5, 2, 9, True)


def test_strip_file_names():
    assert tr.strip_name(0, 0) == "tile1-00.bmp"
    assert tr.strip_name(3, 3) == "tile1-15.bmp"
    assert tr.strip_name(9, 1) == "tile3-05.bmp"
    assert tr.strip_name(12, 2) == "tile4-02.bmp"


def test_water_animation():
    assert tr.water_set(8, 0, 0, 0) == 8
    assert tr.water_set(9, 2, 3, 0) == 8 + ((9 + 3 * 3) & 3)
    assert tr.water_set(8, 0, 0, 4) == 9                # anim >> 2
    assert tr.water_set(11, 5, 7, 99, animate=False) == 8


def synthetic_terrain():
    strips = {}
    for s in range(tr.SETS):
        for j in range(4):
            n = 8 if s in tr.WATER else 14
            strips[(s, j)] = np.full((n * 32, 32), s * 4 + j, np.uint8)
            strips[(s, j)][:, 0] = np.repeat(np.arange(n), 32)   # column 0 = row id
    dirt = np.zeros((128, 32), np.uint8)
    dirt[np.arange(4) * 32, 5] = 200 + np.arange(4)              # one opaque texel per variant
    return tr.TerrainSet(strips, dirt, np.zeros((256, 3), np.uint8))


def test_cell_tile_picks_set_strip_row():
    t = synthetic_terrain().cell_tile((6 << 6) | (1 << 4) | 3, 0, 0)
    assert t[0, 1] == 6 * 4 + 1 and t[0, 0] == 3


def test_row_past_strip_is_none():
    assert synthetic_terrain().cell_tile((9 << 6) | 8, 0, 0, animate=False) is None


def test_dirt_overlay_copies_nonzero_texels():
    T = synthetic_terrain()
    t = T.cell_tile(0x2000 | (2 << 6), 1, 0)       # variant (1 + 0) & 3 = 1
    assert t[0, 5] == 201 and t[0, 6] == 2 * 4


def test_dirt_flag_ignored_on_water():
    T = synthetic_terrain()
    t = T.cell_tile(0x2000 | (8 << 6), 0, 0, animate=False)
    assert t[0, 5] == 8 * 4


# --- flat lit blit -----------------------------------------------------------

def test_light_rows_flat_and_gradients():
    assert (tr.light_rows((46, 46, 46, 46)) == 46).all()
    r = tr.light_rows((0, 32, 0, 32))                # left -> right
    assert r[0, 0] == 0 and r[0, 31] == 31 and (r[:, 16] == 16).all()
    r = tr.light_rows((0, 0, 32, 32))                # top -> bottom
    assert r[0, 0] == 0 and r[31, 0] == 31 and (r[16] == 16).all()
    r = tr.light_rows((10, 10, 9, 9))                # negative step truncates toward 0
    assert r[0, 0] == 10 and r[31, 0] == 9


def test_render_uses_palette_and_light():
    T = synthetic_terrain()
    T.palette = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
    tiles = np.array([[(1 << 6) | 0]], np.uint16)
    flat = tr.render(tiles, T)
    assert flat.shape == (32, 32, 3) and flat[0, 1, 0] == 4
    lit = tr.render(tiles, T, light=np.full((1, 1), 64))       # row 64 = x1
    assert lit[0, 1, 0] == 4


# --- game files ----------------------------------------------------------------

@pytest.mark.skipif(not MAPS, reason="game files not available")
def test_game_maps_tiles_name_existing_sets():
    T = tr.TerrainSet.load(os.path.join(BASE, "data", "graphics", "terrain"))
    assert len(T.strips) == 52
    for p in MAPS:
        t = load_alm(p).tiles.astype(int)
        assert ((t & 0x1FFF) >> 6).max() < tr.SETS
        assert not (t & 0xC000).any()
