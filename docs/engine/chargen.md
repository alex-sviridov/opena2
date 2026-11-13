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
- Only **four** of the five class icons are clickable: sword / axe / mace / pike, resp. fire / water / air / earth. Bow and astral (index 5) are **fully built but
  unpickable**, the removal is **deliberate at the hit level** (CONFIRMED, [1.3](#13-class-column-child-4)): the ctor and the loader (`0x42b052`, `0x42b147`, `0x42b890`) size / init / load
  **5 entries** (pictures `on` / `shine_off` / `shine_on`, rects, mask index, flag word, sound), but the hit test `0x42d1a3` and the press `0x42b736` (rejects `iVar1 > 3`) and the
  paint `0x42b220` loop `< 4`; only the hover clear `0x42b691` loops `< 5`. No path in single player gives school 5 ([1.3](#13-class-column-child-4), INFERRED reason: a cut feature). The engine keeps four pickable (DECISION).
- The hero shown in the bottom-left panel is a **live preview unit** rebuilt after every change (`0x491988` -> `0x4919ff`); Accept sends message `0x48`
  (`0x41c5f5`) = the arguments of `FUN_004f254b`.

## 1. Window tree and layout (640x480; CRect args are (left, top, right, bottom) unless noted)

Panel `+0x36c`: ctor `0x42d39d` (vtable `0x5cb6a8`), builder `0x42d4b0`; children are added in this order, which is the **draw order** (back to front):
`0x42e1ed` (panel paint) only resets the cursor and draws the children (`0x4dbd20` -> `0x4d43e0`, the panel itself draws nothing: slot 12 `0x42e243` is empty).

| # | id | class / ctor (vtable) | rect (CONFIRMED `0x42d4b0`) | bitmaps drawn | paint |
|---|---|---|---|---|---|
| 1 | `0x457` stats | `0x428521` (`0x5cb4c8`), init `0x42864f` | (0, 0, 160, 238) | `main\graphics\chrgen\leftup.bmp` 160x238, at (0,0) (the names Body / Agility / Mind / Spirit and the empty slots are in the picture) | `0x4293cb` |
| 2 | `0x458` full stats | `0x42a0f1` (`0x5cb540`) | ctor args (0, 238, 160, **242**) (CONFIRMED (l, t, r, b), 1.4: a 160 x 4 px band, a bug; its tooltip is unreachable) | `graphics\interface\chrgen\FullStatsL.bmp` 160x242 at (0, 238) | `0x42a2b0` |
| 3 | `0x459` buttons | `0x42a443` (`0x5cb5b8`), init `0x42a549` | (480, 0, 640, 238) | `graphics\interface\Inn\ButtonsArea.bmp` 160x238 at (480, 0) | `0x42a6ee` |
| 4 | `0x45a` class column | `0x42b052` (`0x5cb630`), init `0x42b890` | (160, 0, 480, 480) | `chrgen\fighter\column.bmp` or `chrgen\mag\column.bmp` 320x480 at (160, 0) (NOT `CenterArea.bmp`) | `0x42b220` |
| 5 | `0x467` hint | tips window `0x4dec24` (child of 4) | SetRect(0, 0x118, 0x138, 0x1e0) = (l, t, r, b) relative to the column (160, 0) = screen (160, 280)-(472, 480), 312x200, CONFIRMED (1.5) | none: text box + Close button (`0x45a`) + check box | built `0x42dba8` |

Nothing covers (480..640, 238..480): **CONFIRMED the previous screen's pixels stay**. The root window (`+0xcc`, class vtable `0x5cfcd8`) paints nothing of its own (slot `0x30` = `0x41e790` is an empty `ret`; slot `0x34` `0x4d4468` runs slot `0x2c` = `0x4d43e0`, the children, then slot `0x38` `0x4d44a3` -> `0x4535e4`, which blits the dirty rect from the persistent off-screen buffer to the DirectDraw primary, no fill / clear anywhere); the closing PreCreate panel `+0x374` is only removed from the child list (`0x4d3a89` at the top of `FUN_004891d8`, owner `+0x30 := 0`), never erased or hidden by a paint; `0x48f3f0` just adds `+0x36c` (`0x4d3a64`), resets the cursor sprite (`0x47b8f5`) and redraws. So the quadrant keeps the last PreCreate frame: `MainArea.bmp`, the right torch (`torch2`, frozen at its random frame at the click, covers y 238..272) and the OK button as left at the click (mouse: hover `okl`; Enter: normal). No other child (hint `0x467`, tips) extends there (rects above). Engine: `chargen.py` draws `MainArea` + `torch2` frame 7 + `okl` (DECISION for the unknowable frame / hover state). The screen is 640x480 only (the constants are absolute).

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
Tab / arrows (focus), so **Esc does nothing** here (CONFIRMED end to end: [shell.md 3.5](shell.md); `FUN_00484a76` forwards Esc to the window manager only for `game+0x404` neither 0 nor 1, `0x4d4769` gives it to the focused child, then `0x42e113` -> `0x4dc326` returns 0).

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

The fifth entry is complete in the exe (CONFIRMED `0x42b890`: pictures, rect, size, mask byte `+0x108`; state / sound slot 4 initialised by `0x42b147` (`< 5`); `0x42d027` loads `FBow.wav` / `MAstral.wav`, both present, 17794 / 38626 bytes). The mask pictures **do** contain the fifth region (CONFIRMED, read from the install): fighter `0x66` 3807 px, x 243..383, y 257..283; mage `0xbf` 2968 px, x 292..347, y 154..206 (mage mask also has stray `0x67 / 0x8a / 0x99`, 24 px, never tested). So the hit test would find it with `< 5`; `< 4` makes it return -1 (clicks pass on). Paint, press and idle shimmer never touch slot 4 (paint of slot 4 would be a no-op; `0x42b220` does `state[4] |= 1` through `+0x11c`, INFERRED side effect of the shared flag word, unobservable).

School 5 elsewhere (CONFIRMED by callers): `FUN_00514f59` (callers `0x4919ff` preview and `0x4f254b` creation only) handles schools 1..5 (loop `< 6`, `Uncommon Wood Long Bow` for the fighter, `Drain_Life` + staff for the mage), because the unit has five school skills; the school argument of `0x491988` is only fed from the column index + 1 (`0x42b736`, `0x429e3e` and its minus twin `0x429f41` pass the selected column `+0x134` + 1 = 1..4) or the template's best school (1 for all four templates, [2.1](#21-show-0x42d8dc-vtable-slot-32-confirmed)). `0x4f254b` (callers `0x4ebd5f`, `0x4f515d`, `0x4f856a`) takes the school from message `0x48`. So school 5 is dead code in single player; INFERRED: the five-school code serves a cut or multiplayer path, not a hidden single-player option.

Pictures per column (`...\<name>\on.bmp`, `shine_off.bmp`, `shine_on.bmp`, all the size above; names `sword axe Mace Pike Bow`, `fire water air earth astral`):
flag bit 0 = selected, bit 1 = hovered (`+0x10c + 4 k`); paint `0x42b220` draws, at the position, **selected only: `on`; hovered only: `shine_off`;
both: `shine_on`**; none: nothing (the column picture already shows the engraved icons). Hover bit: set on the hit column by `0x42b691`, cleared on all others every move.
Also an idle shimmer (**CONFIRMED**, `0x42b406`, called only at the end of the column paint `0x42b220`, once per paint; clock = `timeGetTime`, not the animation tick). Globals: idle stamp A `0x61adc8`, step stamp B `0x61adb0`, last hovered column `cur` `0x5eecc4` (init -1), cycle index `idx` `0x61ade8` (init 0), count `0x5eecc8` = 4; A / B are set to "now" on the first call only (flag byte `0x61add4`; the globals outlive the screen). Per paint, `hit` = the column whose mask byte is under the cursor (`0x42d1a3`, regardless of windows on top):
1. Runs only while the hint window exists (`owner+0x80` != 0; also needs `owner+0x100` == 0, INFERRED normal) - **not** after a first click.
2. `now - A < 500` (`0x1f4`): B := now, nothing drawn.
3. Else: if `cur` != -1, `idx := (cur + 1) % 4`. If `hit` != -1 (pointer on a column): A := B := now, `cur := hit`, nothing drawn (so hovering refreshes A only every 500 ms of hover; leaving shows the shimmer at once if A is already 500 ms old, resuming after the last hovered column).
4. Else (no column under the pointer): draw column `idx` with its own paint-rect, `shine_on` if its flag is 1 (selected) else `shine_off` (the selected column is included in the cycle); `cur := -1`; then if `now - B > 300` (`0x12c`, strictly): `idx := (idx + 1) % 4`, B := now. The column stays lit for the 300 ms+ until the next step, columns follow one after the other without a gap (k = 0, 1, 2, 3, 0, ...); the picture is drawn over the normal paint and is gone when the conditions fail.
Clicks and keys do not touch A / B; only a hovered column does. Engine: `CharGen.update(dt_ms)` runs this on a ms clock (`shimmer` = the lit column this frame, `scene()` draws it like a hover picture); A / B start at 0 on every entry.
Loaded but never drawn (INFERRED, no use found): `chrgen\RollStatsR.bmp`, `chrgen\FullStatsR.bmp`, `Inn\RUOver.bmp`.

### 1.4 Full stats (child 2)

`0x42a2b0`: the picture, then **`FUN_0046aa1d`** (the unit info panel text mode, [ui-layout 11](ui-layout.md#11-j1-minimal-ui)) for the **preview unit** (`this.panel+0x94`) in the rect
(l + 12, t, r + 12, b) of the child, i.e. the same HP / mana / attributes / damage list as the in-game panel (font2, gold labels, sage values). Tooltip `0x42a34b` = `FUN_0046b9f0` (hit test of that panel).
**Its mouse / tooltip never fires (CONFIRMED).** The ctor `0x42a0f1` -> `0x4d36ff` -> `0x4d3918` -> `SetRect(this+8, l, t, r, b)` (the same call builds `0x457` = (0, 0, 160, 238), `0x459` = (480, 0, 640, 238), `0x45a` = (160, 0, 480, 480)), so child `0x458` is **(0, 238, 160, 242), 160 x 4**, not 160 x 242. The manager finds the window with `FUN_004d42e8` (children last-to-first, `PtInRect` on the rect `+8`), so the child answers only for a pointer in y 238..241. `0x42a34b` converts the pointer to (x - l - 12, y - t - 12) = y in -12..-9 and `FUN_0046b9f0` returns no text for any y below 0x2c (every branch needs y >= 0x2c; the Life / Mana / attribute rows start at 0x2c = 44, 0x58, 0x7a, 0xad, 0xbe, 0xc8) : the 4 px band never yields a tooltip, and the visible panel (y >= 242) lies in no child, so **the preview panel has no tooltip and no mouse reaction**. The text is still drawn (the paint is not clipped to the rect).

### 1.5 Hint widget `0x467` (TipsMode, default on, `0x622774`)

Built in the show routine `0x42d8dc` (`0x42db99`-`0x42dc0a`): text `town.txt` **`#tips5`** (fighter: "This screen allows you to create your own character. If you are
playing for the first time, you may skip it by clicking <Accept>. ... selecting one of the five weapons classes. This will give you an initial skill of 20 for that
weapon type.") or **`#tips6`** (mage: "... one of the five element spheres. ... initial skill of 20 for that element. The starting set of spells will not be affected."),
chosen by the preview unit's mage flag (`unit+0x1b8 & 2`). The **tips window** (ctor `0x4dec24(id, l, t, r, b, text)` -> base `0x4dbc50` -> `0x4d36ff`, which stores `SetRect(l, t, r, b)` (`0x41e2d0` = the import `SetRect`) at `+8`; vtable `0x5d0568`; builder `0x4deca4`) is CONFIRMED:
- **Rect**: (l, t, r, b), relative to the **parent**: absolute = + the parent chain's `+8 / +0xc` (`0x4d3940` / `0x4d3993`). The hint is added to the class column (`+0x7c`, rect (160, 0, 480, 480)), so the window is at screen (160, 280)-(472, 480), **312 x 200** (not at x 0: the earlier reading ignored the column's origin; it does not cover the preview panel).
- **Frame** (paint `0x4deeb0`): the lm.256 dialog frame of the rect minus the 8 px shadow (body 304 x 192): corner sprites 1/3/6/8, edges 2/7 and 4/5, centre 0 with the 0x30 x 0x20 steps of the common dialog (ui-layout 11.4), shadow pass first; no size snapping (the rect is used as given; 304 and 192 are exact multiples).
- **Children** (window size w x h, rects (l, t, r, b) relative to the window): text box id `0xd` `0x4d4e9b(0x14, 0x18, w - 0x1c, h - 0x24)` = (20, 24)-(w - 28, h - 36) = **264 x 140** here, font2 / gold `0x620d90`, pitch argument 0 = glyph-0 height + 2 = **12** for font2 (`0x4d4e9b` = the `0x4d4dc9` text widget, class `0x5cfdc8`, with a font / table argument; visible lines = min(lines, 140 / 12)). **Text drawing CONFIRMED** (paint slot 11 `0x4d5134` -> `0x45e01d`): **left aligned at the box left** (no centring, no vertical centring, no extra margin; the origin is the box's absolute left / top), line n at y = top + 12 n; wrapped by `0x45ccbb` to the box width (a line is kept while measure < width; engine `Font.wrap(text, w - 1)`, INFERRED equivalent); every line that is not the last of its paragraph is **justified** (`0x45da67`: word gaps = (width - sum of word widths) / (words - 1), x kept as a double, truncated per word; the last line stays left aligned). First-line indent = a font-side field `+0x80`, 0 here (INFERRED). The box starts at (20, 24) inside the 48x48 corner sprites (frame 10 / 12 / 15 / 17 at the body corners), so the first lines of the original do overlap the skull ornaments (computed, not visible-checked); the text is drawn after the frame. **DECISION (user report; screenshot-checked): the engine insets the text box in x only, to (40, 24, w - 44, h - 36) (skull sprites cover x 0..38 and w - 44..w; the flourishes along the edges end at y 12, so the top stays 24), width 312 -> 228 in the hint, 408 -> 324 in the PreCreate window; line counts fit: #tips5 9, #tips6 11 (of 11), #tips7 8, #tips8-10 2-3 (of 6).** **Close** button id `0xe` `0x4d5470(w - 0x78, h - 0x28, w - 0x28, h - 0x16)` = (192, 160)-(272, 178) here (80 x 18), main.txt `0x7f`, posts message `0x45a`; **check box** id `0xf` (class `0x44f170`, vtable `0x5ccdf8`, a one-item check group) `(0x28, h - 0x28, w - 0x7c, h - 0x18)` = (40, 160)-(188, 176) here, main.txt `0x80` "Show tips next time", font2 `0x620d90` (orange `0x620d50` while hovered); built **checked** (`vtable+0x44(&1)`: the window exists only with TipsMode on). Paint `0x4d7b31`: radiob frame 5 (on) / 4 (off) at (x + 1, y) with the shadow (level 4) at (x + 5, y + 4), caption at (x + 6 + 16, y + 3) (the sprite file `0x626c8c` is INFERRED to be the radiob.256 of the options window).
- **Check box action** (CONFIRMED): a click toggles bit 0 of `+0x80` and sends the window message `0x46e` (wparam = id `0xf`, lparam = state); the window's handler (slot `0x48` = `0x4df278`) stores **`TipsMode (0x622774) := lparam` at once** (in memory, nothing is written to the registry by this handler; the options save `0x4416c3` persists the variable like the other options; the click-versus-release moment of the toggle is INFERRED: release). The window is **not** closed by it.
- **Close / keys**: Close posts `0x45a` to the window, which forwards it up (`0x4dc2b0` -> `0x4d4769`) to the owner: the character generator's handler (`0x42d71c`, case `0x45a`) removes the hint from the column (`+0x80`, `0x4d3a89`) and zeroes the field; the window never closes itself. The window's own handler returns 0 for `0x100` (keys), `0x445` and `0x446`, so ESC / Enter do nothing there (the panel's Enter = Accept is unaffected). Mouse messages are not consumed by the text box or the frame (INFERRED: they reach the owner beneath); only Close and the check box react.
- **Callers** of `0x4dec24` (12): chargen hint `0x42dba8`, PreCreate `0x43377e` (shell.md 3.3), the mission message `0x45b` `0x487ff0` (id `0x10`, rect (10, 20, 370, 188) = 360 x 168), and the `#tips1..4, 11, 12` windows of the town / shop / inn screens (`0x49ad63`, `0x49c4be`, `0x49e5b6`, `0x4b8cbe`, `0x4be7d6`, `0x4c04e8`, `0x4ca8b5`, `0x4ce714`, `0x4d0e19`: not decoded one by one, each behind its own `cmp TipsMode`).
With TipsMode off the widget is not built. `#tips` n = line `2n - 1` of `town.txt` (`#tipsN` header on line `2n - 2`, 0-based).

### 1.6 Tooltips (slot 5 `0x429b01`, child 1; active once the panel flag `+0x104` is set)

Hover on: a name rect -> main.txt `0x9b + i` (155..158, the attribute descriptions, `#` = line break); the pool -> `0x111` "Free pool"; A -> `"%s = %d"` (`0x5eeec4`: name, value);
B -> `"%+d"` of **-up(v)** (the price: "-1", "+0" when free); C -> `"%+d"` of **down(v)** (the refund). Shown even for a disabled button.

**The shared tooltip (CONFIRMED).** Slot 5 (vtable `+0x14`) of child `0x457` is the same "tooltip text under the pointer" hook as the bar's `FUN_004ad61c`: the tooltip is not a window of the screen, it is the global mouse manager `0x604500` (`FUN_004268c4`, called from every long routine and the shell loop; [ui-layout 11.6b](ui-layout.md)), so **every rule of 11.6b applies unchanged**: shown after 500 ms without a pointer move (accumulator `499 < acc < 0x639c`, one question at the crossing, an empty text = nothing until the next move), hidden by the next move and at 25 500 ms; box above and to the right of the pointer (left = x, bottom = y, top = y - 5 - 14 n, right = x + widest + 11; shifted left past x 640, down past y 0); fill `(0x24, 0x2c, 0x27)`, bronze bevel and `Ball.bmp` corners; text font2, colour table `0x6200e0` ("tooltip"), shadow 1, one line per `#` part (main 0x9b..0x9e carry the `#` breaks). The enable flag `mgr+0xa0` is 1 in this screen (`0x42d8dc` clears it at its top, `FUN_00437ee0`, and sets it again at its end, `FUN_00437ec0`; it also sets the panel flag `+0x104 := 1`, without which both slot-5 handlers return 0). The hint window `0x467` is an ordinary child, not a modal, and does not disable it. Handler order (`0x429b01`): for row i = 0..3: name rect, pool rect, value box A, plus B, minus C (first hit wins; the 4 name rects are `(16, 57 + 33 i)` with the text width of the name x line height; the font of that measure is INFERRED font 4). The `"%s = %d"` string is name `+0x1bc + 4 i` (main 0xf + i) and the value `+0x1d0 + 4 i`.

Engine (built): `CharGen.tooltip_text(pos)`, `name_rect`, `tip_timer` (`engine.ui.tooltip.TooltipTimer`, `moved` at the event, `update(dt_ms)` from `CharGen.update`), the scene op `Tooltip` (`engine/shell/scene.py`) painted last by `Panels.draw_tooltip` in `backend_pygame/shellkit.py`; the box is placed in panel coordinates (clamp 640 x 480). Tests `tests/test_engine_shell_campaign.py` (`test_stat_tooltip*`).

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

Reset (`0x42dfee`, on release of button 1): `pool := 100`, all four values `:= 25`, `0x491988(25, 25, 25, 25, school)`, states refreshed. **Quirk (CONFIRMED by the code; 45 x4 costs 4 x (27 - 13) = 56 <= 100 so it is reachable, tested in `test_reset_pool_allows_45_on_all_four_attributes_and_the_budget_never_fails`):**
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
into the request. So the preview shows what `FUN_004f254b` will build (skill 20 in that school, shooting 10; the generator offers only schools 1..4; the unit-type check and the order of writes: [triggers 9.3](triggers.md#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed)).

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
3. The right-bottom quadrant: the frozen last PreCreate pixels (CONFIRMED, section 1): `MainArea.bmp` + `torch2` frame 7 + `okl` behind the panel.
4. The preview (child 2) uses the engine's info panel text mode (`engine/ui/info.py`) on a throw-away hero built by `party.apply_spec` with the current values and school.
5. Hint: the tips window of 1.5 at screen (160, 280, 312, 200) when TipsMode is on, `#tips5` / `#tips6`, then `#tips7` after the first class click; Close removes it; the check box writes `Settings.tips` and saves (engine `tipswin.py`, `chargen.py`).
6. Sounds on press (Accept / Reset / Back, class k) and on every successful +/-, via the engine sound table keyed by the paths above; no music change.

7. Placement DECISIONs (the exe's own text origins are left-aligned, the user asked for centred looks): the attribute digits are centred in their 20 px boxes (the exe: left at box.x + 2); the preview panel's hero name is centred on the panel interior (x 12..155 on FullStatsL.bmp), its labels left / values right-aligned inside it; the tips window's bottom row (Close 64 wide + check box) sits between the corner skulls and above the bottom border band (shared geometry `engine/shell/dialog.py`, measured on the `lm.256` sprites: border 14 / 16 px, skull square 40 px); the between-missions dialog uses the same helpers and centres its headings.

## Open questions

None left (L2 research closed; what only a play-through can judge is in prototype.md).
