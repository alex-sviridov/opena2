"""L8 (docs/engine/town-shop.md): the DLL shop table and its chapter updates, the stock of a visit, the shop model's trade rules (drag rules, totals, Buy / Sell / Cancel / Leave, the
hero arrows), and the screen driven by clicks.  The synthetic tests need no install; the install tests (stock from the generator, the sold-item shelf rule, a render of each shop to
out/) skip without one."""

import random
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from allods2.formats import itemgen
from allods2.formats import saves as S
from engine import shop as P
from engine.campaign import CampaignGame
from engine.sim import campaign as C
from allods2.common import INSTALL
from helpers import GFS

needs_install = pytest.mark.skipif(GFS is None or not GFS.exists("graphics/interface/shopinv.bmp"), reason="no install")
OUT = Path(__file__).resolve().parents[1] / "out"

SWORD, POTION, QUEST = 0x0101, 0x0E01, 0x0E55


def item(code=SWORD, count=1, price=100):
    return S.Item(code, count, price)


def game(town=1, gold=1000):
    g = CampaignGame()
    g.new_game(visit=False)
    g.camp.available = [(C.TOWN, town)]
    g.camp.enter((C.TOWN, town))
    g.gold = gold
    return g


def state(g=None, town=1, shelves=None, flags=None):
    g = g or game(town)
    stock = P.Stock(shelves or [[item(), item(POTION, 5, 10)], [], [], []], flags)
    return P.ShopState(g, town, stock, None)


def drag(st, src, dst, whole=False):
    assert st.pick(src[0], src[1], whole)
    return st.drop(*dst)


# -- the DLL's shop table (items.md 13) -----------------------------------------------------------------------------------------------------------

def finish(camp, n):
    camp.enter((C.MISSION, n))
    camp.leave()


def test_new_game_table_is_the_dlls():
    camp = C.Campaign.new_game()
    assert camp.shop[1] == [[0, 1500, 100, 2, 0x1381CC03], [0, 1500, 100, 2, 0x10418103], [0, 1500, 20, 1, 0x28018100], [0, 1500, 20, 1, 0x04000000]]
    assert camp.shop[2][1] == [0, 5000, 20, 1, 0x2BC3C304] and 3 not in camp.shop


def test_mission_completions_change_town_2_and_create_town_3():
    camp = C.Campaign.new_game()
    finish(camp, 10)
    assert camp.get(C.CHAPTER) == 20 and camp.shop[2][0][1] == 5000
    finish(camp, 20)                                              # chapter 30: town 2 max 10,000
    assert camp.shop[2][0][1] == 10000 and camp.shop[1][0][1] == 1500
    finish(camp, 30)                                              # case 30 flags, chapter 40: 22,000
    assert camp.shop[2][0][4] == 0x1383C22C and camp.shop[2][1][4] == 0x2BC3C324 and camp.shop[2][3][4] == 0x10438324 and camp.shop[2][2][4] == 0x04000000
    assert camp.shop[2][3][1] == 22000
    finish(camp, 40)
    assert camp.shop[2][0][4] == 0x1387C26C and 3 not in camp.shop
    finish(camp, 50)                                              # town 3 is created, chapter 60: 150,000
    t3 = camp.shop[3]
    assert [b[4] for b in t3] == [0x13C7D318, 0x2BC7D318, 0x04000000, 0x2BC042F0]
    assert [b[:4] for b in t3] == [[499, 150000, 100, 2], [499, 150000, 20, 1], [0, 150000, 20, 1], [499, 150000, 100, 2]]
    assert camp.talk_to(0x4E02A3) is None and camp.shop[3][3][4] == 0x2BC042F0 | 0x80000
    for n in (60, 70, 80):
        finish(camp, n)                                           # chapter 90
    assert camp.shop[2][0][1] == 1500000 and [camp.shop[2][b][0] for b in (0, 1, 3)] == [12000] * 3 and camp.shop[2][2][0] == 0
    assert camp.shop[2][0][4] == 0x138752E0 and camp.shop[3][0][1] == 1500000
    finish(camp, 90)                                              # chapter 100: 5,000,000, town 2 floors 40,000
    assert camp.shop[2][0][4] == 0x138772C0 and camp.shop[2][0][1] == 5000000 and [camp.shop[2][b][0] for b in (0, 1, 3)] == [40000] * 3
    assert camp.shop[3][1][0] == 499 and camp.shop[3][2][0] == 0
    finish(camp, 100)
    assert camp.shop[3][1][1] == 10000000 and camp.get(C.CHAPTER) == 110


