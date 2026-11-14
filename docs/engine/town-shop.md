# Town mode: the shop windows (L3, window id `0x3e8`, mode bit `2`)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)) and of `Scenario.dll`. Marks: **CONFIRMED** (routine address given) / **INFERRED**.
Part of the L3 town spec ([design](../superpowers/specs/2026-11-13-l3-town-spec-design.md)). The shared message table (`0x445`, `0x44c`, `0x442`, `0x468`, `0x42d` / `0x42e`), the mode-bit table and the hero arrows' list rule are in
[town-worldmap 4](town-worldmap.md#4-messages-in-out) and [town-hero 1 / 3](town-hero.md); the item math in [items §4 / §11-13](../data/items.md); none of it is repeated. Single player only (`client+0x5d8 == 2`). Names of fields are ours; offsets and routines are the exe's.

**Correction to the task text.** The three shop classes are the windows `client+0xf8` (ctor `0x4b6bb2`, vtable `0x5cf300`, **town 1 human**), `client+0xfc` (ctor `0x4bde01`, **town 3 druid**) and `client+0x100` (ctor `0x4c0017`, **town 2 Kaarg**)
(`FUN_0048aea8`, table in [town-hero 1](town-hero.md#1-purpose-and-entry-exit)). The `TalkTo` sites are `0x4b9117` = human load `0x4b8b98`, `0x4bec83` = **druid** (inside the class `0x4bde01`; its `shop\npc31m%d` string `0x5f5a68` is read at `0x4bec51`), `0x4c0995` = **Kaarg** (string `0x5f5c38` read at `0x4c0963`): CONFIRMED by the string xrefs.
All three classes are one design (children, messages, buttons); the human class is decoded fully, the druid / Kaarg ones differ in art, sounds, the shelf rectangles and the fourth shelf (2.3, 3.3).

## 1. Purpose and entry / exit

A full-screen window (640x480 area, id `0x3e8` = 1000, CONFIRMED `FUN_0041b077`, `0x412659`) in which the player buys items from four shelves of the town's stock, and sells items from the packs / equipment of any hero of the party. All trades go through a **table** (a cart):
items are dragged onto it, then Buy / Sell / Cancel send one message each; the server does the move and the gold ([5](#5-data-read--written), [items §12](../data/items.md#12-trade-hero-window-and-wire-flags)).

**Entry (CONFIRMED).** Scene click (human region 1, others flag 1, [town-hero 1](town-hero.md#1-purpose-and-entry-exit)) posts **`0x42a`**. Client handler `0x4877b8` (the same guard as the inn): **`client+0x404 == 0`** or (`+0x5d8 <= 1` and `+0x404 == 1`); then `FUN_0048aea8(msg)`:
mouse capture released (`0x41e730`), if the mission pack bar is open `FUN_0041b077` closes it (`FUN_0041aef1` test), wait cursor; `GetCurrentLocation` -> **town id** (`FUN_00473a30`): 1 -> `+0xf8`, 2 -> `+0x100`, 3 -> `+0xfc`; `AddChild(root +0xcc, window)`;
the window's **load** (vtable `+0x80` = `0x4b8b98`, below); **`client+0x404 |= 2`**; `FUN_004167c2` (the pack view follows the hero); **`FUN_0041a29b` = server message `0x32` EnterShop** (and `|= 2` again); root redraw; `client+0x44c := 0`; cursor default.

**Load (`0x4b8b98`, vtable `+0x80`; CONFIRMED).** In order: `FUN_00437ee0`, the buttons-panel art `0x4bdbac`, the table and stock panels' vtable `+0xb4` call and the shopkeeper panel's `+0x78` (art load), the buttons bitmaps `FUN_004bc8de`, the window art `FUN_004b796f`, the sounds (vtable `+0x8c` = `0x4b995b`);
`window+0x80` = the view (`client+0xd0`), `window+0x7c` = **the unit info panel** (window 7, `client+0xe0`); **tips** (below); the info panel is removed from the root and moved by `OffsetRect(+(640 - width), 0)`, so it ends at **(480, 238)-(640, 480)** exactly as in the inn ([town-hero 2](town-hero.md#2-layout-per-resolution)), then re-added;
the hero list (`FUN_00472460`, the first entry with `+0x1b8 & 0x20` = shown hero `window+0x130`, [town-hero 5](town-hero.md#5-data-read--written)); the pack panel is pointed at that hero (`hero+0xd0` / `+0xe4`, the pack objects: INFERRED); **`FUN_004b3c4e(0)`: the stock panel shows shelf 0**;
`0x405` to the view (clears a pending target mode); the hero is selected (`vtable +0x14(1)`), **`hero +0x1b8 |= 8`**; the three item panels are cleared (`FUN_004b15a3` x3) and refreshed (`FUN_004b1435` x3); `window+0x14c |= 0x2f` (dirty bits); the window opens (`FUN_004dc232`);
`window+0x148 := 1` (loaded); the enter sound `+0xac`; the ambient `FUN_004a0ff0(+0xbc)` (InShop); the shopkeeper's start sound `+0xb0` once if not already playing (`FUN_0045a964`, priority `0x80`); then **`window+0x160 := ScenarioEnterShop()`** and, if non-zero, the speech `shop\npc31m<(word >> 16) & 0xfff>` + `TalkTo(word)`.
**`ScenarioEnterShop` (Scenario.dll `0x1000285f`, ordinal 7 -> exe pointer `0x6273a4`, loader `0x4819a7`-`0x4819b5`) is `xor eax, eax; ret`: it always returns 0, so `window+0x160` is 0 and the speech / `TalkTo` branch never runs in the GOG install** (answers the open question: the word has no writer, the three sites are dead code; `ScenarioLeaveShop` `0x10002866` = ordinal 8 = `0x6273a0`, called by the unload, is an empty `ret`).

**Exit (CONFIRMED).** Three ways, one effect: the **Exit button** (`0x4bda16` case 3 -> `0x4b956e`), **ESC** (`WM_KEYDOWN 0x1b`, `0x4b70a2`; Enter is consumed, nothing else) and the same routine: `0x4b956e` returns every table item (`0x4b94a4`, see 3.2) and the window sends itself **`0x445`**
(base `FUN_004dc2b0` -> the unload `0x4b8954`, then posts **`0x44c`** to the client). Both callers then post **`0x42e`** (the town scene again, [town-hero 1](town-hero.md#1-purpose-and-entry-exit)) **only if `client+0x404 == 2` exactly**.
The client's `0x44c` handler (`FUN_004891d8`, [town-hero 1 table](town-hero.md#1-purpose-and-entry-exit)) for `+0xf8` / `+0xfc` / `+0x100` calls `FUN_0041a311` = **server message `0x36` Leave** and **clears bit 2**, then `FUN_004167c2` (the campaign skips `FUN_004924cd`).
The unload `0x4b8954` also: stops the ambient, puts the info panel back (`OffsetRect(width - 640, 0)`), re-adds / frees the helper windows, frees the sounds (`+0x90` = `0x4b9ab1`), and calls `ScenarioLeaveShop`. The window objects live for the whole session; every opening runs the load again.
No other exit: no cancel key, no click outside. The scene's own leave region is not reachable (the shop window covers the screen).

## 2. Layout per resolution

The window rect is the screen-centred 640x480 area, origin `O = (fx, fy)`, `fx = (W - 640) / 2`, `fy = (H - 480) / 2` (640x480 `O = (0, 0)`, 800x600 `(80, 60)`, 1024x768 `(192, 144)`; the same ctor rect as the inn, [town-hero 2](town-hero.md#2-layout-per-resolution)).
All numbers below are relative to `O`, screen pixels, no scaling; nothing changes with the resolution. What the client paints around the 640x480 area is [town-worldmap open question 3](town-worldmap.md#8-open-questions).

### 2.1 The window and its panels (CONFIRMED, create `0x4b85e2`; ctor args `(id, l, t, r, b, parent)`)

| child | id | class ctor (vtable) | rect (l, t, r, b) | what it is | item region kind |
|---|---|---|---|---|---|
| `+0x68` | `0x3ea` | `0x4b2c61` (`0x5cf0c0`) | (0, 0, 164, 303) | **stock panel**: the shown shelf's items, grid `164 / 80` x `303 / 80` = **2 columns x 3 rows** of 80x80 cells | 5..8 (shelf 0..3) |
| `+0x74` | `0x3ed` | `0x4b9cf5` (`0x5cf398`) | (164, 0, 480, 303) | **shopkeeper scene**: picture, the four shelves, animation | none |
| `+0x70` | `0x3eb` | `0x4b5424` (`0x5cf240`) | (0, 303, 480, 390) | **table** (the cart): `480 / 80 - 1` = **5 cells x 1 row** + scroll arrows | 4 |
| `+0x6c` | `0x3e9` | `0x4b484f` (`0x5cf180`) | (0, 390, 480, 480) | **the hero's pack**: **5 cells x 1 row** + arrows (the same geometry as the mission pack strip, [ui-layout 11.13](ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked)) | 2 |
| `+0x78` | `0x3ee` | `0x4bc2b0` (`0x5cf458`) | (464, 0, 640, 238) | **buttons panel** | none |
| `+0x7c` | (window 7) | the info panel | (480, 238, 640, 480) | the selected hero's paper doll (equipment) + the two hero arrows | 1 |

Cell counts are `width / 0x50` (CONFIRMED in the ctors); the exact cell positions follow the mission pack strip rule (pad, arrows 32x88) of ui-layout 11.13 for the pack and the table (INFERRED identical: the three grids share the base class `0x4b127c`).
The panels overlap by design (buttons 464..640 over the table's right end at 480); add order = draw order: `+0x68`, `+0x6c`, `+0x70`, `+0x74`, `+0x78`, then the info panel (re-added last).
The window's own draw (`0x4b8007`, vtable `+0x30`) fills a rect with colour 0 (black) when `window+0x148` is set; its rect origin is `(left + ...)` of window `+8` with the offsets `0x184` / `0x1d0` / `0x188` (not decoded to a screen rect: [8](#8-open-questions) 4).
The window **redraws every tick** (`0x402`, only when `client+0x404 & 8 == 0`, no modal dialog): `0x4b9144` (animation step), the shopkeeper, pack, stock, table (or the alternate `+0x84` view), info panel, the totals `0x4b960c`, the buttons panel.

### 2.2 Buttons panel (`0x4bc2b0`; rects CONFIRMED as constructed, assignment INFERRED)

Eight rects, relative to `O`: R0 (494, 15, 614, 67); R1 (483, 67, 623, 113); R2 (483, 114, 623, 160); R3 (494, 160, 614, 212); R4 (515, 15, 590, 35); R5 (494, 35, 635, 67); R6 (494, 160, 614, 192); R7 (515, 192, 590, 212).
Hit test `FUN_004bdbd1` returns 0..3 (INFERRED: R0..R3 are the four button pictures `ShopButton1..4`, R4..R7 their caption / hover zones). Mouse: left press `0x4bd988` (`window+0xf8 :=` hit button; sound for button 0 = `+0xc4` Undo, button 3 = `+0xc0` Out), move `0x4bd918`, left release `0x4bda16` (acts only when the release hits the same button and `client+0x3f4 == 0`, i.e. nothing carried):

| button | picture | action (CONFIRMED) |
|---|---|---|
| 0 | `ShopButton1` | **Cancel**: `0x4b954d` = return all table items locally (`0x4b94a4`) + server **`0x35`** |
| 1 | `ShopButton2` | **Buy**: `0x4b93cf` (3.3) |
| 2 | `ShopButton3` | **Sell**: `0x4b935d` (3.3) |
| 3 | `ShopButton4` | **Exit**: `0x4b956e` (1) |

The button order is by index; whether the captions read Cancel / Buy / Sell / Exit is INFERRED from the actions and `#tips3` (`<Buy>`, `<Sell>`); the strings are in the picture files, not the exe. A press on any button also sets `window+0x14c |= 0x20` (redraw). If a carried item is held (`client+0x3f4 != 0`) a release does `0x4b91e8` (return the carried item to where it came from) instead.

### 2.3 The shopkeeper panel (`0x4b9cf5`, panel origin (164, 0))

Rects CONFIRMED as constructed (panel-relative unless noted): **shelf hit rects** in field order A (190, 110, 295, 295), B (5, 110, 110, 295), C (150, 5, 290, 105), D (8, 5, 150, 105) (a 2 x 2 arrangement; the mapping to shelf 0..3 is INFERRED = the order of the shelf pictures
`hili_armor`, `hili_magic`, `hili_potion`, `hili_weapon` / `hili_elven`); highlight rects E (189, 108, 269, 220), F (33, 108, 113, 220), G (149, 20, 281, 108), H (37, 20, 149, 108), I (110, 110, 190, 295); the NPC picture / bubble J (220, 20, 455, 115) (window-absolute, not offset); two small rects K, L computed from the width.
**Click** (`0x4bbfa6`): the pointer is tested against the four shelves; the first hit that the class accepts (vtable `+0xa4(i)`, `0x4bbd46`) starts the shelf animation (`+0x240 |= 0x20`, vtable `+0x80` = `0x4bae3e`), **`FUN_004b3c4e(window+0x132)`** sets the stock panel's shown block to `+0x2100 + shelf * 0x14` and redraws it. Tip `#tips3`: "Click on any shelf to see its contents".
In the druid shop the fourth shelf is gated: **`FUN_004bfd3a(4th)` refuses unless `Var(0x302) != 0`** (`FUN_004bf096`, [3.3 / 5](#5-data-read--written)); selecting a shelf (the same routine) plays `+0xa0` (depart.wav-slot in the human table; the druid table differs, [6](#6-sounds-music-and-tips)), resets that shelf's scroll (`+0x244 + shelf * 4 := 0`) and the stock panel's offset, and stores `window+0x132 := shelf`.

## 3. Widgets and resources

### 3.1 Resources (strings CONFIRMED by the string table; loader routines CONFIRMED by xrefs; install-relative paths, lower-cased on lookup)

| resource | loader | used for |
|---|---|---|
| `graphics\interface\ShopFrame.256` (druid / Kaarg: `shop_druid\`, `shop_kaarg\`) | `0x4baad8` (shopkeeper panel) | the window frame sprite around the shopkeeper scene |
| `graphics\interface\shopanim\ShopMain.bmp` (race dirs: `shop_druid\ShopMain.bmp`, `shop_kaarg\ShopMain.bmp`) | `0x4bab3f` | shopkeeper background |
| `movies\shopanim\Pose2-3\%d.bmp`, `Yes\%d.bmp`, `No\%d.bmp`, `graphics\interface\shopanim\%.2d\%d.bmp` (human); druid `movies\shop_druid\a1%04d.bmp`, `a2%04d.bmp`, `a10001.bmp`; Kaarg `movies\shop_kaarg\a1%04d.bmp`, `a2%04d.bmp`, `a10000.bmp` | `0x4baa98` area | shopkeeper animations: idle poses, **Yes** (a deal), **No** (refused), the shelf-turn clips |
| `shop_druid\hili_armor|magic|potion|elven.bmp`, `elven.bmp`; `shop_kaarg\hili_armor|magic|potion|weapon.bmp`, `fire\dark|select\lite|burn|cicle` | shopkeeper panel | shelf highlights (druid: the 4th shelf is "elven"; Kaarg: weapons; the human shop has `shopanim\%.2d`) |
| `ShopArrow1..4.bmp`, `ShopInv.bmp` (per race dir) | `0x4b2ee9` (stock panel) | scroll arrows (two pairs) and the inventory frame of the stock panel |
| `ShopTable.bmp` (per race dir) | `0x4b563c` (table panel) | table background |
| `graphics\interface\myitem.256`, `shopitem.256` | `0x4b796f` | item-cell frames for the player's own items / the shop's items (`window+0xd4` / `+0xd8`; INFERRED by name) |
| `graphics\interface\costs1..7.bmp`, `costm1..7.bmp` | `0x4b796f` | the **price bar** (60 x 10, 7 digit-count frames; `costm` = sell side), drawn under items; rule in [sprites](../formats/sprites.md): `frame = min(trunc(log10(price)), 6)`, sell text = `(price + 1) / 2` |
| `graphics\interface\backinvg.bmp`, `backinvb.bmp`, `backinvs.bmp` | `0x4b796f` | three cell backgrounds (`window+0xc8`, `+0xcc`, `+0xd0`; their meaning (green = can take / blue / selected?) is INFERRED, [8](#8-open-questions) 3) |
| `ShopButton1..4.bmp`, `ShopMenu.bmp` (druid: `shop_druid\ShopButton*.bmp`) | `0x4bc8de` | the four buttons (`+0x64 + 4 i`) and the panel background (`+0x74`) |
| `graphics\inventory\<name>.16a`, the money sprite `0x626c9c` | item cells ([ui-layout 11.13](ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked)) | item pictures (80x80), the pack's money cell (tooltip main `0x4a` "Money") |
| the unit info panel art | window 7 | the doll, hero arrows `ar1/ar2` ([ui-layout 11.10](ui-layout.md#1110-heads-panel-hero-arrows-and-the-extra-panel-window-6-heads-window-7-arrows-window-8-confirmed-unless-marked)) |

Fonts: the item text and price numbers use the same font2 / `0x620d90` table as the pack ([ui-layout 11.13](ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked)); the shop's own caption text is only in the pictures (INFERRED: the exe has no shop caption string).
**Where the gold number and the Buy / Sell totals are drawn is not decoded** ([8](#8-open-questions) 1).

### 3.2 The item regions and the carried item (CONFIRMED)

Item region kinds (the `kind` byte of the wire, [items §12](../data/items.md#12-trade-hero-window-and-wire-flags)): **1 equipment** (the doll in the info panel), **2 pack**, **4 table**, **5 / 6 / 7 / 8 = shelf 0..3 of the shop** (kind 3 = ground sack, never here).
`client+0x3f4` is the **carried item** (its object has `+0x18` = origin kind), `client+0x3f8` the origin index, `client+0x3fc` the origin kind used by the return routine `0x4b91e8`, `client+0x400` a cursor id (the "can drop here" cursor).
Every grid shares the base `0x4b127c`: left press `0x4b2588` stores the cell index under the pointer (`+0x3f8`) when nothing is carried; the pick-up itself follows the pack rule (pointer moved with the button held, [ui-layout 11.13](ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked)).
Hover with a carried item (`0x4b3efa` on the stock panel): the carried item of kind 5..8 sets `window+0x144 := 1` (drop allowed) with the cursor `client+0x400`; any other carried item sets 0 and the plain cursor (`0x626d14`).
**Release** (`0x4b25cb`, base):
1. cursor back to default; if the carried item's **attribute 1 (the price, `FUN_004b6680` = `FUN_00438e8a(1)`) is 0** and the target region is not the pack (kind 2), the drop is refused (`window+0x144 := 0`): **a price-0 item can only go back to a pack** (never on the table);
2. refused (`+0x144 == 0`): `0x4b91e8` returns the item to its origin region (vtable `+0xa4` of that panel with the origin index, then a redraw) and plays the **nofit** sound (`+0x90`);
3. allowed: target kind 4 (table) -> the drop (`vtable +0xa4`) + totals `0x4b960c` + `window+0x14c |= 0x20`; kinds 1, 2 -> drop; kinds 5..8 -> only back onto **its own shelf** (`region == carried kind`), else returned and nofit.
The drop sends **`0x22` MoveItem** (source kind / index, destination kind / index, count 1 per drag; the stack count rule is the pack's), the server answers with the new content of the regions ([4](#4-messages-in--out)).
The pack, the doll and a hero change never touch the table (tip `#tips4`: pass items between heroes through the table).

### 3.3 Buy, Sell, Cancel and the totals (CONFIRMED)

`0x4b960c` (run every tick and at every action) rebuilds three numbers: `window+0x150` = the **player's gold** (`view+0x9cc` player object `+0x10`); over the table list (`FUN_0041f710` count, `FUN_0046e440(i)`): an item with `+0x18 == 2` (the hero's own: **sell**) adds **`((price + 1) / 2) * count`** to `+0x158`;
every other table item (shop-owned: **buy**) subtracts `price * count` from `+0x154` (so `+0x154 <= 0`); `+0x15c = +0x150 + +0x154 + +0x158` (the gold after the deal). `price` = attribute 1 of the client item.

| button | rule |
|---|---|
| **Buy** `0x4b93cf` | totals; nothing to buy (`+0x154 == 0`) -> nothing. `gold + (-cost) < 0` (**not enough gold**) -> the shopkeeper's refuse animation (`+0x240 |= 0x40`, panel vtable `+0x84`; INFERRED the "No" clip), sound **nofit** `+0x90`, **no message**. Else: shopkeeper panel `+0x80` + `+0x240 |= 0x20` (INFERRED the "Yes" clip), **`0x33`**, sound **buy** `+0xa4` |
| **Sell** `0x4b935d` | totals; `+0x158 != 0` -> the same "Yes" clip, **`0x34`**, sound **sell** `+0xa8`; nothing to sell -> nothing |
| **Cancel** `0x4b954d` | `0x4b94a4`: while the table list is not empty, take its first item and return it to its panel (`+0x6c` if `+0x18 == 2`, else `+0x68`), then **`0x35`**; sound Undo `+0xc4` |

The server settles by its own prices ([items §12](../data/items.md#12-trade-hero-window-and-wire-flags)): buy `cost = item.+0x1c * count` per item in cart order, stops at the first item the gold does not cover; sell pays `ftol(price * count * 0.5 + 0.5)` per stack; so a buy list whose total the client accepts can still be cut short by the server only if the client's attribute-1 price is lower than the server's (display vs charge: [items VERIFY IN GAME](../data/items.md#verify-in-game), [8](#8-open-questions) 2).
**Pack full:** not decoded on the client (no message in the buy path checks it); the server files the item in the pack (`FUN_00529ac2`) and a failing insert is not handled in the client UI paths read here ([8](#8-open-questions) 5).
**Quest items unsellable:** a price-0 item cannot be dropped on the table (3.2 step 1; INFERRED that quest items carry attribute-1 price 0, the server record price is `-1`, [items §4](../data/items.md#4-price)).
**Hero arrows** `0x414` / `0x415` (root -> window slot `+0x48`, `0x4b8273` / `0x4b8102`): `0x405` to the view; `window+0x130` (hero index, a `short`) `+= 1` wrapping to 0 at the list count (`0x4b8102`; `0x4b8273` is the mirror: INFERRED not read line by line); the hero is selected, `FUN_004167c2`, the pack panel is re-pointed at **that hero's pack** (`hero+0xd0`), its scroll offset reset, the doll follows,
`hero +0x1b8 |= 8`, redraw bits `|= 9`. **Gold is the player's** (one number for the whole party); **packs and the doll are per hero; the table is shared** and keeps its items when the hero changes. The hero list is the living heroes in creation order ([town-hero 5](town-hero.md#5-data-read--written)).

### 3.4 Tooltips and item text

Item tooltips: the pack panel's tooltip routine (`FUN_0043901f(item)` text, ui-layout 11.13) is the pattern; the stock panel's tooltip slot is `0x4b37f7`, the shopkeeper's `0x4bb2c4`, the buttons' `0x4bccf8` (not read line by line, [8](#8-open-questions) 6). In the shop the pack's money cell shows main `0x4a` "Money" (ui-layout 11.13).

## 4. Messages in / out

**Into the window (slot `+0x48` = `0x4b7102`, CONFIRMED):**

| message | effect |
|---|---|
| `0x402` tick | (only without a modal dialog) redraw of everything + totals |
| `0x40f` | `0x4b95b7` (alternate view off) or, with `window+0x84 != 0`, `0x4b95e5`: toggles the alternate item view (the mission pack key `I` path; not decoded further) |
| `0x413` (kind, list) | **container contents** from the server: `p3 == 0` -> refresh all three grids + `hero +0x1b8 |= 8`, dirty `0x28`; kind 1 -> doll dirty; kind 2 -> pack `+0xb0(list)`; kind 4 -> table `+0xb0(list)` + totals + dirty `0x20`; kinds 5..8 -> `FUN_004b8443(kind - 5, list)` (the table items' origin fields rewritten, the shelf's array replaced) |
| `0x414` / `0x415` | hero arrows (3.3) |
| `0x45a` | tips window Close: `RemoveChild(+0x88)` |
| `0x46e` (kind) | after a pick / drop: refresh of the named region (7 = pack + doll; 1, 2, 4, 5..8 one grid; 4 also totals) |
| `0x445` | self-sent exit (1) |
| keys | ESC exits, Enter swallowed |

Up to the client, the grid contents arrive in the server's **container message** (the client-loop case at `0x412301`: `byte +0xc & 0x7f` = kind, `u16 +0xd` = item count, items from `+0x13`, wire item decode `0x4387b2` = [items §12](../data/items.md#12-trade-hero-window-and-wire-flags); with `client+0x404 & 2` it is delivered to window `0x3e8` as `0x413(kind, list)`; with bit 4 it feeds the inn); the numeric type of that message is not extracted ([8](#8-open-questions) 7).

**Client -> server (all through `FUN_0050164f` on hub `0x670e50`; layout: `+5` u16 player id, `+7` u16 0, `+9` type, `+0xa` u16 hero id (the selected hero, `view+0x138`)):**

| type | sender | meaning | server (items §12) |
|---|---|---|---|
| `0x32` | `0x41a29b` (open) | EnterShop (the hero id from `FUN_0041f1a0`: INFERRED the first / current hero) | `0x521099` begins the shop session |
| `0x22` | `0x41a20c` | MoveItem: `+0xc` src kind, `+0xd` dst kind, `+0xe` src index u16, `+0x10` dst index u16, `+0x12` count u16; kinds 4..8 on either side go to the shop | `FUN_004f515d` case `0x22` -> `FUN_00522baf` |
| `0x33` | `0x41a387` | Buy | `FUN_0052115f` -> `FUN_00521c29` |
| `0x34` | `0x41a3e1` | Sell | `FUN_0052117b` -> `FUN_00521ae3` |
| `0x35` | `0x41a43b` | Cancel (return the table) | `FUN_005211bb` / `0x5220d9` |
| `0x36` | `0x41a311` (close) | Leave | `FUN_005211bb` + `0x5210c9` / `0x522936` |
| `0x3f` | `0x41aaa5(a, b)` | location entered (two dwords at `+0xa` / `+0xe`), sent at the town scene build (`0x468` handler, `0x487ef0`; and the load path `0x48dc63`); **single player only** (`server+0x74 == 0`): **regenerates the shop stock** (5) | case `0x3f` of `FUN_004f515d` (`0x4f672f`) -> `0x521083` -> `FUN_00522767` on the global shop object `0x68ff30` |

The type numbers were verified in the server's dispatch (`byte +9 - 2` index, table `0x4f835a`, jump table `0x4f82da`: `0x32` -> `0x4f62c3`, `0x33` -> `0x4f64ac`, `0x34` -> `0x4f654b`, `0x35` -> `0x4f65ea`, `0x36` -> `0x4f665b`, `0x3f` -> `0x4f672f`).
**Comparison with the mission item commands** ([items §15](../data/items.md#15-equip-use-pack-and-ground-items-confirmed-engine-sim-gearpy), `engine/sim/gear.py`): `0x22` is the **same message** the mission pack uses (`MoveItem`); kinds 1 and 2 (doll, pack) are what `gear.move_item` already does (equip rules, stacking, `suitable_for`); **kinds 4..8 (table, shelves) and `0x32` / `0x33` / `0x34` / `0x35` / `0x36` / `0x3f` are not in `gear.py`** (items open list). `0x21` PickUp / `0x23` DropGold are not used in the shop.

## 5. Data read / written

**Stock (CONFIRMED structure, [items §11 / §13](../data/items.md#13-campaign-town-shops-scenariodll)).** In single player the stock is **not a map structure**: the server's global shop object (`0x68ff30`, class of `0x522289`) holds four 28-byte blocks (`+0x14 + 0x1c i`, tag byte `+0x10 + 0x1c i` = shelf + 1) and is filled by `FUN_00522767`, which reads the four 20-byte **assortment blocks** of the current town from Scenario.dll
(`ScenarioGetShopAssortment`, ordinal 15 -> `0x627474`, `0x10037420 + 0x50 * town`: `min`, `max`, `count`, `stack`, `flags` per block; the DLL's table is also the "shop table" of the `ScenarioSave` block, [saves 6.3](../formats/saves.md#63-the-client-tail-confirmed-fun_0048dc9f-writes-f)), calls the generator (`FUN_005254e7` + `FUN_00525f67(count, stack, min, max)`, `allods2/formats/itemgen.py` `generate` with the stock flags) and stamps every new item's `+0x4d` with the shelf tag.
Shelf `i` = assortment block `i` = region kind `5 + i`; the item order on a shelf is the generator's sort ([items §12](../data/items.md#12-trade-hero-window-and-wire-flags)).

**When it is generated (CONFIRMED code, INFERRED reading).** `FUN_00522767` runs **only if the object's customer count `+4` is below 1** (nobody is shopping), clears the old blocks first (`FUN_0052469e` / `FUN_0052272e`, INFERRED: begin / clear) and returns 1; otherwise it returns 0 and keeps the stock.
The trigger is message **`0x3f`**, sent every time the **town scene is built** (so: on every entry into a town, from the world map or after loading a saved town), **not** when the shop window opens. Consequences:
**the stock is rerolled at every town visit (fresh random items from the town's current assortment; chapter changes enter through the DLL's block flags and price caps, [items §13](../data/items.md#13-campaign-town-shops-scenariodll)), and is stable while the player walks in and out of the shop inside one visit** (no `0x3f` in between). The generator uses the server RNG (`MsvcRng`), so it is not reproducible from the campaign state alone; it is not saved (the save keeps the DLL assortment, the stock is regenerated at the next `0x3f`; INFERRED).
In the multiplayer path (`server+0x74 != 0`) the shop object lives in a map structure and `0x522d70` regenerates on a flag instead (out of scope).

**Gold.** Server: the field `+0x3c` of the **player** object; client mirror `player +0x10` (read for the totals every tick). Written only by the server (buy `gold -= cost`, sell `gold += ftol(price * count * 0.5 + 0.5)`, pile pick-up, drop); the client never writes it. Engine mapping: `CampaignGame.gold` ([campaign 1](campaign.md#1-api), the roster's `Roster.gold`) is the single party gold; it is carried over by `FUN_004ebd5f` (gold and XP kept, [saves 4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed)).
**Items:** a bought item goes into the pack of the hero whose id is in the message (`FUN_00529ac2`); a sold item leaves that hero's pack (or doll) for the shop block of its group (`FUN_00521d4c`: armour -> flags `0x1000000`, weapons `0x400000`, others `0x4000000`; so a sold item returns to a shelf and can be bought back until the next `0x3f`).

**Prices.** Buy `price x count`; sell `(price + 1) / 2` per unit shown by the client, `ftol(price * count * 0.5 + 0.5)` paid by the server per stack (the same value for one unit, a rounding difference for stacks); price = [items §4](../data/items.md#4-price) (`base + effects`, capped 19,999,999). No other factor exists (no race, reputation or chapter multiplier in the shop code read).
**`Var(0x302)` (CONFIRMED, `FUN_004bf096`)**: `GetVar(0x302) != 0` (always 1 outside the campaign, `+0x5d8 != 2`); callers `0x4bf908`, `0x4bfd3a`, `0x4bfdf1` are in the **druid shop** class; it **unlocks the fourth (elven) shelf** of the druid shop (selection refused while 0, 2.3). `Var(0x302)` is 1 after mission 70 and 2 after the `TalkTo(0x4e02a3)` dialogue, which also ORs `0x80000` into town 3's block 3 flags ([triggers 11.1](triggers.md#111-variable-map)): **town 3 block 3 = the elven shelf**.
**`Var(0x301)` (`0x4cad3c`, `0x4cd0fb`, `0x4cdd0a`)** is read by the **town scenes**, not the shops: `0x4cad3c` is the human scene's leave click (only when `Var(0x301) != 0`, else the speech `plagatguard`, [town-worldmap 1](town-worldmap.md#1-purpose-and-entry-exit)); the druid / Kaarg scene readers are scene business for `town.md` (left open there).

## 6. Sounds, music and tips

- **Music:** none set by the shop (the scene's `b14` / `b16` / `b15` keeps playing, [town-hero 6](town-hero.md#6-sounds-music-and-tips)).
- **Sounds, human class (`0x4b995b`, loaded by `FUN_004384f0(path, &slot)`, played by `FUN_00438570` = priority `0x80` one-shot; CONFIRMED paths and slots):** `+0x90` `SFX\Town\Shop\nofit.wav` (refused drop, **not enough gold**), `+0x94` `step1`, `+0x98` `step2`, `+0x9c` `breath`, `+0xa0` `depart`, **`+0xa4` `SFX\Town\buy.wav`** (Buy accepted), **`+0xa8` `SFX\Town\sell.wav`** (Sell accepted), **`+0xac` `Shop\enter.wav`** (end of the load), `+0xb0` `Shop\start.wav` (shopkeeper wakes), `+0xb4` `Povorot1`, `+0xb8` `Povorot2`, **`+0xbc` `Shop\InShop.wav`** (the ambient loop, `FUN_004a0ff0`), `+0xc0` `SFX\Out.wav` (Exit press), `+0xc4` `SFX\Undo.wav` (Cancel press).
  The shopkeeper idle player `0x4b978f` (slot `+0x88`, run each tick): with no animation running it plays `+0xb0` start once more than 30 s (+ the value `FUN_004a0fd0(30000)` returns: INFERRED a random part) have passed since the last one, if no play is running (then `FUN_004a0fd0(10000)`); during a shelf animation `+0x240 & 0x10` by its frame: frame 1 -> `+0xb4`, frames 10 / 14 / 18 / 22 -> `+0x94` (steps), frame 24 -> `+0xb8`. Druid / Kaarg use their own banks: druid `SFX\Town_Druid\Shop\Dotdel`, `Din2`, `Ddruid5`, `Ddruid6`, `Dtools1..4`; Kaarg `SFX\Town_kaarg\Shop\Kotdel`, `Kin2`, `Kman4`, `Ktools1..4` (slot order not mapped; the shared nofit / buy / sell / Out / Undo are the same files).
  Audio.md's open "shop sounds" question is answered by this list; the **shop speech** (`shop\npc31m%d`, name format in [sound 4.3](../formats/sound.md#43-speech)) can never play (1). Hero arrows: the info panel's click `0xdc`.
- **Tips (CONFIRMED text of `town.txt`, read through `FUN_004ddc9c(n)`):** the shop load (human `0x4b8cbe`; the druid / Kaarg loads `0x4be7d6`, `0x4c04e8`, same code) shows **`#tips3`** in a tips window `FUN_004dec24(0x3f3, 0, 0xa2, 0x138, 0x12a, text)` = rect (0, 162)-(312, 298) (312 x 136; parent not decoded) when `TipsMode` (`DAT_00622774`) is on **and** `+0x5d8 == 2`; stored at `window+0x88`; removed by `0x45a` (Close) and at the unload.
  `#tips4` (the hero-arrow / table-passing tip) has no caller found in the shop window's own routines (it is not in the load nor in `0x4b8102`; the info panel or the arrow tooltip may own it: [8](#8-open-questions) 6). `#tips1` is the town scene's, `#tips2` the inn's ([town-hero 6](town-hero.md#6-sounds-music-and-tips)), `#tips11` (druid, "Ancient Woods ... Druid Shop and Inn") and `#tips12` (Kaarg, "capital of the Allod of Yases") are the **scene** tips of towns 3 and 2 (callers `0x4ce714` / `0x4d0e19`).
  Text of the shop tip: "You are in the Shop. Click on any shelf to see its contents. You can then drag any item onto the table, and click the <Buy> or <Sell> buttons to do the appropriate action."

## 7. What the headless side can test, what needs eyes

**Headless (pure, deterministic):**
- the entry / exit rules: guard `mask == 0`, town id -> class (1 human, 2 Kaarg, 3 druid), `mask |= 2`, `0x32`; exit = `0x445 -> 0x44c` (`0x36`, bit cleared) and `0x42e` **only if the mask is exactly 2** at the click;
- the **trade state machine** over a fake server: region kinds 1 / 2 / 4 / 5..8, drag rules (price-0 refused except to a pack; shop items only back to their shelf; `window+0x144`), the totals (`gold`, `-sum(price x count)`, `+sum(((price + 1) / 2) x count)`), not-enough-gold (no message, nofit), Buy / Sell / Cancel messages, hero change keeps the table, one gold for the party;
- the **server side** of the three numbers: buy cost `price x count`, sell `ftol(price x count x 0.5 + 0.5)`, stop at the first unaffordable item, cancel returning shop-owned items to their block and hero-owned ones to the pack ([items §12](../data/items.md#12-trade-hero-window-and-wire-flags)); gold on `CampaignGame`;
- **stock**: the assortment table per town and chapter (DLL blocks + caps: `engine/sim/campaign.py` does not model the shop table yet, [triggers 11 "Not modelled"](triggers.md)), generation with `itemgen.generate` per block (counts, price window, flags) given an RNG, regeneration at every town entry and persistence inside a visit; the elven-shelf gate (`Var(0x302)`);
- the message encodings (`0x22` fields, `0x32..0x36`, `0x3f`), the window geometry as data (rect tables of 2.1-2.3 and the cell counts `w / 80`), the tips / sound tables, `ScenarioEnterShop` = 0 (no `TalkTo` ever).

**Needs eyes / ears:** the look of the five panels and the overlaps (the buttons over the table's end), the cell placement inside the grids (arrows, pad), the price bar placement, where the gold and the totals are drawn, the shopkeeper animations (idle poses, Yes / No clips, shelf turns, the Kaarg fire) and their timing, the shelf hit rects against the picture, the hover cursor (`client+0x400`), the sounds by ear (slots, the idle start every ~30 s), the tips window rect, the black fill of `0x4b8007`.

**Engine hand-over:** `engine/shell/locations.py` (the L2 stand-in) has no shop; the shop screen needs `CampaignGame` (gold, roster order = hero list) plus the DLL shop table in `engine/sim/campaign.py` ([campaign 1](campaign.md#1-api): `visit_towns` stays the headless policy that never shops). Reusable now: `gear.move_item` for kinds 1 / 2, `itemgen` for the stock, `engine/ui/pack.py` geometry for the pack and table, `shell/tipswin.py` for `#tips3`, the hero-arrow list rule of [town-hero 5](town-hero.md#5-data-read--written). To build: the table / shelf kinds and the settlement (new `gear` / `shop` code), the assortment tables, the shop screen.

## 8. Open questions

1. *(answered, pixels left)* **The gold and the totals.** `FUN_004b960c` (CONFIRMED) fills them every tick: `window+0x150` = **the party's gold** (`player +0x10`), `+0x154` = **minus the sum of the buy prices** (`-price x count` over the table items not owned by the hero), `+0x158` = **the sum of the sell values** (`((price + 1) / 2) x count` over hero-owned table items, item `+0x18 == 2`), `+0x15c` = gold + buy + sell = the balance after the trade. The buttons panel draw `0x4bcd05` writes the three `"%d"` numbers `+0x150`, `+0x154`, `+0x158` after the captions Undo, Buy, Sell (font `0xa`; `+0x15c` is only the enable test). The panel-local pixel positions of the three numbers (relative to rects R4..R7 of [2.2](#22-buttons-panel-0x4bc2b0-rects-confirmed-as-constructed-assignment-inferred)) are read at the build step.
2. *(partly answered)* **Client price vs server price.** The client's price is `FUN_00438e8a(1)`: a lookup over the wire item's `(attribute id, value)` list (byte `+9` = count, list `+0xc`; id 1 carries a u32, every other id one byte): so the client shows **whatever the server put into attribute 1** when it serialised the item. The server's buy (`FUN_00521c29`, below) charges `item +0x1c` x count (`+0x42`). Whether the serialiser writes `+0x1c` into attribute 1 (then the two always agree) is not traced (the writer is in the container message builder, [8](#8-open-questions) 7); the ~41 vs 100 observation of [items VERIFY IN GAME](../data/items.md#verify-in-game) stays a run-time check. For the engine: use one price source (`+0x1c` = the generated item's price) for both display and charge.
3. *(partly answered)* **The cell backgrounds.** The window load (`0x4b796f`) keeps `backinvg.bmp` in `window +0xc8`, `backinvb.bmp` in `+0xcc`, `backinvs.bmp` in `+0xd0`, `myitem.256` in `+0xd4`, `shopitem.256` in `+0xd8` (CONFIRMED by the `push` / store pairs `0x4b79c2`-`0x4b7d4a`). The item panels' cell draw (`0x4b1b24`-`0x4b1de0`, shared base class) picks the background per cell: an **empty or unfitting** cell gets `+0xc8`; for a **shelf item** (region kind `5..8`) it computes the price (`FUN_004b6680`), the "unsuitable for the shown hero" test `FUN_0046a9c2(item)` (CONFIRMED: item `+8` bit `2` and the hero is not a mage, or item bit `4` and the hero is a mage -> 1) and compares the price with the party gold: the `backinvs` background (`+0xd0`) is drawn only when the price is covered **and** the unsuitable flag is set, every other case draws `backinvg` (`+0xc8`), and a set unsuitable flag adds one more draw at `0x4b1d3c` (INFERRED: a tint over the item). `backinvb` (`+0xcc`) is used by the pack / table classes (`0x4b46bb`, `0x4b6492`). The reading of "which colour means what" (g / b / s) and the arrows `ShopArrow1..4` placement are art-dependent and settled at the build step (look at the three bitmaps).
4. *(answered, positions INFERRED)* **The window draw `0x4b8007` and the alternate view.** The draw (vtable `+0x30`) takes the window's absolute origin `(ox, oy)` (`FUN_004d3a23`) and, once loaded (`+0x148`), fills with colour 0 (black, built through the pixel-format shifts `0x5f17d0..0x5f17e0`) the box `(ox, oy + 0x184)`-`(ox + 0x1d0, oy + 0x188)`, i.e. **a black strip 464 x 4 at (0, 388) relative to `O`**, the seam between the table (ends 390) and the pack (starts 390) that the panels leave open (INFERRED from the argument order of `FUN_00456348(x1, y1, x2, y2, colour)`). Message `0x40f` (**the spell-book key**, [ui-layout 11.12](ui-layout.md)) is answered by `0x4b95b7`: `window +0x84 := client +0xec` (the spell-book window) and the table panel `+0x70` is removed from the window (`FUN_004d3a89`): **the book replaces the table while it is open**; the per-tick draw uses `+0x84` instead of the table when set (INFERRED reversal on the next `0x40f`: not traced).
5. *(answered)* **Buy, pack full, leave with items on the table** (server side, CONFIRMED). **Buy** `FUN_00521c29`: walks the table list (`this+0x78`); for each item still owned by the shop (`+0x14 == 0`) it tests the owner player's gold (`+0x3c`) against `price (+0x1c) x count (+0x42)` and **stops at the first item it cannot pay** (`break`: that one and the rest stay on the table), else subtracts the cost, unlinks the item, makes the hero's player the owner, clears `+0x4c` and **files it into the pack** (`FUN_00529ac2` -> `FUN_00529ae2`); afterwards the table is refreshed (`FUN_00521f3a(0)`, `0x516238`, `0x50f065`) and the client is told with `FUN_00502019(.., 0x282000, 0xffb, ..)`. **There is no "pack full"**: `FUN_00529ae2` merges into an equal stackable item (same type: counts add) or inserts at the hero's pack slot index (`param_1`; appended when beyond the end) with **no capacity test**; it only adds the item's weight (`+0x4a` x count) to the hero's load (`+0x20`). So a buy never fails for lack of room, only for gold. **Leave / cancel**: `FUN_00522c75` finds the customer (`FUN_005226f5`; none -> the log line "Invalid shop transaction - no such customer"), then `FUN_0052218b` and `FUN_005220d9`: every table item still owned by the shop goes back to its shelf (`FUN_00521d4c(item, -1)`), every hero-owned one back into the pack (`FUN_00529ac2`), the table list is emptied: **leaving with items on the table cancels them without charge**.
6. *(partly answered)* **`#tips4`'s owner** is the shop window's per-tick animation step `0x4b9144` (called from the `0x402` handler, `0x4b7230`): when the tips window exists (`+0x88`), the table panel's list is **non-empty** (`0x41f710` on `+0x70`'s `+0x84`) and the once-flag `window +0x8c` is 0, it sets the flag and shows `FUN_004ddc9c(4)` = `town.txt #tips4` in the tips window (`0x437fa0`): **the arrow / table tip appears the first time an item lies on the table** (the other callers by id: `1` human scene `0x4ca877`, `2` inn `0x49ad1f` / `0x49c47a` / `0x49e572`, `3` shops `0x4b8c80` / `0x4be798` / `0x4c04aa`, `4` `0x4b91b1`, `11` / `12` the druid / Kaarg scenes `0x4ce6d6` / `0x4d0ddb`). Left: the shop tooltips of the panels (stock `0x4b37f7`, shopkeeper `0x4bb2c4`, buttons `0x4bccf8`; item text `FUN_0043901f`).
7. *(answered)* **The container message `0x76`** (case `0x410dcd`, CONFIRMED). Header: `+0xa` u16 = the unit / object id, **`+0xc` byte: bit `0x80` = the form flag** (the `0x410eec` test selects the second path of a sub-case) and **`(byte & 0x7f)` = the container key** (jump table `0x41620a`, 9 entries): `1` -> `0x411c1a`, `2` -> `0x410ea5`, `3` -> nothing, **`4..8` -> the shared item-list builder `0x4122f6`** (count = u16 at `+0xd`, records from `+0x13`; key 4 branches at `0x412358`), `9` -> `0x412711` = refresh of the open inn window (`FUN_004d4013(0x44c)`, then the person lists `0x41f770` / `0x438d84`). The keys are the **item-region kinds of the shop** ([3.2](#32-the-item-regions-and-the-carried-item-confirmed)): 1 equipment (info panel), 2 pack, 4 table, 5..8 the four shelves; `3` does not exist. Before the switch (`0x410dea`-`0x410e63`): if the client waits for an answer (`client +0x3f4` carried item) and the key equals the awaited one (`+0x3fc`), the wait cursor is restored and the carried item is freed (`0x48ae1e`): **the answer to a move is the server's container message for that key**.
8. The druid / Kaarg classes in detail: the shelf rect order (shelf index <-> rects A..D), the fourth Kaarg shelf (weapons) and the druid sound-slot order, the animation tables (`+0x240` bits `0x10` / `0x20` / `0x40`, `+0x254` frame, `0x4baa98` load, `0x4bae3e`, `0x4baf3f`, `0x4bb040`). Start `0x4bde01`, `0x4c0017`, `0x4b9cf5` slots `+0x78..+0x9c`.
9. *(answered)* **`0x4b8273` and `window+0x132`.** Diffing the two routines instruction by instruction (CONFIRMED): `0x4b8102` (next hero) does `+0x130 += 1`, wraps to 0 when `>= count(list)`; `0x4b8273` (previous) does `-= 1` when `+0x130 != 0`, else wraps to the **last** index (`0x4a0dd0`); everything else (the `0x405` to the view, select the hero, `FUN_004167c2`) is identical, so it is the exact mirror. `window+0x132` is the **shown shelf index** (0..3): `0x4b66f2` returns `+0x132 + 5` = the item-region kind of the stock panel (5..8), `0x4b2a2e` indexes the stock block `+0x2100 + shelf x 0x14`; the ctor value `100` (`0x4b8e6c`, `0x4be984`) is a "no shelf shown yet" marker replaced by `FUN_004b3c4e(0)` at the load.
