"""Drawing units and ground piles (G3a): synthetic depth, animation-clock and minimap-dot tests,
always run; E5 parity and the screenshot goldens are in tests/test_engine_objects.py.
Spec: docs/engine/rendering.md sections 2 and 13."""

import os

import numpy as np
import pytest

from engine.sim import CommandQueue, Simulation, tick_period_ms
from engine.view import Camera, DrawOptions, build_draw_list
from engine.view import drawlist as dl
from engine.view.minimap import MinimapGeometry, dot_box, draw_unit_dots
from engine.world import ITEM_ID_BASE, UNIT_ID_BASE, Item, MapObject, Player, Unit, World

from helpers import GFS, aset_of, sprite_file, unit_type
from test_engine_objects import H, W, FakeAssets, assets as object_assets, cam, flat_world, obj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UnitAssets(FakeAssets):
    def __init__(self, units, **kw):
        super().__init__(**kw)
        self.units = units

    def unit_set(self, tid):
        return self.units.get(tid)

    def sprite(self, path):
        return sprite_file(6)


def uassets(**kw):
    base = object_assets()
    return UnitAssets({1: aset_of(unit_type(1, IdlePhases=4, IdleAnimTime=[1, 1, 1, 1],
                                            IdleAnimFrame=[0, 1, 2, 3])),
                       2: aset_of(unit_type(2, Z=96))},
                      objects=base.objects, structures=base.structures)


def unit(uid, x, y, type_id=1, owner=1, **kw):
    return Unit(UNIT_ID_BASE + uid, type_id, owner, x, y, uid=uid, hp=1, hp_max=1, **kw)


def world_with(*ents):
    w = flat_world()
    w.players[1] = Player(1, 3, "p")
    for e in ents:
        if isinstance(e, Unit):
            w.add_unit(e)
        elif isinstance(e, Item):
            w.add_item(e)
        else:
            w.add_object(e)
    return w


def order(w, opts=DrawOptions(shadows=False)):
    items = build_draw_list(w, cam(), 0, uassets(), opts)
    seen = []
    for i in items:
        if i.kind == "sprite" and i.blend != "half" and i.entity not in seen:
            seen.append(i.entity)
    return seen


# --- depth ---------------------------------------------------------------------------------

def test_unit_behind_and_in_front_of_an_object():
    o = obj(1, 10, 10)
    behind, front = unit(1, 10, 9), unit(2, 10, 11)
    assert order(world_with(o, behind, front)) == [behind.id, o.id, front.id]


def test_same_cell_structure_then_unit_then_object():
    o = obj(1, 10, 10)
    u = unit(1, 10, 10)
    assert order(world_with(o, u)) == [u.id, o.id]


def test_pile_before_unit_flyer_last_and_columns_right_to_left():
    pile = Item(ITEM_ID_BASE, 10, 10)
    u = unit(1, 10, 10)
    fl = unit(2, 10, 5, type_id=2)              # flyer: pass 7, after everything in view
    right, left = unit(3, 12, 8), unit(4, 8, 8)
    w = world_with(u, pile, fl, right, left)
    got = order(w)
    assert got[-1] == fl.id
    assert got.index(pile.id) < got.index(u.id)
    assert got.index(right.id) < got.index(left.id)         # columns right to left


def test_large_unit_is_filed_under_its_footprint_centre_cell():
    u = unit(1, 10, 10)
    assert dl.unit_position(u, 1)[2:] == (10, 10)
    assert dl.unit_position(u, 2)[2:] == (11, 11)            # pos - 0x80 + 2 * 0x80
    assert dl.unit_position(u, 3)[2:] == (11, 11)


def test_unit_facing_team_colour_and_flyer_altitude():
    a = uassets()
    w = world_with(unit(1, 10, 10, facing=0x40), unit(2, 12, 10, type_id=2))
    items = [i for i in build_draw_list(w, cam(), 0, a, DrawOptions(shadows=False)) if i.kind == "sprite"]
    ground, flyer = items[0], items[1]
    assert ground.remap == (3, 0) and ground.sprite[0] == "unit"
    ref = a.units[1].frame_at("idle", 4, 0)
    assert ground.frame == ref.index and ground.mirrored == ref.mirrored
    # same footprint, the flyer is raised by U+0x10 = 16 px and its anchor row differs only by that
    w2 = world_with(unit(1, 10, 10, type_id=2))
    solo = build_draw_list(w2, cam(), 0, a, DrawOptions(shadows=False))[0]
    w3 = world_with(unit(1, 10, 10, type_id=1))
    base = build_draw_list(w3, cam(), 0, a, DrawOptions(shadows=False))[0]
    assert base.sy - solo.sy == dl.FLYER_ALTITUDE


