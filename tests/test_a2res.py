"""a2res (docs/formats/res.md): synthetic archives, one test per spec rule,
the file-system layers, and the GOG archives when the install is present."""

import struct

import numpy as np
import pytest
from PIL import Image

import a2res as R
from allods2.common import INSTALL, have_install


def write_res(path, tree, root_type=0x01):
    """Write a .res from {name: bytes | dict}; children keep dict order."""
    entries, blob = [], bytearray()

    def add(children):
        first = len(entries)
        entries.extend([nm, 0, 0, 0] for nm in children)
        for i, (nm, v) in enumerate(children.items()):
            if isinstance(v, dict):
                entries[first + i][1:] = [*add(v), 0x01]
            else:
                entries[first + i][1:] = [0x18 + len(blob), len(v), 0]
                blob.extend(v)
        return first, len(children)
    first, count = add(tree)
    d = 0x18 + len(blob)
    out = struct.pack("<6I", R.SIGNATURE, first, count, root_type, d, len(entries)) + bytes(blob)
    for nm, a, b, t in entries:
        out += struct.pack("<4I", 0, a, b, t) + nm.encode("cp1251").ljust(16, b"\0")[:16]
    path.write_bytes(out)
    return str(path)


def archive(tmp_path, tree, root_type=0x01, name="test.res"):
    return R.ResArchive(write_res(tmp_path / name, tree, root_type))


# --- archive format and lookup ---------------------------------------------

def test_header_walk_and_check(tmp_path):
    with archive(tmp_path, {"units": {"units.reg": b"reg", "a.256": b"xy"}, "top.txt": b"t"}) as a:
        assert a.name == "test"
        assert [(p, a.read_entry(e).tobytes()) for p, e in a.walk()] == [
            ("units/units.reg", b"reg"), ("units/a.256", b"xy"), ("top.txt", b"t")]
        assert a.dir_offset + 32 * len(a.entries) == a.size
        bad, odd, *_ = a.check()
        assert not bad and not odd


def test_bad_signature(tmp_path):
    p = tmp_path / "x.res"
    p.write_bytes(b"\0" * 0x18)
    with pytest.raises(ValueError, match="signature"):
        R.ResArchive(str(p))


def test_inline_directory_flag_rejected(tmp_path):
    with pytest.raises(ValueError, match="inline"):
        archive(tmp_path, {"f": b"x"}, root_type=0x01 | R.DIR_INLINE)


def test_unsorted_lookup_ignores_case_and_backslashes(tmp_path):
    with archive(tmp_path, {"Units": {"Units.REG": b"r"}}) as a:
        assert a.read("units\\units.reg").tobytes() == b"r"
        assert "UNITS/units.reg" in a


def test_sorted_lookup_is_case_sensitive(tmp_path):
    with archive(tmp_path, {"Abc": b"1", "abc": b"2"}, root_type=0x11) as a:
        assert a.read("abc").tobytes() == b"2"
        assert a.read("Abc").tobytes() == b"1"
        assert "ABC" not in a


def test_names_compare_on_15_chars(tmp_path):
    with archive(tmp_path, {"a" * 15: b"x"}) as a:
        assert a.read("a" * 15 + "zzz").tobytes() == b"x"


def test_trailing_space_name_only_reachable_with_the_space(tmp_path):
    with archive(tmp_path, {"file ": b"x"}) as a:
        assert "file" not in a
        assert a.read("file ").tobytes() == b"x"


def test_shadowed_name_listed(tmp_path):
    with archive(tmp_path, {"abc": b"1", "ABC": b"2"}) as a:    # unsorted: first match wins
        assert a.read("ABC").tobytes() == b"1"
        assert a.check()[1] == ["ABC"]


def test_deleted_entry_skipped(tmp_path):
    with archive(tmp_path, {"f": b"x"}) as a:
        assert "f" in a
        a.entries[0].type |= R.DELETED
        assert "f" not in a


def test_section_is_not_a_file(tmp_path):
    with archive(tmp_path, {"d": {"f": b"x"}}) as a:
        with pytest.raises(FileNotFoundError):
            a.read("d")


def test_gap_reported(tmp_path):
    with archive(tmp_path, {"f": b"xy", "g": b"z"}) as a:
        a.entries[1].a += 1                        # leave a hole after "f"
        assert any("gap" in b for b in a.check()[0])


def test_extract(tmp_path):
    with archive(tmp_path, {"d": {"f": b"x"}}, name="world.res") as a:
        assert R.extract(a, str(tmp_path / "out")) == 1
    assert (tmp_path / "out" / "world" / "d" / "f").read_bytes() == b"x"


# --- file systems ----------------------------------------------------------

