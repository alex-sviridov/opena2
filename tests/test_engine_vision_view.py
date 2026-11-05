"""Fog of war in the view (docs/engine/vision.md 2-3): hidden units, piles and structures are not drawn or pickable; the minimap blocks; the update cost
on the largest map; goldens.  Synthetic tests always run, the rest needs the install."""

import hashlib
import importlib.util
import json
import os
import time

import numpy as np
import pytest

from allods2 import vision as v
from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import vision as sv
from engine.view import Camera, DrawOptions, Minimap, build_draw_list
from engine.view import fog as vf
from allods2.graphics.palette import pack16, unpack16
from engine.view.minimap import MinimapGeometry, apply_fog
from engine.view.pick import pick_at
from engine.world import Player, World

from helpers import GFS
from test_engine_objects import cam
from test_engine_unit_draw import uassets, unit, world_with

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTS = DrawOptions(shadows=False)


def fogged(*ents, seen=()):
    """world_with(...) + fog; `seen` cells are revealed (2x2 tiles each)."""
    w = world_with(*ents)
    sv.enable(w, 1)
    v.reveal(w.fog, seen)
    return w


def sprite_entities(dlist):
    return {i.entity for i in dlist if i.kind == "sprite"}


def test_enemy_in_fog_is_not_drawn_not_picked_not_targeted():
    mine, foe = unit(1, 10, 10, owner=1), unit(2, 12, 10, owner=2)
    a = uassets()
    t = a.units[1].t
    t.SelectionX1, t.SelectionY1, t.SelectionX2, t.SelectionY2 = -10, -40, 10, 0
    w = fogged(mine, foe)                                              # nothing revealed
    d = build_draw_list(w, cam(), 0, a, OPTS)
    assert foe.id not in sprite_entities(d) and mine.id in sprite_entities(d)
    assert [p.entity for p in d.picks] == [mine.id] and [p.entity for p in d.hover_picks] == [mine.id]
    # the same enemy once its cell is in sight: drawn and pickable; it vanishes again when the sight moves on
    v.reveal(w.fog, [(12, 10)])
    d = build_draw_list(w, cam(), 0, a, OPTS)
    assert foe.id in sprite_entities(d) and foe.id in [p.entity for p in d.picks]
    p = next(p for p in d.picks if p.entity == foe.id)
    assert pick_at(d.picks, (p.x1 + p.x2) // 2, (p.y1 + p.y2) // 2) == foe.id
    v.begin_refresh(w.fog)                                             # explored only: gone again, cannot be clicked
    d = build_draw_list(w, cam(), 0, a, OPTS)
    assert foe.id not in sprite_entities(d) and pick_at(d.picks, (p.x1 + p.x2) // 2, (p.y1 + p.y2) // 2) != foe.id


def test_no_fog_draws_everything():
    mine, foe = unit(1, 10, 10, owner=1), unit(2, 12, 10, owner=2)
    w = world_with(mine, foe)
    assert w.fog is None
    d = build_draw_list(w, cam(), 0, uassets(), OPTS)
    assert {mine.id, foe.id} <= sprite_entities(d)


def test_own_units_always_visible_even_on_black_cells():
    mine = unit(1, 10, 10, owner=1)
    d = build_draw_list(fogged(mine), cam(), 0, uassets(), OPTS)
    assert mine.id in sprite_entities(d)


def test_piles_need_a_seen_cell():
    w = world_with()
    sv.enable(w, 1)
    pile = type("P", (), {"x": 10, "y": 10})()
    assert not vf.item_visible(w, pile)
    v.reveal(w.fog, [(10, 10)])
    assert vf.item_visible(w, pile)
    v.begin_refresh(w.fog)
    assert not vf.item_visible(w, pile)


def test_foreign_structure_states():
    w = world_with()
    sv.enable(w, 1)
    ent = type("S", (), {"owner": 2, "x": 10, "y": 10, "footprint": ((0, 0, True), (1, 0, True))})()
    assert vf.structure_state(w, ent) == 2
    v.reveal(w.fog, [(10, 10)])
    v.begin_refresh(w.fog)
    assert vf.structure_state(w, ent) == 1
    v.reveal(w.fog, [(11, 10)])
    assert vf.structure_state(w, ent) == 0
    ent.owner = 1
    w.fog[:] = 0
    assert vf.structure_state(w, ent) == 0                             # the viewer's own: always


def test_overlay_levels():
    w = world_with()
    sv.enable(w, 1)
    v.reveal(w.fog, [(10, 10)])
    v.reveal(w.fog, [(14, 10)])
    v.begin_refresh(w.fog)
    v.reveal(w.fog, [(10, 10)])
    c = Camera(320, 320, w.width, w.height, 8 * 32, 8 * 32)
    lv, sy, cols, rows = vf.overlay(w, c, np.zeros((w.height + 1, w.width + 1), np.int64))
    assert lv[10 - 8, 10 - 8] == 0 and lv[10 - 8, 14 - 8] == 8 and lv[0, 0] == 16
    assert lv.shape == (rows + 3, cols + 1) and sy.shape[0] >= rows + 2


def test_minimap_blocks():
    g = MinimapGeometry(40, 40)
    fog = v.new_fog(40, 40)
    v.reveal(fog, [(12, 12)])
    v.begin_refresh(fog)
    v.reveal(fog, [(20, 20)])
    img = np.full((g.height, g.width, 3), 198, np.uint8)               # 565-exact values (round-tripped below)
    bg = np.full_like(img, 40)
    apply_fog(img, g, fog, bg)
    s = 1 << g.k
    at = lambda c: tuple(img[(c - 8) * s, (c - 8) * s])
    rt = lambda c: tuple(int(x) for x in unpack16(pack16(np.full(3, c, np.uint8))))        # 5-6-5 round trip
    a, b = pack16(np.full(3, 198, np.uint8)), pack16(np.full(3, 40, np.uint8))
    half = int(((a >> 1) & 0x7bef) + ((b >> 1) & 0x7bef))
    assert at(20) == rt(198)                                           # in sight: the map pixel
    assert at(12) == tuple(int(x) for x in unpack16(np.uint16(half)))  # explored: (bg >> 1 & M) + (map >> 1 & M) on the words
    assert at(30) == rt(40)                                            # never seen: the panel picture


def test_minimap_unit_dots_need_sight():
    from engine.view.minimap import draw_unit_dots
    mine, foe = unit(1, 12, 12, owner=1), unit(2, 20, 20, owner=2)
    w = fogged(mine, foe, seen=[(20, 20)])
    w.players[2] = Player(2, 1)
    g = MinimapGeometry(w.width, w.height)
    img = np.zeros((g.height, g.width, 3), np.uint8)
    draw_unit_dots(img, g, w, np.full((16, 3), 255, np.uint8))
    s = 1 << g.k
    assert img[(20 - 8) * s, (20 - 8) * s].any() and not img[(12 - 8) * s, (12 - 8) * s].any()


def test_vision_update_cost_on_the_largest_map():
    """256 x 256, 24 own units spread out: a full refresh (clear + every mask) stays well under one tick (~30 ms at the fastest speed)."""
    n = 256
    hts = np.random.default_rng(1).integers(-20, 40, (n, n)).astype(np.int8)
    w = World(np.zeros((n, n), np.uint16), hts, "big")
    sv.enable(w, 1)
    obs = [(10 + 9 * (i % 6), 20 + 10 * (i // 6) * 2) for i in range(24)]
    cells = [v.sight_mask(hts, n, n, x, y, 9 << 8) for x, y in obs]    # cold
    t0 = time.perf_counter()
    for _ in range(20):
        v.begin_refresh(w.fog)
        for c in cells:
            v.reveal(w.fog, c)
    warm = (time.perf_counter() - t0) / 20
    t0 = time.perf_counter()
    for x, y in obs:
        v.sight_mask(hts, n, n, x, y, 9 << 8)
    cold = time.perf_counter() - t0
    assert warm < 0.015 and cold < 0.6, (warm, cold)


# --- install ----------------------------------------------------------------------------------------------------------------

def _tool():
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not GFS, reason="game files not present")
def test_fog_goldens():
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["fog"]
    assert _tool().fog_hashes(GFS) == gold, "fog drawing changed; run tools/update_golden.py --only fog"


@pytest.mark.skipif(not GFS, reason="game files not present")
def test_real_map_hides_monsters_the_hero_cannot_see():
    a = AssetCache(GFS)
    w = World.from_map(open_map("10", GFS), a)
    hero = next(u for u in w.units.values() if u.human)
    sv.enable(w, hero.owner)
    sv.vision_system(w, [])
    foes = [u for u in w.units.values() if u.owner != hero.owner]
    far = [u for u in foes if not v.cell_in_sight(w.fog, u.x, u.y)]
    assert far and len(far) < len(foes) + 1
    c = Camera(640, 480, w.width, w.height, hero.x * 32 - 320, hero.y * 32 - 240)
    d = build_draw_list(w, c, 0, a, DrawOptions())
    drawn = sprite_entities(d)
    assert hero.id in drawn and not ({u.id for u in far} & drawn) and not ({u.id for u in far} & {p.entity for p in d.picks})