# -- the stock of a visit ---------------------------------------------------------------------------------------------------------------------------

def test_the_stock_lives_for_a_visit_and_is_regenerated_at_the_next_arrival():
    from engine.town import TownCore
    g = game()
    core = TownCore(g.camp)
    core.camp.available = [(C.TOWN, 1)]
    core.open_map()
    core.walk_to((C.TOWN, 1))
    assert core.visit == 1 and core.stock is None
    a = P.open_stock(core, g, 1, random.Random(1))
    assert P.open_stock(core, g, 1, random.Random(2)) is a            # in and out of the shop inside one visit
    core.send(0x42b)
    core.close_window()
    assert P.open_stock(core, g, 1) is a
    core.post(0x468)
    core.pump()
    assert core.visit == 2 and core.stock is None and P.open_stock(core, g, 1) is not a


@needs_install
def test_generated_stock_follows_the_blocks():
    table = _assets().items()
    blocks = C.new_game_shop()[1]
    stock = P.Stock.generate(table, blocks, itemgen.MsvcRng(7))
    assert len(stock.shelves) == 4 and all(stock.shelves[b] for b in range(4))
    assert stock.flags == [b[4] for b in blocks]
    for shelf in stock.shelves[:3]:                                   # the stock shelf (books, scrolls, potions) is outside the price window
        assert all(0 <= P.price_of(table, it) <= 1500 for it in shelf)
    kinds = {P.group_of(table, it) for it in stock.shelves[3]}
    assert kinds <= {3, 4, 5} and 3 in kinds                        # books, scrolls, potions (stock flag)
    assert {P.group_of(table, it) for it in stock.shelves[0]} == {1}  # armour
    assert {P.group_of(table, it) for it in stock.shelves[1]} == {2}  # weapons
    again = P.Stock.generate(table, blocks, itemgen.MsvcRng(7))
    assert [[(i.code, i.count) for i in s] for s in again.shelves] == [[(i.code, i.count) for i in s] for s in stock.shelves]


def _assets():
    from allods2.assets import AssetCache
    from allods2.common import INSTALL
    return AssetCache(INSTALL)


# -- the trade rules (town-shop 3.2 / 3.3) ----------------------------------------------------------------------------------------------------------

def test_a_shop_item_goes_to_the_table_one_piece_at_a_time_and_totals_follow():
    st = state()
    assert drag(st, (P.KIND_SHELF, 1), (P.KIND_TABLE, -1)) == []
    assert st.shelf_items()[1].count == 4 and st.lots[0].item.count == 1 and st.lots[0].side == "buy"
    assert st.totals() == (1000, -10, 0, 990)
    drag(st, (P.KIND_SHELF, 1), (P.KIND_TABLE, -1), whole=True)
    assert len(st.lots) == 1 and st.lots[0].item.count == 5 and st.shelf_items() == [item()]     # equal stackable items merge on the table
    assert st.totals()[1] == -50


def test_price_zero_goes_to_a_pack_only_and_a_shop_item_returns_only_to_its_shelf():
    st = state(shelves=[[item(QUEST, 1, 0), item()], [], [], []])
    assert drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))[0].value == "nofit" and not st.lots
    assert st.carried is None and len(st.shelf_items()) == 2                           # returned to its origin
    drag(st, (P.KIND_SHELF, 1), (P.KIND_TABLE, -1))
    assert st.pick(P.KIND_TABLE, 0) and st.drop(P.KIND_SHELF + 1, 0)[0].value == "nofit" and len(st.lots) == 1    # not onto another shelf
    assert st.pick(P.KIND_TABLE, 0) and st.drop(P.KIND_SHELF, 0) == [] and not st.lots and len(st.shelf_items()) == 2


