"""L10e-B: mission saves, `World` <-> `game%d.sav` with the loaded flag 1 (engine/missionsave.py; docs/engine/save.md, docs/formats/saves.md 7).

Invariants (game files, skipped without the install): save -> load -> N ticks == N ticks without a save (world-dump hash and the full engine state), mid-fight with
spells, effects, carriers, corpses, piles and fog; save -> load -> save is byte-identical; a mission-start save restarts the mission; the objective oracle still wins
after a mid-mission reload; a save without the engine extension (the original's) loads through the stream.  The codec tests are synthetic and always run."""

import json
import zlib
from collections import Counter

import numpy as np
import pytest

from allods2.formats import saves as S
from allods2.formats import serverstream as SS
from engine import missionsave as M
from engine import world as W
from engine.rng import Rng

from helpers import GFS, needs_data


# --- the generic state codec (always) -----------------------------------------------------------------------------------------------------------

def roundtrip(obj, unit_type=None):
    d = json.loads(json.dumps(M.Encoder().enc(obj)))
    return M.Decoder(unit_type).dec(d)


def test_codec_keeps_tuples_dicts_sets_bytes_arrays():
    v = {"a": (1, 2, (3,)), (4, 5): [None, True, "x"], "s": {3, 1}, "b": bytearray(b"\x00\xff"), "c": Counter({("k", 1): 2}),
         "n": np.arange(6, dtype=np.uint16).reshape(2, 3)}
    back = roundtrip(v)
    assert back["a"] == (1, 2, (3,)) and back[(4, 5)] == [None, True, "x"] and back["s"] == {1, 3}
    assert back["b"] == bytearray(b"\x00\xff") and isinstance(back["b"], bytearray) and back["c"] == Counter({("k", 1): 2})
    assert back["n"].dtype == np.uint16 and (back["n"] == v["n"]).all()


def test_codec_shares_dataclass_objects_and_keeps_frozen_ones():
    u = W.Unit(1, 2, 1, 5, 6)
    u.effects = [W.Effect(3, 1, 2, 4, 5, caster=9)]
    back = roundtrip({"units": {1: u}, "again": [u, u], "rng": Rng(77)})
    assert back["again"][0] is back["again"][1] is back["units"][1]
    assert back["units"][1].effects[0] == u.effects[0] and back["rng"].state == 77
    assert back["units"][1].mover.turn_rate == u.mover.turn_rate and back["units"][1].fx == u.fx


def test_codec_refuses_what_it_cannot_save():
    with pytest.raises(TypeError):
        M.Encoder().enc(object())


def test_the_rng_state_rides_in_the_tail_of_the_debug_block():
    """DECISION (saves.md 7): the stream has no RNG word (6.11); the engine's LCG state is the last 8 bytes of the 400-byte debug block."""
    s = SS.ServerStream(loaded=1, mission=SS.Mission())
    import struct
    dbg = bytearray(SS.DEBUG_SIZE)
    struct.pack_into("<II", dbg, SS.DEBUG_SIZE - 8, M.RNG_MAGIC, 0xDEADBEEF)
    s.debug = bytes(dbg)
    back = SS.ServerStream.parse(s.pack())
    assert struct.unpack_from("<II", back.debug, SS.DEBUG_SIZE - 8) == (M.RNG_MAGIC, 0xDEADBEEF) and back.debug[:SS.DEBUG_SIZE - 8] == bytes(SS.DEBUG_SIZE - 8)


def test_fog_runs_round_trip():
    class F:
        pass
    w = F()
    w.fog = np.zeros((4, 5), np.uint16)
    w.fog[1, 2:4] = 0x8000
    w.fog[3, :] = 0xC000
    first, runs = M.fog_runs(w)
    assert first == 0 and sum(runs) == 20
    out = np.zeros((4, 5), np.uint16)
    M.apply_fog_runs(out, first, runs)
    assert ((out >> 15) == (w.fog >> 15)).all()


def test_client_state_carries_the_engine_blob_through_the_reg_tree():
    st = S.ClientState(in_battle=1, engine=bytes(range(256)) * 7 + b"abc")
    tail = S.ClientTail.new("d", st)
    back = S.parse_tail(S.pack_tail(tail), 0)
    assert back.state.engine == st.engine and back.state.in_battle == 1
    assert S.ClientState().engine == b"" and S.ClientTail.new("d").state.engine == b""


