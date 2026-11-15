"""`engine.saveslots` (docs/engine/save-ui.md): the slot folder model.  Synthetic files only: no install, no pygame."""

import os
import struct

import pytest

from engine import saveslots as SS
from engine.audio import settings as ST


def fake(path, description="", offset=8, magic=SS.MAGIC, size=SS.DESC_SIZE, mtime=None):
    """A file with the first u32 = magic, the u32 at 4 = where the description starts, the 0x100 description bytes there."""
    raw = struct.pack("<II", magic, offset)
    raw += b"\0" * (offset - 8) + description.encode("cp1251").ljust(size, b"\0")[:size]
    with open(path, "wb") as f:
        f.write(raw)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def slots(tmp_path):
    return SS.SaveSlots(tmp_path)


def test_scan_lists_valid_saves_newest_first(slots, tmp_path):
    fake(tmp_path / "game0000.sav", "old", mtime=1000)
    fake(tmp_path / "game0002.sav", "newest", mtime=3000)
    fake(tmp_path / "game0001.sav", "middle", mtime=2000)
    (tmp_path / "game0003.sav").write_bytes(b"not a save at all")        # first u32 is not the magic: left out of the list
    (tmp_path / "other.sav").write_bytes(b"x")
    (tmp_path / "game0004.txt").write_bytes(b"x")
    assert [s.name for s in slots.scan()] == ["game0002.sav", "game0001.sav", "game0000.sav"]
    assert [s.description for s in slots.scan()] == ["newest", "middle", "old"]


def test_description_sits_at_the_offset_named_at_plus_4(slots, tmp_path):
    fake(tmp_path / "game0000.sav", "deep", offset=0x400)
    assert slots.scan()[0].description == "deep"
    fake(tmp_path / "game0001.sav", "x" * 0x100, offset=8)                # no terminator: the whole 0x100 bytes
    assert len(slots.describe("game0001.sav").description) == 0x100
    (tmp_path / "game0002.sav").write_bytes(struct.pack("<II", SS.MAGIC, 0x4000) + b"\0" * 8)   # description beyond the file
    assert slots.describe("game0002.sav") is None


def test_description_is_cp1251(slots, tmp_path):
    fake(tmp_path / "game0000.sav", "Битва")
    assert slots.scan()[0].description == "Битва"


def test_hidden_autosaves(slots, tmp_path):
    fake(tmp_path / "game9999.sav", "Restart last mission", mtime=5000)
    fake(tmp_path / "game9998.sav", "Abort mission and return to town", mtime=4000)
    fake(tmp_path / "game0001.sav", "mine", mtime=1000)
    assert [s.name for s in slots.scan()] == ["game0001.sav"]                       # the Save dialog hides both
    assert [s.name for s in slots.scan(include_hidden=True)] == ["game9999.sav", "game9998.sav", "game0001.sav"]
    assert all(s.hidden for s in slots.scan(include_hidden=True)[:2])


def test_ties_break_by_name(slots, tmp_path):
    for n in ("game0003.sav", "game0001.sav", "game0002.sav"):
        fake(tmp_path / n, n, mtime=100)
    assert [s.name for s in slots.scan()] == ["game0001.sav", "game0002.sav", "game0003.sav"]


def test_any_saves_counts_any_file_even_invalid(slots, tmp_path):
    assert not slots.any_saves()
    (tmp_path / "gamefoo.sav").write_bytes(b"junk")
    assert slots.any_saves() and slots.scan() == []                                  # `FindFirstFile` finds it; the list does not
    assert not SS.SaveSlots(tmp_path / "missing").any_saves()


def test_new_name_smallest_unused_index():
    s = lambda *nums: [SS.Slot("game%04d.sav" % n, "", 0.0) for n in nums]
    assert SS.new_name([]) == "game0000.sav"
    assert SS.new_name(s(0)) == "game0001.sav"
    assert SS.new_name(s(0, 1, 2)) == "game0003.sav"
    assert SS.new_name(s(2, 0, 1, 4)) == "game0003.sav"                              # the gap, whatever the list order
    assert SS.new_name(s(1, 2)) == "game0000.sav"
    assert SS.new_name(s(0, 1, 9)) == "game0002.sav"
    assert SS.new_name(s(0, 9999)) == "game0001.sav"
    assert SS.new_name(s(*range(10000))) == "game10000.sav"                          # `game%ld.sav` once the four digits are gone