def test_buy_needs_the_gold_and_files_the_item_in_the_shown_heros_pack():
    st = state(g=game(gold=15))
    drag(st, (P.KIND_SHELF, 1), (P.KIND_TABLE, -1), whole=True)                     # 5 x 10 = 50 > 15
    fx = st.buy()
    assert [(e.kind, e.value) for e in fx] == [("refuse", None), ("sound", "nofit")] and st.gold == 15 and st.lots
    st.game.gold = 60
    fx = st.buy()
    assert [(e.kind, e.value) for e in fx] == [("yes", None), ("sound", "buy")]
    assert st.gold == 10 and not st.lots and [(i.code, i.count) for i in st.pack()] == [(POTION, 5)]
    assert st.buy() == []                                                           # nothing on the table


def test_server_buy_stops_at_the_first_item_the_gold_does_not_cover():
    """The client sum passes (130 <= 130), then the gold shrinks under the second price (another window / the autosave race): the server buys in table order and stops."""
    st = state(g=game(gold=130), shelves=[[item(SWORD, 1, 80), item(0x0102, 1, 50)], [], [], []])
    drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))
    drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))
    assert st.totals() == (130, -130, 0, 0)
    st.totals = lambda: (130, -130, 0, 0)                           # the client's check at the click saw 130 gold
    st.game.gold = 100
    assert [e.kind for e in st.buy()] == ["yes", "sound"]
    assert st.gold == 20 and [l.item.code for l in st.lots] == [0x0102] and [i.code for i in st.pack()] == [SWORD]


def test_sell_pays_half_rounded_up_and_the_item_returns_to_a_shelf_of_its_group():
    g = game(gold=0)
    g.roster[0].bought = (item(SWORD, 1, 101), item(POTION, 3, 11))
    st = P.ShopState(g, 1, P.Stock([[], [], [], []], [0, 0x400000, 0, 0x4000000]), _FakeTable())
    drag(st, (P.KIND_PACK, 0), (P.KIND_TABLE, -1))
    assert st.totals() == (0, 0, 51, 51)
    drag(st, (P.KIND_PACK, 0), (P.KIND_TABLE, -1), whole=True)
    assert st.totals()[2] == 51 + 3 * 6
    fx = st.sell()
    assert [(e.kind, e.value) for e in fx] == [("yes", None), ("sound", "sell")]
    assert st.gold == 51 + (3 * 11 + 1) // 2 and not st.lots and st.pack() == []
    assert [i.code for i in st.stock.shelves[1]] == [SWORD] and [i.code for i in st.stock.shelves[3]] == [POTION]


class _FakeTable:
    """Just enough of the item table for the group rule: `resolve(code, effects)` -> a record with the defn kind / subtype by code."""

    def resolve(self, code, effects=()):
        from allods2.formats import itemdefs as idefs
        kind, sub = (idefs.WEAPON, 0) if code == SWORD else (idefs.SPECIAL, 3)
        return SimpleNamespace(defn=SimpleNamespace(kind=kind, subtype=sub, effects_text=""), price=0)


def test_cancel_and_leave_return_the_table_without_charge():
    g = game(gold=500)
    g.roster[0].bought = (item(SWORD, 1, 40),)
    st = state(g=g)
    drag(st, (P.KIND_SHELF, 1), (P.KIND_TABLE, -1), whole=True)
    drag(st, (P.KIND_PACK, 0), (P.KIND_TABLE, -1))
    assert len(st.lots) == 2 and st.pack() == []
    assert [(e.kind, e.value) for e in st.cancel()] == [("sound", "undo")]
    assert not st.lots and st.gold == 500 and [i.code for i in st.shelf_items()] == [SWORD, POTION]
    assert [i.code for i in st.pack()] == [SWORD]
    drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))
    st.leave()
    assert not st.lots and len(st.shelf_items()) == 2 and st.gold == 500


