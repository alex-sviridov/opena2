"""K11: hero / class voices (docs/engine/audio.md 2.3): cooldown 3000 / 2000 ms with one shared stamp, an empty slot still stamps, `rand(count-1)`
inclusive from the audio layer's own RNG, the move / swarm skip rule, bank choice."""

from types import SimpleNamespace

import pytest

from allods2.formats.soundtable import BANKS
from engine.audio.voices import COMMAND_VOICE, Voices, bank_of, is_voice_hero, voice_path
from engine.rng import Rng


def unit(uid, sid=10210, name="Start_MF", hp=10, human=True):
    return SimpleNamespace(uid=uid, server_id=sid, stats=SimpleNamespace(name=name), hp=hp, human=human)


def banks(**cats):
    base = {"select": [], "attack": [], "move": [], "swarm": [], "retreat": [], "pickup": [], "defend": []}
    p = "sfx/characters/aldor/"
    for c, n in cats.items():
        base[c] = ["%s%s/%d.wav" % (p, c, i + 1) for i in range(n)]
    return {"aldor": base}


def test_bank_choice():
    assert bank_of(unit(1, 10210, "Start_MF")) == "aldor" and bank_of(unit(1, 10211, "Start_FF")) == "sagita"
    assert bank_of(unit(1, 10212, "Start_MM")) == "hildarius" and bank_of(unit(1, 10213, "Start_FM")) == "galinel"
    assert bank_of(unit(1, 10220, "Fighter_Hero")) == "igles" and bank_of(unit(1, 10230, "Mage_Hero")) == "dina"
    assert [bank_of(unit(1, s, "x")) for s in range(1, 7)] == list(BANKS[6:12])
    assert bank_of(unit(1, 7, "Man_Axe")) is None and bank_of(unit(1, 2000, "CH")) is None
    assert bank_of(unit(1, 10210, "Start_MF", human=False)) is None
    assert is_voice_hero(unit(1, 7, "Man_Axe")) and not is_voice_hero(unit(1, 2000, "CH"))


def test_cooldown_is_3000_ms_and_shared_by_every_order_voice():
    v = Voices(banks(move=1, attack=1, defend=1), Rng(1))
    u = unit(1)
    assert v.voice("MoveUnits", [u], 10000)[2] == "ok"
    for cmd in ("MoveUnits", "AttackUnit", "Guard"):
        assert v.voice(cmd, [u], 12999)[2] == "dropped:cooldown"
    assert v.voice("AttackUnit", [u], 13000)[2] == "ok"                  # exactly 3000 ms later
    assert v.stamp[1] == 13000


def test_select_cooldown_is_2000_ms_but_the_stamp_is_the_same_one():
    v = Voices(banks(select=2, move=1), Rng(1))
    u = unit(1)
    assert v.voice("SelectUnits", [u], 5000)[2] == "ok"
    assert v.voice("SelectUnits", [u], 6999)[2] == "dropped:cooldown"
    assert v.voice("SelectUnits", [u], 7000)[2] == "ok"
    assert v.voice("MoveUnits", [u], 8000)[2] == "dropped:cooldown"      # a move 1 s after a select: the 3000 ms test against the shared stamp


def test_an_empty_slot_still_starts_the_cooldown():
    v = Voices(banks(move=1), Rng(1))
    u = unit(1)
    assert v.voice("Retreat", [u], 100) == (u, None, "silent")           # no retreat sample
    assert v.stamp[1] == 100
    assert v.voice("MoveUnits", [u], 2000)[2] == "dropped:cooldown"


def test_units_have_their_own_stamp():
    v = Voices(banks(move=1), Rng(1))
    a, b = unit(1), unit(2)
    assert v.voice("MoveUnits", [a], 0)[0] is a
    assert v.voice("MoveUnits", [b], 10)[0] is b


def test_the_variant_draw_is_inclusive_and_covers_every_file():
    seen = set()
    for seed in range(200):
        v = Voices(banks(move=4), Rng(seed))
        _, snd, res = v.voice("MoveUnits", [unit(1)], 0)
        seen.add(snd)
    assert seen == {("hero", "aldor", "move/%d" % i) for i in (1, 2, 3, 4)}     # the last file is reachable


def test_one_file_draws_no_number_and_the_world_rng_is_never_touched():
    r = Rng(5)
    v = Voices(banks(move=1), r)
    before = r.state
    u = unit(1)
    v.voice("MoveUnits", [u], 0)
    assert r.state != before                                             # the pick of a single unit still draws (size * rand / 0x7fff)
    r2 = Rng(5)
    r2.rand15()
    assert r.state == r2.state                                           # but the one-file sample drew nothing more


def test_the_move_and_swarm_skip_rule_and_the_others_have_none():
    v = Voices(banks(move=1, swarm=1, attack=1), Rng(1))
    u = unit(1)
    assert v.voice("MoveUnits", [u], 0, skip=True) == (None, None, "silent") and not v.stamp
    assert v.voice("Swarm", [u], 0, skip=True)[2] == "silent" and not v.stamp
    assert v.voice("UseStructure", [u], 0, skip=True)[2] == "ok"         # patrol / use structure: no skip test
    assert v.voice("AttackUnit", [unit(2)], 0, skip=True)[2] == "ok"


def test_pick_takes_one_alive_unit_with_a_bank_heroes_first():
    v = Voices(banks(move=1), Rng(1))
    dead, plain = unit(1, hp=0), unit(2, 2000, "CH")
    hero, cls = unit(3), unit(4, 3, "Man_Sword")
    for _ in range(20):
        assert v.pick([dead, plain, hero, cls]) is hero
    assert v.pick([dead, plain, cls]) is cls and v.pick([dead, plain]) is None


def test_command_table_and_paths():
    assert COMMAND_VOICE["MoveUnits"] == ("move", True) and COMMAND_VOICE["Swarm"] == ("swarm", True)
    assert COMMAND_VOICE["UseStructure"] == ("move", False) and COMMAND_VOICE["Retreat"][0] == "retreat"
    assert all(COMMAND_VOICE[c][0] == "defend" for c in ("Guard", "Stop", "StandStill"))
    assert voice_path(("hero", "dina", "select/2")) == "sfx/characters/dina/select/2.wav"
    assert voice_path(("hero", "aldor", "easy")) == "sfx/characters/aldor/easy.wav"


def test_real_banks_resolve_every_variant():
    from helpers import GFS
    if GFS is None:
        pytest.skip("no install")
    from allods2.formats import soundtable
    b = soundtable.hero_banks(GFS)
    for seed in range(30):
        v = Voices(b, Rng(seed))
        _, snd, _ = v.voice("SelectUnits", [unit(1)], 0)
        assert GFS.exists(voice_path(snd))
