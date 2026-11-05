"""Info panel of a hovered structure (docs/engine/ui-layout.md 10 / 11.1): rows, picture name, hover rule, pick rects.  Synthetic tests always run; the
worked example reads map 10 and building.txt from the install."""

from allods2.anim.structures import StructureSet
from engine.sim import SelectUnits
from engine.ui import MainText
from engine.ui import info as I
from engine.ui.selection import SelectionInput
from engine.view import DrawOptions, build_draw_list
from engine.view.pick import PickRect, pick_at
from engine.world import FLAG_DESTROYED, MapObject

from helpers import GFS, needs_data, sprite_file
from test_engine_death import unit, world
from test_engine_objects import FakeAssets, cam, srec

TEXTS = MainText(["t%02x" % i for i in range(0x100)])
NAMES = ["b%d" % i for i in range(60)]
PLAIN = DrawOptions(shadows=False, lit=False, smoothing=False)


def structure(w, uid, x, y, type_id=100, hp=40, hp_max=50, **kw):
    ob = MapObject(0x6000 + uid, "structure", type_id, x, y, uid=uid, hp=hp, hp_max=hp_max, **kw)
    w.add_object(ob)
    return ob


def assets(**kw):
    return FakeAssets(structures={100: StructureSet(srec(**kw), sprites={"main": sprite_file(8)})})


def test_structure_rows_are_name_health_and_hp_all_centred_at_0x48():
    w = world()
    s = structure(w, 1, 8, 8, type_id=3)
    rows = I.structure_rows(s, TEXTS, NAMES)
    assert [(r.text, r.x, r.y, r.flags, r.table) for r in rows] == [
        ("b2", 0x48, 0x1C, I.CENTRE, "label"), ("t13", 0x48, 0x2C, I.CENTRE, "label"), ("40/50", 0x48, 0x36, I.CENTRE, "value")]   # name = line type - 1


def test_structure_hp_is_signed_s16_and_an_unknown_type_has_an_empty_name():
    w = world()
    s = structure(w, 1, 8, 8, type_id=900, hp=-5)
    rows = I.structure_rows(s, TEXTS, NAMES)
    assert rows[0].text == "" and rows[2].text == "-5/50"


def test_picture_is_the_records_picture_without_suffix():
    w = world()
    s = structure(w, 1, 8, 8, type_id=23)
    assert I.structure_picture(s, {23: {"Picture": "ogreh"}}) == "graphics/infowindow/ogreh.bmp"
    assert I.structure_picture(s, {23: {}}) is None and I.structure_picture(s, {}) is None


def test_hovered_structure_is_shown_while_selection_and_units_keep_priority_rules():
    w = world()
    s = structure(w, 1, 8, 8)
    u = unit(w, 2, 5, 5, owner=1)
    assert I.selection_summary(w, 1, s.id) == ("structure", s)
    assert I.selection_summary(w, 1, s.id, modal=True) == ("none", None)
    assert I.selection_summary(w, 1, u.id) == ("unit", u)
    w.players[1].selection = (u.id,)
    assert I.selection_summary(w, 1, s.id) == ("structure", s)             # hover wins over the selected unit
    assert I.selection_summary(w, 1) == ("unit", u)
    assert I.shown_structure(w, 0x7777) is None


def pick(w, **kw):
    return build_draw_list(w, cam(), 0, assets(**kw), PLAIN).hover_picks


def test_pick_rect_is_the_selection_rect_at_cell_x32_and_y_plus_th_minus_fh():
    w = world()
    s = structure(w, 1, 8, 8)
    (r,) = pick(w, SelectionX1=3, SelectionY1=4, SelectionX2=60, SelectionY2=50)
    assert r == PickRect(s.id, 256 + 3, 256 - 32 + 4, 256 + 60, 256 - 32 + 50)
    assert pick_at([r], 256 + 10, 224 + 10) == s.id and pick_at([r], 5, 5) is None


def test_indestructible_structure_is_hit_only_when_usable_and_flat_or_destroyed_never():
    w = world()
    s = structure(w, 1, 8, 8)
    assert len(pick(w, Indestructible=1)) == 0                                  # +0x64 set, +0x8c clear: the hover loop skips it
    assert len(pick(w, Indestructible=1, Usable=1)) == 1
    assert len(pick(w, Usable=0, Indestructible=0)) == 1
    assert len(pick(w, Flat=1)) == 0                                            # +0x90: no rect registered
    s.hp, s.flags = 0, FLAG_DESTROYED
    assert len(pick(w)) == 0                                                    # destroyed (INFERRED death stage)


def test_unit_and_structure_picks_merge_in_draw_order():
    w = world()
    s = structure(w, 1, 8, 8)
    items = build_draw_list(w, cam(), 0, assets(SelectionX1=0, SelectionY1=0, SelectionX2=64, SelectionY2=64), PLAIN)
    assert [r.entity for r in items.hover_picks] == [s.id] and items.picks == []


def test_click_on_a_structure_leaves_the_selection_alone():
    picks = [PickRect(0x6001, 0, 0, 50, 50)]
    sel = SelectionInput(1, 640, lambda: picks, lambda e: None, lambda: (0x6009,))
    sel.press(10, 10)
    assert sel.release(10, 10) is None
    sel.press(10, 10)
    assert sel.release(10, 10, shift=True) is None


@needs_data
def test_worked_example_map_10_ogre_house_and_snake_house():
    """Map 10: structure 0x6006 = type 23 at (42, 67), 500/500: building.txt line 22 "Ogre House", picture `ogreh.bmp`; type 26 (norka) is the
    "Snake House" with 100/100; the destroyed norka 0x6019 and the sphinx (Indestructible, no picture file) are never hover targets."""
    from allods2.assets import AssetCache
    from engine.view import Camera
    from engine.world import World
    a = AssetCache(GFS)
    from allods2.common import as_fs
    from allods2.cli import open_map
    w = World.from_map(open_map("10", GFS), a)
    names = MainText.load(as_fs(GFS), "main/text/building.txt").lines
    ogre = w.objects[0x6006]
    rows = I.structure_rows(ogre, MainText.load(as_fs(GFS)), names)
    assert [r.text for r in rows] == ["Ogre House", "Health", "500/500"]
    assert I.structure_picture(ogre, a.structures_reg()) == "graphics/infowindow/ogreh.bmp" and GFS.exists("graphics/infowindow/ogreh.bmp")
    assert I.structure_rows(w.objects[0x600A], MainText.load(as_fs(GFS)), names)[0].text == "Snake House"
    ids = {r.entity for r in build_draw_list(w, Camera(w.width * 32, w.height * 32, w.width, w.height, 0, 0), 0, a, DrawOptions()).hover_picks}
    assert 0x6006 in ids and 0x6019 not in ids and 0x6003 not in ids and 0x6002 not in ids      # destroyed / sphinx / flat bee house
    assert all(GFS.exists(I.structure_picture(w.objects[i], a.structures_reg())) for i in ids if i in w.objects)