def test_hero_arrows_wrap_keep_the_table_and_pass_items_between_heroes():
    g = game()
    g.recruit(0x16)
    g.roster[0].bought = (item(SWORD, 1, 40),)
    st = state(g=g)
    assert len(st.entries) == 2 and st.hero == 0
    drag(st, (P.KIND_PACK, 0), (P.KIND_TABLE, -1))
    assert st.hero_next() == 1 and st.hero_next() == 0 and st.hero_prev() == 1 and len(st.lots) == 1      # the table is shared
    assert st.pick(P.KIND_TABLE, 0) and st.drop(P.KIND_PACK, -1) == []
    assert [i.code for i in st.pack()] == [SWORD] and g.roster[1].bought and not g.roster[0].bought      # now in the second hero's pack


def test_the_doll_is_a_source_for_a_hero_with_a_carried_state_only():
    g = game()
    equipment = tuple([S.Item(0, 0)] * 12)
    equipment = (item(SWORD, 1, 60),) + equipment[1:]
    g.roster[0].state = SimpleNamespace(pack=(), equipment=equipment, carried=(), carried_mods=())
    st = state(g=g)
    assert st.pick(P.KIND_EQUIP, 0) and st.drop(P.KIND_TABLE, -1) == []
    assert st.lots[0].side == "sell" and not any(i.code for i in g.roster[0].state.equipment)
    assert st.totals()[2] == 30
    st.cancel()
    assert [i.code for i in g.roster[0].state.pack] == [SWORD] and g.roster[0].state.carried == (SWORD,)    # back in the pack (the server files it there)


def test_the_table_holds_five_lots_and_merges_equal_stackables():
    st = state(shelves=[[item(0x0101 + i, 1, 10) for i in range(7)], [item(POTION, 9, 10)], [], []])
    for _ in range(5):
        assert drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1)) == []
    assert len(st.lots) == 5
    assert st.pick(P.KIND_SHELF, 0) and st.drop(P.KIND_TABLE, -1)[0].value == "nofit" and len(st.lots) == 5       # `0x4b5a63`: full, nothing merges
    st.select_shelf(1)
    assert st.pick(P.KIND_SHELF + 1, 0) and st.drop(P.KIND_TABLE, -1)[0].value == "nofit"
    st.lots.pop()
    assert drag(st, (P.KIND_SHELF + 1, 0), (P.KIND_TABLE, -1)) == []
    assert drag(st, (P.KIND_SHELF + 1, 0), (P.KIND_TABLE, -1)) == [] and len(st.lots) == 5 and st.lots[-1].item.count == 2     # the same potion merges even when the table is full


def test_the_pack_refuses_a_shop_owned_lot_but_takes_a_hero_lot():
    """`0x4b5156` (CONFIRMED): the pack hover allows a carried item whose `+0x18` is 1 or 2 only, so the table -> pack "quirk" of the server's mixed path cannot be reached by a bought lot."""
    st = state(g=game(gold=0))
    drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))
    assert st.pick(P.KIND_TABLE, 0) and st.drop(P.KIND_PACK, -1)[0].value == "nofit"
    assert len(st.lots) == 1 and not st.pack() and len(st.shelf_items()) == 1           # the lot stays on the table
    assert st.pick(P.KIND_SHELF, 0) and st.drop(P.KIND_PACK, -1)[0].value == "nofit"    # a shelf item straight to the pack does nothing
    st.cancel()
    st.entry().bought = (item(SWORD, 1, 40),)
    drag(st, (P.KIND_PACK, 0), (P.KIND_TABLE, -1))
    assert st.pick(P.KIND_TABLE, 0) and st.drop(P.KIND_PACK, -1) == [] and [i.code for i in st.pack()] == [SWORD]       # the hero's own lot goes back


