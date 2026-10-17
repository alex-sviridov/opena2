# In-game interface: layout, cursor, picking, selection (G3b)

Facts from the GOG `allods2.exe` (sha256 in [formats/README](../formats/README.md)), found with REA on
2026-10-17. CONFIRMED = read in disassembly or decompile; INFERRED = deduced. Engine choices are
marked DECISION. Design: [interface and selection design](../superpowers/specs/2026-10-17-interface-selection-design.md).
Code: `engine/ui/layout.py`, `cursor.py`, `selection.py`, `engine/sim/commands.py`, `engine/view/pick.py`.

## 1. Screen modes and windows

- Three modes: 640x480 (default), 800x600 (`-800`), 1024x768 (`-1024`); chosen in the game-object constructor
  `FUN_00481efc` (`0x482068`-`0x4821c3`) by command-line substring. Screen size = `DAT_00621418` (W) x
  `DAT_0062141c` (H). CONFIRMED (that the string is the command line: INFERRED). Dialogs use a centred 640x480 rect.
- `FUN_00483129` creates the in-game windows (ctor args: id, left, top, right, bottom; child rects are
  parent-relative). CONFIRMED:

| window | id | class / draw | rect (parent-relative) |
|---|---|---|---|
| view (map) | 1 | `FUN_00402af6` / `FUN_00406f43` | (0, 0, W-160, H) |
| right column | 4 | `FUN_004ab65f` | (W-160, 0, W, H) |
| minimap (crystal) panel | 5 | `FUN_004ab753` / `FUN_004ac414` | (0, 0, 160, 158) in the column |
| heads / command bar | 6 | `FUN_004ad57e` / `FUN_004adb65` | (0, 158, 160, 238) |
| unit info | 7 | `FUN_004adf45` / `FUN_004af3bf` | (0, 238, 160, 480) |
| extra / text | 8 | `FUN_004b0823` / `FUN_004b0a10` | (0, 480, 160, H) (height H-480: 0 / 120 / 288) |
| bottom bars (inventory 2, spell book 3) | 2, 3 | `FUN_004a2bba`, `FUN_004c61e7` | (0, H-90, W-160, H) in the view, both the same rect, one shown |
| top strip | 0x4b0 | `FUN_0043b219` | (0, 0, W-160, 30); purpose INFERRED (message line) |

- The view's 16 px **left strips** are drawn by the view itself, inside its rect, at x = W-176 (`FUN_00406f43`
  `0x40a6xx`-`0x40a8xx`), over the terrain. CONFIRMED.

## 2. Layout per resolution (screen px, x y w h)

Graphics are `graphics\interface\*.bmp` (24-bit), loaded by `FUN_00476a6d` into the globals shown.

| panel | graphic (global) | size | 640x480 | 800x600 | 1024x768 |
|---|---|---|---|---|---|
| map viewport | terrain | | 0 0 480 480 | 0 0 640 576 | 0 0 864 768 |
| strip A | CrystalL (`0x626be4`) | 16x158 | 464 0 | 624 0 | 848 0 |
| strip B | HeadsL (`0x626bec`) or CommandBarL (`0x626bf4`) | 16x80 | 464 158 | 624 158 | 848 158 |
| strip C | HumanBackL (`0x626c00`) or TextBackL (`0x626c08`) | 16x242 | 464 238 | 624 238 | 848 238 |
| strip D | extra800l (`0x626c7c`) / extra1024l (`0x626c64`), 1024: TextBackL below | 16 x 96 / 46 | none | 624 480 | 848 480 |
| minimap panel | CrystalR (`0x626be0`) | 160x158 | 480 0 | 640 0 | 864 0 |
| heads / command panel | HeadsR (`0x626be8`), CommandBarR (`0x626bf0`), CommandDnR (`0x626bf8`), CommandEmpR (`0x626bfc`) | 160x80 | 480 158 | 640 158 | 864 158 |
| unit info panel | HumanBackR (`0x626c04`) or TextBackR (`0x626c0c`) | 160x242 | 480 238 | 640 238 | 864 238 |
| extra panel | extra800r (`0x626c80`) / extra1024r (`0x626c68`) | 160 x 96 / 46 | none | 640 480 | 864 480 |
| bottom bar | InvFrame, SpellBook, spb/inv caps | W-160 x 90 | 0 390 | 0 510 | 0 678 |