# --- scenarios on the install ---------------------------------------------------------------------------------------------------------------------

def fight(name="73", seed=3):
    """The party of map `name` dropped next to the nearest hostile unit, the mage with every spell: a schedule of casts and attacks."""
    from engine import objective as O
    from engine.session import build_game
    from engine.sim import AttackUnit, CastSpell
    w, a = build_game(name, seed=seed, vision=True)
    heroes = [u for u in w.units.values() if w.players[u.owner].human]
    mage = next((u for u in heroes if u.mana_max > 0), heroes[0])
    mage.spellbook = sum(1 << n for n in range(1, 30))
    mage.mana = mage.mana_max = 900
    foes = [u for u in w.units.values() if u.owner != 1 and O.at_war(w, 1, u.owner) and u.hp > 0]
    foe = min(foes, key=lambda f: (f.x - mage.x) ** 2 + (f.y - mage.y) ** 2)
    for i, h in enumerate(heroes):
        O._adjacent(w, h, foe.x, foe.y, radius=3 + i)
        h.hp = h.hp_max = max(h.hp_max, 400)
    free = next((mage.x + dx, mage.y + dy) for dx in (1, -1, 2, -2) for dy in (0, 1, -1) if not w.blocked(mage.x + dx, mage.y + dy) and not w.units_at(mage.x + dx, mage.y + dy))
    near = sorted(foes, key=lambda f: (f.x - mage.x) ** 2 + (f.y - mage.y) ** 2)[:6]
    sch = {1: [AttackUnit(1, (h.id,), near[0].id) for h in heroes if h is not mage],
           2: [CastSpell(1, (mage.id,), 25, cell=free)], 60: [CastSpell(1, (mage.id,), 27, cell=(mage.x, mage.y))],
           90: [CastSpell(1, (mage.id,), 6, cell=(near[0].x, near[0].y))], 130: [CastSpell(1, (mage.id,), 2, cell=(near[1].x, near[1].y))],
           170: [CastSpell(1, (mage.id,), 3, cell=(near[2].x, near[2].y))], 200: [CastSpell(1, (mage.id,), 1, target_id=near[3].id)],
           240: [CastSpell(1, (mage.id,), 20, target_id=heroes[0].id)]}
    return w, a, sch


def make_sim(w):
    from engine.sim import Simulation
    return Simulation(w, triggers=True, vision=True)


def run(sim, sch, n):
    for _ in range(n):
        sim.step(sch.get(sim.world.tick, ()))


def state_json(w):
    return json.dumps(M.capture(w), sort_keys=True, separators=(",", ":"))


def reload(w, a, **kw):
    data = M.world_to_save(w, **kw).pack()
    return M.world_from_save(data, a), data


@needs_data
@pytest.mark.parametrize("save_at", [0, 37, 100, 171, 250, 420])
def test_resume_equals_no_save_in_a_fight(save_at):
    """Map 73, the mage casts Shield / Summon / Poison Cloud / Fire Ball / Wall of Fire / Fire Arrow / Bless while the party fights: carriers, cell effects, effect lists,
    corpses and piles exist by the later save ticks."""
    w, a, sch = fight()
    sim = make_sim(w)
    run(sim, sch, save_at)
    lm, data = reload(w, a)
    w2 = lm.world
    assert lm.exact and w2.dump_hash() == w.dump_hash() and state_json(w2) == state_json(w)
    sim2 = make_sim(w2)
    for _ in range(200):
        cmds = sch.get(w.tick, ())
        sim.step(cmds)
        sim2.step(cmds)
    assert w2.dump_hash() == w.dump_hash()
    assert state_json(w2) == state_json(w)                         # every engine field, not only the dump


@needs_data
def test_the_fight_exercises_what_the_task_names():
    w, a, sch = fight()
    sim = make_sim(w)
    seen = set()
    for _ in range(420):
        sim.step(sch.get(w.tick, ()))
        seen |= {n for n, ok in (("carrier", w.carriers), ("cell_fx", w.cell_fx), ("effect", any(u.effects for u in w.units.values())), ("corpse", w.corpses),
                                 ("pile", w.items), ("fog", w.fog is not None), ("summon", any(u.master for u in w.units.values())),
                                 ("cell_trap", w.cell_effects)) if ok}
    assert seen >= {"carrier", "cell_fx", "effect", "corpse", "pile", "fog", "summon"}