@pytest.fixture
def install(tmp_path):
    d = tmp_path / "game"
    d.mkdir()
    write_res(d / "graphics.res", {"units": {"a.256": b"AAAA", "b.pal": b"PP"}})
    write_res(d / "World.RES", {"data": {"data.bin": b"DB"}})
    return d


def test_resfs_mounts_by_stem_and_reads_views(install):
    fs = R.ResFS(str(install))
    assert list(fs.archives) == ["graphics", "world"]     # ARCHIVES order
    v = fs.read("Graphics\\UNITS\\a.256")
    assert isinstance(v, memoryview) and v.tobytes() == b"AAAA"
    assert np.frombuffer(v, np.uint8).base is not None     # zero copy
    assert fs.read_bytes("world/data/data.bin") == b"DB"
    assert fs.listdir("") == ["graphics", "world"] and fs.listdir("graphics/units") == ["a.256", "b.pal"]
    assert fs.isdir("graphics/units") and not fs.isfile("graphics/units")
    assert fs.files() == ["graphics/units/a.256", "graphics/units/b.pal", "world/data/data.bin"]
    assert fs.glob("*.pal") == ["graphics/units/b.pal"]
    with pytest.raises(FileNotFoundError):
        fs.read("graphics/units/none")
    arc, e = fs.entry("graphics/units/b.pal")
    assert arc.name == "graphics" and e.b == 2


def test_resfs_lower_cases_the_path_first(tmp_path):
    d = tmp_path / "game"
    d.mkdir()
    write_res(d / "speech.res", {"abc.wav": b"w", "Upper.wav": b"u"}, root_type=0x11)
    fs = R.ResFS(str(d))
    assert fs.read_bytes("SPEECH\\ABC.WAV") == b"w"        # sorted root, strcmp after lowering
    assert "ABC.WAV" not in fs.archives["speech"]           # the archive alone is case-sensitive
    assert not fs.isfile("speech/Upper.wav")                # stored upper case is unreachable
    assert R.game_lower("A\\Zé") == "a\\zé"


def test_open_gives_seekable_file(install, tmp_path):
    img = Image.fromarray(np.arange(12, dtype=np.uint8).reshape(2, 2, 3))
    loose = tmp_path / "loose"
    (loose / "graphics").mkdir(parents=True)
    img.save(loose / "graphics" / "t.bmp")
    fs = R.DirFS(str(loose))
    with fs.open("GRAPHICS/T.BMP") as f:
        assert np.array_equal(np.asarray(Image.open(f)), np.asarray(img))
    m = R.MemoryFile(memoryview(b"abcdef"))
    m.seek(2)
    assert m.read(2) == b"cd" and m.tell() == 4 and m.seek(-1, 2) == 5 and m.read() == b"f"


def test_chain_first_layer_wins_and_listings_merge(install, tmp_path):
    over = tmp_path / "over" / "graphics" / "units"
    over.mkdir(parents=True)
    (over / "A.256").write_bytes(b"new")
    (over / "c.256").write_bytes(b"c")
    fs = R.ChainFS(R.DirFS(str(tmp_path / "over")), R.ResFS(str(install)))
    assert fs.read_bytes("graphics/units/a.256") == b"new"
    assert fs.read_bytes("graphics/units/b.pal") == b"PP"
    assert fs.listdir("graphics/units") == ["A.256", "c.256", "b.pal"]


def test_open_fs_picks_the_layer(install, tmp_path):
    assert isinstance(R.open_fs(str(install)), R.ResFS)
    assert isinstance(R.open_fs(str(tmp_path)), R.DirFS)
    assert R.open_fs(None) is R.OS


# --- the GOG install ---------------------------------------------------------

needs_gog = pytest.mark.skipif(not have_install(), reason="GOG install not present: " + INSTALL)


@needs_gog
def test_gog_archives_validate():
    fs = R.ResFS(INSTALL)
    assert list(fs.archives) == list(R.ARCHIVES)
    files = {}
    for stem, a in fs.archives.items():
        bad, odd, _, n, _ = a.check()
        assert not bad and not odd, stem
        files[stem] = n
    assert files == {"graphics": 4049, "main": 104, "patch": 1, "world": 5, "music": 21,
                     "video": 16, "sfx": 446, "movies": 156, "scenario": 47, "speech": 1133}
    assert len(fs.files()) == sum(files.values())


@needs_gog
def test_gog_paths_as_the_game_names_them():
    fs = R.ResFS(INSTALL)
    assert fs.read("graphics\\units\\units.reg")[:4].tobytes() == b"&YA1"
    assert fs.read("main\\graphics\\famehall\\hall.bmp")[:2].tobytes() == b"BM"
    assert fs.read("SFX\\Add.wav")[:4].tobytes() == b"RIFF"
    assert fs.isfile("scenario/10.alm") and fs.isfile("world/data/data.bin")