- Y offsets 0 / 0x9e / 0xee / 0x1e0 are the same at every mode. CONFIRMED.
- Strip B image: **Heads when `view+0x140 == 0` (nothing selected) or `view+0x144 & 0x24` (foreign / structure
  selection), else CommandBar**; strip C: HumanBack, or TextBack when `FUN_004b011e() == 0`. CONFIRMED
  (`0x40a9xx`; `FUN_004b011e` meaning INFERRED: text mode).
- The 800x600 bottom bar is taken from H-90 = 510 before the view is trimmed to 576. CONFIRMED order.
  Rows 576..600 of the view column: INFERRED black.
- Which bottom bar (2 or 3) is the default: INFERRED, not drawn in G3b.

## 3. Map viewport and camera

- `FUN_00402fb8` (map attached): view cells `+0x64` = rect width / 32, `+0x68` = rect height / 32 (integer), then the
  rect bottom is snapped **down** to whole cells: 15x15 (640x480), 20x18 (800x600), 27x24 (1024x768). CONFIRMED.
- Camera cell range `[8, mapW-8-viewW]` x `[8, mapH-8-viewH]` (`FUN_0041efe0`/`FUN_0041eff0` = 8,
  `FUN_0041f000`/`FUN_0041f020`); the 8-cell border is never shown. CONFIRMED.
- The terrain is drawn over the whole view rect; the left strips cover its last 16 px (480 -> 464 visible at 640x480). CONFIRMED.

## 4. Minimap panel

- At the top of the right column: screen (W-160, 0), 160x158, **flush with the corner, no margin** (replaces the
  INFERRED 8 px margin of G2c). Image centre = panel point (72, 82) (`FUN_004ac414`). CONFIRMED.
- Click: `FUN_004ad32f` takes the cell under the pointer, subtracts half the view size, adds 8 and posts message
  `0x406` to the view: `cell = ((mx - panelLeft - offX) >> z) - viewW/2 + 8` (z < 0: `* 2`). CONFIRMED formula;
  that it runs on mouse-down (and drag): INFERRED.
- Hover cursor over the minimap: `FUN_004accb4` (message `0x402`): outside the map image the `sdefault` cursor
  (`0x626cfc`), inside the `smove` cursor (`0x626d00`) or attack / spell variants. CONFIRMED; not used in G3b.

## 5. Edge scrolling and keys

- Per game tick (`FUN_00488aa1`; variants `FUN_00488900`, `FUN_00488e25`), in game state 1 and when mouse-manager
  field `+0x9c == 0` (`FUN_0041e730`; meaning INFERRED: no drag capture): mouse x == 0 -> x velocity -1
  (`FUN_00403f4f`), y == 0 -> y -1 (`FUN_00403fc5`), x >= W-2 -> +1, y >= H-2 -> +1. **The test is on the screen
  border only; panels do not matter** (x >= W-2 lies over the right column). The view applies the velocity at
  `0x407067` and zeroes it after the draw (`0x40aefd`): **one whole cell per tick** (32 px x 16 ticks/s = 512 px/s
  at the default speed), diagonal when both axes trigger, clamped to the camera range. CONFIRMED.
- Arrow keys (`FUN_0040c8a0`, VK 0x25-0x28) add the same +-1 velocity. CONFIRMED.
- The cursor chooser `FUN_0040b2b8` uses the same thresholds for the arrow cursors (section 6).

## 6. Cursors

