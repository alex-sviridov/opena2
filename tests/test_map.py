"""docs/formats/map.md: header and terrain layer; synthetic maps run without game files."""

import struct

import numpy as np
import pytest

from allods2.alm import SEC_GENERAL
from allods2.cli import main
from allods2.common import campaign_maps
from allods2.formats import Map, decode_text
from allods2.formats.map import parse_header
from allods2.graphics import terrain as tr

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")


def general(w, h, version=1600, name=b"", desc=b"", counts=(2, 3, 4, 5, 6, 0, 7, 8, 9, 10),
            sets=0x1FFF, f84=1, f88=2):
    """Section 0 bytes in the game's read order (name/description NUL-padded with junk after)."""
    players, n4, n6, n7, n8, n10, a, b, c, n12 = counts
    out = struct.pack("<II", w, h) + struct.pack("<f", 0.5) + struct.pack("<iiii", 360, 21, 63, sets)
    out += struct.pack("<5I", players, n4, n6, n7, n8)
    if version > 1149:
        out += struct.pack("<I", n10)
    if version > 1229:
        out += struct.pack("<3I", a, b, c)
    if version > 1299:
        out += struct.pack("<I", n12)
    out += (name + b"\0" + b"junk" * 16)[:0x40].ljust(0x40, b"\0")
    out += struct.pack("<ii", f84, f88)
    if version > 1159:
        out += struct.pack("<ii", 5, 60000000)
    out += (desc + b"\0" + b"junk" * 128)[:0x200].ljust(0x200, b"\0")
    return out


def alm(w, h, tiles, version=1600, gen=None, tag=7, **kw):
    """Whole file; section 0 declared 16 bytes shorter than what the reader consumes."""
    gen = gen if gen is not None else general(w, h, version, **kw)
    secs = [(0, gen[:-16]), (1, struct.pack("<%dH" % len(tiles), *tiles)),
            (2, bytes(range(w * h))), (3, bytes([1]) * (w * h))]
    body = b""
    for k, (sid, data) in enumerate(secs):
        body += struct.pack("<5I", tag, 20, len(data), sid, 99) + data
        if k == 0:
            body += gen[-16:]
    return b"M7R\0" + struct.pack("<4I", 20, w * h * 4 + 72, len(secs), version) + body


def test_header_fields_and_texts():
    name = "Карта".encode("cp1251")
    m = Map.parse(alm(2, 2, [1, 2, 3, 4], name=name, desc=b"line1\r\nline2"), "t.alm")
    h = m.header
    assert (h.width, h.height, h.version, h.tag, h.id_extra) == (2, 2, 1600, 7, 99)
    assert h.angle == 0.5 and (h.field_0c, h.ambient, h.diffuse, h.tile_sets) == (360, 21, 63, 0x1FFF)
    assert (h.player_count, h.n_sec4, h.n_sec6, h.n_sec7, h.n_sec8) == (2, 3, 4, 5, 6)
    assert (h.n_sec10, h.n_sec11, h.n_sec12) == (0, (7, 8, 9), 10)
    assert h.name == "Карта" and h.description == "line1\r\nline2"
    assert (h.field_84, h.field_88, h.field_8c, h.field_90) == (1, 2, 5, 60000000)
    assert h.tile_set_list == list(range(13)) and h.cells == 4


def test_description_reads_past_the_declared_section_size():
    # the last description bytes lie in the 16 bytes after section 0
    desc = b"x" * 0x1F8 + b"tail-end"
    m = Map.parse(alm(1, 1, [0], desc=desc[:0x1FF]))
    assert m.header.description.endswith("tail-en") and len(m.header.description) == 0x1FF


def test_text_stops_at_nul_and_decodes_cp1251():
    assert decode_text(b"\xcf\xf0\xe8\xe2\xe5\xf2\0garbage") == "Привет"
    assert decode_text(b"") == ""


