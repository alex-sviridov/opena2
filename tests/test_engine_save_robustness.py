"""L10f: robustness and original-file tolerance of saved games (docs/engine/save.md "Robustness"): fuzzed town and mission files never crash the shell (a clean notice, nothing of the shell
replaced), crafted counts / zlib bombs / wrong magic / outdated / multiplayer files, the pass-through of what the engine does not model (load -> save of an original-style file keeps option words,
unnamed unit bytes, script blocks, unknown `.reg` keys), the `save-info` / `save-diff` diagnostics and the settings-side `famehall.dat`.  Synthetic tests always run; the mission ones need the install."""

import os
import random
import struct
import time
import zlib

import pytest

from allods2.formats import saves as S
from allods2.formats import serverstream as SS
from engine import famehall
from engine import saveinfo
from engine import savegame as SG
from engine import saveslots as SL_
from engine.shell import Shell
from engine.shell import saveload as SL
from helpers import GFS, needs_data
from test_savegame_town import FakeAssets, new_game

FAMILY = ValueError                       # ArchiveError and MultiplayerSave are ValueErrors


def town_game():
    g = new_game(attributes=(40, 36, 25, 17), school=2, name="Aldor")
    g.gold = 4321
    g.camp.set(0x301, 7)
    return g


def mutate(data, rng):
    b = bytearray(data)
    m = rng.choice(["trunc", "flip", "flips", "word", "zero"])
    if m == "trunc":
        return bytes(b[:rng.randrange(len(b))])
    if m == "flip":
        k = rng.randrange(len(b))
        b[k] ^= 1 << rng.randrange(8)
    elif m == "flips":
        for _ in range(8):
            k = rng.randrange(len(b))
            b[k] ^= 1 << rng.randrange(8)
    elif m == "word":
        k = rng.randrange(0, len(b) - 4)
        b[k:k + 4] = rng.choice([b"\xff\xff\xff\xff", b"\0\0\0\0", b"\xff\xff\xff\x7f", b"\0\0\0\x80"])
    else:
        k = rng.randrange(len(b))
        b[k:k + rng.randrange(1, 64)] = bytes(64)[:len(b[k:k + 64])]
    return bytes(b)


# --- the readers: only the ValueError family, and fast ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fuzzed_town_saves_raise_only_value_errors_and_never_hang(seed):
    data = town_game().to_save("fuzz").pack()
    rng = random.Random(seed)
    outcomes = set()
    for _ in range(400):
        raw = mutate(data, rng)
        t = time.time()
        try:
            sv = S.parse_save(raw)
            SG.kind(sv)
            SG.from_save(sv, assets=FakeAssets())
            outcomes.add("ok")
        except FAMILY:
            outcomes.add("refused")
        assert time.time() - t < 2
    assert outcomes == {"ok", "refused"}


def test_container_refusals_have_the_exes_texts():
    good = town_game().to_save("x").pack()
    with pytest.raises(ValueError, match="Invalid save file"):
        S.parse_save(b"\0" * 64)
    with pytest.raises(ValueError, match="Invalid save file"):
        S.parse_save(good[:10])
    wrong = struct.pack("<I", 0x12345678) + good[4:]
    with pytest.raises(ValueError, match="Invalid save file"):
        S.parse_save(wrong)
    old = good[:8] + struct.pack("<I", 0x0BAD0001) + good[12:]
    with pytest.raises(ValueError, match="Outdated save file"):
        S.parse_save(old)
    sv = S.parse_save(good)
    end = 16 + len(good[16:]) - len(sv.tail.__class__.__name__) * 0                  # the server block end is in the header
    end = struct.unpack_from("<I", good, 4)[0]
    mp = good[:end] + S.MP_HEADER + bytes(0x100 - len(S.MP_HEADER)) + good[end + 0x100:]
    with pytest.raises(S.MultiplayerSave):
        S.parse_save(mp)


