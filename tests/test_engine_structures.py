"""K6: using a structure (docs/engine/structures.md): the walk, the toggle of a switch, the position lookup quirk, no passability change, replay."""

import pytest

from engine.sim import Simulation, UseStructure
from engine.sim import structures as st
from engine.world import FLAG_DESTROYED, MapObject

from gear_helpers import world_with_hero
from helpers import have_install


def switch(w, uid, x, y, type_id=28, hp=1):
    ob = MapObject(0x6000 + uid, "structure", type_id, x, y, uid=uid, hp=hp, hp_max=1, owner=0, flags=0 if hp else FLAG_DESTROYED)
    w.add_object(ob)
    return ob


def run(sim, n):
    for _ in range(n):
        sim.step()


def test_use_walks_to_the_switch_and_toggles_it_once_per_command():
    w, u = world_with_hero()
    s = switch(w, 1, 26, 20)
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), s.id)])
    assert u.order == st.USE_ORDER and u.use_dest == (26, 20) and u.use_dist == 1
    run(sim, 300)
    assert s.hp == 0 and s.flags & FLAG_DESTROYED                 # once: not toggled back by the stand ticks
    assert u.order == 0xC and max(abs(u.x - 26), abs(u.y - 20)) == 1
    sim.step([UseStructure(1, (u.id,), s.id)])
    run(sim, 100)
    assert s.hp == 1 and not s.flags & FLAG_DESTROYED             # any use toggles back (no one-shot flag)


def test_use_does_not_touch_the_block_layer():
    w, u = world_with_hero()
    s = switch(w, 1, 26, 20)
    before = w.block.copy()
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), s.id)])
    run(sim, 300)
    assert s.hp == 0 and (w.block == before).all()                # a destroyed structure keeps its stamps (structures.md 4)


def test_other_structure_types_are_not_toggled():
    w, u = world_with_hero()
    g = switch(w, 1, 26, 20, type_id=39)                          # King's Grave: no server effect
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), g.id)])
    run(sim, 300)
    assert g.hp == 1 and u.order == 0xC


def test_the_exe_toggles_the_first_structure_near_the_hero_not_the_clicked_one():
    for clicked, expect in ((True, (1, 0)), (False, (0, 1))):
        w, u = world_with_hero()
        a = switch(w, 1, 25, 18)                                  # earlier in the list and within 2 of (x-1, y-1) of the hero's stop cell
        b = switch(w, 2, 26, 20)
        w.use_clicked = clicked
        sim = Simulation(w)
        sim.step([UseStructure(1, (u.id,), b.id)])
        run(sim, 300)
        assert (a.hp, b.hp) == expect


def test_unknown_id_and_map_objects_drop_the_command():
    w, u = world_with_hero()
    w.add_object(MapObject(0x10000, "object", 5, 30, 30))
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), 0x7777), UseStructure(1, (u.id,), 0x10000)])
    assert u.order != st.USE_ORDER


def test_use_replays_to_the_same_hash():
    def play():
        w, u = world_with_hero()
        s = switch(w, 1, 28, 24)
        sim = Simulation(w)
        sim.step([UseStructure(1, (u.id,), s.id)])
        run(sim, 300)
        return w.dump_hash(), s.hp
    assert play() == play() and play()[1] == 0


def test_approach_by_footprint_width():
    big = MapObject(1, "structure", 16, 10, 10, footprint=tuple((dx, dy, True) for dx in range(3) for dy in range(3)))
    wide = MapObject(2, "structure", 16, 10, 10, footprint=tuple((dx, 0, True) for dx in range(5)))
    one = MapObject(3, "structure", 28, 10, 10)
    assert st.approach(one) == ((10, 10), 1) and st.approach(big) == ((11, 11), 2) and st.approach(wide) == ((12, 12), 3)


def test_the_town_cursor_over_a_structure_sends_the_use_command():
    from engine.ui import OrderInput
    from engine.ui.cursor import CursorState as S
    o = OrderInput(1, 640, lambda: (4, 5), lambda: "own")
    what, cmd = o.release(S.TOWN, (3, 4), 0x6007)
    assert what == "order" and cmd == UseStructure(1, (5,), 0x6007)


# --- the switch puzzles (maps 96 and 103; solutions: structures.md 6) ------------------------------------------------------------------

