# The character generator panel (L2 step 1)

What follows the PreCreate screen ([shell.md 3.3](shell.md)): the panel `+0x36c` of the shell window, shown by `0x48f3f0` after OK. Facts from the GOG
`allods2.exe` (sha256 in [formats/README](../formats/README.md)), found with REA (decompile + disassembly) on 2026-11-10. CONFIRMED = read in the
exe (routine given), INFERRED = deduced. Engine choices are DECISION. Built in L2: `engine/shell/chargen.py` (model `ChargenState` + screen), tests `tests/test_engine_shell_campaign.py`, goldens `["shell"]` `chargen*`; the hint dialog is placed at the bottom of the class column (its rect would cover the preview), black is transparent in the class pictures (`Image.key`).
The creation call that Accept leads to is [triggers 9.3](triggers.md#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed) (`FUN_004f254b`).

**Headline facts (they differ from the old shell.md text).**
- There is **no dice and no "Roll"** in this panel (CONFIRMED): the three bottom buttons are **Accept / Reset / Back** (main.txt `0xee` "Accept", `0xef` "Reset",
  `0x104` "Back"). `chrgen\cube\sprites.16a` and `chrgen\loader\*` belong to the mission loading / statistics screen (strings used only at `0x42ec2e`-`0x42ef4f`,
  class of `FUN_0042ee73`, built from `0x431b4b`), not to this panel.
- The attributes **start at the template hero's** (Start_MF / FF / MM / FM) with a **free pool of 0** (`0x42dd7d`-`0x42dd8b` in `0x42d8dc`: `+0x1f0 := 0` after the load). The panel only
  **re-distributes** points between the four attributes at marginal cost; **Reset** sets 25 / 25 / 25 / 25 and a pool of **100** (`0x42dfee`).
- Only **four** of the five class icons are clickable (hit loops `< 4`: `0x42d1a3`, paint `0x42b220`): sword / axe / mace / pike, resp. fire / water / air / earth.
  Bow and astral (index 5) are in the picture but cannot be picked.
- The hero shown in the bottom-left panel is a **live preview unit** rebuilt after every change (`0x491988` -> `0x4919ff`); Accept sends message `0x48`
  (`0x41c5f5`) = the arguments of `FUN_004f254b`.

## 1. Window tree and layout (640x480; CRect args are (left, top, right, bottom) unless noted)

Panel `+0x36c`: ctor `0x42d39d` (vtable `0x5cb6a8`), builder `0x42d4b0`; children are added in this order, which is the **draw order** (back to front):
`0x42e1ed` (panel paint) only resets the cursor and draws the children (`0x4dbd20` -> `0x4d43e0`, the panel itself draws nothing: slot 12 `0x42e243` is empty).

| # | id | class / ctor (vtable) | rect (CONFIRMED `0x42d4b0`) | bitmaps drawn | paint |
|---|---|---|---|---|---|
| 1 | `0x457` stats | `0x428521` (`0x5cb4c8`), init `0x42864f` | (0, 0, 160, 238) | `main\graphics\chrgen\leftup.bmp` 160x238, at (0,0) (the names Body / Agility / Mind / Spirit and the empty slots are in the picture) | `0x4293cb` |
| 2 | `0x458` full stats | `0x42a0f1` (`0x5cb540`) | ctor args (0, 238, 160, **242**) (INFERRED a bug: a 4 px band, see 6) | `graphics\interface\chrgen\FullStatsL.bmp` 160x242 at (0, 238) | `0x42a2b0` |
| 3 | `0x459` buttons | `0x42a443` (`0x5cb5b8`), init `0x42a549` | (480, 0, 640, 238) | `graphics\interface\Inn\ButtonsArea.bmp` 160x238 at (480, 0) | `0x42a6ee` |
| 4 | `0x45a` class column | `0x42b052` (`0x5cb630`), init `0x42b890` | (160, 0, 480, 480) | `chrgen\fighter\column.bmp` or `chrgen\mag\column.bmp` 320x480 at (160, 0) (NOT `CenterArea.bmp`) | `0x42b220` |
| 5 | `0x467` hint | tips window `0x4dec24` (child of 4) | (0, 0x118, 0x138, 0x1e0) = (0, 280, 312, 480), INFERRED reading | none: text box + Close button (`0x45a`) + check box | built `0x42dba8` |

Nothing covers (480..640, 238..480) (INFERRED: the pixels of the previous screen stay; open 2). The screen is 640x480 only (the constants are absolute).

### 1.1 Stat rows (child 1; rects from `0x42864f`, point + size, absolute pixels)

Row `i = 0..3` (Body, Agility, Mind, Spirit; names main.txt `0xf..0x12` "Body" "Agility" "Mind" "Spirit", stored in the string array `+0x1bc`):

| rect | x, y, w, h | use |
|---|---|---|
| name `+0x64 + 0x10 i` | (0x10, 0x39 + 0x21 i), w x h = text size of the name | tooltip only (the name is in the bitmap) |
| A value box `+0xb4 + 0x30 i` | (0x52 = 82, 0x36 + 0x20 i = 54 + 32 i), 20x20 | the number; hit type 0 (tooltip only) |
| B plus `+0xc4 + 0x30 i` | (0x6b = 107, 54 + 32 i), 20x20 | **+** button, hit type 1 |
| C minus `+0xd4 + 0x30 i` | (0x84 = 132, 54 + 32 i), 20x20 | **-** button, hit type 2 |
| pool `+0xa4` | (0x2e = 46, 0xb5 = 181), 77x22 | the free pool |

Hit test `0x4296f2`: rects of A, B, C of each row in row order, Win32 `PtInRect` (left <= x < right), result `row << 8 | type`, or -1.
Text: `"%d"` (`0x5eeebc`) of the value at (A.x + 2, A.y + 4), left aligned (mode 0), font **font4** (`0x620dc8`, 16x16, [fonts](../formats/fonts.md)) through
`FUN_0045d536` (1 px shadow), gold gradient `0x620ec0` row 0 ([palettes 6](../formats/palettes.md)); the pool `"%d"` (`0x5eeec0`) centred in the pool rect
(x = l + w/2, y = t + h/2 + 2, mode `0xa`), same font and colour (`0x4293cb`).
Button pictures (`graphics\interface\chrgen\buttons\*.bmp`, 20x20), CONFIRMED loaders `0x428b45`, state function `0x429827` (state arrays `+0x174 + 8 i` plus, `+0x178 + 8 i` minus):

| state | plus (B) | minus (C) |
|---|---|---|
| normal | `pnloff` | `mnloff` |
| hover (left button up) | `ploff` | `mloff` |
| pressed (left button down on it) | `plon` | `mlon` |
| disabled | `pdisable` | `mdisable` |

Plus is **enabled** iff `pool >= up(v)` and `v < 45`; minus iff `v > 15`, where `up(v) = cost(v+1) - cost(v)`, `down(v) = cost(v) - cost(v-1)`
(`0x42a033`, `0x42a063`, `cost` = `FUN_004f250e`). Hover / pressed apply only to an enabled button; pressed = hover + flag bit 0 of the event (`flags & 1`).
The states are recomputed on mouse move / down / up (`0x4299d8`, `0x4299fb`, `0x429a6e`; the down handler computes them **before** applying the change)
and by Reset.

### 1.2 Buttons (child 3)

Button pictures `graphics\interface\Inn\button{1,2,3}{off,on}.bmp` 140x46; background picture at (480, 0). Rects (CONFIRMED `0x42a549`, in order of `+0x90`, `+0xa0`, `+0xb0`):

| index | role | rect (l, t, r, b) | caption (main.txt) | on release does | sound on press |
|---|---|---|---|---|---|
| 0 | **Accept** | (484, 44, 624, 90) | `0xee` | posts `0x445` (`0x42e250`) | `SFX\Click_Ok.wav` |
| 1 | **Reset** | (484, 91, 624, 137) | `0xef` | `0x42dfee`: values 25 x4, pool 100, preview refresh | `SFX\Sbros.wav` |
| 2 | **Back** | (484, 138, 624, 184) | `0x104` | posts `0x446` (`0x42e26f`) | `SFX\Back.wav` |

Paint `0x42a6ee`: the button picture `off` at (480 + l, t); **`on`** instead when this button is hovered **and** held (`+0xc0 == +0xc4 == i`). Caption: font4 centred
(mode `0xa`) at (l + w/2, t + h/2), **+1 px down while pressed**; colour gold `0x620ec0` normally, **yellow `0x620dc4`** (255, 255, 116) while hovered.
Mouse: move `0x42abcb` (hover = the hit button when the left button is up, or when held and it is the pressed one; else none); **press** `0x42a9c9` (hit -> `+0xc0`,
plays the sound); **release** `0x42aa58` runs the action only when the pointer is still on the pressed button; the panel clears the hover when the pointer leaves
the button area (`0x42d85a` -> `0x42ab1b`). Enter (key `0xd`) = Accept (`0x42e113` -> `0x42e250`); the base dialog key handler `0x4dc326` only handles
Tab / arrows (focus), so **Esc does nothing** here (INFERRED for the shell window; open 7).

### 1.3 Class column (child 4)

Mask picture `chrgen\{fighter,mag}\mask.bmp` (8 bit, 320x480, panel-local x = screen x - 160): the hit value is the palette index at `mask[y * 320 + x - 160]` (`0x42d1a3`;
the BMP is stored bottom-up, rows counted from the bottom). Hit indices (CONFIRMED `0x42c361`, `0x42cd66`), column `k = 0..3`:

| k | fighter: weapon (school) | mask idx | pos, size (screen) | mage: sphere (school) | mask idx | pos, size |
|---|---|---|---|---|---|---|
| 0 | sword (1) | `0xff` | (248, 93) 140x47 | fire (1) | `0x7f` | (360, 150) 44x52 |
| 1 | axe (2) | `0xbf` | (252, 126) 132x57 | water (2) | `0x66` | (232, 165) 48x36 |
| 2 | mace (3) | `0x98` | (248, 182) 140x46 | air (3) | `0xff` | (292, 98) 48x38 |
| 3 | pike (4) | `0x7f` | (244, 225) 148x28 | earth (4) | `0x98` | (300, 228) 48x38 |
| (4) | bow (5), **not pickable** | `0x66` | (248, 250) 140x40 | astral (5), **not pickable** | `0xbf` | (296, 158) 48x45 |

Pictures per column (`...\<name>\on.bmp`, `shine_off.bmp`, `shine_on.bmp`, all the size above; names `sword axe Mace Pike Bow`, `fire water air earth astral`):
flag bit 0 = selected, bit 1 = hovered (`+0x10c + 4 k`); paint `0x42b220` draws, at the position, **selected only: `on`; hovered only: `shine_off`;
both: `shine_on`**; none: nothing (the column picture already shows the engraved icons). Hover bit: set on the hit column by `0x42b691`, cleared on all others every move.
Also an idle shimmer (`0x42b406`): after 500 ms (`0x1f4`) without hover or click, one column per 300 ms (`0x12c`) cycling k = 0..3 draws `shine_on` (selected) or
`shine_off` (not); it only runs after the first click or while the hint is shown (INFERRED reading; open 4).
Loaded but never drawn (INFERRED, no use found): `chrgen\RollStatsR.bmp`, `chrgen\FullStatsR.bmp`, `Inn\RUOver.bmp`.

### 1.4 Full stats (child 2)

`0x42a2b0`: the picture, then **`FUN_0046aa1d`** (the unit info panel text mode, [ui-layout 11](ui-layout.md#11-j1-minimal-ui)) for the **preview unit** (`this.panel+0x94`) in the rect
(l + 12, t, r + 12, b) of the child, i.e. the same HP / mana / attributes / damage list as the in-game panel (font2, gold labels, sage values). Tooltip `0x42a34b` = `FUN_0046b9f0` (hit test of that panel).

### 1.5 Hint widget `0x467` (TipsMode, default on, `0x622774`)

Built in the show routine `0x42d8dc` (`0x42db99`-`0x42dc0a`): text `town.txt` **`#tips5`** (fighter: "This screen allows you to create your own character. If you are
playing for the first time, you may skip it by clicking <Accept>. ... selecting one of the five weapons classes. This will give you an initial skill of 20 for that
weapon type.") or **`#tips6`** (mage: "... one of the five element spheres. ... initial skill of 20 for that element. The starting set of spells will not be affected."),
chosen by the preview unit's mage flag (`unit+0x1b8 & 2`). The tips window (`0x4dbc50` / `0x4deca4`: text box at (20, 24) size (w - 28, h - 36) in font2 / gold
`0x620d90`; a **Close** button (main.txt `0x7f`, posts `0x45a`, which removes the window) and a check box "Show tips next time" (`0x80`) at its bottom; the rect is the
one in the table). **After the first class click** (`0x42e14b`, counter `+0x100 == 0`) the text is replaced by **`#tips7`** ("Now you can change the basic stats ... Click on <Accept> when you're done.").
With TipsMode off the widget is not built. `#tips` n = line `2n - 1` of `town.txt` (`#tipsN` header on line `2n - 2`, 0-based).

### 1.6 Tooltips (slot 5 `0x429b01`, child 1; active once the panel flag `+0x104` is set)

Hover on: a name rect -> main.txt `0x9b + i` (155..158, the attribute descriptions, `#` = line break); the pool -> `0x111` "Free pool"; A -> `"%s = %d"` (`0x5eeec4`: name, value);
B -> `"%+d"` of **-up(v)** (the price: "-1", "+0" when free); C -> `"%+d"` of **down(v)** (the refund). Shown even for a disabled button. How the shared tooltip window places it is not decoded (open 5).

## 2. Behaviour

### 2.1 Show (`0x42d8dc`, vtable slot 32; CONFIRMED)

1. The preview unit `panel+0x94 := hero list[game+0x6c]` (`0x42e28e`); this is the unit the PreCreate hero / code chose.
2. `0x429309`: the four values `+0x1d0, +0x1d4, +0x1d8, +0x1dc` (Body, Agility, Mind, Spirit) := the unit's attribute bytes `+0x144, +0x147, +0x145, +0x146`
   = the **template's attributes** (Start_MF 40 / 36 / 25 / 17, FF 37 / 39 / 21 / 25, MM 28 / 20 / 41 / 32, FM 19 / 23 / 30 / 42; units.md); backup copy `+0x1e0` (`0x429388`).
3. Mage flag `+0xf0 := (unit+0x1b8 & 2) << 5` (0x40 = mage), female `+0xf4 := (unit+0x1b8 & 4) << 6`; portrait index `+0xf8 := unit+0x28 - 1`.
4. Classes load their pictures by the mage flag (`0x42b890`, sounds `0x42d027`), tips as 1.5, the shared sounds are loaded (`0x42e676`):
   `+0x84` `SFX\ChrGen\+_-.wav`, `+0x88` `SFX\Click_Ok.wav`, `+0x8c` `SFX\Sbros.wav`, `+0x90` `SFX\Back.wav`; class sounds `SFX\ChrGen\Skill\` `FSword FAxe FClub FPike FBow` /
   `MFire MWater MAir MEarth MAstral` `.wav` (the sound of column k is entry k).
5. **Pool `+0x1f0 := 0`**, states computed, all class flags cleared and **column `game+0x4ac - 1` selected** (`game+0x4ac` = the request's school: 0 at construction, then the
   preview refresh stores the template's best school `unit+0x23c`, which is **1** for all four templates: sword / fire), `+0x104 := 1` (ready), the default cursor, no music call (the
   `chrgen` music of PreCreate keeps playing, INFERRED).

### 2.2 The rules (CONFIRMED `0x42a033`, `0x42a063`, `0x429e3e`, `0x429f41`, `0x429827`)

`cost(v) = trunc(0.349 * (v - 1)^1.15 + 0.5)` ([triggers 9.3](triggers.md#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed), `engine.party.attribute_cost`).
Values 15..45: `7 8 8 9 10 10 11 12 12 13 13 14 15 15 16 17 17 18 19 19 20 21 22 22 23 24 24 25 26 26 27`.

| rule | value |
|---|---|
| min / max of an attribute | **15 / 45** (minus needs `v > 15`, plus needs `v < 45`) |
| plus on row i (mouse press on B) | if `pool >= up(v)` and `v < 45`: `v += 1; pool -= up(v_old)` |
| minus on row i (press on C) | if `v > 15`: `v -= 1; pool += down(v_old)` |
| `up(v)`, `down(v)` | `cost(v+1) - cost(v)`, `cost(v) - cost(v-1)`: 0 or 1 below 25, up to 1 at 45 (see the list); 0 steps exist (e.g. 16 -> 17 is free, 17 -> 16 refunds 0) |
| pool | 0 at show; Reset = 100; displayed under the pool rect |
| on success | play `+_-.wav` (`0x4385b0` stop, `0x438570` play) **on each change**, then `0x491988(body, agility, mind, spirit, selected_column + 1)` (preview refresh), redraw |
| trigger | the **press** (and the second press of a double click, slot 23 -> slot 21), not the release; **no auto-repeat** |

Reset (`0x42dfee`, on release of button 1): `pool := 100`, all four values `:= 25`, `0x491988(25, 25, 25, 25, school)`, states refreshed. **Quirk (CONFIRMED by the code):**
`4 * cost(25) = 52`, so Reset gives pool 100 + 52 = 152 cost points; with the limit 45 per attribute the most one can reach is `4 * cost(45) = 108` (all four 45, pool
left 48), so the server budget `0x8c = 140` of `FUN_004f254b` can **never** fail from this panel (the 25-fallback only protects the network path). Reset does **not** restore the template
(the backup `+0x1e0` is stored but no reader was found: INFERRED unused).

### 2.3 Class pick (`0x42b736`, press on a column k = 0..3)

All flags bit 0 cleared, bit 0 of k set, `+0x134 := k`; plays class sound k (`0x438570` on `+0x120 + 4 k`); `0x491988(current values, k + 1)`; the hint changes (1.5); the press is
passed on to the base handler. A click outside the four columns is ignored (passed on). The sphere / weapon only decides the **school** argument; no pool change.

### 2.4 The preview unit (`0x491988` -> `0x4919ff`)

`0x491988(a, b, c, d, school)` stores the four attributes in the request `game+0x450` (`+0x4c, +0x50, +0x54, +0x58`) and, when `school != 0`, `+0x5c`, marks the unit dirty,
then `0x4919ff` builds a fresh temporary unit of the template (`req+0x34 & 0xc0` = the code: `0x00` Start_MF, `0x40` Start_MM, `0x80` Start_FF, `0xc0` Start_FM, creation `0x5143e4`),
writes the four `+0x84, +0x86, +0x88, +0x8a` when `req+0x4c != 0` (no budget check here), recomputes (vslot `0x58`), sets `+0x4b`, applies the school with
`FUN_00514f59(unit, school, 20)` (school 0 -> the unit's best school `+0x23c`), copies the result into the displayed preview unit (`0x4699d2`) and reads the attribute bytes back
into the request. So the preview shows what `FUN_004f254b` will build (skill 20 in that school; [triggers 9.3](triggers.md#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed)).

### 2.5 Accept and Back

- **Accept** (press: sound; release: `0x445`) or Enter. Shell handling is already in [shell.md 3.3](shell.md): single player `0x40d480` (resets the client / world state), then
  **`0x49183e`** -> `0x41c5f5` builds message **`0x48`**: bytes `+0xa..+0xd` = `req+0x4c, +0x50, +0x54, +0x58` (the **values of the request** = the panel's values after the last refresh), `+0xe` = `req+0x5c` (**school 1..4**; the template's best school = 1 if no
  class was clicked), `+0xf` = `portrait index (unit+0x28) | hero code (game+0x484)` (low 6 bits = the name index `FUN_00439eb0`, bits 6 / 7 = mage / female), `+0x10` = `game+0x4d8`; the handler `FUN_004f6af6` -> `FUN_004f254b`.
  **Accept without changes** therefore sends the template's own four attributes and **school 1**: it does not mean "school unchanged": the hero gets
  skill 20 in school 1 and shooting skill 10 as for any pick, so the engine must pass `school = 1`, never `None` ([party.py `apply_spec`](../../engine/party.py)).
- **Back** (press: `Back.wav`; release: `0x446`): returns to PreCreate (`0x48f4e2`, chrgen music restarts; [shell.md 3.3](shell.md)).
- Multiplayer-only (single player returns at the top, `game+0x5d8 == 2`): messages `0x414` / `0x415` (`0x42e2a4` / `0x42e485`) cycle the portrait list; not reachable in the GOG single player.

### 2.6 Worked example (Start_MF = 40 / 36 / 25 / 17, pool 0)

Template cost = 24 + 21 + 13 + 8 = 66 (`cost(17) = 8`). Press **-** on Body: 40 -> 39, `down(40) = cost(40) - cost(39) = 24 - 23 = 1`, pool 1.
Press **+** on Spirit: `up(17) = cost(18) - cost(17) = 9 - 8 = 1 <= pool`, Spirit 18, pool 0. Press **+** on Mind: `up(25) = 14 - 13 = 1 > 0`: disabled.
Free steps (`up = 0`, e.g. 16 -> 17) work with an empty pool. Click mace: school 3, `0x491988(39, 36, 25, 18, 3)`. Accept -> message `0x48` (39, 36, 25, 18, school 3, code 0x00, name index) -> `FUN_004f254b`:
`cost` sum 23 + 21 + 13 + 9 = 66 <= 140, attributes as sent, Iron Mace, mace skill 20.

## 3. Mapping to the engine

| exe | engine |
|---|---|
| request `+0x4c..+0x58` | `HeroChoice.attributes` (body, reaction, mind, spirit) = `HeroSpec.attributes` |
| request `+0x5c` | `HeroChoice.school` = `HeroSpec.school` (1..4 from the panel; default **1**, DECISION: never `None` from the generator) |
| code `0x00 / 0x40 / 0x80 / 0xc0` | `HeroChoice.start` `MF / MM / FF / FM` ([campaign.md](campaign.md)) |
| name | PreCreate name field (the panel never edits it) |

## DECISIONs (L2 step 2)

1. A pure model `engine/shell/chargen.py` (no pygame): `ChargenState(start)` with `values`, `pool`, `school`, `plus(i)`, `minus(i)`, `reset()`, `pick(k)`, `choice()` -> `HeroChoice`;
   rules exactly as 2.2 / 2.3 (min 15, max 45, marginal costs, pool 0, Reset 25 x4 + pool 100, school default 1, columns 0..3 only). The view draws 1 (rects of the tables above, pictures, texts).
2. Keep the quirks (4 columns, free steps, Reset pool 100): the exe's behaviour is the spec; list them in the in-game notes only.
3. The right-bottom quadrant: draw the PreCreate `MainArea.bmp` (static, no torches) behind the panel (INFERRED, open 2).
4. The preview (child 2) uses the engine's info panel text mode (`engine/ui/info.py`) on a throw-away hero built by `party.apply_spec` with the current values and school.
5. Hint: show `#tips5` / `#tips6` in the bottom-left rect when TipsMode is on (engine has no TipsMode: show once), change to `#tips7` after the first class click; Close removes it.
6. Sounds on press (Accept / Reset / Back, class k) and on every successful +/-, via the engine sound table keyed by the paths above; no music change.

## Open questions

1. Fifth class (bow / astral): the loops are `< 4`, the pictures exist: is it a deliberate removal? Starting routine `0x42d1a3`, `0x42b220`; verify in play.
2. What the lower-right quadrant (480..640, 238..480) shows (nothing draws it; previous screen?). `0x42e1ed`, `0x48f3f0`.
3. The tips window layout and the rect (0, 280, 312, 480) (INFERRED reading of the CRect args), whether the check box writes TipsMode. `0x4deca4`, `0x42dba8`.
4. Exact rules of the idle shimmer. `0x42b406`.
5. How the shared tooltip window places and styles the text of slot 5. `0x429b01`.
6. Child `0x458` is built with the rect (0, 238, 160, 242) (a 4 px band): do its mouse events / tooltip (`0x42a34b`) ever reach it? `0x42a0f1`, `0x42d4b0`.
7. Esc in this state at the shell window level (`FUN_004852d8` key path); the panel itself ignores it.
8. Verify in play: Reset + pool 100 allows 45 / 45 / 45 / 45; the unreachable server budget check.
