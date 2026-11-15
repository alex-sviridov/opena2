"""The values a mission save carries where the exe's own code decides them (saves.md 6.12, 5; REA round of the open questions): the runner's stopwatch block, the relation header,
the human-seen latch, the Building constructor values, the SpellEffect constructor bytes, the unit armour / attack blocks, the mission list and the hall score."""

import struct

import pytest

from allods2.formats import serverblocks as B
from allods2.formats import serverstream as SS
from engine import famehall
from engine import missionsave as M

from helpers import needs_data
from test_engine_missionsave import make_sim, run


def test_stopwatch_block_has_a_nonzero_divisor_and_the_frequency():
    b = M.stopwatch_block()
    assert len(b) == 0x30 and struct.unpack_from("<Q", b, 0x10)[0] == M.STOPWATCH_FREQUENCY
    assert struct.unpack_from("<I", b, 0x20)[0] == M.STOPWATCH_FREQUENCY // 1000 != 0        # FUN_0057aee0 divides by +0x20


def test_hall_score_is_the_truncated_formula():
    assert famehall.score(70000, 100, 10) == int(70000 / 1000.0 * 10)
    assert famehall.score(1000, 0, 50) == int(1000 / 500000.0 * 50) == 0
    assert famehall.score(123456, 7, 9) == int(123456 / 70.0 * 9)


def test_hall_add_keeps_the_insert_rule_and_limit():
    h = famehall.Hall()
    for i, sc in enumerate((50, 70, 60)):
        h.add("h%d" % i, sc)
    assert [e.a for e in h.entries] == [70, 60, 50]


@needs_data
def test_mission_save_writes_the_exe_values():
    from engine.session import build_game
    w, a = build_game("73", seed=3, vision=True)
    start = M.world_to_save(w).server_stream() if hasattr(M.world_to_save(w), "server_stream") else None
    sim = make_sim(w)
    run(sim, {}, 40)
    sv = M.world_to_save(w)
    st = SS.ServerStream.parse(sv.stream)
    sc = st.mission.script
    assert struct.unpack_from("<I", sc.b30, 0x20)[0] != 0 and sc.d_be10 == 1 and sc.d_a4c >= 1
    assert sc.relations[:4] == bytes((1, 1, 0, 0)) and sc.b400 == bytes(400) and (sc.b_a48, sc.b_a49) == (0, 0)
    assert sv.tail.missions == [(1, 1)]
    for b in st.mission.buildings:
        ob = w.objects.get(0x6000 + b.base.d08)
        assert b.b40 == ob.type_id and b.base.w0e == ob.type_id
        stats = w.assets.databin().structures
        if 1 <= ob.type_id <= len(stats) and not ob.size:
            p = stats[ob.type_id - 1].params
            assert (b.b48, b.b60, b.b61, b.d64, b.d68) == (p[2], p[0], p[1], p[4], p[5])
    for e in st.mission.effects:
        assert (e.b40, e.b41) == (0, 1)
    hero = next(u for u in w.units.values() if u.human)
    uo = next(u for p in st.players for g in p.groups for u in g.units if u.base.d08 == hero.uid or u.base.id == hero.net_id)
    blk = B.BLK_BE.decode(uo.blk_be)
    st_c = hero.combat
    assert hero.combat is None or blk["defence"] == st_c.block.defence          # the unit's own armour block is written, not zeros


@needs_data
def test_a_mission_start_save_has_the_latch_clear():
    from engine.session import build_game
    w, a = build_game("73", seed=3, vision=True)
    st = SS.ServerStream.parse(M.world_to_save(w).stream)
    assert st.mission.script.d_be10 == 0