def test_new_name_counts_only_listed_files(slots, tmp_path):
    fake(tmp_path / "game0000.sav", "a")
    (tmp_path / "game0001.sav").write_bytes(b"junk")                                # not listed: its number is free again
    assert SS.new_name(slots.scan()) == "game0001.sav"


def test_slot_number_reads_four_characters_as_digits():
    assert SS.slot_number("game0042.sav") == 42
    assert SS.slot_number("game1234.sav") == 1234
    assert SS.slot_number("game12345.sav") == 1234                                   # the characters at 4..7 only (the exe's quirk)


def test_autosave_names_use_9999_minus_slot():
    assert SS.autosave_name(0) == "game9999.sav" and SS.autosave_name(1) == "game9998.sav"
    assert SS.AUTOSAVE_MISSION == 9999 and SS.AUTOSAVE_TOWN == 9998


def test_date_text_is_day_month_year_and_24_hour_clock(monkeypatch):
    import time
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    try:
        assert SS.date_text(1000000000) == "09.09.2001  01:46:40"
        assert SS.entry_text(SS.Slot("game0000.sav", "My game", 1000000000)) == "My game  09.09.2001  01:46:40"
    finally:
        monkeypatch.undo()
        time.tzset()


def test_choose_target_rules():
    slots = [SS.Slot("game0000.sav", "first", 3.0), SS.Slot("game0002.sav", "second", 2.0)]
    assert SS.choose_target("", 0, slots) is None                                    # Ok is disabled with an empty field
    assert SS.choose_target("fresh", 0, slots) == (0, "game0001.sav", "fresh")      # a new file at the smallest free index
    assert SS.choose_target("second", 0, slots) == (2, "game0002.sav", "second")    # the text equals a listed description: that row, its file
    assert SS.choose_target("second", 1, slots) == (2, "game0002.sav", "second")
    assert SS.choose_target("renamed", 1, slots) == (1, "game0000.sav", "renamed")  # quirk: the selected row's file is overwritten with the new text
    assert SS.choose_target("x", 5, slots) == (5, "game0001.sav", "x")              # a stale selection past the list: the new name


def test_write_is_atomic_and_replaces(slots, tmp_path):
    p = slots.write("game0007.sav", b"one")
    assert open(p, "rb").read() == b"one"
    slots.write("game0007.sav", b"two")
    assert slots.read("game0007.sav") == b"two"
    assert sorted(os.listdir(tmp_path)) == ["game0007.sav"]                          # no temp file left


def test_failed_write_leaves_the_old_file(slots, tmp_path, monkeypatch):
    slots.write("game0001.sav", b"keep")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        slots.write("game0001.sav", b"new")
    monkeypatch.undo()
    assert slots.read("game0001.sav") == b"keep" and sorted(os.listdir(tmp_path)) == ["game0001.sav"]


def test_write_creates_the_folder(tmp_path):
    s = SS.SaveSlots(tmp_path / "a" / "b")
    s.write("game0000.sav", b"x")
    assert s.read("game0000.sav") == b"x"


def test_delete(slots, tmp_path):
    fake(tmp_path / "game0000.sav", "a")
    assert slots.delete("game0000.sav") and not slots.delete("game0000.sav")
    assert slots.scan() == []


def test_names_cannot_leave_the_folder(slots):
    for bad in ("../x.sav", "a/b.sav", "", ".."):
        with pytest.raises(ValueError):
            slots.path(bad)


def test_the_slot_folder_comes_from_the_settings_file(tmp_path):
    env = {"ALLODS2_SETTINGS": str(tmp_path / "cfg" / "settings.json")}
    assert ST.saves_path(None, env) == str(tmp_path / "cfg" / "saves")                # default: beside the settings file
    s = ST.Settings(save_dir=str(tmp_path / "mine"))
    assert ST.saves_path(s, env) == str(tmp_path / "mine")
    p = str(tmp_path / "s.json")
    assert ST.save(s, p) and ST.load(p).save_dir == str(tmp_path / "mine")
    assert ST.load(str(tmp_path / "none.json")).save_dir == ""