def _use(w, sim, hero, uid, stand=None):
    """Debug solve step: put the hero on `stand` (cell offsets tried in order) next to switch `uid`, order the use and run until the hero stands."""
    from engine.sim import triggers as T
    sw = next(o for o in w.objects.values() if o.kind == "structure" and o.uid == uid)
    for a, b in stand or ((1, 0), (0, 1), (-1, 0), (0, -1)):
        if T.teleport(w, hero, sw.x + a, sw.y + b):
            break
    sim.step([UseStructure(1, (hero.id,), sw.id)])
    for _ in range(2500):
        hero.hp = 300
        sim.step()
        if hero.order == 0xC:
            break
    assert hero.order == 0xC, "switch %d: the hero never arrived" % uid
    return sw


def _build(n):
    from engine.session import build_game
    w, _ = build_game(str(n), seed=1)
    sim = Simulation(w, triggers=True)
    return w, sim, next(u for u in w.units.values() if u.owner == 1 and u.human)


def _thrown(w):
    return sorted(o.uid for o in w.objects.values() if o.kind == "structure" and o.type_id in (28, 29) and o.hp == 0)


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_96_both_switches_open_the_teleporter():
    w, sim, hero = _build(96)
    assert (102, 34) not in w.cell_effects
    _use(w, sim, hero, 2)
    assert _thrown(w) == [2] and (102, 34) not in w.cell_effects
    _use(w, sim, hero, 3)
    assert _thrown(w) == [2, 3]
    for _ in range(40):
        hero.hp = 300
        sim.step()
    assert (102, 34) in w.cell_effects                      # trigger "Teleporter opens": check 21 on both != 1 -> instant 25 (Set trap)


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_103_the_two_puzzles_drop_the_quest_items():
    w, sim, hero = _build(103)
    assert not w.items
    stand = {7: ((1, 1), (1, 0)), 9: ((1, 1),)}              # the exe's lookup hits 7 only from the east side and 9 only from the SE cell (structures.md 6)
    for uid in (4, 6, 7, 9, 14, 16):
        _use(w, sim, hero, uid, stand.get(uid))
    assert _thrown(w) == [4, 6, 7, 9, 14, 16]
    for _ in range(80):
        hero.hp = 300
        sim.step()
    assert sorted((p.x, p.y) for p in w.items.values()) == [(24, 77), (75, 71)]       # Drop all of units 132 and 131 (triggers 27 and 30)


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_103_a_wrong_switch_keeps_the_reward_away():
    w, sim, hero = _build(103)
    for uid in (1, 4, 6, 7, 9):
        _use(w, sim, hero, uid, {7: ((1, 1), (1, 0)), 9: ((1, 1),)}.get(uid))
    for _ in range(80):
        hero.hp = 300
        sim.step()
    assert (24, 77) not in {(p.x, p.y) for p in w.items.values()}


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_103_session_replays_to_the_same_hash():
    w, sim, hero = _build(103)
    sw = next(o for o in w.objects.values() if o.kind == "structure" and o.uid == 6)
    from engine.sim import triggers as T
    assert T.teleport(w, hero, 22, 65)                      # a use walk to a blocked cell is bounded (structures.md 2.1): start near
    sim.step([UseStructure(1, (hero.id,), sw.id)])
    for _ in range(6000):
        hero.hp = 300
        sim.step()
    assert _thrown(w) == [6]
    w2, sim2, _ = _build(103)
    h2 = next(u for u in w2.units.values() if u.owner == 1 and u.human)
    assert T.teleport(w2, h2, 22, 65)
    by_tick = {}
    for tick, cmd in sim.log:
        if w2.ai_on and getattr(cmd, "ai", False):
            continue                                        # the AI regenerates its commands
        by_tick.setdefault(tick, []).append(cmd)
    for i in range(6001):                                   # the same unkillable hero as the first run (the hp is not a command)
        if i:
            h2.hp = 300
        sim2.step(by_tick.get(w2.tick, ()))
    assert w2.dump_hash() == w.dump_hash()


def test_state_f_has_no_action_of_its_own_and_the_hero_faces_the_structure():
    """structures.md 3.1: the exe sends no message for state 0xf; the draw keeps the action of the last step / turn (idle once the unit stops) and the
    facing is the facing to the destination cell."""
    from engine.sim import combat, movement as mv
    w, u = world_with_hero()
    s = switch(w, 1, 26, 20)
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), s.id)])
    for _ in range(300):
        sim.step()
        if u.state == st.USE_STATE:
            break
    assert u.state == st.USE_STATE
    assert u.facing == combat.octant(st.foot(u), st.Foot(*u.use_dest))
    sim.step()
    assert u.state == mv.IDLE_STATE and u.action == mv.IDLE