def test_a_higher_version_loads_and_is_written_back_as_stored():
    good = town_game().to_save("x").pack()
    newer = good[:8] + struct.pack("<I", 0x0BAD0009) + good[12:]
    assert S.parse_save(newer).pack() == newer


def test_huge_counts_are_refused_not_allocated():
    good = town_game().to_save("x").pack()
    sv = S.parse_save(good)
    # the Scenario.dll location count, the mission list count and the reg entry count at 0xffffffff
    tail = bytearray(S.pack_tail(sv.tail))
    for needle_off in (len(tail) - (4 + 9 * 8) - 4,):                                  # location list count region: patched generically below
        pass
    for off in range(0, len(tail) - 4, 4):
        t = bytearray(tail)
        t[off:off + 4] = b"\xff\xff\xff\xff"
        start = time.time()
        try:
            S.parse_tail(bytes(t), 0)
        except ValueError:
            pass
        assert time.time() - start < 1
    stream = bytearray(sv.stream)
    for off in range(0, min(len(stream) - 4, 600), 2):                                  # the head and the first lists: every aligned word set to 0xffffffff
        t = bytearray(stream)
        t[off:off + 4] = b"\xff\xff\xff\xff"
        start = time.time()
        try:
            SS.ServerStream.parse(bytes(t))
        except ValueError:
            pass
        assert time.time() - start < 1


def test_an_engine_blob_that_is_a_zlib_bomb_or_garbage_is_refused():
    from engine import missionsave as M
    with pytest.raises(ValueError):
        M.inflate(b"not zlib")
    bomb = zlib.compress(bytes(1 << 20) * 8, 9)
    with pytest.raises(ValueError, match="too large"):
        M.inflate(bomb, limit=1 << 20)
    assert M.inflate(zlib.compress(b"abc")) == b"abc"


def test_a_damaged_client_tree_is_a_value_error_not_a_type_error():
    sv = S.parse_save(town_game().to_save("x").pack())
    st = sv.tail.state
    raw = bytearray(sv.tail.reg_bytes)
    # turn a leaf's type word into garbage: reading the tree must raise ValueError (or still work), never TypeError
    for off in range(0x18, len(raw) - 8, 4):
        t = bytearray(raw)
        t[off:off + 4] = b"\xfe\xff\xff\x7f"
        tail = S.ClientTail(sv.tail.description, None, bytes(t), sv.tail.missions, sv.tail.mission_tail, sv.tail.scenario, sv.tail.hotkeys)
        try:
            from allods2.reg import parse_reg
            tail.reg = parse_reg(bytes(t), "save")
            tail.state
        except ValueError:
            pass


# --- the shell: a clean notice, nothing replaced --------------------------------------------------------------------------------------------------