def test_a_drop_on_the_doll_needs_a_carried_state_and_a_hero_owned_item():
    st = state(g=game(gold=0))
    assert st.pick(P.KIND_SHELF, 0) and st.drop(P.KIND_EQUIP, -1) == [] and len(st.shelf_items()) == 2       # shop-owned: returned silently (`0x4aebc8`, no sound)
    st.entry().bought = (item(SWORD, 1, 40),)
    assert st.pick(P.KIND_PACK, 0) and st.drop(P.KIND_EQUIP, -1) == [] and [i.code for i in st.pack()] == [SWORD]  # a hero with no carried state: no doll model, refused



def test_the_pick_up_takes_one_piece_and_shift_the_stack():
    st = state()
    assert st.pick(P.KIND_SHELF, 1) and st.carried.count == 1
    st.carried = None
    assert st.pick(P.KIND_SHELF, 1, whole=True) and st.carried.count == 5


@needs_install
def test_a_sold_item_goes_to_the_block_the_exes_scans_pick():
    table = _assets().items()
    flags = [0x1381CC03, 0x10418103, 0x28018100, 0x04000000]            # town 1: armour, weapons, staves with modifiers, stock
    rng = itemgen.MsvcRng(5)
    made = [[P.from_generated(g) for g in itemgen.generate(table, 0, 1500, fl, 40, 2, rng)] for fl in flags]
    plain_weapon = next(i for i in made[1] if not i.mods)
    modified = next(i for i in made[2] if i.mods)
    potion = next(i for i in made[3] if P.group_of(table, i) == 3)
    stock = P.Stock(None, flags)
    assert stock.block_for(table, plain_weapon) == 1 and stock.block_for(table, potion) == 3
    assert stock.block_for(table, modified) == 2                           # a non-stackable item takes the enchant block
    assert P.Stock(None, [0x1381CC03, 0x10418103, 0x04000000, 0x04000000]).block_for(table, modified) == 3     # none: block 3
    assert P.Stock(None, [0, 0, 0, 0]).block_for(table, plain_weapon) == 3


def test_the_druid_shops_fourth_shelf_is_gated_by_var_0x302():
    g = game(town=3)
    st = state(g=g, town=3)
    assert st.select_shelf(3) == [] and st.shelf == 0
    assert [e.value for e in st.select_shelf(1)] == ["depart", 1] and st.shelf == 1
    g.camp.vars[0x302] = 1
    assert st.select_shelf(3) and st.shelf == 3
    human = state(g=game(town=1))
    assert human.select_shelf(3) and human.shelf == 3                  # only the druid shop has the gate


def test_price_bar_frame_is_log10_capped_at_six():
    assert [P.price_bar_frame(p) for p in (0, 1, 9, 10, 999, 1000, 9999999, 10**8)] == [None, 0, 0, 1, 2, 3, 6, 6]


def test_geometry_is_the_windows():
    assert P.stock_cell(0) == (1, 31, 80, 80) and P.stock_cell(5) == (81, 191, 80, 80)            # `0x4b35b0`
    assert P.strip_cell(P.TABLE_PANEL, 0) == (32, 303, 80, 80) and P.strip_cell(P.PACK_PANEL, 4) == (352, 395, 80, 80)      # `0x4b579d` / `0x4b4a05`
    assert [P.rect_has(r, 500, 30) for r in P.BUTTONS] == [True, False, False, False]
    assert P.STRIP_ARROWS["pack"] == ((0, 0, 32, 90), (432, 0, 48, 90)) and P.STOCK_ARROWS == ((46, 0, 72, 32), (46, 271, 72, 32))


