# Shop windows: second REA round (shelves, price text, shopkeeper animation, tooltips)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)); continues [town-shop](town-shop.md) (sections 2.3, 8.8, 9) and answers the three play-test faults of [town.md 5 "L8 as built"](town.md#l8-as-built). **CONFIRMED** = read in the exe (routine given), **INFERRED** = shape / analogy. Coordinates are relative to the shopkeeper panel origin `P` (window `(164, 0)`) unless noted; `O` = window origin.

## 0. Findings in one table

| play-test fault | cause (engine) | exe fact |
|---|---|---|
| (a) shelves select the wrong block | `SHELF_RECTS` = the **human** rects used for all three towns | the Kaarg and druid panels **replace the four hit rects** in their own constructors (`0x4c0ee5`, `0x4beccf`); shelf index = block index in every town, but the rect -> art mapping is per town (3) |
| (b) no animation / highlight | not built | the clicked shelf stays highlighted (clip or picture), the keeper idles, buy / sell / refuse clips; **no hover effect exists** (4, 5) |
| (c) no price number | `_cell` draws no `Text` | exe draws the number **on the bar, right-aligned**; bar is at the **top** of the cell, not the bottom (6) |

## 1. Panel classes (CONFIRMED)

One panel class family draws the keeper scene (`client+0xf8/+0xfc/+0x100` windows own it as child `+0x74`):

| class | ctor | vtable | town |
|---|---|---|---|
| base / human | `0x4b9cf5` | `0x5cf398` | 1 |
| druid | `0x4beccf` (calls the base ctor, then sets vtable and **overwrites** the rects) | `0x5cf570` | 3 |
| Kaarg | `0x4c0ee5` (same) | `0x5cf6b8` | 2 |

Slots (human / druid / Kaarg): `+0x14` tooltip `0x4bb2c4` / `0x4bfee2` / `0x4c3036`; `+0x2c` draw `0x4bb3d7` / `0x4bf908` / `0x4c28c6`; `+0x4c` mouse move `0x4bbf2c` (shared; returns **100 = no hover state**, `0x4c33f0`); `+0x54` left press `0x4bbfa6` / `0x4bfdf1` / `0x4c2f57`; `+0x78` art load `0x4baa98` / `0x4bf0d6` / `0x4c12ca`; `+0x7c` unload; `+0x80` / `+0x84` Yes / No start (human `0x4bae3e` / `0x4baf3f`; druid `0x4bf5de` / `0x4bf5f7` only free frames); `+0x88` animation step (`0x4bb040` / `0x4bf610` / `0x4c25ce`); `+0x8c` shelf-clip load (human `0x4bacbd`); `+0xa4` accept shelf `i` (`0x4bbd46` / `0x4bfd3a` / `0x4c2df2`).
Panel fields: `+0x60 + 0x10 i` hit rect of shelf `i`; `+0xa0 + 0x10 i` human highlight-clip rect `i`; `+0xe0` keeper rect (tooltip only); `+0x240` state bits (`1<<i` shelf clip i running (human), `0x10` idle clip (human) / idle clip a1 (druid, Kaarg), `0x20` Yes (human) / idle clip a2 or buy reaction (druid, Kaarg), `0x40` No, `0x80` item-identify box); `+0x244 + 4 i` shelf clip frame; `+0x254` pose / clip frame counter; window `+0x132` = selected shelf (**100 = none**, ctor value).

## 2. Hit rects and art per town (CONFIRMED ctors; rects are `P`-relative, final = after the ctor's `OffsetRect(5, 5)` for druid / Kaarg)

The shopkeeper picture `ShopMain.bmp` (288 x 288) is drawn at **P + (5, 8)** by all three classes (`+0x49`), after the frame sprite `ShopFrame.256` (316 x 303, hole `x 5.., y 8..295`) at `P + (0, 0)` (`0x4bb3d7`, `0x4bf908`, `0x4c28c6`). **The engine draws it at (14, 7): wrong.**