# --- the real stop cell of a use walk (structures.md 2.1, simulation.md 7.1) -----------------------------------------------------------

def _stop(w, sim, hero, cell, uid, ticks=3000):
    from engine.sim import triggers as T
    assert T.teleport(w, hero, *cell) and (hero.x, hero.y) == cell
    sw = next(o for o in w.objects.values() if o.kind == "structure" and o.uid == uid)
    sim.step([UseStructure(1, (hero.id,), sw.id)])
    for _ in range(ticks):
        hero.hp = 300
        sim.step()
        if hero.order == 0xC:
            break
    return (hero.x - sw.x, hero.y - sw.y), _thrown(w)


def test_the_walk_targets_the_blocked_cell_and_stops_on_the_first_ring_cell_it_reaches():
    """FUN_00555411(unit, dest, 1): the planner target is the structure's own (blocked) cell; the fallback is the cheapest labelled cell of its first
    ring, so the hero stops on the side it comes from (no 'nearest free cell' search)."""
    for start, stop in (((14, 20), (-1, 0)), ((34, 20), (1, 0)), ((26, 12), (0, -1)), ((20, 14), (-1, -1)), ((32, 28), (1, 1)), ((20, 26), (-1, 1))):
        w, u = world_with_hero()
        s = switch(w, 1, 26, 20)
        sim = Simulation(w)
        from engine.sim import triggers as T
        assert T.teleport(w, u, *start) and (u.x, u.y) == start
        sim.step([UseStructure(1, (u.id,), s.id)])
        assert u.use_goal == (26, 20)
        run(sim, 400)
        assert u.order == 0xC and s.hp == 0
        assert max(abs(u.x - 26), abs(u.y - 20)) == 1 and (u.x - 26, u.y - 20) == stop


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_103_the_approach_side_decides_which_switch_is_thrown():
    """structures.md 6: the hero stops on the first ring cell of its own side and the exe's lookup (x-1, y-1) then picks the first switch within 2."""
    w, sim, hero = _build(103)
    # (start cell, switch uid) -> (stop offset, the one switch thrown)
    for start, uid, stop, thrown in (((33, 65), 7, (1, -1), [7]),         # from the NE: the east side of 7
                                     ((17, 65), 7, (-1, -1), [6]),        # from the NW: the west side of 7 is captured by 6
                                     ((36, 89), 9, (1, 1), [9]),          # from the SE: the SE cell of 9
                                     ((36, 73), 9, None, [2]),             # from the NE: the NE cell of 9 is captured by 2
                                     ((20, 89), 9, (-1, 1), [3])):        # from the SW: the SW cell of 9 is captured by 3
        for o in w.objects.values():
            if o.kind == "structure" and o.type_id in (28, 29):
                o.hp, o.flags = 1, o.flags & ~FLAG_DESTROYED
        sw = next(o for o in w.objects.values() if o.kind == "structure" and o.uid == uid)
        from engine.sim import triggers as T
        if not T.teleport(w, hero, *start) or (hero.x, hero.y) != start:
            pytest.skip("start cell %s not free" % (start,))
        sim.step([UseStructure(1, (hero.id,), sw.id)])
        for _ in range(3000):
            hero.hp = 300
            sim.step()
            if hero.order == 0xC:
                break
        assert _thrown(w) == thrown, (start, uid)
        if stop is not None:
            assert (hero.x - sw.x, hero.y - sw.y) == stop


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_103_a_far_use_walk_to_the_blocked_switch_fails_like_the_exe():
    """The static search to a blocked target is bounded (dist + min(5, dist/4) levels; unbounded only to a free cell, FUN_0054d76e): from the hero's start
    the detour is too long, so the use order ends without a step; a normal move first brings the hero near."""
    w, sim, hero = _build(103)
    start = (hero.x, hero.y)
    sw = next(o for o in w.objects.values() if o.kind == "structure" and o.uid == 1)
    sim.step([UseStructure(1, (hero.id,), sw.id)])
    for _ in range(600):
        hero.hp = 300
        sim.step()
    assert (hero.x, hero.y) == start and _thrown(w) == []