def test_version_gates_drop_fields():
    old = general(1, 1, 1100)
    h = parse_header(type("S", (), {"data": old[:-16], "tail": old[-16:]})(), 1100)
    assert (h.n_sec10, h.n_sec11, h.n_sec12, h.field_8c, h.field_90) == (0, (0, 0, 0), 0, 0, 0)
    assert h.width == 1 and h.player_count == 2


def test_terrain_layer():
    tiles = [0x0041, 0x2302, 0x8001, 0x0000]
    m = Map.parse(alm(2, 2, tiles))
    assert m.terrain.shape == (2, 2) and m.terrain.dtype == np.uint16
    assert m.terrain.tolist() == [[0x41, 0x2302], [0x8001, 0]]
    assert m.runtime_terrain().tolist() == [[0x41, 0x0302], [0x8001, 0]]     # dirt bit cleared
    assert m.heights.tolist() == [[0, 1], [2, 3]] and m.objects.tolist() == [[1, 1], [1, 1]]
    assert set(m.sections) == set()                                         # nothing else here


def test_unparsed_sections_stay_raw():
    data = alm(1, 1, [0])
    extra = struct.pack("<5I", 7, 20, 3, 4, 0) + b"abc"
    data = data[:12] + struct.pack("<I", 5) + data[16:] + extra
    assert Map.parse(data).sections == {4: b"abc"}


def test_rejects_bad_sizes_and_versions():
    with pytest.raises(ValueError):
        Map.parse(alm(2, 2, [0, 0, 0, 0], gen=general(3, 2)))                # header ≠ container size
    with pytest.raises(ValueError):
        Map.parse(alm(2, 2, [0, 0, 0, 0])[:-1])


def test_cli_info_on_a_disk_file(tmp_path, capsys):
    p = tmp_path / "t.alm"
    p.write_bytes(alm(2, 2, [0x2000 | 0x40] * 4, name=b"Hi", desc=b"d"))
    assert main(["map", "info", str(p)]) == 0
    out = capsys.readouterr().out
    assert "2 x 2 cells" in out and "'Hi'" in out and "4 with the dirt flag" in out


# --- the install's 46 campaign maps -------------------------------------------

@needs_maps
def test_every_header_is_consistent():
    for path in MAPS:
        m = Map.load(path, GFS)
        h, S = m.header, m.alm.sections
        assert h.version in (1300, 1600) and h.tag in (5, 7), path
        assert (h.width, h.height) in ((80, 80), (144, 144), (256, 256)), path
        assert m.terrain.shape == (h.height, h.width)
        assert len(S[5].data) == 76 * h.player_count and 1 <= h.player_count <= 9, path
        assert len(S[6].data) == 48 * h.n_sec6, path
        assert len(S[11].data) == 12 * sum(h.n_sec11), path
        assert h.n_sec10 == 0 and len(S[10].data) == 0, path
        used = {int(s) for s in np.unique((m.terrain & 0x1FFF) >> 6)}
        assert used <= set(h.tile_set_list), path        # the mask lists every used set
        assert not (m.terrain & 0xC000).any(), path      # no fog bits in the files


@needs_maps
def test_every_tile_resolves():
    terrain = tr.TerrainSet.load(GFS)
    bad = {}
    for path in MAPS:
        m = Map.load(path, GFS)
        t = m.terrain.astype(int)
        s, j, r = (t & 0x1FFF) >> 6, (t >> 4) & 3, t & 0xF
        rows = np.array([[terrain.rows(a, b) for b in range(4)] for a in range(16)])
        n = int((r >= rows[s, j]).sum())
        if n:
            bad[m.name] = n
    assert bad == {"74.alm": 5}                           # terrain.md: the game reads past the strip


@needs_maps
def test_names_and_descriptions_decode():
    names = {Map.load(p, GFS).name: Map.load(p, GFS).header.name for p in MAPS}
    assert names["31.alm"] == "Adamantium mines"
    assert sum(1 for v in names.values() if v) == 19            # the rest are unnamed
