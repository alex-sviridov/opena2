"""Fog and corpses (vision.md 2), the hover flags of structures and the hover light row (ui-layout.md 6 / 7).  Synthetic tests always run; the map-32 test
needs the install."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2 import vision as v
from allods2.anim.structures import StructureSet
from engine.sim import vision as sv
from engine.ui.cursor import CursorState as S, choose_cursor
from engine.view import DrawOptions, Projection, build_draw_list
from engine.view.pick import PickRect
from engine.world import MapObject, Player

from helpers import GFS, needs_data, sprite_file
from test_engine_objects import FakeAssets, cam, srec
from test_engine_unit_draw import uassets, unit, world_with

OPTS = DrawOptions(shadows=False)


def sprites(dlist):
    return {i.entity for i in dlist if i.kind == "sprite"}


# --- corpses under fog: the exe has no corpse rule (FUN_00468762 is the unit's own test) -----------------------------

def corpse(uid, x, y, owner):
    u = unit(uid, x, y, owner=owner)
    u.hp = -12
    return u


def test_corpse_in_fog_follows_the_unit_cell_test_and_is_not_remembered():
    mine, foe = corpse(1, 10, 10, 1), corpse(2, 12, 10, 2)
    w = world_with()
    w.players[2] = Player(2, 3)
    w.corpses[mine.id], w.corpses[foe.id] = mine, foe
    sv.enable(w, 1)
    a = uassets()
    d = build_draw_list(w, cam(), 0, a, OPTS)
    assert sprites(d) == {mine.id}                                      # never seen: the foe's body is not drawn, the own body always is
    v.reveal(w.fog, [(12, 10)])
    assert foe.id in sprites(build_draw_list(w, cam(), 0, a, OPTS))     # in sight
    v.begin_refresh(w.fog)                                              # explored only (0x8000): gone again, nothing remembers where it lay
    assert foe.id not in sprites(build_draw_list(w, cam(), 0, a, OPTS))
    assert mine.id in sprites(build_draw_list(w, cam(), 0, a, OPTS))


# --- hover light row ------------------------------------------------------------------------------------------------

def test_hovered_unit_takes_light_row_0_others_the_day_row():
    a, b = unit(1, 10, 10), unit(2, 14, 10)
    w = world_with(a, b)
    d = build_draw_list(w, cam(), 0, uassets(), OPTS, hover=a.id)
    rows = {i.entity: i.light_row for i in d if i.kind == "sprite"}
    assert rows[a.id] == 0 and rows[b.id] not in (None, 0)
    d = build_draw_list(w, cam(), 0, uassets(), DrawOptions(shadows=False, lit=False), hover=a.id)
    assert {i.light_row for i in d if i.kind == "sprite"} == {None}     # no light model, no row


# --- structure hover flags and the cursor ----------------------------------------------------------------------------

def structure(w, uid, owner, usable=0):
    ob = MapObject(0x6000 + uid, "structure", 100, 8, 8, uid=uid, hp=40, hp_max=50, owner=owner)
    w.add_object(ob)
    return ob, FakeAssets(structures={100: StructureSet(srec(Usable=usable, SelectionX1=0, SelectionY1=0, SelectionX2=64, SelectionY2=64),
                                                         sprites={"main": sprite_file(8)})})


def input_over(w, ent, assets, selected, **mods):
    from engine.backend_pygame import window
    layout = SimpleNamespace(viewport=SimpleNamespace(contains=lambda x, y: True), screen=SimpleNamespace(w=640, h=480))
    picks = [PickRect(ent.id, 0, 0, 640, 480)]
    w.players[1].selection = (selected.id,)
    return window.cursor_input(w, cam(), layout, picks, (300, 300), 1, Projection(w.heights), 0,
                               (mods.get("ctrl", False), mods.get("alt", False), False), assets=assets)


def setup(owner, usable=0):
    me = unit(1, 4, 4, owner=1)
    me.human = True
    w = world_with(me)
    w.players[2] = Player(2, 3, relations=(1, 0))
    w.players[1].relations = (0, 1)
    ob, a = structure(w, 5, owner, usable)
    return w, me, ob, a


def test_hostile_structure_is_only_ever_select_even_with_ctrl():
    w, me, ob, a = setup(2)
    for mods in ({}, {"ctrl": True}):
        ci = input_over(w, ob, a, me, **mods)
        assert ci.hover_structure and not ci.hover_unit and ci.hover_hostile and not ci.hover_enterable
        assert choose_cursor(ci) is S.SELECT
    assert choose_cursor(input_over(w, ob, a, me, alt=True)) is S.MOVE


def test_friendly_structure_select_ctrl_attack_and_usable_hero_town():
    w, me, ob, a = setup(1)
    assert choose_cursor(input_over(w, ob, a, me)) is S.SELECT
    assert choose_cursor(input_over(w, ob, a, me, ctrl=True)) is S.ATTACK
    w, me, ob, a = setup(1, usable=1)
    ci = input_over(w, ob, a, me)
    assert ci.hover_enterable and choose_cursor(ci) is S.TOWN            # one hero selected + 0x800
    me.human = False
    assert choose_cursor(input_over(w, ob, a, me)) is S.SELECT           # a non-hero cannot enter


def test_fogged_cell_sets_the_fogged_flag_and_hides_item_piles_from_the_cursor():
    w, me, ob, a = setup(1)
    sv.enable(w, 1)
    ci = input_over(w, ob, a, me)
    assert ci.hover_fogged
    cell = Projection(w.heights).hover_cell(cam().ix + 300, cam().iy + 300)
    v.reveal(w.fog, [cell])
    assert not input_over(w, ob, a, me).hover_fogged


@needs_data
def test_map_32_hostile_structures_give_the_select_cursor():
    from allods2.assets import AssetCache
    from test_engine_mission32 import build
    ac = AssetCache(GFS)
    w, _, hero, _ = build()
    hero.human = True
    foes = [o for o in w.objects.values() if o.kind == "structure" and o.owner != 1]
    assert len(foes) == 2
    for ob in foes:
        for mods in ({}, {"ctrl": True}):
            ci = input_over(w, ob, ac, hero, **mods)
            assert ci.hover_hostile and ci.hover_structure
            assert choose_cursor(ci) is S.SELECT


def test_selected_foreign_unit_is_deselected_when_it_leaves_the_sight():
    mine, foe = unit(1, 10, 10, owner=1), unit(2, 12, 10, owner=2)
    w = world_with(mine, foe)
    w.players[2] = Player(2, 3)
    sv.enable(w, 1)
    v.reveal(w.fog, [(12, 10)])
    w.players[1].selection = (foe.id,)
    sv.vision_system(w, ())
    assert w.players[1].selection == (foe.id,)                          # in sight: stays
    v.begin_refresh(w.fog)
    sv.vision_system(w, ())
    assert w.players[1].selection == ()                                 # S = 1: obj+0x80 cleared
    w.players[1].selection = (mine.id,)
    sv.vision_system(w, ())
    assert w.players[1].selection == (mine.id,)                         # own units never