@needs_data
def test_save_load_save_is_byte_identical():
    w, a, sch = fight()
    sim = make_sim(w)
    run(sim, sch, 150)
    lm, data = reload(w, a)
    assert M.world_to_save(lm.world).pack() == data


@needs_data
@pytest.mark.parametrize("name,ticks", [("86", 200), ("32", 300), ("40", 160), ("63", 100), ("10", 220)])
def test_resume_on_several_maps(name, ticks):
    from engine.session import build_game
    w, a = build_game(name, seed=2, vision=True)
    sim = make_sim(w)
    run(sim, {}, ticks)
    lm, data = reload(w, a)
    sim2 = make_sim(lm.world)
    run(sim, {}, 250)
    run(sim2, {}, 250)
    assert lm.world.dump_hash() == w.dump_hash() and state_json(lm.world) == state_json(w)
    assert M.world_to_save(lm.world).pack() == M.world_to_save(w).pack()


@needs_data
def test_every_campaign_map_resumes_exactly():
    """46 maps: 70 ticks, save, load, 40 more ticks: the dump hash and the re-save agree (the squads the script keeps awake, the build report, the party ...)."""
    import os
    from allods2.cli import campaign_maps
    from engine.session import build_game
    for p in campaign_maps(GFS):
        name = os.path.basename(p).rsplit(".", 1)[0]
        w, a = build_game(name, seed=1, vision=True)
        sim = make_sim(w)
        run(sim, {}, 70)
        lm, _ = reload(w, a)
        sim2 = make_sim(lm.world)
        run(sim, {}, 40)
        run(sim2, {}, 40)
        assert lm.world.dump_hash() == w.dump_hash(), name
        assert M.world_to_save(lm.world).pack() == M.world_to_save(w).pack(), name


@needs_data
def test_the_selection_the_view_and_the_fog_bits_come_back():
    w, a, sch = fight()
    sim = make_sim(w)
    run(sim, sch, 60)
    hero = w.players[1].main_hero
    w.players[1].selection = (hero,)
    st = S.ClientState(view_x=1234, view_y=567, groups={1: [hero]}, spellbook_open=1)
    lm, data = reload(w, a, client_state=st)
    assert lm.client_state.view_x == 1234 and lm.client_state.groups == {1: [hero]} and lm.client_state.in_battle == 1
    assert lm.world.players[1].selection == (hero,)
    save = S.parse_save(data)
    first, runs = M.fog_runs(w)
    assert save.tail.state.fog_first_state == first and save.tail.state.fog_data == runs and sum(runs) == w.width * w.height
    assert (lm.world.fog == w.fog).all()


@needs_data
def test_a_mission_start_save_restarts_the_mission():
    """`game9999`: the state at the mission entry; loading it gives the world a fresh start gives (tick 0, the party at the drop cell)."""
    from engine.session import build_game
    w, a = build_game("86", seed=5, vision=True)
    data = M.world_to_save(w).pack()
    sim = make_sim(w)
    run(sim, {}, 120)                                               # the player plays on, then loads the restart save
    lm = M.world_from_save(data, a)
    fresh, _ = build_game("86", seed=5, vision=True)
    assert lm.world.tick == 0 and lm.world.dump_hash() == fresh.dump_hash()
    sim2, simf = make_sim(lm.world), make_sim(fresh)
    run(sim2, {}, 200)
    run(simf, {}, 200)
    assert lm.world.dump_hash() == fresh.dump_hash()


@needs_data
@pytest.mark.parametrize("name", ["86", "30", "93", "42", "10", "32"])
def test_the_objective_oracle_wins_after_a_mid_mission_reload(name):
    from engine import objective as O
    from engine.session import build_game
    w, a = build_game(name, seed=1)
    sim = make_sim(w)
    run(sim, {}, 96)
    lm, _ = reload(w, a)
    r = O.run(name, GFS, world=lm.world)
    assert r["result"] == "won", (r["result"], r["edits"], r["stuck"])