def test_button_captions_and_numbers_follow_the_exes_arithmetic():
    """`0x4bcd05`: x = rect left + width / 2; caption y = top + 6 (Sell 8) + height / 4, number y = top - 2 (Sell 0) + 3 height / 4, one pixel lower while pressed."""
    assert [P.label_at(i) for i in range(4)] == [(554, 34), (553, 84), (553, 133), (554, 179)]
    assert [P.number_at(i) for i in range(4)] == [(554, 52), (553, 99), (553, 148), (554, 197)]
    assert P.label_at(1, True) == (553, 85) and P.number_at(2, True) == (553, 149)


def test_shelf_rects_are_the_ctors_a_b_c_d_in_shelf_order():
    assert P.SHELF_RECTS[0] == (190, 110, 105, 185) and P.SHELF_RECTS[3] == (8, 5, 142, 100)


# -- the screen ---------------------------------------------------------------------------------------------------------------------------------------

def click(sh, pos, button=1):
    from engine.shell.events import Move, Press, Release
    for ev in (Move(*pos), Press(pos[0], pos[1], button), Release(pos[0], pos[1], button)):
        sh.handle(ev)


def shop_shell(town=1, gold=100):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from shell_scenarios import click_region, map_walk
    from engine.shell import Services, Shell
    sounds = []
    sh = Shell(None, services=Services(sound=sounds.append, log=lambda s: None))
    sh.campaign = g = game(town, gold)
    sh.rng = random.Random(3)
    sh.start("locations")
    map_walk(sh, (C.TOWN, town))
    assert sh.name == "town"
    click_region(sh, 1)
    assert sh.name == "shop" and sh.town_core().mask == 2
    return sh, g, sounds


def test_screen_drag_buy_and_leave_by_clicks():
    sh, g, sounds = shop_shell()
    cur = sh.current
    st = cur.state
    st.stock.shelves[0] = [item(SWORD, 1, 30), item(POTION, 4, 10)]
    st.stock.flags = [0x400000, 0, 0, 0]
    click(sh, cur.point_of("cell", P.KIND_SHELF, 1))
    from engine.shell.events import Move, Press, Release
    x, y = cur.point_of("cell", P.KIND_SHELF, 0)
    tx, ty = cur.point_of("cell", P.KIND_TABLE, 0)
    for ev in (Move(x, y), Press(x, y)):
        sh.handle(ev)
    assert st.carried is not None and st.carried.item.code == SWORD
    for ev in (Move(tx, ty), Release(tx, ty)):
        sh.handle(ev)
    assert st.carried is None and [l.item.code for l in st.lots] == [SWORD]
    assert cur.scene().ops                                                                  # draws with the carried item and the table
    click(sh, cur.point_of("button", P.B_BUY))
    assert g.gold == 70 and [i.code for i in st.pack()] == [SWORD] and "sfx/town/buy.wav" in sounds
    ax, ay = cur.point_of("arrow", 1)
    click(sh, (ax, ay))
    assert st.hero == 0                                                                     # one hero: the arrow wraps onto himself
    st.lots.append(P.Lot(item(POTION, 2, 10), "buy", 0))
    sh.handle(__import__("engine.shell.events", fromlist=["Key"]).Key("escape"))
    assert sh.name == "town" and sh.town_core().mask == 0 and not st.lots
    assert sh.history[-3:] == ["town", "shop", "town"]


def test_screen_refused_drop_plays_nofit_and_a_shelf_click_selects():
    sh, g, sounds = shop_shell(town=3)
    cur = sh.current
    st = cur.state
    st.stock.shelves[1] = [item(SWORD, 1, 30)]
    click(sh, cur.point_of("shelf", 3))
    assert st.shelf == 0                                                                    # the elven shelf is shut
    click(sh, cur.point_of("shelf", 1))
    assert st.shelf == 1 and "sfx/town_druid/shop/dotdel.wav" in sounds
    from engine.shell.events import Move, Press, Release
    x, y = cur.point_of("cell", P.KIND_SHELF + 1, 0)
    px, py = cur.point_of("cell", P.KIND_PACK, 0)
    for ev in (Move(x, y), Press(x, y), Move(px, py), Release(px, py)):
        sh.handle(ev)
    assert st.carried is None and len(st.shelf_items()) == 1 and "sfx/town/shop/nofit.wav" in sounds
    click(sh, cur.point_of("button", P.B_EXIT))
    assert sh.name == "town" and "sfx/out.wav" in sounds