def test_flyer_shadow_is_unsheared_and_stays_on_the_ground():
    a = uassets()
    w = world_with(unit(1, 10, 10, type_id=2))
    items = build_draw_list(w, cam(), 0, a, DrawOptions())
    sh = [i for i in items if i.kind == "shadow"]
    spr = [i for i in items if i.kind == "sprite" and i.blend != "half"]
    assert sh and sh[0].shear == 0 and sh[0].depth[0] == dl.PASS_FLYER_SHADOW
    assert spr[0].depth[0] == dl.PASS_FLYER and items.index(sh[0]) < items.index(spr[0])
    assert (spr[0].sy + dl.FLYER_ALTITUDE) - sh[0].sy == 0       # same anchor row, sprite raised


def test_pile_frame_from_gold():
    assert [dl.backpack_frame(g) for g in (0, 5, 100, 5000, 10000, 10 ** 9)] == [0, 0, 2, 3, 4, 5]


def test_units_option_off_hides_units_and_piles():
    w = world_with(unit(1, 10, 10), Item(ITEM_ID_BASE, 12, 12, gold=100))
    assert order(w, DrawOptions(shadows=False, units=False)) == []


# --- animation time comes from the simulation ----------------------------------------------------

def run_loop(world, fps, seconds, speed=4):
    """The accumulator main loop of docs/engine/architecture.md section 5 at `fps` render
    rate; returns {tick: draw items of the unit sprite seen at that tick} from the frames."""
    sim, queue = Simulation(world), CommandQueue()
    period, acc, seen, a = tick_period_ms(speed), 0.0, {}, uassets()
    for _ in range(int(seconds * fps)):
        acc += 1000.0 / fps
        while acc >= period:
            sim.step(queue.drain())
            acc -= period
        items = build_draw_list(world, cam(), world.tick, a, DrawOptions(shadows=False))
        seen[world.tick] = [(i.frame, i.mirrored) for i in items if i.kind == "sprite"]
    return seen


def test_frames_depend_on_the_tick_not_on_the_render_rate():
    mk = lambda: world_with(unit(1, 10, 10, facing=0x80), unit(2, 14, 12, facing=0x30))
    s30, s60 = run_loop(mk(), 30, 6), run_loop(mk(), 60, 6)
    common = sorted(set(s30) & set(s60))
    assert len(common) > 60 and all(s30[t] == s60[t] for t in common)
    a = uassets().units[1]
    for t in common:                                      # and both equal the direct frame_at
        for (frame, mir), u in zip(s30[t], (0x80, 0x30)):
            ref = a.frame_at("idle", u >> 4, t)
            assert (frame, mir) == (ref.index, ref.mirrored)
    assert len({tuple(v) for v in s30.values()}) > 1     # the idle animation does advance


def test_action_start_tick_offsets_the_animation():
    a = uassets()
    w = world_with(unit(1, 10, 10, action_start_tick=3))
    w.tick = 7
    it = build_draw_list(w, cam(), w.tick, a, DrawOptions(shadows=False))[0]
    assert it.frame == a.units[1].frame_at("idle", 8, 4).index


# --- minimap dots ----------------------------------------------------------------------------

def test_minimap_dot_boxes_follow_the_scale_rule():
    g = MinimapGeometry(80, 80)                            # k = 1: 2 x 2 dots
    assert dot_box(g, 8, 8) == (0, 0, 1, 1) and dot_box(g, 10, 9) == (4, 2, 5, 3)
    assert dot_box(g, 7, 20) is None and dot_box(g, 72, 20) is None
    g = MinimapGeometry(200, 200)                          # k = -1: one pixel, >> 1
    assert dot_box(g, 8, 8) == (0, 0, 0, 0) and dot_box(g, 20, 30) == (6, 11, 6, 11)
    g = MinimapGeometry(144, 144)                          # k = 0
    assert dot_box(g, 20, 30) == (12, 22, 12, 22)


def test_unit_dots_use_the_owner_colour_row():
    w = World(np.zeros((80, 80), np.uint16), np.zeros((80, 80), np.int8))
    w.players[1], w.players[2] = Player(1, 0, "a"), Player(2, 5, "b")
    w.add_unit(unit(1, 10, 10, owner=1))
    w.add_unit(unit(2, 20, 20, owner=2))
    colors = np.arange(48, dtype=np.uint8).reshape(16, 3)
    img = np.zeros((128, 128, 3), np.uint8)
    draw_unit_dots(img, MinimapGeometry(80, 80), w, colors)
    assert (img[4:6, 4:6] == colors[0]).all() and (img[24:26, 24:26] == colors[5]).all()
    assert (img != 0).any(axis=2).sum() == 8
