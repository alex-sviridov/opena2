"""The shop windows' model (L8, docs/engine/town-shop.md; the screen is `engine/shell/shop.py`): the four shelves of the town's stock, the table (the cart), the trade rules of
the client (drag rules, totals, the Buy / Sell refusals) and of the server (settlement by its own prices, Cancel / Leave returning the cart), the hero arrows and the one
gold of the party.  Pure: no pygame, no files; the item table (`assets.items()`) is an argument.

CONFIRMED (town-shop 3.2 / 3.3 / 5, items 12 / 13): region kinds 1 equipment, 2 pack, 4 table, 5..8 shelf 0..3; a price-0 item goes to a pack only; a shop item returns only to
its own shelf; the totals `gold`, `-sum(price x count)` over the shop-owned table items, `+sum(((price + 1) / 2) x count)` over the hero-owned ones; Buy with `gold + buy < 0` sends
nothing (the nofit sound); the server buys in table order and stops at the first item the gold does not cover, sells at `ftol(price x count x 0.5 + 0.5)`, files a sold item
on the shelf whose block takes its group (armour `0x1000000`, weapon `0x400000`, other `0x4000000`), Cancel / Leave return shop items to their shelf and hero items to the pack.
The stock is regenerated at every arrival in a town (`TownCore.visit`), not at every opening of the window.

CONFIRMED in the L8 REA round (town-shop 9): a drag moves one piece, Shift (`0x6227dc`) the whole stack (`0x4b242d`); the table holds 5 lots (`0x4b5a63`); a table lot dropped on a pack is
filed there by the server's mixed path (`0x4f5bec` -> `0x4f5e15`) with no payment, the client's release has no origin test (`0x4b25cb`): the exe's own quirk, kept; shelf -> pack does nothing on the
server; a sold item goes to the block of `Stock.block_for` (never gone).
DECISIONs (INFERRED): the doll is refused as a target (the town has no equip path: no world); a hero that was never in a world has only the items he bought (`RosterEntry.bought`) to sell; one
price source (the item's own price) for display and charge."""

import random
from dataclasses import dataclass, replace

from allods2.formats import itemdefs as idefs
from allods2.formats import itemgen
from allods2.formats import saves as S

from engine import inn as I
from engine.sim import campaign as C
from engine.sim import gear

KIND_EQUIP, KIND_PACK, KIND_TABLE, KIND_SHELF = 1, 2, 4, 5
SHELVES = 4
DRUID_TOWN, DRUID_GATE = 3, 0x302                  # `FUN_004bfd3a`: the druid shop's fourth shelf needs `Var(0x302) != 0`
GROUP_FLAG = {1: itemgen.GEN_ARMOUR, 2: itemgen.GEN_WEAPONS, 3: itemgen.GEN_STOCK, 4: itemgen.GEN_STOCK, 5: itemgen.GEN_STOCK}      # `FUN_00521d4c`