@needs_install
def test_render_each_shop_and_stock_of_a_real_visit():
    pytest.importorskip("pygame")
    from engine.backend_pygame.shell import screenshot
    from engine.shell import Services, Shell
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from shell_scenarios import click_region, map_walk
    OUT.mkdir(exist_ok=True)
    for town in (1, 2, 3):
        sh = Shell(GFS, services=Services(log=lambda s: None))
        sh.campaign = g = CampaignGame(INSTALL)
        g.new_game(visit=False)
        g.camp.vars[C.CHAPTER] = 60
        if town == 3:
            g.camp.shop[3] = [[499, 60000, 100, 2, 0x13C7D318], [499, 60000, 20, 1, 0x2BC7D318], [0, 60000, 20, 1, 0x04000000], [499, 60000, 100, 2, 0x2BC042F0]]
        g.camp.available = [(C.TOWN, town)]
        g.camp.enter((C.TOWN, town))
        g.gold = 5000
        sh.rng = random.Random(town)
        sh.start("locations")
        map_walk(sh, (C.TOWN, town))
        click_region(sh, 1)
        assert sh.name == "shop"
        st = sh.current.state
        assert any(st.stock.shelves)
        rgb = screenshot(sh)
        from PIL import Image
        Image.fromarray(rgb).save(OUT / ("shop_%d.png" % town))


@needs_install
def test_bought_items_reach_a_hero_that_was_never_in_a_world_and_the_doll_sells_after_a_mission():
    g = CampaignGame(INSTALL)
    g.new_game(visit=True)
    table = g.assets.items()
    gen = itemgen.generate(table, 0, 1500, 0x4000000, 5, 2, itemgen.MsvcRng(3))
    potion = next(i for i in map(P.from_generated, gen) if P.group_of(table, i) == 3 and P.price_of(table, i) > 0)
    g.gold = 500
    st = P.ShopState(g, 1, P.Stock([[potion], [], [], []]), table)
    drag(st, (P.KIND_SHELF, 0), (P.KIND_TABLE, -1))
    assert [e.value for e in st.buy()] == [None, "buy"] and g.gold < 500
    assert g.roster[0].state is None and [i.code for i in g.roster[0].bought] == [potion.code]
    world, _ = g.start_mission(10)
    hero = next(u for u in world.units.values() if u.hero_no == g.roster[0].number)
    assert potion.code in [i.code for i in hero.pack] and potion.code in hero.carried
    g.carry_over(world)
    entry = g.roster[0]
    assert entry.state is not None and potion.code in [i.code for i in entry.state.pack]
    st = P.ShopState(g, 1, P.Stock(None, [0x400000, 0, 0, 0x4000000]), table)
    assert st.pick(P.KIND_PACK, [i.code for i in st.pack()].index(potion.code), True) and st.drop(P.KIND_TABLE, -1) == []
    gold = g.gold
    st.sell()
    assert g.gold > gold and [i.code for i in st.stock.shelves[3]] == [potion.code]