# --- the stream (the exe's view) --------------------------------------------------------------------------------------------------------------------

@needs_data
def test_the_stream_holds_players_groups_units_structures_piles_and_script():
    w, a, sch = fight()
    sim = make_sim(w)
    run(sim, sch, 250)
    save = M.world_to_save(w, description="x")
    st = SS.ServerStream.parse(save.stream)
    assert st.loaded == 1 and st.tick == w.tick and st.block == (w.tick + 1) >> 4
    assert {p.w04 for p in st.players} == set(w.players)
    n = len(w.units) + len(w.corpses) + (len(w.script.phased) if w.script else 0)
    assert len(st.units) == n == len(st.container)
    assert len(st.mission.buildings) == sum(1 for o in w.objects.values() if o.kind != "object")
    assert len(st.mission.sacks) == len(w.items) and len(st.mission.effects) == len(w.carriers)
    assert st.mission.script.variables == tuple(w.script.values) and st.mission.script.fired_flags == tuple(w.script.fired)
    hero = next(u for p in st.players if p.human for u in p.units if u.hum is not None)
    mine = w.units[0x6000 + hero.base.d08]
    assert (hero.base.pos["cell_x"], hero.base.pos["cell_y"]) == (mine.x, mine.y) and hero.words[8] == mine.hp & 0xFFFF
    import struct
    assert struct.unpack_from("<II", st.debug, SS.DEBUG_SIZE - 8) == (M.RNG_MAGIC, w.rng.state)
    assert SS.ServerStream.parse(st.pack()).pack() == st.pack()


@needs_data
def test_a_save_without_the_extension_loads_through_the_stream():
    """The original's saves carry no engine blob: the world is rebuilt from the stream (units, orders, items, effects, groups, script values, fog), derived state
    (cell slots, effect masks, the compiled script) rebuilt; what the exe never stores (RNG, the script's pass counters, animation starts) takes its constructor value."""
    w, a, sch = fight()
    sim = make_sim(w)
    run(sim, sch, 150)
    save = M.world_to_save(w)
    state = save.tail.state
    state.engine = b""
    plain = S.SaveGame(save.stream, save.tail.with_state(state)).pack()
    lm = M.world_from_save(plain, a)
    w2 = lm.world
    assert not lm.exact and w2.tick == w.tick
    assert set(w2.units) == set(w.units) and set(w2.corpses) == set(w.corpses)
    for i, u in w.units.items():
        v = w2.units[i]
        assert (v.x, v.y, v.sub_x, v.sub_y, v.facing, v.hp, v.hp_max, v.mana, v.owner, v.order, v.state, v.brain_order) == \
               (u.x, u.y, u.sub_x, u.sub_y, u.facing, u.hp, u.hp_max, u.mana, u.owner, u.order, u.state, u.brain_order)
        assert [(e.id, e.kind, e.value, e.ticks) for e in v.effects] == [(e.id, e.kind, e.value, e.ticks) for e in u.effects]
        assert v.effect_mask == u.effect_mask and v.skills == u.skills and v.carried == u.carried and v.target == u.target
    assert w2.script.values == w.script.values and bytes(w2.script.fired) == bytes(w.script.fired)
    assert sorted((i.x, i.y, i.gold, i.codes) for i in w2.items.values()) == sorted((i.x, i.y, i.gold, i.codes) for i in w.items.values())
    assert [o.hp for o in w2.objects.values()] == [o.hp for o in w.objects.values()]
    assert w2.check_consistency() == []
    sim2 = make_sim(w2)
    run(sim2, sch, 150)                                              # it plays on
    assert w2.tick == w.tick + 150


@needs_data
def test_a_stream_only_load_still_reaches_the_objective():
    from engine import objective as O
    from engine.session import build_game
    w, a = build_game("86", seed=1)
    run(make_sim(w), {}, 96)
    save = M.world_to_save(w)
    state = save.tail.state
    state.engine = b""
    lm = M.world_from_save(S.SaveGame(save.stream, save.tail.with_state(state)).pack(), a)
    assert O.run("86", GFS, world=lm.world)["result"] == "won"