# -- geometry of the window (town-shop 2.1; window-relative, 640x480 area) ------------------------------------------------------------------------
STOCK_PANEL, TABLE_PANEL, PACK_PANEL = (0, 0, 164, 303), (0, 303, 480, 87), (0, 390, 480, 90)
SHOPKEEPER_PANEL = (164, 0, 316, 303)
BUTTONS_PANEL = (464, 0, 176, 238)
BUTTONS = ((494, 15, 120, 52), (483, 67, 140, 46), (483, 114, 140, 46), (494, 160, 120, 52))      # R0..R3 = Cancel, Buy, Sell, Exit (INFERRED assignment, town-shop 2.2)
B_CANCEL, B_BUY, B_SELL, B_EXIT = range(4)
INFO_PANEL, ARROWS = I.INFO_PANEL, I.ARROWS         # the unit info panel and its hero arrows are the inn's (town-shop 2.1: moved to (480, 238) the same way)
SHELF_RECTS = ((190, 110, 105, 185), (5, 110, 105, 185), (150, 5, 140, 100), (8, 5, 142, 100))      # panel-relative A, B, C, D = shelf 0..3 (CONFIRMED: `0x4bbfa6` tests the fields `+0x60 + 0x10 i`, the ctor `0x4b9cf5` fills them A, B, C, D)
CELL = 80
STOCK_COLS, STOCK_ROWS, STOCK_LEFT, STOCK_TOP = 2, 3, 1, 31       # CONFIRMED `0x4b35b0`: cell (i, j) = (x + 80 i + 1, arrow bottom + 80 j - 1), the arrow rects end at y = 32
STOCK_ARROWS = ((46, 0, 72, 32), (46, 271, 72, 32))             # CONFIRMED `0x4b35b0`: (0x2e, 0)-(0x76, 0x20) and (0x2e, 0x10f)-(0x76, 0x12f)
STRIP_COLS, STRIP_LEFT = 5, 32
STRIP_TOP = {"table": 0, "pack": 5}                             # CONFIRMED `0x4b579d` (cell y = panel top + 80 j) / `0x4b4a05` (+ 5)
TABLE_CAPACITY = STRIP_COLS                                     # CONFIRMED `0x4b5a63`: the table refuses a new item when its list holds `cols x rows` entries and none merges
STRIP_ARROWS = {"table": ((0, 0, 32, 87), (432, 0, 48, 87)), "pack": ((0, 0, 32, 90), (432, 0, 48, 90))}     # CONFIRMED: `(x, y, x + 0x20, bottom)` and `(x + 0x1b0, y, right, bottom)`
LABEL_LINES = (0x48, 0x46, 0x47, 0x49)                          # main.txt Undo / Buy / Sell / Exit, drawn over the number of the same button
LABEL_DY = (6, 6, 8, 6)                                         # CONFIRMED `0x4bcd05`: caption y = rect top + dy + height / 4, number y = rect top + dy - 8 + 3 height / 4 (dy 0 for the Sell button, 6 else, + 1 while pressed)