| town | shelf | hit rect (l, t, w, h) | art there (verified by rendering the bitmaps over the picture) | tooltip main id | shelf block holds (generator, this install) |
|---|---|---|---|---|---|
| 1 human | 0 | (190, 110, 105, 185) | lower right: armour, shields | `0x3e` "Armor" | armour (flags `0x1381CC03`) |
| | 1 | (5, 110, 105, 185) | lower left: spears, axes | `0x3f` "Weapons" | weapons (`0x10418103`) |
| | 2 | (150, 5, 140, 100) | upper right: amulets, bow | `0x40` "Magic Items" | staffs with modifiers (`0x28018100`) |
| | 3 | (8, 5, 142, 100) | upper left: bottles, books | `0x41` "Scrolls, Books & Potions" | books, scrolls, potions (`0x04000000`) |
| 2 Kaarg | 0 | (5, 5, 60, 202) | left: armour | `0x116` "Armors" | armour (`0x1383C305`) |
| | 1 | (65, 63, 48, 150) | middle lower: staffs | `0x117` "Magic items" | enchanted staffs, clubs, bows (`0x2BC3C304`) |
| | 2 | (65, 5, 124, 58) | top middle: books, potion | `0x118` "Scrolls, spellbooks and potions" | stock (`0x04000000`) |
| | 3 | (195, 5, 98, 260) | right: axes, bow | `0x119` "Weapons" | weapons (`0x10438305`) |
| 3 druid | 0 | (5, 109, 88, 112) | left lower: armour | `0x112` "Armors and weapons" | armour + weapons (`0x13C7D318`) |
| | 1 | (5, 49, 96, 60) | upper left: staffs | `0x113` "Magic items" | enchanted (`0x2BC7D318`) |
| | 2 | (121, 33, 72, 112) | middle: potions | `0x114` "Scrolls, spellbooks and potions" | stock (`0x04000000`) |
| | 3 | (93, 169, 96, 104) | lower middle: bow = elven goods; hit **only when `Var(0x302) != 0`** (`0x4bfdf1`) | `0x115` "Elven goods" | block 3, empty until `0x80000` is OR-ed in (`talk_to(0x4e02a3)`) |
| all | keeper | human (110, 110, 80, 185); druid (197, 89, 72, 164); Kaarg (125, 113, 72, 96) | the shopkeeper | `0x3d` "Shopkeeper" | |

Source of the numbers: human `0x4b9cf5` (`+0x60`: `(0xbe, 0x6e, 0x127, 0x127)` etc. = A, B, C, D of town-shop 2.3, **= shelf 0..3 CONFIRMED**: the press loop `0x4bbfa6` reads `lea ecx, [edx + ecx + 0x60]`, `ecx = i << 4`); druid `0x4beccf` (`CRect(point, size)` pairs `(0,0x68)+(0x58,0x70)`, `(0,0x2c)+(0x60,0x3c)`, `(0x74,0x1c)+(0x48,0x70)`, `(0x58,0xa4)+(0x60,0x68)`, keeper `(0xc0,0x54)+(0x48,0xa4)`, each `OffsetRect(5, 5)` = `FUN_0041e320`, CONFIRMED the IAT slot `0x6cf038` -> "OffsetRect"); Kaarg `0x4c0ee5` (`(0,0)+(0x3c,0xca)`, `(0x3c,0x3a)+(0x30,0x96)`, `(0x3c,0)+(0x7c,0x3a)`, `(0xbe,0)+(0x62,0x104)`, keeper `(0x78,0x6c)+(0x48,0x60)`). Tooltip ids: `FUN_0041f350(0x3e + i)` (human, `0x4bb2c4`), `0x112 + i` (druid, `0x4bfee2`), `0x116 + i` (Kaarg, `0x4c3036`); the keeper `0x3d` in all three; no tooltip while the `0x80` box is up. The main.txt texts are read from the install.
The **block order is the server's**: shelf `i` = Scenario.dll assortment block `i` of the town (town-shop 5; `Campaign.shop[town][i]`), **in every town** (CONFIRMED by the stock generator in the engine: town 1 `[armour, weapons, staffs+mods, books/scrolls/potions]`, town 2 `[armour, staffs/clubs/bows+mods, stock, weapons]`, town 3 `[armour+weapons, ring/amulet/armour+mods, stock, elven (rings, amulets, ...)]`). Only the **rect -> shelf** table differs per town. The old engine mapping `A, B, C, D = 0..3` is right for town 1 only; in Kaarg it sent the weapons strip (right) to shelf 2 (books) and the armour strip (left) to shelf 3 (weapons) - exactly the play-test report.

