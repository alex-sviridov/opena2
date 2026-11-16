"""Shop play-test fixes (docs/engine/shop-rea2.md, item-new-rea.md): per-town shelf rects, the price number and bar, the picture offset, the keeper animation, the same-shelf rule,
and the pack sparkle that only magic items get."""

import random
import types

from allods2.formats import saves as S
from engine import shop as P
from engine import shopkeeper as K
from engine.shell import Text
from engine.shell.events import Move, Press, Release

from test_engine_shop import click, item, shop_shell, SWORD


def test_price_text_has_commas_and_bar_frame_uses_the_full_price():
    assert P.price_text(5) == "5" and P.price_text(1234) == "1,234" and P.price_text(1234567) == "1,234,567"
    assert P.price_bar_frame(9) == 0 and P.price_bar_frame(10) == 1 and P.price_bar_frame(99999999) == 6 and P.price_bar_frame(0) is None
    assert P.BAR_AT == (20, 0) and P.PICTURE_AT == (5, 8) and P.COUNT_AT == (10, -15)


def test_kaarg_and_druid_rects_are_their_own():
    assert P.SHELF_RECTS_BY_TOWN[1] == P.SHELF_RECTS
    k, d = P.SHELF_RECTS_BY_TOWN[2], P.SHELF_RECTS_BY_TOWN[3]
    assert k[0] == (5, 5, 60, 202) and k[3] == (195, 5, 98, 260)                  # armour left, weapons right
    assert d[0] == (5, 109, 88, 112) and d[3] == (93, 169, 96, 104)


def test_kaarg_left_strip_is_armour_and_right_strip_weapons():
    sh, g, sounds = shop_shell(town=2)
    cur = sh.current
    px, py = cur.origin[0] + 164, cur.origin[1]
    assert cur.hit(px + 30, py + 100) == ("shelf", 0)                              # the left strip: armour (was shelf 3, the weapons)
    assert cur.hit(px + 240, py + 100) == ("shelf", 3)                             # the right strip: weapons (was shelf 2, the books)
    assert cur.hit(px + 120, py + 30) == ("shelf", 2)                              # top middle: books and potions


def test_same_shelf_again_does_nothing_and_the_first_click_is_accepted():
    sh, g, sounds = shop_shell(town=1)
    cur = sh.current
    assert cur.state.selected is None
    click(sh, cur.point_of("shelf", 0))                                            # nothing selected at the first opening: shelf 0 is accepted
    assert cur.state.selected == 0 and cur.keeper.sel == 0 and sounds.count("sfx/town/shop/depart.wav") == 1
    click(sh, cur.point_of("shelf", 0))
    assert sounds.count("sfx/town/shop/depart.wav") == 1


def test_cells_draw_the_price_number_on_the_bar_one_pixel_below_the_top():
    sh, g, sounds = shop_shell(town=1)
    cur = sh.current
    cur.state.stock.shelves[0] = [item(SWORD, 3, 1234)]
    ops = cur.scene().ops
    texts = [o for o in ops if isinstance(o, Text) and o.text in ("1,234", "3")]
    ox, oy = cur.origin
    price = [o for o in texts if o.text == "1,234"][0]
    assert (price.x, price.y, price.flags, price.font) == (ox + 1 + 80 - 6, oy + 31 + 1, 1, 2)
    count = [o for o in texts if o.text == "3"][0]
    assert (count.x, count.y) == (ox + 1 + 10, oy + 32 + 80 - 15)


# -- the keeper -----------------------------------------------------------------------------------------------------------------------------------

def run(kp, ticks):
    for _ in range(ticks):
        kp.update(K.TICK_MS)


def test_human_shelf_clip_plays_1_2_3_then_4_to_9_looping_and_ends_on_deselect():
    kp = K.Keeper(1, random.Random(1))
    kp.select(2)
    seen = [kp.highlight_pics()[0].path.rsplit("/", 1)[1]]
    for _ in range(14):
        run(kp, 1)
        seen.append(kp.highlight_pics()[0].path.rsplit("/", 1)[1])
    assert seen == ["%d.bmp" % n for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 4, 5, 6, 7, 8, 9)]
    assert kp.highlight_pics()[0].path.startswith("graphics/interface/shopanim/02/") and (kp.highlight_pics()[0].x, kp.highlight_pics()[0].y) == (149, 20)
    kp.select(0)
    run(kp, 1)
    assert [p.path.split("/")[3] for p in kp.highlight_pics()] == ["04"]            # shelf 2's clip ended on the next step, shelf 0's (set 04) runs