def stock_cell(i):
    """Rect of the stock panel's cell `i` (0..5, row major)."""
    return (STOCK_LEFT + CELL * (i % STOCK_COLS), STOCK_TOP + CELL * (i // STOCK_COLS), CELL, CELL)


def strip_cell(panel, k):
    """Rect of the table / pack strip's cell `k` (0..4), window-relative."""
    key = "table" if panel == TABLE_PANEL else "pack"
    return (panel[0] + STRIP_LEFT + CELL * k, panel[1] + STRIP_TOP[key], CELL, CELL)


def label_at(i, pressed=False):
    """Centre of button `i`'s caption (`0x4bcd05`: x = rect left + width / 2, y = top + dy + height / 4, one pixel lower while pressed)."""
    x, y, w, h = BUTTONS[i]
    return x + w // 2, y + LABEL_DY[i] + h // 4 + (1 if pressed else 0)


def number_at(i, pressed=False):
    """Centre of the number under the caption: y = top + dy - 8 + 3 height / 4 (the exe's -2 / 0 / -2 / -2 against the caption's +6 / +8 / +6 / +6)."""
    x, y, w, h = BUTTONS[i]
    return x + w // 2, y + LABEL_DY[i] - 8 + (3 * h) // 4 + (1 if pressed else 0)


def rect_has(r, x, y):
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


def price_bar_frame(price):
    """The price bar's frame (60 x 10, `costs1..7` / `costm1..7`): `min(trunc(log10(price)), 6)` (sprites.md); price 0 has none."""
    if price < 1:
        return None
    n = 0
    while price >= 10 and n < 6:
        price //= 10
        n += 1
    return n


# -- items ------------------------------------------------------------------------------------------------------------------------------------------

def price_of(table, item):
    """The client's attribute 1: the item's own price, else the table record's (`gear.make_item`); never negative (a quest item's `-1` is 0)."""
    if item is None or not item.code:
        return 0
    p = item.price
    if not p:
        r = gear.resolve(table, item)
        p = r.price if r is not None else 0
    return max(0, p)


def group_of(table, item):
    """The item group byte `+0x44` (1 armour, 2 weapon, 3 potion, 4 scroll, 5 book, 0 quest)."""
    r = gear.resolve(table, item)
    if r is None:
        return 0
    d = r.defn
    if d.kind == idefs.WEAPON:
        return itemgen.T_WEAPON
    if d.kind in (idefs.ARMOUR, idefs.SHIELD):
        return itemgen.T_ARMOUR
    return d.subtype if d.subtype in (itemgen.T_POTION, itemgen.T_SCROLL, itemgen.T_BOOK) else 0


def from_generated(g):
    return S.Item(g.code & 0xFFFF, g.count, g.price, gear.mods_of(g.effects))


class Stock:
    """The server's shop object: four shelves of `saves.Item`s and the flags of the blocks they were made from (the sold-item shelf rule)."""

    def __init__(self, shelves=None, flags=None):
        self.shelves = shelves if shelves is not None else [[] for _ in range(SHELVES)]
        self.flags = flags if flags is not None else [0] * SHELVES

    @classmethod
    def generate(cls, table, blocks, rng):
        """`FUN_00522767`: per assortment block `[min, max, count, stack, flags]` the generator (`itemgen.generate`) and the stamp of the shelf."""
        shelves, flags = [], []
        for b in range(SHELVES):
            blk = blocks[b] if b < len(blocks) else [0, 0, 0, 0, 0]
            lo, hi, count, stack, fl = blk
            items = itemgen.generate(table, lo, hi, fl, count, stack, rng) if table is not None and count else []
            shelves.append([from_generated(g) for g in items])
            flags.append(fl)
        return cls(shelves, flags)

    def block_for(self, table, item):
        """`FUN_00521d4c` (CONFIRMED): the shelf a returned hero item goes to.  A non-stackable item (modifiers) that is not a book takes the first of blocks 0..2 with the
        enchant flag `0x20000000`, else block 3; any other item takes the first block with its group bit and without the enchant flag, else the first with the group bit, else
        block 3 (the scans stop at 3 whatever they found)."""
        g = GROUP_FLAG.get(group_of(table, item), 0)
        fl = self.flags
        if not gear.stackable(table, item) and group_of(table, item) != itemgen.T_BOOK:
            return next((b for b in range(3) if fl[b] & itemgen.GEN_ENCHANT), 3)
        b = next((b for b in range(3) if fl[b] & g and not fl[b] & itemgen.GEN_ENCHANT), 3)
        if not fl[b] & g or fl[b] & itemgen.GEN_ENCHANT:
            b = next((b for b in range(3) if fl[b] & g), 3)
        return b

    def file(self, table, item):
        """File a returned hero item on its block's shelf (merging a stackable one); returns the shelf."""
        b = self.block_for(table, item)
        gear.pack_insert(table, self.shelves[b], item)
        return b


def open_stock(core, game, town, rng=None):
    """The stock of the current visit (`TownCore.stock`; made at the first opening after an arrival, kept while the player walks in and out of the shop)."""
    if core.stock is None or core.stock_visit != core.visit:
        seed = (rng or random).getrandbits(31)
        table = game.assets.items() if game.install is not None or game._assets is not None else None
        core.stock = Stock.generate(table, game.camp.shop.get(town, []), itemgen.MsvcRng(seed or 1))
        core.stock_visit = core.visit
    return core.stock


# -- the heroes' bags -------------------------------------------------------------------------------------------------------------------------------

def hero_entries(game):
    """The living heroes in creation order (town-hero 5): the roster's story heroes (the same list as the inn's arrows)."""
    return [e for e in game.roster if e.human and e.number in C.STORY_HEROES]


class Bag:
    """One hero's pack and doll as the shop reaches them: the carried state of the roster entry (`CARRY`), or the entry's `bought` list while he was never in a world."""

    def __init__(self, entry):
        self.entry = entry

    @property
    def pack(self):
        st = self.entry.state
        return list(st.pack) if st is not None else list(self.entry.bought)

    def set_pack(self, items):
        st = self.entry.state
        if st is not None:
            st.pack = tuple(items)
            gear.sync_carried(st)
        else:
            self.entry.bought = tuple(items)

    def slots(self):
        st = self.entry.state
        return gear.slots_of(st) if st is not None and st.equipment else {}

    def take_slot(self, slot):
        st = self.entry.state
        slots = gear.slots_of(st)
        item = slots.pop(slot, None)
        if item is not None:
            gear._store(st, slots)
        return item


@dataclass
class Lot:
    """One entry of the table: `side` "buy" (shop-owned, from `shelf`) or "sell" (hero-owned, `hero` = the roster number it came from)."""
    item: object
    side: str
    shelf: int = -1
    hero: int = 0


@dataclass
class Carried:
    """The carried item (`client+0x3f4`): the region it comes from and `count` pieces of `item`."""
    kind: int
    index: int
    count: int
    item: object


@dataclass(frozen=True)
class Effect:
    """What an action did, in order: `("sound", slot)`, `("yes",)` / `("refuse",)` (the shopkeeper's clips), `("shelf", i)`."""
    kind: str
    value: object = None


class ShopState:
    """One opening of the shop window (`0x4b8b98` load): the shown hero (the first of the list), the shown shelf 0, an empty table."""

    def __init__(self, game, town, stock, table):
        self.game, self.town, self.stock, self.table = game, town, stock, table
        self.entries = hero_entries(game)
        self.hero = 0
        self.shelf = 0
        self.lots = []
        self.carried = None
        self.scroll = {"stock": 0, "table": 0, "pack": 0}
        self.log = []

    # -- what is shown ---------------------------------------------------------------------------------------------------------------------------
    @property
    def gold(self):
        return self.game.gold

    def entry(self):
        return self.entries[self.hero] if self.entries else None

    def bag(self, entry=None):
        entry = entry or self.entry()
        return Bag(entry) if entry is not None else None

    def pack(self):
        b = self.bag()
        return b.pack if b is not None else []

    def shelf_items(self):
        return self.stock.shelves[self.shelf]

    def price(self, item):
        return price_of(self.table, item)

    def totals(self):
        """`FUN_004b960c`: (gold, minus the buy prices, the sell values, the gold after the deal)."""
        buy = -sum(self.price(l.item) * l.item.count for l in self.lots if l.side == "buy")
        sell = sum(((self.price(l.item) + 1) // 2) * l.item.count for l in self.lots if l.side == "sell")
        return self.gold, buy, sell, self.gold + buy + sell

    def hero_next(self):
        if self.entries:
            self.hero = 0 if self.hero + 1 >= len(self.entries) else self.hero + 1
        self.scroll["pack"] = 0
        return self.hero

    def hero_prev(self):
        if self.entries:
            self.hero = len(self.entries) - 1 if self.hero == 0 else self.hero - 1
        self.scroll["pack"] = 0
        return self.hero

    # -- shelves -----------------------------------------------------------------------------------------------------------------------------------
    def shelf_open(self, i):
        """`FUN_004bfd3a` / `FUN_004bf096`: the druid shop's fourth shelf is refused while `Var(0x302)` is 0 (single player)."""
        return not (self.town == DRUID_TOWN and i == 3 and not self.game.camp.get(DRUID_GATE))

    def select_shelf(self, i):
        """A click on a shelf: the stock panel shows it from the start; `[]` when refused."""
        if not 0 <= i < SHELVES or not self.shelf_open(i):
            return []
        self.shelf = i
        self.scroll["stock"] = 0
        return [Effect("sound", "depart"), Effect("shelf", i)]

    # -- carrying ----------------------------------------------------------------------------------------------------------------------------------
    def pick(self, kind, index, whole=False):
        """The pick-up of a cell (`0x4b2588` + the mouse move): one piece, the whole stack with `whole`.  False when the cell is empty or something is carried."""
        if self.carried is not None:
            return False
        item = self.item_at(kind, index)
        if item is None:
            return False
        n = item.count if whole else 1
        self.carried = Carried(kind, index, max(1, min(n, item.count)), replace(item, count=max(1, min(n, item.count))))
        return True

    def item_at(self, kind, index):
        if kind == KIND_EQUIP:
            b = self.bag()
            return b.slots().get(index + 1) if b is not None else None
        if kind == KIND_PACK:
            pack = self.pack()
            return pack[index] if 0 <= index < len(pack) else None
        if kind == KIND_TABLE:
            return self.lots[index].item if 0 <= index < len(self.lots) else None
        if KIND_SHELF <= kind < KIND_SHELF + SHELVES:
            items = self.stock.shelves[kind - KIND_SHELF]
            return items[index] if 0 <= index < len(items) else None
        return None

    def drop_allowed(self, kind):
        """The hover test `0x4b3efa` / release rules 1 and 3: the carried item may go to region `kind`."""
        c = self.carried
        if c is None:
            return False
        if self.price(c.item) == 0 and kind != KIND_PACK:
            return False
        if kind == KIND_TABLE:
            return c.kind == KIND_TABLE or self.table_room(c.item)
        if kind == KIND_PACK:
            return c.kind in (KIND_PACK, KIND_EQUIP, KIND_TABLE)      # a table lot of either side: the server's mixed path files it in the pack, paid or not (below)
        if KIND_SHELF <= kind < KIND_SHELF + SHELVES:
            return c.kind == kind or (c.kind == KIND_TABLE and self.lots[c.index].shelf == kind - KIND_SHELF)
        return False

    def table_room(self, item):
        """`0x4b5a63` (CONFIRMED): the table takes an item when it merges with a lot (same code, both stackable) or has fewer than `TABLE_CAPACITY` lots."""
        if any(l.item.code == item.code and gear.stackable(self.table, l.item) and gear.stackable(self.table, item) for l in self.lots):
            return True
        return len(self.lots) < TABLE_CAPACITY

    def drop(self, kind, index=-1):
        """The release of the carried item over region `kind` (cell `index`, -1 = past the items): the move (message `0x22`), or the return to its origin with the nofit sound."""
        c = self.carried
        if c is None:
            return []
        ok = self.drop_allowed(kind)
        self.carried = None
        if not ok:
            return [Effect("sound", "nofit")]
        if kind == KIND_TABLE:
            if c.kind == KIND_TABLE:
                return []
            self._to_table(c)
        elif kind == KIND_PACK:
            self._to_pack(c, index)
        else:
            self._to_shelf(c)
        return []

    def _merge_lot(self, lot):
        for l in self.lots:
            if (l.side, l.shelf, l.hero) == (lot.side, lot.shelf, lot.hero) and l.item.code == lot.item.code and gear.stackable(self.table, l.item) and gear.stackable(self.table, lot.item):
                l.item = replace(l.item, count=l.item.count + lot.item.count)
                return
        self.lots.append(lot)

    def _to_table(self, c):
        if KIND_SHELF <= c.kind < KIND_SHELF + SHELVES:
            items = self.stock.shelves[c.kind - KIND_SHELF]
            item = gear.pack_take(items, c.index, c.count)
            if item is not None:
                self._merge_lot(Lot(item, "buy", c.kind - KIND_SHELF))
            return
        bag, number = self.bag(), self.entry().number
        if c.kind == KIND_PACK:
            pack = bag.pack
            item = gear.pack_take(pack, c.index, c.count)
            bag.set_pack(pack)
        else:
            item = bag.take_slot(c.index + 1)
            if item is not None:
                bag.set_pack(bag.pack)                     # the slot change is stored by `take_slot`; mirror the pack for the carried lists
        if item is not None:
            self._merge_lot(Lot(item, "sell", hero=number))

    def _to_pack(self, c, index):
        bag = self.bag()
        if c.kind == KIND_TABLE:
            item = self._take_lot(c.index, c.count)
            if item is not None:
                self._file(bag, item, index)
        elif c.kind == KIND_PACK:
            pack = bag.pack
            item = gear.pack_take(pack, c.index, c.count)
            if item is not None:
                gear.pack_insert(self.table, pack, item, index if index >= 0 else gear.APPEND)
            bag.set_pack(pack)
        else:
            item = bag.take_slot(c.index + 1)
            if item is not None:
                self._file(bag, item, index)

    def _to_shelf(self, c):
        shelf = c.kind - KIND_SHELF if c.kind != KIND_TABLE else self.lots[c.index].shelf
        if c.kind == KIND_TABLE:
            item = self._take_lot(c.index, c.count)
            if item is not None:
                gear.pack_insert(self.table, self.stock.shelves[shelf], item)

    def _take_lot(self, i, count):
        lot = self.lots[i]
        if count < lot.item.count:
            lot.item = replace(lot.item, count=lot.item.count - count)
            return replace(lot.item, count=count)
        self.lots.pop(i)
        return lot.item

    def _file(self, bag, item, index=-1):
        pack = bag.pack
        gear.pack_insert(self.table, pack, item, index if index >= 0 else gear.APPEND)
        bag.set_pack(pack)

    # -- the buttons -------------------------------------------------------------------------------------------------------------------------------
    def buy(self):
        """`0x4b93cf`: nothing to buy -> nothing; not enough gold -> the refuse clip + nofit, no message; else message `0x33` and the server's settlement."""
        gold, buy, _, _ = self.totals()
        if buy == 0:
            return []
        if gold + buy < 0:
            return [Effect("refuse"), Effect("sound", "nofit")]
        bag = self.bag()
        for lot in [l for l in self.lots if l.side == "buy"]:         # `FUN_00521c29`: table order, stops at the first item the gold does not cover
            cost = self.price(lot.item) * lot.item.count
            if self.game.gold < cost:
                break
            self.game.gold -= cost
            self.lots.remove(lot)
            if bag is not None:
                self._file(bag, lot.item)
        return [Effect("yes"), Effect("sound", "buy")]

    def sell(self):
        """`0x4b935d`: no sell value -> nothing; else message `0x34`: the server pays `ftol(price x count x 0.5 + 0.5)` per stack and the item goes back to a shelf."""
        _, _, sell, _ = self.totals()
        if sell == 0:
            return []
        for lot in [l for l in self.lots if l.side == "sell"]:
            p = self.price(lot.item)
            if p == 0:
                continue
            self.game.gold += (p * lot.item.count + 1) // 2
            self.lots.remove(lot)
            self.stock.file(self.table, lot.item)
        return [Effect("yes"), Effect("sound", "sell")]

    def return_table(self):
        """`0x4b94a4` + the server's cancel (`FUN_005220d9`): shop items back to their shelf, hero items into the pack of the hero they came from (the shown one when he is gone)."""
        shown = self.entry()
        for lot in self.lots:
            if lot.side == "buy":
                gear.pack_insert(self.table, self.stock.shelves[lot.shelf], lot.item)
            else:
                owner = next((e for e in self.entries if e.number == lot.hero), shown)
                if owner is not None:
                    self._file(Bag(owner), lot.item)
        self.lots = []

    def cancel(self):
        self.return_table()
        return [Effect("sound", "undo")]

    def leave(self):
        """Exit / ESC (`0x4b956e`): the table is returned (no charge), then the window closes."""
        self.carried = None
        self.return_table()
        return []