### What the engine must do (item 1)
- `SHELF_RECTS[town]` = the table above (druid / Kaarg after the offset); hit-test shelves 0..3 in order, first hit wins, druid shelf 3 only when `Var(0x302) != 0` (a refused hit tests the next shelf: the loop continues).
- Draw the main picture at `P + (5, 8)`, frame sprite first.
- Stock build is correct (shelf `i` = block `i`); no change.

## 3. Selection feedback (CONFIRMED)

No hover state: the move handler returns 100 (`0x4c33f0`, `0x4bbf2c` only refreshes dirty bits). The only shelf visuals are **tied to the clicked (selected) shelf**; the selection is `window+0x132`, 100 at construction (**no shelf highlighted at the first opening, although `FUN_004b3c4e(0)` already lists shelf 0's items**: `0x4b3c4e` just sets the stock panel's list pointer `+0x2100 + n * 0x14`; whether the load resets `+0x132` to 100 at a later opening is open, 9).

**Accept** (`+0xa4`, all classes, `0x4bbd46` / `0x4bfd3a` / `0x4c2df2`): same shelf as `+0x132` -> return 0 (nothing: no sound, no Yes, no highlight change). Else: stop + play the window's `+0xa0` sound (human `depart`, druid `Dotdel`, Kaarg `Kotdel`); if `+0x132 == 100` all bits / counters cleared, else the old shelf's clip counter := 9 (ends on the next step); human: bit `1 << i` set, clip `i` loaded, counter 0; `+0x132 := i`; the stock panel's scroll offset := 0. The press handler (`0x4bbfa6`) then sets `+0x240 |= 0x20` (the Yes reaction, **human only**; druid / Kaarg presses do nothing more), calls `+0x80`, `FUN_004b3c4e(+0x132)` (stock shows the new shelf) and redraws the stock panel. In the human class the press also does nothing while the `0x80` box is up.

### 3.1 Human: shelf clip (`0x4bacbd`, `0x4bbe9d`, draw `0x4bb3d7`)
Shelf `i` plays `graphics\interface\shopanim\%.2d\%d.bmp` with `%.2d = 4 - i`, frames 1..11 (CONFIRMED `FUN_00582c50(.., 4 - param_1, k + 1)`), drawn at the highlight rect `+0xa0 + 0x10 i` (CONFIRMED constructor values; the bitmap sizes equal the rect sizes):

| shelf | set | frame size | draw at (P-relative) | covers |
|---|---|---|---|---|
| 0 | `04` | 80 x 112 | (189, 108) | lower right (armour) |
| 1 | `03` | 80 x 112 | (33, 108) | lower left (weapons) |
| 2 | `02` | 132 x 88 | (149, 20) | upper right (magic) |
| 3 | `01` | 112 x 88 | (37, 20) | upper left (potions, books) |

Step (every 100 ms while the bit is set): `counter += 1`; `== 9` -> `3` (loop); `== 10` -> bit cleared, frames freed. So the clip shows file numbers `counter + 1`: **1, 2, 3, then 4..9 looping**; files 10, 11 exist and are never drawn. A deselected shelf's counter is set to 9 so it ends on the next step. Frames are drawn **opaque** over the picture (**CONFIRMED** `0x4bb3d7`: clips, the keeper and the base pictures all use vtable `+0x18` = `FUN_004254ea`, the opaque whole-bitmap blit of the `0x424e4b` class, bitmaps.md; no colour key). Druid / Kaarg draws (`0x4bf908`, `0x4c28c6`) not read for this; the engine keeps them keyed.

