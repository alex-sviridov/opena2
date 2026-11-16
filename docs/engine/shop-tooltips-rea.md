# Shop window tooltips (REA of the GOG `allods2.exe`)

Marks: **CONFIRMED** = read in the decompilation / disassembly (routine given); **INFERRED** = deduced. Texts are `main.txt` lines read from the install (`FUN_0041f350(n)` = line n, 0-based, `main.line(n)` in the engine; check: line `0x4a` = "Money", `0x48` = "Undo"). The mouse manager (500 ms hover, box above / right of the pointer, `#` = line break) is [ui-layout 11.6b](ui-layout.md#116b-tooltips-mouse-manager-fun_004268c4-bar-fun_004ad61c-box-fun_0042787b--fun_00427999) and already built (`engine/ui/tooltip.py`). It asks the deepest window under the pointer for its **vtable slot 5 (`+0x14`)**; an empty answer = nothing shown until the pointer moves again.

## 1. Slot 5 of every shop panel (CONFIRMED, vtable dumps)

| panel (class vtable) | slot 5 | notes |
|---|---|---|
| stock `0x5cf0c0` (also `0x5cf768`, `0x5cf828`: the same routine) | `0x4b37f7` | all three towns |
| table `0x5cf240` | `0x4b5939` | all towns (ctor shared) |
| pack strip `0x5cf180` | `0x4b4ba3` | all towns |
| shopkeeper human `0x5cf398` / druid / Kaarg | `0x4bb2c4` / `0x4bfee2` / `0x4c3036` | |
| buttons `0x5cf458` | `0x4bccf8` = `return 0` | ctor `0x4bc2b0` is called by all three windows (`0x4b85e2`, `0x4bde3a`, `0x4c0050`): no tooltip in any town |
| the three shop windows `0x5cf300` etc. | `0x4d43b5` (generic) | returns the base window's stored tooltip string unless virtual `+0x20(0x20)` is non-zero; INFERRED empty (the shop sets no text) |
| unit info panel (window 7, the same one as in the mission) | `0x4ae232` | see 3 |

**Gates common to stock / table / pack / shelf / buttons panels (CONFIRMED):** shop window `+0x148` (loaded flag) must be non-zero, else no tooltip. Stock, table and pack also need **`client+0x3f4 == 0` (no item carried on the cursor)**: while an item is dragged these three show nothing. The shopkeeper panel does not test the carried item, only `panel+0x240 & 0x80` (the identify box, never set in the GOG single player, INFERRED dead) which suppresses it.

## 2. Table: what answers where

Pointer is converted to window-relative coordinates (`0x4b65b0`), then `+0x8c` (cell hit test) returns a cell index or < 0.

| region (window-relative; per-panel rects of [town-shop 2.1](town-shop.md#21-the-window-and-its-panels-confirmed-create-0x4b85e2-ctor-args-id-l-t-r-b-parent) and `engine/shop.py`) | text | condition |
|---|---|---|
| **Stock cell** (2 x 3 cells 80x80 at panel (1 + 80 i, 31 + 80 j) of panel (0,0,164,303)) | item: `FUN_004b14d4` (below) | cell holds an item (list entry non-null); empty cell: none |
| Stock scroll arrow up, panel rect (46, 0)-(118, 32) (`+0x20cc`) | main `0x38` "Scroll up" | pointer not on a cell |
| Stock scroll arrow down, (46, 271)-(118, 303) (`+0x20dc`) | main `0x39` "Scroll down" | same |
| Stock panel elsewhere | main `0x3c` "Shop Shelf" | same |
| **Pack cell** (5 x 1 at panel x 32 + 80 i, y 5, panel (0,390,480,90)) | item: `FUN_004b14d4` | hero-owned item; empty cell: none. The money cell (`FUN_0041ea40`: item word `+6 == -1`) shows main `0x4a` "Money" instead |
| Pack arrow left (0,0)-(32,90) (`+0x20cc`) | main `0x36` "Scroll left" | pointer not on a cell |
| Pack arrow right (432,0)-(480,90) (`+0x20dc`) | main `0x37` "Scroll right" | same |
| Pack panel elsewhere | main `0x3a` "Your hero's inventory" | same |
| **Table cell** (5 x 1, panel (0,303,480,87), cell x 32 + 80 i) | item: `FUN_004b14d4` | item on the table; empty cell: none |
| Table panel elsewhere, **including its two scroll arrows** (no arrow test in `0x4b5939`) | main `0x3b` "Put items here to buy/sell" | pointer not on a cell |
| **Shelf i** of the keeper panel, rect `+0x60 + 0x10 i` (panel-relative, SHELF_RECTS_BY_TOWN in `engine/shop.py`), tested i = 0..3, first hit wins | town 1 human: main `0x3e + i` = "Armor", "Weapons", "Magic Items", "Scrolls, Books & Potions"; town 3 druid: `0x112 + i` = "Armors and weapons", "Magic items", "Scrolls, spellbooks and potions", "Elven goods"; town 2 Kaarg: `0x116 + i` = "Armors", "Magic items", "Scrolls, spellbooks and potions", "Weapons" | `panel+0x240 & 0x80 == 0`. The 4th druid shelf rect answers **even while `Var(0x302) == 0`** (the tooltip does not test it; only the click does): CONFIRMED by `0x4bfee2` (no Var test), INFERRED that the elven shelf is therefore announced before it is unlocked. No per-shelf "selected / empty" variation |
| Keeper rect `+0xe0` (human (110,110,80,185), druid (197,89,72,164), Kaarg (125,113,72,96), panel-relative l,t,w,h) not inside a shelf rect | main `0x3d` "Shopkeeper" | same |
| Keeper panel elsewhere (outside all five rects) | none | |
| **Buttons panel** (all 4 buttons R0..R3, captions, numbers) | none (`return 0`) | always. Main `0x42` "Buy all items placed on the table", `0x43` "Sell all items placed on the table", `0x44` "Clear table", `0x45` "Exit shop" have **no caller in the shop** (INFERRED unused) |
| Shop window background / gaps | none (INFERRED, generic slot) | |

Rect coordinates for the keeper: `0x4bb2c4` subtracts the panel's own rect origin (`panel+0x5c` window rect `+8`) from the pointer, so shelf / keeper rects are panel-relative (CONFIRMED asm `0x4bb2ee`..`0x4bb322`); shelf rects at `this + 0x60 + 16 i`, keeper at `this + 0xe0` (CONFIRMED). The rect order druid / Kaarg and values are from shop-rea2 section 2 (not re-read here).

## 3. Item text (cell tooltips) and the info panel

**Item cell routine `FUN_004b14d4`** (shared by stock / table / pack; CONFIRMED asm): list entry = `FUN_0041f7a0(index)` of the panel's list (`+0x84`); entry null -> no tooltip; money item (`FUN_0041ea40`) -> main `0x4a` "Money"; `FUN_004a4170(item)` (= not money and item word `+0x10 == 0`) -> no tooltip (INFERRED: item without a template record); else **`FUN_0043901f(item)`**: exactly the pack tooltip of [ui-layout 11.13](ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked) (`itemname.txt` name, then one `#Name value` row per `itemname.pkt` descriptor tag, `Magic:` row and modifier rows for enchanted items; engine `pack.item_tooltip`). **No shop-specific addition: no price, no count, no "sell value"** (the routine receives only the item; the price is the cell's drawn price bar). A hero-owned item in the table / pack and a stock item use the same text (no owner test).

**Info panel (`0x4ae232`, window 7, client mode `+0x404`; in the shop mode = 2, CONFIRMED asm, rects relative to the panel at (480,238)-(640,480)):**

| region | text | condition (shop) |
|---|---|---|
| hero arrow left (481,443)-(513,475) | main `0x34` "Previous hero" | `mode & 0x226` set (shop bit 2) and not `mode & 0x200` branch |
| hero arrow right (599,443)-(631,475) | main `0x35` "Next hero" | same |
| mode button (608,238)-(640,274) | panel `+0x70 == 0` -> `0xc` "Switch to Picture <TAB>"; `+0x70 != 0` -> `0xd` "Switch to Stats <TAB>" (CONFIRMED asm `0x4ae54d`..`0x4ae566`; check against ui-layout 11.13, which names `0xc` the text-mode line) | `mode & 0x600 == 0` and the mission-only flag `bVar1` (mode == 1) false |
| book button (480,238)-(508,274) | `0x8` "Open Spellbook <Q>,<B>" / `0x9` "Close Spellbook <Q>,<B>" (`FUN_0041aef1` = book open) | answers whenever `mode & 3 != 0` and `mode & 4 == 0`, i.e. also in the shop (CONFIRMED code); whether the button is drawn in the shop is INFERRED yes (same window), so the tip is live |
| pack button (480,440)-(508,480) | none in the shop | needs `mode & 1` and not `mode & 2` |
| disk button (606,444)-(638,476) | none in the shop | only reached when `mode & 0x226 == 0` (`0xe` "Main Menu <ESC>") |
| doll layer of the shown hero (`client+0x140 == 1`, hero `client+0x138`) | picture mode: `FUN_0043901f(equipped item)` via the 160-wide hit mask at `window+0x78` (`byte != 0`, layer index; empty slot -> none); text mode: `FUN_0046b9f0` row text | `mode & 8 == 0`; if the hero's record `+0x14 -> +4` is set and `FUN_0041e860(...)` is zero (a foreign / not-ours hero) only the text-mode row text is shown, never the picture-mode item; INFERRED the shop's hero is ours so the item text shows |
| everywhere | none while an item is carried (`client+0x3f4 != 0`) or a modal (`mode & 8`) | |
| portrait itself | none other than the doll-layer rule | |

## 4. When NO tooltip appears (summary)
- Shop not yet loaded (`window+0x148 == 0`); a modal dialog (`mode & 8`), manager enable flag `+0xa0 == 0` (cleared while a modal window opens).
- An item is on the cursor: stock, table, pack and info panel are silent (the keeper panel is not gated).
- Empty stock / table / pack cell; null-template item.
- Buttons panel (all four buttons, all towns).
- Identify box up (`+0x240 & 0x80`, dead code in the GOG single player).
- Pointer in the keeper panel outside the five rects.

## 5. Engine to-do (not done here)
Add to `engine/shell/shop.py`: a `tooltip_text(pos)` using the table in 2 and 3 (the info panel and item rows reuse `pack.item_tooltip` / `info` helpers), gated on "nothing carried"; texts via `main.line(n)`.