@needs_install
def test_equip_path_of_a_drop_on_the_doll():
    """Server `0x4f5d27` / `put` `FUN_00512573` through the client rules `0x4b028d`: worn, the replaced piece goes to the pack at the source index, an unusable item and a quest item are refused,
    a potion is used up, a stack gives one piece."""
    from engine.ui import pack as UP
    g = CampaignGame(INSTALL)
    g.new_game(visit=True)
    table = g.assets.items()
    world, _ = g.start_mission(10)
    g.carry_over(world)
    entry = g.roster[0]
    state_ = entry.state
    assert state_.equipment and any(i.code for i in state_.equipment)
    st = P.ShopState(g, 1, P.Stock([[], [], [], []]), table)
    gen = [P.from_generated(x) for x in itemgen.generate(table, 0, 3000, 0x10418103, 12, 1, itemgen.MsvcRng(5))]
    mage = gear_is_mage(state_)
    weapons = [i for i in gen if UP.usable_by(UP.item_flags(table, i), mage) and (UP.item_flags(table, i) & 6)]
    assert weapons
    w = P.replace(weapons[0], count=1)
    slots_before = {k: v.code for k, v in P.gear.slots_of(state_).items()}
    entry.state.pack = (w,) + tuple(state_.pack)
    n_pack = len(state_.pack)
    assert st.pick(P.KIND_PACK, 0) and st.drop(P.KIND_EQUIP, -1) == []
    slots_after = {k: v.code for k, v in P.gear.slots_of(state_).items()}
    assert w.code in slots_after.values()                                                  # worn
    assert len(state_.pack) in (n_pack - 1, n_pack) and state_.carried == tuple(i.code for i in state_.pack)
    if slots_before != slots_after and len(slots_before) == len(slots_after):
        assert len(state_.pack) == n_pack                                                 # the replaced piece took the place in the pack
    quest = S.Item(QUEST, 1, 0)
    entry.state.pack = (quest,)
    assert st.pick(P.KIND_PACK, 0) and st.drop(P.KIND_EQUIP, -1) == [] and [i.code for i in state_.pack] == [QUEST]    # no usable bit: refused, stays


def gear_is_mage(st):
    return P.gear.is_mage(st)


@needs_install
def test_a_potion_dropped_on_the_doll_is_used_up_one_piece_at_a_time():
    g = CampaignGame(INSTALL)
    g.new_game(visit=True)
    table = g.assets.items()
    world, _ = g.start_mission(10)
    g.carry_over(world)
    state_ = g.roster[0].state
    st = P.ShopState(g, 1, P.Stock([[], [], [], []]), table)
    gen = itemgen.generate(table, 0, 1500, 0x4000000, 5, 2, itemgen.MsvcRng(3))
    potion = next(i for i in map(P.from_generated, gen) if P.group_of(table, i) == 3 and P.price_of(table, i) > 0 and P.UP.item_flags(table, i) & 2)
    state_.pack = (replace(potion, count=3),)
    assert st.pick(P.KIND_PACK, 0, True) and st.drop(P.KIND_EQUIP, -1) == []
    assert [(i.code, i.count) for i in state_.pack] == [(potion.code, 2)]


def test_a_returned_item_is_appended_to_its_shelf_or_merged_into_the_first_equal_stackable():
    """`0x52151c` (CONFIRMED): scan the list in order; an equal stackable entry takes the count, else `Add` at the END (no sorting)."""
    table = _assets_or_none()
    shelf = [item(0x0101 + 1, 1, 10), item(POTION, 5, 10), item(POTION, 2, 10)]
    P.gear.pack_insert(table, shelf, item(POTION, 1, 10))
    assert [(i.code, i.count) for i in shelf] == [(0x0102, 1), (POTION, 5 + 1), (POTION, 2)] or table is None
    P.gear.pack_insert(table, shelf, item(0x0150, 1, 10))
    assert shelf[-1].code == 0x0150


def _assets_or_none():
    return _assets().items() if GFS is not None and GFS.exists("graphics/interface/shopinv.bmp") else None


def test_a_lost_mission_does_not_touch_the_dlls_shop_table():
    """`0x486a68` case `0x41d` (CONFIRMED): with the victory latch `+0x3e4` clear the exe ends the game and posts `0x421` (main menu); `ScenarioLeaveLocation` (the shop table update) and the
    carry-over run only on the victory path."""
    g = game()
    before = repr((g.camp.shop, g.camp.vars))
    assert g.leave_mission(None, "lost").kind == "main_menu"
    assert repr((g.camp.shop, g.camp.vars)) == before
