"""The Retreat command (key R / bar button 8, cmd 0x14) and the retreat mode (Ctrl+W, message 0x46 sub 1); docs/engine/simulation.md 9.3.
Synthetic worlds, always run."""

from engine.sim import CommandQueue, MoveUnits, Retreat, SelectUnits, SetRetreatMode, Simulation, Stop, replay
from engine.sim.movement import RETREAT_ORDER
from engine.ui import OrderInput
from engine.ui import bar as bar_mod
from test_engine_ai import hero, run, unit, world
from test_engine_orders_determinism import PERIOD, TOTAL_MS, drive, frame_times  # noqa: F401


def setup(enemy_at=(25, 24)):
    w = world()
    h = hero(w, 1, 20, 24)
    e = unit(w, 2, enemy_at[0], enemy_at[1], 2, 0, hp=500, scan=0, lo=0) if enemy_at else None
    return w, h, e


# --- the command: FUN_00419e72 -> msg 0x14 -> FUN_00570c31 / FUN_0056da4f ----------------------------------------------------------

def test_retreat_sets_order_0x16_group_order_0_mode_0_and_keeps_the_anchor():
    w, h, _ = setup(None)
    sim = Simulation(w)
    sim.step([MoveUnits(1, (h.id,), (35, 24))])
    run(sim, 6)
    assert h.mode_go and h.order == 1
    h.anchor = (7, 7)
    sim.step([Retreat(1, (h.id,))])
    g = w.groups[h.order_group]
    assert g.order == 0 and h.order == RETREAT_ORDER == 0x16
    assert not (h.mode_go or h.mode_attack or h.mode_cast or h.mode_look) and h.anchor == (7, 7)


def test_a_new_command_ends_the_retreat():
    w, h, _ = setup()
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    sim.step([Stop(1, (h.id,))])
    assert h.order == 0xC and w.groups[h.order_group].order == 3


# --- the executor FUN_0056c9bc, run by the group pass every 16 ticks -------------------------------------------------------------------

def test_a_hostile_within_ten_cells_makes_the_unit_walk_three_cells_away():
    w, h, e = setup((25, 24))
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 16)
    assert h.order == 0x16 and h.mode_go and h.mover.goal == (17, 24)         # 3 beyond the unit on the ray enemy -> unit
    run(sim, 30)
    assert h.x <= 17 and h.order == 0x16                                      # the order has no end of its own


def test_the_flee_repeats_while_the_hostile_stays_within_ten_cells():
    w, h, e = setup((25, 24))
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 200)
    assert h.x < 14 and h.order == 0x16            # 5 cells away at the start, 3 more per pass until it is 11+ away or hits the border clamp


def test_a_hostile_beyond_ten_cells_changes_nothing():
    w, h, e = setup((32, 24))
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 64)
    assert (h.x, h.y) == (20, 24) and not h.mode_go and h.order == 0x16


def test_flee_is_away_along_the_dominant_axis_and_clamped_to_the_border():
    w, h, e = setup((20, 18))                      # the hostile is north: the unit goes south
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 16)
    assert h.mover.goal == (20, 27)
    w = world()
    h, e = hero(w, 1, 9, 24), unit(w, 2, 11, 24, 2, 0, hp=500, scan=0, lo=0)
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 16)
    assert h.mover.goal[0] == 8                    # x - 3 = 6 is clamped to 8 (the playable border)


def test_a_dead_hostile_is_not_fled_from():
    w, h, e = setup((25, 24))
    e.hp = 0                                       # listed (dying bodies stay) but not alive
    sim = Simulation(w, ai=True)
    sim.step([Retreat(1, (h.id,))])
    run(sim, 32)
    assert not h.mode_go and h.x == 20


def test_every_unit_of_the_group_retreats():
    w, h, e = setup((25, 24))
    h2 = hero(w, 3, 21, 26)
    sim = Simulation(w)
    sim.step([Retreat(1, (h.id, h2.id))])
    run(sim, 16)
    assert h.mode_go and h2.mode_go and h.order == h2.order == 0x16 and h.order_group == h2.order_group


# --- the retreat mode: message 0x46 sub 1 -> FUN_0057393c / FUN_00573b38 --------------------------------------------------------------

def test_retreat_mode_sets_wimpy_to_a_percentage_of_max_hp_and_withdraw_to_zero():
    w, h, e = setup((25, 24))
    h.hp = 200
    sim = Simulation(w)
    for mode, want in ((1, 50), (2, 150), (0, 0), (7, 0)):
        sim.step([SetRetreatMode(1, mode)])
        assert (h.wimpy_hp, h.withdraw_hp) == (want, 0)
    assert e.wimpy_hp is None                       # another player's unit is untouched


def test_retreat_mode_makes_a_wounded_unit_leave_its_walk():
    w, h, e = setup((25, 24))
    sim = Simulation(w)
    sim.step([SetRetreatMode(1, 2)])
    h.hp = 100                                      # 20 %: below the 30 % threshold (150 of 500)
    sim.step([MoveUnits(1, (h.id,), (22, 30))])
    run(sim, 20)
    assert h.mover.goal == (17, 24) and h.order == 1


def test_default_mode_and_healthy_units_keep_their_walk():
    for mode, hp in ((0, 100), (2, 400)):
        w, h, e = setup((25, 24))
        sim = Simulation(w)
        sim.step([SetRetreatMode(1, mode)])
        h.hp = hp
        sim.step([MoveUnits(1, (h.id,), (22, 30))])
        run(sim, 20)
        assert h.mover.goal == (22, 30), (mode, hp)


# --- the UI: R key and bar button 8 ------------------------------------------------------------------------------------------------

def make_input(state="own"):
    return OrderInput(1, 640, lambda: (10, 11), lambda: state, 0)


def test_r_key_sends_retreat_at_once_and_clears_the_pending_mode():
    oi = make_input()
    oi.pending = 2
    assert oi.key("r") == (Retreat(1, (10, 11)), None) and oi.pending == 0
    assert make_input("foreign").key("r") == (None, None)
    assert make_input("none").key("r") == (None, None)


def test_bar_cell_8_runs_the_retreat_key():
    assert bar_mod.press(7, make_input(), False) == Retreat(1, (10, 11))
    assert bar_mod.press(7, make_input("foreign"), False) is None


# --- replay -------------------------------------------------------------------------------------------------------------------------

def session_world():
    w, h, e = setup((26, 24))
    hero(w, 3, 21, 25)
    return w


def test_retreat_session_replays_to_the_same_hash_at_30_and_60_fps():
    ids = [u.id for u in session_world().units.values() if u.owner == 1]
    ev = [(100, ("select", ids)), (200, ("click", (30, 30))), (1500, ("key", "r")), (6000, ("key", "t")), (6600, ("key", "r"))]
    rec = drive(session_world(), 30, TOTAL_MS, inputs=(1, ev))
    n, log, want = rec.world.tick, rec.log, rec.world.dump_hash()
    assert {"Retreat", "Stop", "MoveUnits"} <= {type(c).__name__ for _, c in log}
    assert any(u.order == 0x16 for u in rec.world.units.values())
    for fps in (30, 60):
        assert drive(session_world(), fps, TOTAL_MS, log=log).world.dump_hash() == want, fps
    batch = Simulation(session_world())
    replay(batch, log, n)
    assert batch.world.dump_hash() == want
    short = Simulation(session_world())
    replay(short, [lc for lc in log if type(lc[1]).__name__ != "Retreat"], n)
    assert short.world.dump_hash() != want