Table `FUN_0047b92d` ([animation §4.8](../formats/animation.md#48-cursors) has files, hot spots, periods). Globals:

| global | cursor | global | cursor | global | cursor |
|---|---|---|---|---|---|
| `0x626cb8` | default | `0x626cdc` | arrow0 (up) | `0x626cfc`..`0x626d10` | sdefault, smove, sattack, sdefend, spatrol, scast |
| `0x626cbc` | move | `0x626ce0` | arrow4 (down) | `0x626d14` | cantput |
| `0x626cc0` | swarm | `0x626ce4` | arrow6 (left) | `0x626d18` | town |
| `0x626cc4` | attack | `0x626ce8` | arrow2 (right) | `0x626d1c` | dice |
| `0x626cc8` | defend | `0x626cec` | arrow7 (up-left) | `0x626d20` | wait |
| `0x626ccc` | select | `0x626cf0` | arrow5 (down-left) | `0x626d24` | backpack |
| `0x626cd0` | patrol | `0x626cf4` | arrow1 (up-right) | | |
| `0x626cd4` | cast | `0x626cf8` | arrow3 (down-right) | | |
| `0x626cd8` | pickup | | | | |

All CONFIRMED from the table order. Chooser `FUN_0040b2b8` (run each frame from the view draw, game state 1):

1. **Screen border first** (CONFIRMED): x == 0: y == 0 -> arrow7, y < H-2 -> arrow6, else arrow5. x < W-2: y == 0 ->
   arrow0, y >= H-2 -> arrow4, else the in-view logic. x >= W-2: y == 0 -> arrow1, y < H-2 -> arrow2, else arrow3.
2. **In the view rect** and `view+0x9b4 == 0` (no pending command target), not casting. Inputs: hover flags `h` of
   `FUN_004180c6` (1 CUnit, 2 CAirUnit, 0x20 CStructure (0x820 if the template's `+0x8c != 0`, enterable),
   **4 = the hovered object's owner has relation bit 0 set toward the viewer** (`FUN_0041e830`; bit 0 = war, INFERRED),
   0x40 = the cell is fully visible and holds a ground item, 0x400 = fogged); `view+0x140` selected count;
   `view+0x144` summary bits (1 unit, 2 air unit, 0x20 structure, 4 foreign, 8 hero-type); modifiers Ctrl
   `DAT_006227d8`, Shift `DAT_006227dc`, Alt `DAT_006227e0` (VK 0x11 / 0x10 / 0x12; `FUN_0048509b`, `FUN_0048521c`).
   - Nothing selected, or foreign / structure selection (`0x144 & 0x24`): `h & 0x23` -> **select**, else **default**.
   - Own selection, hovered object hostile (`h & 4`): no modifier -> structure ? select : **attack**; Ctrl -> swarm; Alt -> move.
   - Own selection, hovered object not hostile: ground -> **move** (**pickup** when exactly one selected, hero-type
     (`obj+0x1b8 & 1`) and `h == 0x40` or the hovered object is it); Ctrl -> swarm; Alt -> move; object -> **select**
     (**town** for an enterable structure with a single hero; Ctrl -> attack).
   - Pending command target `view+0x9b4`: 1 attack, 2 move, 4 defend, 5 cast, 6 swarm, 8 patrol.
   - Afterwards: an open dialog window (ids 2 / 3, `FUN_004d4013`) under the pointer -> default; a tooltip / modal
     cursor `gamestate+0x3f4` overrides.
3. Setting a cursor resets its animation frame only when it differs from the current one (`FUN_0047b8f5`).

G3b implements: the eight arrows, default, select (hover over a unit), pickup (own selection of one hero over a ground
item, no click action yet). Later phases: move, attack, swarm, defend, patrol, cast, town, cantput, dice, wait,
backpack, the small `s*` cursors over the minimap, and the pending-target modes.

## 7. Picking

- The view draw registers one **screen rect per drawn object** (`FUN_00404d99`, `0x408713`-`0x4087df`; `view+0x134`
  = count) while the object's death stage is `< 2`: the type's `SelectionX1/Y1/X2/Y2` offset by
  `(obj+0x64 - CenterX, obj+0x68 - CenterY - obj+0x6c - obj+0x10)` (screen position of the sprite anchor, minus
  ground height `Z`, minus flyer altitude). CONFIRMED ([units](../formats/units.md)).
- `FUN_004180c6` (hover, every frame): the mouse box `(x-1, y-1, x+1, y+1)`; the rects are walked from the **last
  registered to the first** and the first whose `IntersectRect` with the box is non-empty wins. **Rectangle picking,
  not pixel and not cell.** CONFIRMED. Structures whose template has `+0x64 != 0` and `+0x8c == 0` are transparent to
  the picker (they `continue`); other structures are hit.
- The hovered object is drawn fully lit (`FUN_004632a1` forces the light parameter to 0 while `view+0x994 == this`);
  INFERRED reading. Hovering also sets the object's redraw flag.

## 8. Selection

- **Selection is a flag on each client object** (`obj+0x80`, setter `FUN_0046dd20`), not a list; the server stores
  none. `FUN_004167c2` recomputes `view+0x138` (first selected), `+0x140` (count), `+0x144` (bits above) after every
  change. No size limit on the client; an order packet carries at most 253 ids (`FUN_0050bbb8`). CONFIRMED.
- Mouse release (message `0x40e` left, `0x40f` right: INFERRED) always ends in `FUN_004175c7`: the rect between the press
  point (`0x604500 + 0x6c`) and the release point; **drag when its width or height exceeds `screenW * 10 / 640`**
  (10 / 12 / 16 px), else click. CONFIRMED.
  - Nothing selected, or the cursor is *select*: `FUN_00417986` (select). With a selection the other cursors
    issue orders instead (move 0x16, attack 0x19, 0x1a, 0x1b, 0x1d, 0x21, 0x24, spells 0x1e/0x1f): not in G3b.
- **Click select** (`FUN_00417986`): the topmost rect hit; if the object is **not a structure it is selected whatever
  its owner** (own, ally, neutral, enemy), after clearing the old selection. A structure hit leaves the selection alone.
  Selecting a foreign object is info-only (`view+0x144` bit 4 blocks orders). A click on empty ground with a selection
  is a move order (cursor *move*); with nothing selected it selects nothing. CONFIRMED.
- **Drag select**: every rect whose intersection with the drag rect has area > 10 px^2, **own** (`obj+0x14 == view+0x9cc`)
  non-structure objects only; if none qualifies the old selection is kept; otherwise it is replaced. CONFIRMED.
- **Shift**: click or drag *toggles* each own object; only while the selection is not foreign. CONFIRMED.
- Squads (control groups): `obj+0x88` is a 32-bit mask; digit n selects group n (Shift adds), Ctrl+digit assigns the
  selected own units exclusively, Ctrl+Shift+digit adds, Alt+digit selects and centres the view. No double-click
  select, no Ctrl+A found. Alt with a single selected unit that belongs to a squad selects the whole squad. CONFIRMED.
  Not in G3b.
- **No rubber band is drawn** (no GDI rectangle call; the drag rect is only read by `FUN_0040b2b8` and
  `FUN_004175c7`): INFERRED.
- Deselecting: a click on empty ground does not (it orders). The exe's way to clear the selection was not traced
  (right button `0x40f` untraced). Open question.
- Orders carry the unit list: packet `0x6904b8` (`+5` u16 player id, `+9` command byte, `+0xa`/`+0xc` target cell or
  unit id, `+0x12` count n, `+0x13` n x u16 ids), sent by `FUN_0050164f`. Selecting sends nothing. CONFIRMED.

## 9. Selection marker

Per-unit overlay, vtable `+0x30` = `FUN_004653a5`, called by the view draw (`0x409f4d`-`0x40a0xx`) for objects with
`obj+0x80` set, or **all** objects when the Ctrl+H toggle `view+0xab8` is on. CONFIRMED. Only while `obj+0x184 < 5`
(not dead) and not for invisible objects the viewer cannot see. Geometry, CONFIRMED:

- Bar span `x1..x2` = the pick rect's left and right (screen), `y` = the pick rect's top edge. Track `x1+4 .. x2-4`,
  inner width `Wd = x2 - x1 - 8`.
- **HP bar** (4 rows `y-2 .. y+1`): fill width `hp * Wd / max` (at least 1 when `hp > 0`). Empty track: rows
  `y-2`, `y+1` grey `0x40`, row `y-1` `0x80`, row `y` `0x60`. Fill: rows `y-2`, `y+1` the dark colour, row `y-1` the
  bright colour, row `y` the mid colour. Colours (bright / mid / dark): `hp < max/4` red (255,0,0) / (192,0,0) / (128,0,0);
  `hp < max/2` yellow (255,255,0) / (192,192,0) / (128,128,0); else green (0,255,0) / (0,192,0) / (0,128,0)
  (`FUN_00460db1` draws one bar).
- **Mana bar** when `obj+0x14a > 0`: the same shape 4 px lower (`y+4`), blue (0,0,255) / (0,0,192) / (0,0,128).
- **End caps**: `graphics\interface\Ball.bmp` (4x4, `DAT_00626cac`) blitted at `(x1, y-2)` and `(x2-4, y-2)` of
  each bar.
- Unselected units under Ctrl+H: colours halved and a translucent bar; squad number (`FUN_004610f3`) at `(x1, y+4)`.
- Name above the bar (`obj+0xec` / `obj+0xf8`, at `y-0x0f` / `y-0x19`, centred, owner-coloured) only for named
  (hero) units and when the names option `DAT_0062278c` is on.
- **No circle or ellipse under the unit and no tile highlight.** INFERRED (none found).

## 10. Info panel

`FUN_004af3bf` (unit info window, 160x240 inside the 160x242 panel): shows the hovered object (`view+0x9a8`) in game
mode 1 when no tooltip is active, else the single selected object (`view+0x140 == 1`). CONFIRMED.

- Portrait: `graphics\infowindow\<template+0xf8>.bmp` (+ count suffix when `obj+0x28 > 1`) over the panel; structures
  `<template+0x54>.bmp`. Nothing selected: texts `0x2f` / `0x30` at (L+0x48, T+0x36 / 0x42); two or more selected:
  texts `0x31` / `0x32` and the count.
- Unit text (`FUN_0046aa1d`, L, T = panel origin): name `obj+0xec` at y T+0x12 and `obj+0xf8` at T+0x1c, or when
  empty the type name `FUN_00474733(obj+0x24)` centred at (R-0x58, T+0x1c); **HP**: label text `0x13` at
  (L+0x73, T+0x2c), `"%d/%d"` of `obj+0x104 / 0x108` at (L+0x73, T+0x36); **mana**: label `0x14` at T+0x40, value at
  T+0x4a; primary stats labels `0xf`-`0x12` at (L+6, T+0x2c..), values at L+0x50; armour / attack / resist rows
  further down. Detail level 0..7 depends on the viewer's knowledge of the unit (7 for own and allied).
- Structures: name `FUN_00474733(obj+0x24 - 1)` at (R-0x58, T+0x1c), HP as above.

## Open questions

- How the exe clears a selection (right button `0x40f`, Esc?); the engine uses right click (DECISION).
- Which bottom bar is shown first; meaning of mouse-manager `+0x9c`; the purpose of the 30 px top strip.
- `FUN_004b011e` (text vs human panel) and the command-bar contents (`FUN_004adcea`, `FUN_004aff34`, `FUN_004b0a10`).
- Hover brightness exact effect; structure picking rects (types and `+0x64` / `+0x8c` flags in data.bin).
- Names of orders (command bytes) and the squad voice `FUN_0041da16`.