def test_a_refused_file_leaves_the_shell_untouched(tmp_path):
    sh = Shell(None, (640, 480), slots=SL_.SaveSlots(tmp_path))
    sh.campaign = sentinel = object()
    good = town_game().to_save("x").pack()
    cases = {"game0001.sav": b"", "game0002.sav": good[:len(good) // 2], "game0003.sav": b"\xff" * 300,
             "game0004.sav": good[:8] + struct.pack("<I", 1) + good[12:],
             "game0005.sav": good[:struct.unpack_from("<I", good, 4)[0]] + S.MP_HEADER + bytes(0x100 - len(S.MP_HEADER))}
    for name, data in cases.items():
        (tmp_path / name).write_bytes(data)
        status, text = SL.load_file(sh, name)
        assert status == "error" and text.startswith(("Invalid save file", "Outdated save file", "multiplayer")), (name, text)
        assert sh.campaign is sentinel
    assert SL.load_file(sh, "game0007.sav")[0] == "error"                            # no such file: a notice too


@needs_data
@pytest.mark.parametrize("seed", [1, 2])
def test_fuzzed_town_files_through_the_shell_never_crash(tmp_path, seed):
    from engine.campaign import CampaignGame, HeroChoice
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    data = g.to_save("fuzz").pack()
    sh = Shell(GFS, (640, 480), slots=SL_.SaveSlots(tmp_path))
    rng = random.Random(seed)
    seen = set()
    for _ in range(80):
        (tmp_path / "game0001.sav").write_bytes(mutate(data, rng))
        t = time.time()
        status, res = SL.load_file(sh, "game0001.sav")
        assert status in ("ok", "error") and time.time() - t < 5
        seen.add(status)
    assert seen == {"ok", "error"}


# --- original-file tolerance: the pass-through ------------------------------------------------------------------------------------------------------

def test_an_original_style_town_save_survives_load_and_save_byte_for_byte():
    g = town_game()
    sv = g.to_save("orig")
    stream = SS.ServerStream.parse(sv.stream)
    stream.words = tuple(range(1, 12))                                                  # option words, the d20 word, the debug block: none of them is modelled
    stream.d20 = 77
    stream.debug = bytes(random.Random(1).randrange(256) for _ in range(400))
    hero = stream.players[0].groups[0].units[0]
    hero.blk_a6 = bytes(range(1, 0x19))
    hero.blk_114 = bytes(range(0x30, 0x48))
    hero.mover = bytes(range(0xB4))
    hero.brain = bytes(range(0xB8))
    tail = sv.tail.with_state(S.ClientState(name="Aldor", extra={"Foo": {"Bar": 5}, "Other": [1, 2, 3]}))
    original = S.SaveGame(stream.pack(), tail).pack()
    g2 = SG.from_save(original, assets=FakeAssets())
    back = g2.to_save("orig").pack()
    assert saveinfo.diff(original, back).startswith("no typed field differs")          # every value, raw block and unknown reg key as the file had it (pointer keys are renumbered: they mean nothing outside one file)
    assert S.parse_save(back).tail == S.parse_save(original).tail
    g2.gold += 5                                                                         # what play changes is written, the rest still the original's
    changed = S.parse_save(g2.to_save("orig").pack())
    s2 = SS.ServerStream.parse(changed.stream)
    assert s2.players[0].gold == g.gold + 5 and s2.words == tuple(range(1, 12)) and s2.d20 == 77 and s2.debug == stream.debug
    assert s2.players[0].groups[0].units[0].blk_a6 == hero.blk_a6 and changed.tail.state.extra["Foo"] == {"Bar": 5}


def test_unknown_client_keys_are_kept_by_the_typed_view():
    st = S.ClientState(name="x", extra={"Weird": {"K": 1}, "Top": 9})
    back = S.ClientState.from_reg(S.parse_save(town_game().to_save("a").pack()).tail.with_state(st).reg)
    assert back.extra == {"Weird": {"K": 1}, "Top": 9} and back.name == "x"


@needs_data
def test_an_original_style_mission_save_keeps_what_the_engine_does_not_model():
    from engine import missionsave as M
    from engine.campaign import CampaignGame, HeroChoice
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    world, _ = g.start_mission(10)
    sv = M.world_to_save(world, g)
    stream = SS.ServerStream.parse(sv.stream)
    rng = random.Random(5)
    stream.words, stream.d20 = tuple(range(1, 12)), 9
    stream.debug = bytes(rng.randrange(256) for _ in range(400))
    for u in stream.units[:30]:
        for name, off, v in (("blk_a6", 3, 0x5A), ("blk_114", 9, 0x33), ("brain", 0x58, 7), ("brain", 0xA4, 9), ("mover", 0x20, 1)):
            b = bytearray(getattr(u, name))
            b[off] = v
            setattr(u, name, bytes(b))
    sc = stream.mission.script
    sc.b30, sc.b400, sc.d_a4c = bytes(range(0x30)), (bytes(range(200, 256)) * 8)[:400], 5
    st = sv.tail.state
    st.engine, st.extra = b"", {"Mystery": {"A": 1}}
    original = S.SaveGame(stream.pack(), sv.tail.with_state(st)).pack()
    lm = M.world_from_save(original, g.assets)
    assert not lm.exact
    out = M.world_to_save(lm.world, lm.campaign)
    fa, _ = saveinfo.fields_of(original)
    fb, _ = saveinfo.fields_of(out.pack())
    differ = {k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
    # nothing played: every value and raw byte as the file had it (pointer keys renumbered); only what the load itself derives differs (the engine blob, the fog the loader turns on, the
    # world-map rectangles Scenario.dll gives the locations)
    assert differ <= {"client.engine_blob", "client.fog_data", "client.fog_data.#", "container.stream_len", "scenario.locations"}, sorted(differ)[:10]
    assert out.tail.state.extra == {"Mystery": {"A": 1}}
    again = M.world_from_save(out.pack(), g.assets)                                      # and ours loads exactly, with the origin kept for the next save
    assert again.exact
    assert saveinfo.diff(out.pack(), M.world_to_save(again.world, again.campaign).pack()).startswith("no typed field differs")


# --- diagnostics -------------------------------------------------------------------------------------------------------------------------------------

def test_save_info_and_diff_on_town_saves():
    g = town_game()
    a = g.to_save("first").pack()
    g.gold = 99
    g.camp.set(0x301, 8)
    b = g.to_save("second").pack()
    text = saveinfo.info(a)
    assert "kind                 town" in text and "'first'" in text and "0x301=7" in text and "round trip           pack() == file bytes" in text and "no engine extension" in text
    d = saveinfo.diff(a, b)
    assert "scenario.var[769]" in d and "7 -> 8" in d and "gold" in d and "tail.description" in d
    assert saveinfo.diff(a, a).startswith("no typed field differs")
    assert saveinfo.info(b"junk" * 10).count("REFUSED") == 1 and "Invalid save file" in saveinfo.info(b"x" * 40)
    mp = a[:struct.unpack_from("<I", a, 4)[0]] + S.MP_HEADER + bytes(0x100 - len(S.MP_HEADER))
    assert "multiplayer" in saveinfo.info(mp)


def test_save_info_reports_an_untyped_client_key_and_a_stream_that_does_not_parse():
    g = town_game()
    sv = g.to_save("x")
    extra = sv.tail.with_state(S.ClientState(extra={"Mystery": {"A": 1}}))
    assert "Mystery/A" in saveinfo.info(S.SaveGame(sv.stream, extra).pack())
    broken = S.SaveGame(sv.stream[:len(sv.stream) // 2], sv.tail).pack()
    assert "DOES NOT PARSE" in saveinfo.info(broken)


def test_the_cli_commands_run(tmp_path, capsys):
    from engine import __main__ as E
    g = town_game()
    (tmp_path / "a.sav").write_bytes(g.to_save("a").pack())
    g.gold = 5
    (tmp_path / "b.sav").write_bytes(g.to_save("b").pack())
    assert E.main(["save-info", str(tmp_path / "a.sav")]) == 0
    assert "kind" in capsys.readouterr().out
    assert E.main(["save-diff", str(tmp_path / "a.sav"), str(tmp_path / "b.sav")]) == 0
    assert "differing typed fields" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        E.main(["save-info", str(tmp_path / "missing.sav")])


@needs_data
def test_save_info_on_a_mission_save():
    from engine import missionsave as M
    from engine.campaign import CampaignGame, HeroChoice
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    world, _ = g.start_mission(10)
    data = M.world_to_save(world, g, description="mission start").pack()
    text = saveinfo.info(data)
    assert "kind                 mission" in text and "mission branch" in text and "engine extension present" in text and "script  " in text
    sv = S.parse_save(data)
    st = sv.tail.state
    st.engine = b""
    plain = S.SaveGame(sv.stream, sv.tail.with_state(st)).pack()
    assert "original-style" in saveinfo.info(plain)
    d = saveinfo.diff(data, plain)
    assert "client.engine_blob" in d and d.startswith("no typed field differs")


@needs_data
@pytest.mark.parametrize("seed", [1, 2])
def test_fuzzed_mission_files_through_the_shell_never_crash(tmp_path, seed):
    from engine import missionsave as M
    from engine.campaign import CampaignGame, HeroChoice
    from engine.sim import Simulation
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    world, _ = g.start_mission(10)
    data = M.world_to_save(world, g).pack()
    sv = S.parse_save(data)
    st = sv.tail.state
    st.engine = b""
    plain = S.SaveGame(sv.stream, sv.tail.with_state(st)).pack()                          # the stream-only path is the one a real file takes
    sh = Shell(GFS, (640, 480), slots=SL_.SaveSlots(tmp_path))
    sh.campaign = g
    rng = random.Random(seed)
    seen = set()
    for blob in (plain, data):
        for _ in range(40):
            (tmp_path / "game0001.sav").write_bytes(mutate(blob, rng))
            t = time.time()
            status, res = SL.load_file(sh, "game0001.sav")
            assert status in ("ok", "error") and time.time() - t < 10
            seen.add(status)
            if status == "ok":
                loaded = res[1].get("loaded")
                if loaded is not None:
                    try:
                        sim = Simulation(loaded.world, triggers=True, vision=True)
                        for _ in range(2):
                            sim.step()
                    except Exception:               # noqa: BLE001  a mutated value can break play; the game screen turns that into the menu (ShellGame.run), never into a crashed shell
                        pass
                sh.campaign = g
    assert seen == {"ok", "error"}


# --- famehall.dat ----------------------------------------------------------------------------------------------------------------------------------------

def test_the_hall_insert_rule_and_the_exit_write(tmp_path):
    h = famehall.Hall([S.HallEntry("a", 300, 0, 0), S.HallEntry("b", 200, 0, 0), S.HallEntry("c", 100, 0, 0)], limit=4)
    assert h.add("new", 250) == 1 and [e.name for e in h.entries] == ["a", "new", "b", "c"]
    assert h.add("tie", 250) == 1                                                        # `new.a < entry.a` moves on: a tie goes before the older entry
    assert [e.name for e in h.entries] == ["a", "tie", "new", "b"]
    assert h.add("last", 1) == 4 and len(h.entries) == 4                                 # appended, then cut to the limit
    file = tmp_path / "cfg" / "famehall.dat"
    assert famehall.write(h, str(file)) == str(file)
    assert [e.name for e in famehall.load(str(file)).entries] == ["a", "tie", "new", "b"]
    assert famehall.path(str(tmp_path / "cfg" / "settings.json")) == str(file)


def test_the_shell_writes_the_hall_at_shutdown_into_the_settings_folder(tmp_path):
    install = tmp_path / "install"
    install.mkdir()
    (install / "famehall.dat").write_bytes(S.build_famehall([S.HallEntry("Hero", 70006, 0, 0)]))
    from allods2.common import as_fs
    file = tmp_path / "cfg" / "famehall.dat"
    sh = Shell(as_fs(str(install)), (640, 480), hall_file=str(file))
    assert not file.exists()
    assert sh.shutdown() == str(file) and [e.name for e in famehall.load(str(file)).entries] == ["Hero"]
    assert (install / "famehall.dat").read_bytes() == S.build_famehall([S.HallEntry("Hero", 70006, 0, 0)])      # the install is never written
    assert Shell(None, (640, 480)).shutdown() is None                                    # no settings folder (tests): nothing written
    file.write_bytes(b"\xff\xff")                                                        # a damaged settings copy: the install's is used
    assert [e.name for e in famehall.load(str(file), as_fs(str(install))).entries] == ["Hero"]