def test_human_yes_clip_is_twelve_frames_then_back_to_the_pose():
    kp = K.Keeper(1, random.Random(1))
    kp.yes()
    names = [kp.keeper_pic().path.split("/", 2)[2]]
    for _ in range(11):
        run(kp, 1)
        names.append(kp.keeper_pic().path.split("/", 2)[2])
    assert names == ["Pose2-3/1.bmp"] + ["Yes/%d.bmp" % n for n in range(2, 13)]
    run(kp, 1)
    assert kp.reply is None and kp.keeper_pic().path == K.IDLE[1]


def test_idle_clip_starts_after_five_to_nine_seconds_and_plays_files_2_to_28():
    kp = K.Keeper(1, random.Random(1))
    wait = kp.wait
    assert 5000 <= wait <= 9000
    run(kp, wait // K.TICK_MS - 1)
    assert kp.idle is None
    run(kp, 1)
    assert kp.idle == ("idle", 0)
    files = []
    for _ in range(30):
        run(kp, 1)
        if kp.idle is None:
            break
        files.append(int(kp.keeper_pic().path.rsplit("/", 1)[1][:-4]))
    assert files == list(range(2, 29))                                              # 27 frames; the clip ends at counter 28 (file 29 is never drawn)
    assert kp.idle is None


def test_druid_and_kaarg_idle_clips_and_highlights():
    kd = K.Keeper(3, random.Random(1))
    kd.select(1)
    p = kd.highlight_pics()[0]
    assert p.path == "graphics/interface/shop_druid/hili_magic.bmp" and (p.x, p.y) == (5, 52)
    kd.yes()
    assert kd.idle == ("a2", 0)
    run(kd, 1)
    assert kd.keeper_pic().path == "movies/shop_druid/a20002.bmp"
    run(kd, 28)
    assert kd.idle == ("a2", 29)                                                    # file 30 is the last frame
    run(kd, 1)
    assert kd.idle is None
    kk = K.Keeper(2, random.Random(1))
    kk.select(3)
    assert kk.highlight_pics()[0].path.endswith("shop_kaarg/hili_weapon.bmp")
    kk.select(1)
    assert kk.highlight_pics()[0].path.endswith("hili_magic.bmp")


def test_kaarg_fire_ignites_on_weapons_and_dies_down_again():
    kp = K.Keeper(2, random.Random(1))
    run(kp, 7)
    assert 0 <= kp.fire < 6 and "fire/dark/" in kp.fire_pic().path                  # idle loop 0..5
    kp.select(0)                                                                    # first click: no change
    kp.select(3)
    assert kp.fire_dir == 1
    run(kp, 20)
    assert 12 <= kp.fire <= 17 and "fire/select/" in kp.fire_pic().path             # lit loop 12..17
    kp.select(1)
    assert kp.fire_dir == -1
    run(kp, 30)
    assert 0 <= kp.fire < 6 and kp.fire_dir == 0


# -- the pack sparkle -----------------------------------------------------------------------------------------------------------------------------

def test_only_items_with_modifiers_are_magic_and_sparkle():
    plain = S.Item(code=0x0104, count=1, new=True)                                   # picked up: the pickup mark, not magic
    magic = S.Item(code=0x0104, count=1, price=100, mods=((44, 3, 2),))
    skipped = S.Item(code=0x0104, count=1, price=100, mods=((S.K_SKIPPED, 1, 0),))
    assert not plain.magic and magic.magic and not skipped.magic


# -- tooltips (docs/engine/shop-tooltips-rea.md) ------------------------------------------------------------------------------------------------------

def _texts(cur):
    cur.main = types.SimpleNamespace(line=lambda n: "T%x" % n)         # no install behind the fixture: every main.txt line is its own number
    return cur


def _tip_at(sh, pos, ms=600):
    cur = _texts(sh.current)
    sh.handle(Move(*pos))
    cur.update(0)
    cur.update(ms)
    return cur.tooltip_text(pos), cur.tip_timer.tip


def test_shelf_and_keeper_texts_per_town():
    for town, base in ((1, 0x3E), (2, 0x116), (3, 0x112)):
        sh, g, sounds = shop_shell(town=town)
        cur = _texts(sh.current)
        for i in range(4):
            assert cur.tooltip_text(cur.point_of("shelf", i)) == cur.main.line(base + i)
        r = P.KEEPER_RECT[town]
        sx, sy, _, _ = P.SHOPKEEPER_PANEL
        ox, oy = cur.origin
        outside = [(ox + sx + r[0] + dx, oy + sy + r[1] + dy) for dx in (1, r[2] - 2) for dy in (1, r[3] - 2)]
        assert any(cur.tooltip_text(p) == cur.main.line(P.T_KEEPER) for p in outside)


def test_panel_texts_and_arrows_and_silent_buttons():
    sh, g, sounds = shop_shell(town=1)
    cur = _texts(sh.current)
    ox, oy = cur.origin
    line = cur.main.line
    assert cur.tooltip_text(cur.point_of("stock_arrow", 0)) == line(P.T_UP)
    assert cur.tooltip_text(cur.point_of("stock_arrow", 1)) == line(P.T_DOWN)
    assert cur.tooltip_text(cur.point_of("strip_arrow", "pack", 0)) == line(P.T_LEFT)
    assert cur.tooltip_text(cur.point_of("strip_arrow", "table", 1)) == line(P.T_TABLE)     # the table's arrows have no text of their own
    assert cur.tooltip_text(cur.point_of("arrow", 0)) == line(P.T_PREV)
    assert cur.tooltip_text(cur.point_of("button", 1)) == ""


def test_item_cell_shows_the_item_text_and_empty_cell_none_and_nothing_while_carried():
    sh, g, sounds = shop_shell(town=1)
    cur = _texts(sh.current)
    cur.state.stock.shelves[0] = [item(SWORD, 1, 100)]
    cur.state.select_shelf(0)
    cur.state.table = types.SimpleNamespace(packets={}, display_name=lambda *a: "Sword")      # the bare-name path of `pack.item_name`
    p0, p1 = cur.point_of("cell", P.KIND_SHELF, 0), cur.point_of("cell", P.KIND_SHELF, 1)
    assert cur.tooltip_text(p0) != "" and cur.tooltip_text(p1) == ""
    cur.state.pick(P.KIND_SHELF, 0)
    assert cur.tooltip_text(p0) == ""
    assert cur.tooltip_text(cur.point_of("shelf", 1)) != ""                        # the keeper panel is not gated


def test_hover_shows_the_box_after_half_a_second_and_a_move_hides_it(monkeypatch):
    monkeypatch.setattr("engine.shell.shop.measure_font2", lambda shell, t: 7 * len(t))
    sh, g, sounds = shop_shell(town=1)
    cur = sh.current
    pos = cur.point_of("shelf", 0)
    text, tip = _tip_at(sh, pos)
    assert tip is not None and tip.lines == (cur.main.line(0x3E),)
    assert any(type(o).__name__ == "Tooltip" for o in cur.scene().ops)
    sh.handle(Move(pos[0] + 3, pos[1]))
    assert cur.tip_timer.tip is None


def test_real_item_tip_through_the_shop_against_the_install():
    from allods2.assets import AssetCache
    from allods2.common import game_fs
    from allods2.formats import itemdefs as ii
    try:
        fs = game_fs()
    except Exception:                                  # noqa: BLE001
        import pytest
        pytest.skip("no install")
    sh, g, sounds = shop_shell(town=1)
    cur = sh.current
    a = AssetCache(fs)
    lines = ii.decode_text(fs.read("main/text/main.txt")).split("\r\n")
    cur.main = types.SimpleNamespace(line=lambda i: lines[i])
    cur.assets, cur.state.table = a, a.items()
    assert cur._item_tip(S.Item(0x1102, 1)) == "Bronze Dagger#Damage 3-4#Attack +10"
    assert cur._item_tip(S.Item(0xE06, 1)) == "Scroll of Fire Arrow#Damage: 13-26#Range: 8"