### 3.2 Druid / Kaarg: static highlight (`0x4bf908`, `0x4c28c6`)
Drawn every frame while `+0x132 == i`, no animation (positions `P`-relative; sizes are the bitmaps'):

| town | shelf | bitmap | draw at | size |
|---|---|---|---|---|
| druid | 0 | `shop_druid\hili_armor.bmp` | (5, 112) | 88 x 112 |
| | 1 | `hili_magic.bmp` | (5, 52) | 96 x 60 |
| | 2 | `hili_potion.bmp` | (121, 36) | 72 x 112 |
| | 3 | `hili_elven.bmp` instead of `elven.bmp` | (93, 172) | 96 x 104 |
| Kaarg | 0 | `shop_kaarg\hili_armor.bmp` | (5, 8) | 72 x 216 |
| | 1 | `hili_magic.bmp` | (49, 72) | 80 x 148 |
| | 2 | `hili_potion.bmp` | (49, 8) | 152 x 80 |
| | 3 | `hili_weapon.bmp` | (153, 8) | 140 x 288 |

Druid extra: `elven.bmp` (96 x 104) is part of the scene **only when `Var(0x302) != 0`**, at (93, 172), drawn after the main picture and before the highlights and the keeper (`0x4bf908`).

## 4. Keeper animation

All timers are process globals set once (statics `0x627648/58/50`, `0x627638/54/4c`, `0x62765c/40/3c`), so the schedule continues across window openings; the first draw ever behaves as if the last tick were 100 ms ago.

**Tick** (inside the panel draw): runs when `now - last >= 100 ms` (`99 < dt`): `window vtable +0x88` (the sound player `0x4b978f`, town-shop 6), `last := now`; shelf clips step (3.1); then the idle scheduler: elapsed since the last clip end `>= (rand() % 5) * 1000 + 5000` ms (**5, 6, 7, 8 or 9 s, fresh draw every tick**) and no clip bit set -> start an idle clip. The tick has no effect while the window is not loaded (`window+0x148 == 0`).

| class | keeper bitmap | idle at rest | draw at | idle clip start | idle clip frames | end |
|---|---|---|---|---|---|---|
| human | `movies\shopanim\Pose2-3\%d.bmp` (76 x 176; 29 files) | `Pose2-3\1.bmp` (`+0x4a`) | (113, 112) | bit `0x10` | step `0x4bb040`: `counter = (counter + 1) % 30`, file `counter + 1`: files **2..28** (counter 1..27 shown; at counter 28 (`0x1c`) the bit is cleared in the same tick, file 29 is loaded but not drawn) = 27 frames x 100 ms | timer := now, counter 0 |
| druid | `movies\shop_druid\a1%04d.bmp` / `a2%04d.bmp` (72 x 164; 30 + 30 files, plus an unused `a30001`) | `a10001.bmp` | (197, 92) | bit `0x10 << rand(2)` (`FUN_004a0fd0(2)`: INFERRED 0 or 1) = **a1 or a2** | `0x4bf610`: `counter = (counter + 1) % 30`, file `counter + 1`: files **2..30** (29 frames) | counter wraps to 0: bits `&= 0xf`, idle bitmap back, timer := now |
| Kaarg | `movies\shop_kaarg\a1%04d.bmp` / `a2%04d.bmp` (72 x 84; 20 + 20, plus `a10000`) | `a10000.bmp` | (125, 116) | same, a1 or a2 | `0x4c25ce`: `% 20`: files **2..20** (19 frames) | as druid |

**Yes / No reactions (human, CONFIRMED loaders `0x4bae3e`, `0x4baf3f`)**: Yes = slot 0 `Pose2-3\1.bmp`, then `movies\shopanim\Yes\2..12.bmp` (12 slots; `Yes\1` and `Yes\13` exist, unused); No = `Pose2-3\1.bmp`, `movies\shopanim\No\2..12.bmp`. Drawn at (113, 112) like the idle clip (priority: idle `0x10` > Yes `0x20` > No `0x40` > rest). Each tick `counter += 1`; at **12** the bit is cleared (clip is 12 frames x 100 ms = 1.2 s: counter 0..11 = `Pose1, Yes2 .. Yes12`), timer := now, counter 0, frames freed (`+0x94` / `+0x98`).
Triggers (CONFIRMED sites in town-shop 3.3, INFERRED the clip meaning): **Yes** (`|= 0x20`) on an accepted shelf click, on a Buy that the client accepts, on a Sell; **No** (`|= 0x40`) on a Buy the gold does not cover.
**Druid / Kaarg**: bit `0x20` is the **a2 idle clip**, so Buy / Sell success plays a2 (the same loader path, `+0x80` / `+0x84` are no-ops that free frames: `0x4bf5de` -> `0x4bf754`); a shelf click starts nothing; the No bit `0x40` is never drawn (a refused Buy has only the nofit sound).

**Kaarg fire (CONFIRMED draw / accept, INFERRED the bitmap order)**: a brazier at **(193, 204)** (80 x 88) from two lists of 18 bitmaps loaded in the order `lite`, `burn`, `cicle` (string xrefs `0x4c162c`, `0x4c1ac1`, `0x4c1efb`): dark list `graphics\interface\shop_kaarg\fire\dark\{lite,burn,cicle}1..6.bmp` (index 0..5 lite, 6..11 burn, 12..17 cicle) drawn while the weapons shelf (3) is **not** selected, `...\fire\select\...` (same names) while it is. Frame `f` (`+0x2fc`), direction `d` (`+0x300`); each 100 ms tick: `d == 0` -> `f += 1`; `f == 6` -> 0 (idle loop = frames 0..5); `f > 17` -> 12 (lit loop = 12..17); `d != 0` -> `f += d`, `d := 0` when `f < 1` or `f > 16`. Accept of shelf 3 sets `d = 1` when `f < 12` (ignite: 6..16 then loops 12..17); accept of another shelf sets `d = -1` when `f > 0` (back down to 0); neither when the previous selection was 100 (the first click). Draw order: frame, main, highlight, keeper, fire last.

## 5. Sounds (unchanged; town-shop 6 / 9.8)
Shelf change: window slot `+0xa0` (depart / Dotdel / Kotdel). The Yes clip has no sound of its own; Buy / Sell / nofit as before.

## 6. Price bar, price number, count (CONFIRMED `FUN_004b18e2`, called by the draw of all three grids: stock `0x4b392a`, pack `0x4b4cd6`, table `0x4b59bf`)

Per cell (rect `(l, t, r, b)` = the cell, `r - l = 80`; **the exe draws everything at `y = t + 1`**: background `+0xc8` / `+0xd0` / `+0xcc`, item picture, flag overlay; the engine's cell rects are `t`, so draws are one pixel low in the exe):

| element | position | notes |
|---|---|---|
| price bar | **(r - 60, t + 1)** = cell `(l + 20, t + 1)` | 60 x 10 bitmap from `window+0xf0` (costs1..7, buy / shelf items) or `+0xdc` (costm1..7, items with `+0x18 == 2` = the hero's own); drawn keyed (`+0x38`), **no shadow** (`+0x1c` is a no-op on this class); frame from the **unhalved** price: `idx = ftol(log10(price))`, if `idx > 7` then `7` (quirk: the cap is `count`, not `count - 1`: a price >= 10^7 indexes past the 7 entries: INFERRED unreachable except at chapter 110 prices up to 19,999,999; the engine clamps to 6) |
| price number | **right edge `r - 6`, `y = t + 1`**, right-aligned | `FUN_0045d536(x, y, text, flags = 1, table = 0x620d90, shadow = 1)`: font2 (`[0x620500]`), gold table, 1 px shadow; text = `price` (shelf, table items of the shop), **`(price + 1) / 2`** (signed `cdq / sar`, truncated toward zero) for `+0x18 == 2` items; **not multiplied by the count**; formatted `"%d"` (`0x5f5174`) then through `FUN_00475263` which inserts a **`,` every three digits** (CONFIRMED `0x2c`; the grouping loop: INFERRED standard `1,234,567`, a leading sign is kept) |
| stack count (item `+0x10 > 1`) | **(l + 10, b - 15)**, left-aligned | `flags = 0`, same font / table / shadow, `"%d"` (`0x5f5170`) with the same comma pass; (the mission pack's `(3, -14)` of ui-layout 11.13 is another routine) |
| money cell | `0x626c9c` sprite instead of the item, no bar | item with `FUN_0041ea40` set (the pack's gold) |

The text sits at the top of the cell over the bar's right end (bar x range `l + 20 .. l + 80`, text ends at `l + 74`). Which items get a bar: every item of the three grids except the money cell and the `FUN_004a4170` case (INFERRED hidden / unknown item: background only). A price of 0 would index `log10(0) = -inf` (out of range); no such item is generated, the engine draws no bar.
**What is wrong now**: `BAR_AT = (10, 66)` (bottom-left, INFERRED) must be `(20, 0)` relative to the item sprite origin (`l, t + 1`); the number is not drawn at all; the sell-side frame uses `(price + 1) / 2` and must use the full price (the bar frame can differ from the text for 10, 100, ... : e.g. price 10 -> frame 1, text 5); the count text is at `(l + 3, b - 14)` and must be `(l + 10, b - 15)`; all draws one pixel higher than the exe's `t + 1`.

## 7. Files in the install (venv `game_fs()`)

| path | files | size |
|---|---|---|
| `movies/shopanim/pose2-3/1..29.bmp` | 29 | 76 x 176 |
| `movies/shopanim/yes/1..13.bmp` | 13 (2..12 used) | 76 x 176 |
| `movies/shopanim/no/1..12.bmp` | 12 (2..12 used) | 76 x 176 |
| `movies/shop_druid/a10001..a10030`, `a20001..a20030`, `a30001` | 61 | 72 x 164 |
| `movies/shop_kaarg/a10000..a10020`, `a20001..a20020` | 41 | 72 x 84 |
| `graphics/interface/shopanim/01..04/1..11.bmp` | 44 | 112 x 88, 132 x 88, 80 x 112, 80 x 112 |
| `graphics/interface/shopanim/shopmain.bmp`, `myitem.bmp`, `shopitem.bmp` | 3 | 288 x 288, 80 x 80, 80 x 80 |
| `graphics/interface/shop_druid/`: `hili_armor` 88 x 112, `hili_magic` 96 x 60, `hili_potion` 72 x 112, `hili_elven` 96 x 104, `elven` 96 x 104, `shopmain` 288 x 288, `shopframe.256` / `.bmp` 316 x 303, `shopinv` 164 x 303, `shoptable` 472 x 87, `shopmenu` 176 x 238, `shopbutton1..4`, `shoparrow1..4` 72 x 32 | 19 | |
| `graphics/interface/shop_kaarg/`: `hili_armor` 72 x 216, `hili_magic` 80 x 148, `hili_potion` 152 x 80, `hili_weapon` 140 x 288, same art set | 18 | |
| `graphics/interface/shop_kaarg/fire/{dark,select}/{burn,cicle,lite}1..6.bmp` | 36 | 80 x 88 |

## 8. Tooltips (CONFIRMED where read)
Hover tooltips (500 ms, ui-layout 11.6b) of the keeper panel: shelf `i` and keeper as in the table of 2 (main.txt `0x3e..0x41` human, `0x112..0x115` druid, `0x116..0x119` Kaarg, `0x3d` keeper), shown by the `+0x14` slot, nothing while the identify box (`+0x240 & 0x80`) is up. The buttons panel returns no tooltip (`0x4bccf8` = `return 0`; main `0x42` "Buy all items placed on the table", `0x43` "Sell all ...", `0x44` "Clear table" have no caller here: INFERRED unused in the shop). The item tooltip of the stock panel (`0x4b37f7`) is not read (open 3).
The `0x80` box (`0x4bb3d7`, press `0x4bbfa6`): a filled rect J (220, 20)-(455, 115) window-relative with main `0x4f` "Do you want to identify this item", `0x50` "for %d gold coins?" and two text buttons main `0x4b` "Yes" / `0x4c` "No" (gold when hovered); an identify-for-gold confirm. Nothing in the single-player shop code read sets bit `0x80` (INFERRED dead / multiplayer).

## Open questions
1. Item tooltips of the stock panel's text branch (`0x4b37f7`, **partly CONFIRMED**: empty while the identify box is not allowed (`+0x148 == 0`) or an item is carried (`client+0x3f4`); a hit-test of slot `+0x8c` returning `>= 0` gives the item text `FUN_004b14d4`; otherwise main `0x38`, `0x39` or `0x3c` by two rect tests `FUN_0041e3d0`: not mapped to which rects) and the table / pack panels; the writer of the `0x80` identify box.
2. Kaarg fire list order `lite` -> 0..5, `burn` -> 6..11, `cicle` -> 12..17 is inferred from the string xref order and the draw's loop bounds (`0x4c12ca`, blocks at `0x4c162c` / `0x4c1ac1` / `0x4c1efb`).
3. Are the druid / Kaarg keeper and highlight draws (`0x4bf908`, `0x4c28c6`) opaque (`+0x18`) like the human one?

### Answered (REA 2026-11-16)
- **Window load resets the shelf: CONFIRMED.** `0x4b8b98` writes `window+0x132 = 100` on every load (after the keeper lists are rebuilt), so the first click on shelf 0 of each opening plays Yes + highlight.
- **`FUN_004a0fd0(n)` = `((rand() * n) / 0x7fff) % n`: CONFIRMED** (`rand` = CRT `0x583290`, LCG `0x343fd`, `0x269ec3`, bits 16..30). For `n = 2` that is not `rand() % 2` but `0` for `rand < 0x4000` or `== 0x7fff`, else `1`; the engine's `randrange(n)` has the same distribution except one value in 32768 (not modelled).
- **Keeper / clip colour key: none, opaque** (see 3.1).
