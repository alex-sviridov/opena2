# The shell (L0: startup, main menu, options, new game, quit)

Code: `engine/shell/` (pure: the state machine and the screens), `engine/backend_pygame/shell.py` (window, painter, services, loop),
`engine/__main__.py` (`PlaySession`, `shell_cmd`). Tests: `tests/test_engine_shell.py`, `test_engine_shell_options.py`, `test_engine_shell_loop.py`,
goldens `tests/golden.json["shell"]` (`tools/update_golden.py --only shell`).
Facts are marked **CONFIRMED** (read in `allods2.exe`, routine address given; GOG build 1.01, sha256 in [formats/README](../formats/README.md)) or **INFERRED**;
engine choices are **DECISION**. Message ids of the exe double as screen-state ids (`FUN_0041e3f0(msg)` posts one to the game window; handler
`FUN_004852d8`, child-closed handler `FUN_004891d8` on message `0x44c`).

## 1. Corrections to earlier notes (CONFIRMED)

- `game+0x404` is a **bit mask of open screens**, not a single mode: `1` mission, `0x80` main menu shown, `0x100` slide window, `0x10` cut-scene list, `0x40` hall of fame /
  credits, `0x200` / `0x400` / `0x800` the new-game panels (`+0x36c`, `+0x370`, `+0x374`), `0x2000` a video is playing (`0x48f919`, `0x48fb2a`), `8` any modal dialog, `4` the hero panels.
  Message `0x421` (back to the menu, `FUN_0048b569`) acts only when the mask is exactly 0, then sets `|= 0x80`. `game+0x5d8 == 2` = single player.
- State `0x438` index 6..9 (window `game+0x134`, bitmaps `graphics\interface\logo\*.bmp`: `SSS256`, `Buka256`, `Nival256`, `Allods`, `Intro`, `Web`, `splash1..4`) is a **dead
  splash chain**: nothing posts `0x427` or `0x438(0)`. It is not the way into `0x425`; that was the open question in ui-layout / open-questions. **The way into `0x425` is main-menu
  button 0, NEW GAME** (§3.3).

## 2. Startup (CONFIRMED, `InitInstance` `0x480cf2-0x4818d1`)

1. Switches `-latency -timeout -nomusic -trace -safevideo -cfg -window -startserver -saveonserver -internetserver -640 -800 -1024`; registry (HKLM `SOFTWARE\Rage of Mages 2`)
   `CDSPEED`, `RESOLUTION` (string `-640` / `-800` / `-1024`, default 640x480), `INSTALLDIR`, `CD`.
2. Archives in order `cs main patch world music video sfx movies scenario speech` `.res` (+ `update.lst`); no `video.res` = no videos (`0x5f17e4 := 0`).
3. DirectDraw full screen, **16 bpp** (`0x452978`), mode W x H (`0x453036`); text tables; `famehall.dat`; `scenario.dll`.
4. **Screen geometry** (`0x48205b-0x4821c3`): W x H is 640x480, 800x600 or 1024x768. `0x621420 = (W - 640) / 2`, `0x621424 = (H - 480) / 2`: every shell screen is a **640x480 picture centred on
   a black screen** (the screen is cleared to colour 0 first; `0x456348`). Videos: 640x480 at the same origin, 640x360 at `+0x3c` (letterbox).
5. **Videos** (`0x48fb2a`, `0x4818a0`): `video\logos\publisher.smk`, and only if it ran to the end `video\logos\nival.smk`, then `video\intro\01.smk` (`0x48f919(0)`), then post `0x421` = the main
   menu (posted even when the chain was interrupted). Publisher comes first. The player `0x48fc2e` aborts on a key press or a mouse button (either), `WM_QUIT` / `WM_CLOSE`; the callers treat
   an abort as "stop the chain". The music player is stopped first. Skipped with `-startserver`, `-cfg`, `.asl`.
6. Music: `music\menu.wav` through the `menu` playlist when music is enabled ([audio §4](audio.md)).

**Engine (DECISION, step 2 of the L0 prompt):** videos are placeholders. `Startup` logs `video skipped: video/logos/publisher.smk`, `video skipped: video/logos/nival.smk`,
`video skipped: video/intro/01.smk` and shows the menu at once. The decoder (Smacker, §6) is the `cutscenes` step.

## 3. The original's screens

### 3.1 Main menu (CONFIRMED: class `0x5cec48`, ctor `0x4a71d6`, loader `0x4a7657`, paint `0x4a7b3f`, mouse `0x4a7d0d` / `0x4a813c` / `0x4a81a3`)

Resources (`main\graphics\MainMenu\`, all 24-bit, 640x480 unless stated): `menu_.bmp` the background (a stone tablet with eight carved buttons), `MenuMask.bmp` the hit
mask (never drawn; red channel = value), `button<n>p.bmp` (hover image), `button<n>.bmp` (held image), `text<n>.bmp` (180x80 caption), n = 1..8. Click sound `SFX\ChrGen\Ok.wav` (`0x4a840e`,
`0x4a815f`). `graphics\interface\sprites.16a` is also drawn at (480, 360) on every paint (`0x4a7c85-0x4a7cb5`: slot `+0x18` = `FUN_00427ef0` alpha, args `(x, y, 0, 0, 0)` = frame 0, the sprite's own table, not mirrored). **CONFIRMED: it draws nothing.** The file (1,042 bytes) holds one 160x120 frame whose data is the single word `0x4078` = "skip 120 rows" ([sprites](../formats/sprites.md)), so no pixel is covered; the engine's omission is exact (a leftover slot for a corner decoration at the bottom right, 160x120 ending at (640, 480)).

| n | button | image rect (x, y, w, h) | mask value | message | opens |
|---|---|---|---|---|---|
| 0 | NEW GAME | 204, 52, 104, 96 | `0x80` | `0x425` | the new-game chain (§3.3) |
| 1 | MULTI PLAYER | 124, 156, 108, 76 | `0x90` | `0x426` | network lobby (out of scope) |
| 2 | CUT SCENES | 124, 252, 96, 88 | `0xa0` | `0x43b` | the list of seen videos (`cutscene.txt` titles, mask in registry `Using VxD`); OK plays one and re-opens the list |
| 3 | CREDITS | 208, 340, 100, 100 | `0xb0` | `0x428` | `credits.txt`, music `credit.wav`; on close `0x421` (or `0x429` hall of fame when `FUN_00493da0` is set) |
| 4 | LOAD GAME | 340, 52, 88, 100 | `0xc0` | `0x418` | the save list (600x450 at (100, 30)); OK `0x419` loads |
| 5 | SERVER | 424, 152, 84, 88 | `0xd0` | `0x487` | dedicated-server dialog (out of scope) |
| 6 | HALL OF FAME | 412, 260, 96, 84 | `0xe0` | `0x429` | `famehall\hall.bmp` + the table of `famehall.dat`, OK returns to `0x421` |
| 7 | EXIT | 344, 348, 72, 80 | `0xf0` | `0x10` = WM_CLOSE | no confirmation |

Mask values `0x10..0x1e` (even) are outline pixels and 0 the background: no action. The caption `text<n>.bmp` is drawn at **(232, 200)** (the empty middle tablet) for the index under the
pointer. Behaviour (`0x4a7d0d`, `0x4a813c`, `0x4a81a3`): fields `+0xec` index under the pointer, `+0xf4` index pressed, `+0xf0` highlight = under the pointer unless another button is held,
`+0xf8` disabled bit mask. Hover draws `button<n>p` at the image rect; a held button `button<n>`; a **disabled button gets no highlight and no action** (its caption still shows). The sound plays on the
**mouse press** of an enabled button only (no hover sound); the action runs on the **release over the same button**. The window has no child widgets and no key handling (**INFERRED**, not run): the
key router acts on ESC / F1-F3 / Pause only for `game+0x404` 0 or 1, and with the menu open keys go to the window manager, which has no children to receive them.
Enabled state: LOAD GAME is disabled when no `game*.sav` exists (`0x43ff4a`, mask bit `0x10`, `0x48b66f`); if the CD / registry check fails (`0x62282c`) four buttons are disabled
(mask `0x35`, `0x4872ef-0x4873b5`; the GOG build is expected to pass, INFERRED).

### 3.2 No options entry in the main menu (CONFIRMED)

The eight buttons are all there is. The options windows are reached **in a mission** through the in-game menu (ESC, message `0x416`): Game Options `0x41b`, Sound Options `0x422` ([ui-layout 11.4](ui-layout.md)).
Settings live in the registry, read at start-up (`0x4415d4`, `0x43c978`) and written at exit (`0x440cd2`); the options dialogs only edit memory. See §5.

### 3.3 The screen-state graph of the original (single player)

```
(start) -> videos -> 0x421 MAIN MENU
MAIN MENU -- NEW GAME 0x425 --> PreCreate (+0x374, music chrgen) -- Cancel 0x446 --> 0x421
                                       \-- OK 0x445 --> confirm panel (+0x36c, 0x48f3f0) -- Back 0x446 --> PreCreate
                                                          \-- OK --> hero from the choices (0x49183e), scenario vars 0x308 / 0x30d, difficulty 0x493d80(sel + 1) --> town 0x42e
MAIN MENU -- LOAD 0x418 --> list -- OK --> 0x419 (load, `0x48db37`) / Cancel --> 0x421
MAIN MENU -- CREDITS 0x428 --> 0x421 | 0x429 ;  HALL OF FAME 0x429 --> 0x421 ;  CUT SCENES 0x43b <-> video ;  EXIT 0x10 -> destructor
in a mission: ESC 0x416 menu -> Game Options 0x41b / Sound Options 0x422 / End Quest 0x41c -> Exit to Main Menu 0x41e (end game 0x48f2e5) + 0x421 | Exit to Windows 0x10
```
CONFIRMED in `FUN_004891d8` (cases `+0x374`, `+0x36c`, `+0x13c`, `+0x11c`, `+0x130`, `+0x3c0`). The NEW GAME handler (case `0x425` of `FUN_004852d8`) loads `main\text\town.txt`, sets `+0x5d4 := 1`, the server
kind 2 (`0x48c0e2`) and shows the PreCreate panel with music `chrgen` (`0x48f4e2`).

**PreCreate screen** (ctor `0x43270d`, 0x220 bytes, resource `0x466`, class vtable `0x5cb998`: paint `0x43541e`, message `0x436c1d`, mouse move `0x436d10`, mouse down `0x436d48`, key `0x436cc3`, show `0x4334df` /
reset routine `0x433520-0x43389d`; bitmaps in `graphics.res`, `graphics\interface\chrgen\PreCreate\`). **CONFIRMED rects (ctor `0x432cd5-0x433174`):** levels 48x72 at (8, 0), (296, 0), (580, 0); heroes 64x244 at
(116, 44), (180, 44), (392, 44), (456, 44); Cancel (16, 400); OK (548, 400). Bitmaps: `MainArea.bmp` (640x480 stained-glass hall), the hit mask `Mask.bmp` (24-bit, red channel): `0x14` / `0x28` / `0x3c` = level 0 / 1 / 2
(boxes (9,2)-(51,68), (298,5)-(340,71), (583,4)-(625,70)), `0x50` / `0x64` / `0x78` / `0x8c` = hero 0..3 ((118,59), (183,67), (398,67), (458,59) ...), `0xa0` Cancel, `0xb4` OK, `0xc8` the name plate; `Heroes\h<1..4>on.bmp`
(64x244), `h<n>sel.bmp` / `h1sel2`, `h2sel1`, `h3sel4`, `h4sel3` (268x340), `Levels\level<0..2>{on,l,lon}.bmp` (48x72), `torch1\t1%04d.bmp` / `torch2\t2%04d.bmp` (15 frames each), `cancell.bmp` 64x76, `Okl.bmp` 80x76,
`tablol.bmp` 312x84; music `chrgen`.

- **Acts on the mouse PRESS** (`0x436d48`): a press selects a level or hero, presses Cancel or OK; a move with the button held selects too (`0x434f15`). Flag arrays: heroes `this+0x134`, levels `+0x148`; bit 1 selected, bit 2 hovered
  (`0x434df5-0x434ecd`). Sounds: `SFX\ChrGen\Level1/2/3.wav` per level, `Char.wav` per hero, `Ok.wav` for OK and for Cancel (the loader `0x437690` lists nine sounds; the second `ChrGen\Ok.wav` is the Cancel sound).
- **Heroes (CONFIRMED)**: value 0 **Aldor** = male fighter (`h1`, x 116), 1 **Sagita** = female fighter (`h2`), 2 **Galinel** = female mage (`h3`), 3 **Gildarius** = male mage (`h4`) (pixel match of `h<n>on` against `MainArea.bmp`); table `0x5cdd60`
  `{0, 2, 3, 1}`, `window+0x484 = code << 6`: bit `0x40` = mage, bit `0x80` = female. The show routine selects **hero 0** (`+0x208 := 0`, `0x4335d6-0x4335fb`). Big portrait of the selected hero: `h<n>sel`, or
  `h<n>sel<partner>` while the partner pane is lit (pairs (h1, h2) and (h4, h3)); the small `h<n>on` window highlight draws for a hovered hero. Names (`npcnames.txt` 0x17..0x1a: Aldor, Sagita, Gildarius, Galinel; the exe's
  file order puts Gildarius before Galinel, the engine pairs the names with the hero identities above, INFERRED).
- **Levels**: `+0x20c` 0 / 1 / 2 = Easy / Medium / Hard; paint (`0x43541e`, `0x435650-0x43584c`): state 1 selected -> `level<n>on`, 2 hover -> `level<n>l`, 3 both -> `level<n>lon`, 0 nothing extra. The window's `+0x20c` is never set
  before the first show (the exe's own selector `game+0x598 := 1` = Medium, `0x493b60` at `0x48631b`, is overwritten by the window's level at OK): **INFERRED default highlight level 0 (Easy)**, so an OK without a click starts Easy.
- **Name field** (edit class vtable `0x5cb920`, ctor `0x4320b0`, draw `0x43240a`): single player adds only `+0x1ec`, rect (300, 433)-(464, 449); font4 text at (left, bottom - glyph height), a `|` appended while focused and blinking
  every 500 ms (restarted by a typed key). Text in the widget CString (`+0x60`), committed to `this+0x1fc` (`0x493ca0`). WM_CHAR `0x4323cf`: accepted when the length is **< 10** and the character >= 0x20 (`0x4321e9`; punctuation and
  spaces allowed; `0x474c85` remaps >= 0x80 when the char map is on); Backspace (`0x432397` -> `0x432234`) deletes the last character; no Delete / arrows, the caret stays at the end; each accepted key plays `Letter<n>.wav`
  (`0x437985`, object `+0x1dc + 4 * +0x1e8`; `+0x1e8` is never written, so INFERRED always `SFX\Letter2.wav`). **Enter** (`0x437829`) = OK when the name is non-empty (plays Ok.wav, sends `0x445`), **ESC** (`0x437955`) = Cancel (sends `0x446`);
  **an empty name does nothing**; the mouse OK / Cancel call the same two routines. Initial text "Master Oberic" (`0x5efba8`, 13 characters: the field accepts nothing more until it is shortened). `0x437d90(name)`: true when the name equals one
  of the four hero names or "Unnamed" (`_stricmp`); the show routine resets a default name to `npcnames` 0x14 "Aldor" (`0x433628-0x433650`); clicking another hero replaces the name by that hero's default only while the field holds a
  default name (`0x436ebb-0x4371a0`). Tooltips of the edit widgets: `main.txt` 0x16d "Name:" (id `0x464`), 0x16e "Clan:" (id `0x465`, not shown in single player).
- **Tips** (TipsMode `0x622774` on, the default): a static text widget id `0x467` (`0x4dec24`, args `0xe8, 0x30, 0x280, 0xb8`: INFERRED (l, t, r, b) = (232, 48, 640, 184); the class is the **tips window**, a common-dialog-based window (`0x4dbc50`, vtable `0x5d0568`, builder `0x4deca4`: gold table `0x620d90`, font2 `0x620500`, an OK button that posts `0x45a`) with `town.txt` `#tips8` "Select the class and the sex of your character by clicking on the
  appropriate portrait.", stored in `+0x1f8`, removed by message `0x45a` (posted by the tips window itself) and at close. **Not built** (the engine has no TipsMode option and the tips window's frame and layout `0x4deca4` are not decoded; the same window serves the mission `tips:` messages).
- **Torches**: `torch1` / `torch2` = 15-frame flame animations of 48x72 (opaque BMPs that include the wall behind) on the two braziers, **at (4, 200) and (589, 200)** (CONFIRMED by pixel identity: the pixels that never change over the 15
  frames equal `MainArea.bmp` there, mean error < 0.001; the right brazier is `torch2`); a global frame timer advances them every 67 ms (`GetTickCount - last > 0x43`, `0x61adcc`). The exe starts the torches at random frames (`rand`,
  `0x436222-0x43632d`; the engine uses 0 and 7). **Built.** The same paint function runs a second effect (`0x4361ae-0x43632d`): an animation that idles for 500 + rand % 65 ms (`0x61adc0`), then appears at a random point inside a
  random one of five rects (the three level rects, OK and Cancel: list `+0x80`, built `0x4331d3-0x4332f2`) and plays its frames at 63 ms (`0x61ade4`, `+0x70` / `+0x74`); which bitmap vector it plays is **open** (not built).
- **After OK** (`FUN_004891d8`, case `+0x374`): the name -> `game+0x460`, `game+0x598 := level`, `game+0x484 := code << 6`, `strncpy(client+0x3f6c+0xec, name, 12)`, then **`0x48f3f0` shows the panel `+0x36c`**.
- **Panel `+0x36c` is the real character generator** (class ctor `0x42d39d`, resource `0x456`; children `0x457..0x45a`; not a confirm dialog and not `0x49183e`): `0x457` (`0x428521`) stat +/- buttons (`main\graphics\chrgen\leftup.bmp`,
  `chrgen\buttons\{pl,pnl,ml,mnl}{on,off}.bmp`, `pdisable.bmp`, `mdisable.bmp`; strings `"%s = %d"`, `"%+d"`), `0x458` (`FullStatsL.bmp`), `0x459` (`Inn\button{1,2,3}{on,off}.bmp`, `ButtonsArea.bmp`: the bottom buttons, the third
  = Accept), `0x45a` (`RollStatsR.bmp`, `FullStatsR.bmp`, `Inn\RUOver.bmp`, the class columns `chrgen\fighter\{mask,column}.bmp` + weapon icons sword / axe / mace / pike / bow, or `chrgen\mag\...` fire / water / air / earth / astral,
  skill sounds `SFX\ChrGen\Skill\*.wav`), dice `chrgen\cube\sprites.16a`, `chrgen\loader\LeftUp.bmp`; sounds `SFX\ChrGen\+_-.wav`, `SFX\Click_Ok.wav`, `SFX\Sbros.wav`, `SFX\Back.wav`; hint widget `0x467`: `town.txt` `#tips5`
  (fighter: "This screen allows you to create your own character. If you are playing for the first time, you may skip it by clicking <Accept>. ... an initial skill of 20 for that weapon type") or `#tips6` (mage: five element spheres)
  at (0x118, 0x138). The player re-allocates the attribute budget (`FUN_004f254b`, [ai](ai.md)) and picks the weapon class or sphere; **Accept without changes keeps the starting template**. **Back (`0x446`)** returns to PreCreate
  (`0x48f4e2`, chrgen music restarts). **OK**, single player: `0x40d480` (resets the client / world state), **`0x49183e` = a creation call only, no window** (it waits for the server object, picks the template by `window+0x484`:
  `0x00` `Start_MF`, `0x40` `Start_MM`, `0x80` `Start_FF`, `0xc0` `Start_FM`, creates the unit with `0x5143e4(name, 1, 0)`, copies the four stats from the generator's template `0x4699d2`), then Scenario `SetVar(0x308, is_mage)`,
  `SetVar(0x30d, is_female)`, difficulty `0x493d80(selector + 1)`, post `0x42e` (town). Handed on: name, hero code, level, the stats. The generator's rects, attribute-roll rules and texts are open (L2).
- **Engine (DECISION)**: `engine/shell/newgame.py` builds all of the above that is CONFIRMED; OK starts the first campaign map (`10`) with `difficulty = level + 1`, the hero value and code and the name until L2 builds the
  generator panel and the campaign chain. The hover pictures of Cancel / OK (`cancell`, `okl`) and the portrait placement (x 112 for heroes 0-1, 260 for 2-3, y 44) are INFERRED by template matching.

**Credits and the hall of fame (CONFIRMED `FUN_00493da0`, `0x493da3-0x493db9`):** it returns `Scenario.GetVar(0x300) >= 0x78`, the "campaign finished" test (the chapter counter reaches 120 when mission 110 is completed;
only Scenario.dll writes it, [triggers §11](triggers.md)); users: closing the credits (`0x493da0() == 0` -> `0x421`, else `0x429` the hall of fame) and the ending path of message `0x41d` (`>= 0x78` -> `0x428` credits). So the credits
lead on to the hall of fame only after the campaign has been finished in this session or a loaded save.

## 4. The engine's state machine (`engine/shell/`)

```
startup -> menu
             \-> newgame -> game -> menu          every screen -> quit (the window's close box; the menu's EXIT)
             \-> load -> game | menu              (load is in the graph, its button is disabled)
```
`machine.GRAPH` is the spec: `Shell.go(name)` raises `ShellError` for an edge outside it and runs `exit()` / `enter(**params)` / the screen's music request around every move. A screen is a
`Screen` (UI layer object): `enter`, `exit`, `event(ev)` (a shell input event: `Move`, `Press`, `Release`, `Key`, `Wheel`; positions in screen pixels), `update(dt_ms)`, `scene()` (a list of draw ops:
`Image`, `Text`, `Fill`, `Frame`, `Button`, `Sprite`), `music`; `event` / `update` return the next screen (`"menu"` or `("game", {params})`) or None. Screens never import pygame, the world, the simulation or
the view (`tests/test_engine_boundaries.py`); they reach the outside through `Services` (sound, music, log, `apply_settings`, `save_settings`, `start_game`) that the backend fills.

**World ownership.** Only `GameScreen` has a world: `enter(params)` calls `services.start_game(params)`, the backend builds a `PlaySession` (World, simulation inputs, session files) and returns it; the screen is
`driven`, so the backend loop hands over to `session.run()` (the existing `window.run` with `in_shell=True`: the display and the audio device stay open, the reason is `sim.ui.quit`), which returns `menu` (End Quest ->
Exit to Main Menu, victory, defeat, a crash) or `quit` (Exit to Windows, the window closed). `exit()` drops the session: after it no World exists. Every menu screen runs without one (tested: `World.__init__`
is never called before the game screen).

**Screens (L0).**

| screen | what | music | notes |
|---|---|---|---|
| `startup` | the three video placeholders (§2), then `menu` | - | black |
| `menu` | §3.1, from `MenuMask.bmp`, hover / held / disabled, click on release; no key handling, no options entry (as the original) | `menu` | DECISION: MULTI PLAYER, CUT SCENES, CREDITS, SERVER, HALL OF FAME and LOAD GAME are disabled in the original's own way (no highlight, no action) until their step; only NEW GAME and EXIT act |
| `newgame` | §3.3 PreCreate: heroes (hero 0 selected), levels, the name field, Cancel, OK; acts on the press | `chrgen` | OK (a non-empty name) starts the first campaign map (`10`) with the difficulty (`level + 1`, `ai.md 10.1`); L2 replaces this by the character generator panel and the campaign chain |
| `load` | in the graph, bounces to `menu` | - | the button is disabled until the Save / load step |
| `game` | the in-game screen | the mission's | the loop of J1-J3 |

Sounds: the click of the menu and PreCreate presses is the literal file `sfx/chrgen/ok.wav` (`Director.path_of` accepts a literal game path); the options buttons use the dialog click (sound id 2, [audio 2.4](audio.md)).

## 5. Options

### 5.1 The original's windows (CONFIRMED unless marked)

**Where they open (CONFIRMED `FUN_004852d8`):** message `0x41b` builds Game Options only while `game+0x404 == 1` (a mission, `0x485cc4`); `0x422` builds Sound Options in a mission or, with a running game (`0x6044c4 != 0`), in a town screen (`0x485bf3`); the main menu (`0x80`) has no way to either, and the in-game menu's entries close the menu first (bit 8 clear). Both are common-dialog windows (`FUN_004dc48e`): the size rule of [ui-layout 11.4](ui-layout.md) (`w' = ((w - 8) / 0x60) * 0x60 + 8`, `h' = ((h - 0x68) / 0x40) * 0x40 + 0x68`, centred on the real screen, the 8 px shadow inside), children
relative to the dialog, widgets: label `0x4d4b56`, slider `0x4da54d`, check box `0x44ee70`, radio group `0x44efe0`, text button `0x4d5470`, dialog button `0x4d55cb`, list box `0x4d82f8`.

**Game Options** (message `0x41b`, `0x4417c3(1, 0x14, 0, 0x26c, 0x1e0)` = 600x480 -> **584x424**, builder `FUN_004417fa`, handler `FUN_00442e8b`). Title `dialogs[0x96]` at (0x28, 0x14), centred. Widgets (dialog-relative; `dialogs.txt`
unless `patch`):

| widget | rect (l, t)-(r, b) | text | stores |
|---|---|---|---|
| label + slider | (0x28, 0x38) / (0x28, 0x54)-(0xe8, 0x6c) | `[0x32]` Game Speed | GameSpeed 0..8 (`game+0x41c`; disabled when `+0x5d8 == 0`) |
| check | (0x28, 0x78)-(0xe8, 0x90) | `[0x37]` Day/Night changes | ShowTimeFlow `0x622770` |
| check | (0x28, 0x94) | `[0x35]` Smoothing | `0x622768` |
| check | (0x28, 0xb0) | `patch[0x34]` Shadows | `0x5f17e8` |
| check | (0x28, 0xcc) | `patch[0x35]` Dynamic lighting | `0x5f17f0` |
| check | (0x28, 0xe8) | `patch[0x36]` Object animations | `0x5f17ec` |
| check | (0x118, 0x29)-(0x1f0, 0x41) | `[0x39]` Show Health | ShowAllHitPoints (client `+0xab8`) |
| check | (0x118, 0x45) | `[0x4e]` Display damage points | ShowFlyingHP (client `+0xabc`) |
| check | (0x118, 0x61) | `[0x9c]` Tips (kind 2) | TipsMode `0x622774` |
| check | (0x118, 0x7d) | `[0x57]` "Join" (the registry name is MessageColors) | `0x622818` |
| label + 3 checks | (0x118, 0x9a), (0x118, 0xb0 / 0xcc / 0xe8) | `[0xa6]` AutoCast for units: `[0xa7..0xa9]` Own / Allies / Neutral | bits 1 / 2 / 4 of `0x62277c` |
| 3 radio groups | (0x28, 0x120)-(0xd0, 0x168), (0xd0, ..)-(0x178, ..), (0x178, ..)-(0x220, ..) | Formation Mode `[0x3a]` Off / Auto / On; Retreat Mode `[0x3f]` Never / Low / Medium; AutoCast mode `[0xaa]` Minimum / Average / Maximum | `0x62275c`, `0x622760`, bits `0x10` / `0x20` of `0x62277c` |
| buttons | **CONFIRMED `0x442c7e-0x442d18`**: top = bottom of the last widget (the AutoCast-mode radio, id `0x8d`: `0x168`) + 8 = `0x170`, height `0x18`; OK x `W/7 .. 3W/7`, Cancel `4W/7 .. 6W/7`, W = the dialog width (584: 83..250, 333..500); `0x4d55cb` buttons, font1, ids `0xa` / `0xb` | `[0]` Ok (`0x445`, flag `0x10` = default, `0x442db6`), `[1]` Cancel (`0x446`) | |

**Apply on OK only** (`0x442e8b`): each widget is read (`+0x3c`) into its variable, GameSpeed through `0x48bfaa`; **Animation off forces Lighting off** (`0x442fb7`); AutoCasting is rebuilt as
`8 | 0x10 / 0x20 (mode radio) | 1 / 2 / 4`; then `0x41a617(Formation)`, `0x41a4ef(Retreat)`, `0x41a5b9(AutoCast)` push to the client. **Cancel closes without applying.** **ESC = Cancel (CONFIRMED):** the class vtable `0x5cc200` has `FUN_004dc595` in slot `0x6c` (the same key handler as the pause / failed windows: ESC sends message `0x446` to slot `0x48`) and `FUN_00442e8b` in slot `0x48`. Defaults: Smoothing 1, ShowTimeFlow 1, TipsMode 1,
AutoCasting `0x19`, Shadows / Lighting / Animation 1, GameSpeed 4. The window is opened by `0x48b33b` (modal).

**Sound Options** (message `0x422`, `0x43cacb(1, 100, 0x1e, 0x280, 0x1c2, ...)` = 540x420 -> **488x360** at (76, 60), handler `0x43d8a7`, opens only when a sound device exists): title `[7]`; track list (id 3, `w' - 0x40` wide,
(0x28, 0x50)-(.., 0xaa), `tunes.txt` titles) with a scroll bar; check `[0xa5]` Acknowledgments (0x28, 0xbe); buttons Play `[0xd]` (0x28, 0x100)-(0x8c, 0x118) = message `0x477` (`MusicEnabled := 1`, plays the
selected track), Stop `[0xf]` (0x96, 0x100)-(0xfc, 0x118) = `0x478` (stops, `MusicEnabled := 0`), Return `[8]` (0x28, 0x122)-(0xfc, 0x13a) = `0x476`; right column x 0x102 .. `w' - 0x28`: label `[0x10]` Music volume (y 0xaf) +
slider id 6 (y 0xbe..0xd6), `[0x11]` SFX volume (0xe0) + slider 7 (0xf0..0x108), `[0x12]` Speech volume (0x113) + slider 8 (0x122..0x13a). The "Random Order" widget `[9]` is handled but never built.
**Sliders act live** (message `0x46e`: id 6 sets the music volume, 7 `0x622698`, 8 `0x6226a0`) and **Cancel does not revert them** (there is no Cancel button); releasing a slider sends `0x474`: id 7 selects `sfx[100]` (`0x420eb0(100)`) and plays it at the SFX volume (`0x45aa2f`, priority `0xdc`), id 8 plays **whatever sample is current** at the speech volume without selecting one
(CONFIRMED `0x43d8a4`; so after an SFX test it is the same sword sample, INFERRED; the engine plays nothing for the speech release). **ESC** (slot `0x6c` `FUN_004dc595`, vtable `0x5cbcb0`, handler `0x43d8a4`) falls to the default `FUN_004dc2b0(0x446)` = close; the Return button (`0x476`) first stores the Acknowledgments check and then closes with `0x445`; Play (`0x477`) sets `MusicEnabled`, plays the selected track and Stop (`0x478`) stops (fade 2000 / 8000 on device kind 1). Slider position -> mB: `mB = trunc(-R * ((pos - R) / R)^2)` (`0x45b3a3`), inverse `pos = trunc(R - R * sqrt(-mB / R))` (`0x45b36e`); the engine keeps the K11
percent scale ([audio §6](audio.md)).

**Game speed** (`0x48bfaa`, jump table `0x48c0be`): 0..8, default 4; ticks per second `{8, 10, 12, 14, 16, 20, 24, 28, 32}`, period `1000 / rate` integer ms `{125, 100, 83, 71, 62, 50, 41, 35, 31}` (the table of
[simulation](simulation.md) section 2); the change re-bases the tick clock.

**Look and behaviour (CONFIRMED: slider `0x4da80f` draw, `0x4da324` thumb rect, `0x4da4a1` x -> value, `0x4dade4` mouse down, vtable `0x5d00e8`; check group `0x4d757c`).**
- **Slider** (`graphics\interface\scrlbars.256`, 26 frames of 24x24; horizontal when the rect is wider than high): the left end **frame 0** (pressed **3**) at the rect's left, the rail **frame 7** tiled every 24 px from the second tile to
  `width / 24 - 1`, the right end **frame 8** (pressed **11**) at `right - 24`, the thumb **frame 10** (the eye) last; each frame is preceded by its own darkened silhouette at (+4, +4) (the thumb at (+5, +4), drawn 1 px right of its
  rect), darken level **4** (`dst * 12 / 16`). The vertical bar uses frames `0x12` / `0x15` (top, pressed), `0x13` (rail), `0x14` / `0x17` (bottom, pressed), `0x16` (thumb). Thumb rect: left `= l - 4 + 24 + usable * value / max`,
  16 wide, `usable = width - (2 * 24 - 8) - 12 = width - 52` (`max == 0`: `l - 4 + 24`). **Press** (`0x4dade4`): left of the thumb `value -= max(1, max >> 4)` (clamped at 0), right of it `+=` (clamped at `max`), on the thumb the drag starts and
  the value follows the pointer by `0x4da4a1`: `value = clamp(max * (x - (l + 2 + 24)) / usable)` (truncated toward zero); every change posts `0x46e` (id, value); the pressed end frame shows while the side region is held. The end frames are not buttons of their own.
- **Check box** (`radiob.256`: frame **2** off / **3** on, 24x24; frames 0 / 1 are the radio button, 4 / 5 the 16x16 variants): darkened silhouette (level 4) at (left + 5, row + 4), the frame at (left + 1, row); the caption at
  (left + 6 + 24, row + 5) in font1, shadow 1, **gold table `0x620d90` while the widget has the focus bit 4** (the pointer-over rule of the buttons), else the normal table `0x620928`.
- **Disabled look (CONFIRMED, every widget of the family)**: when the flag bit 1 is clear the rect expanded by 1 px is darkened by `FUN_004564df(rect, level 3)` (`dst * 13 / 16`), the same as the dialog buttons; no other change.
- Check boxes, radios and sliders play **no sound**; the text buttons do (`0x4d5c86`, priority `0xdc`; which of the sound indices 1 / 2 / 4 each mouse event uses is open: the engine plays the dialog click, id 2, on the press).

### 5.2 Registry names (CONFIRMED `0x441372` writer, `0x4415d4` reader; HKLM `SOFTWARE\Rage of Mages 2`, DWORDs, written at exit `0x440cd2`)

GameSpeed, FormationMode, WimpyMode, ShowAllHitPoints, Smoothing, ShowFlyingHP, ShowTimeFlow, TipsMode, AutoCasting, Acknowledgement, Shadows, Lighting, Animation, ClanNames, MessageColors; sound:
SoundMusPos, SoundSfxPos, SoundSpeechPos, MusicEnabled, SoundRandom ([sound §5](../formats/sound.md)); video: `RESOLUTION` (string); videos seen: `Using VxD` (a bit per cut-scene code, forced >= 1).

### 5.3 The engine's options (DECISION: the file, the subset, the reach)

The settings file is the K11 file (`~/.config/allods2-engine/settings.json`, `$ALLODS2_SETTINGS`; [audio §6](audio.md)), now with the options the engine applies. The windows open **from the in-game menu** (ESC ->
Game Options / Sound Options, enabled since L0; `GameUi.options_request`, then `window.run` runs `backend_pygame/optionsview.run_options` as a modal sub-loop over the frozen frame; one-to-one with the exe, so the shell has no
options screen and no key for them). `engine/shell/options.py` `OptionsPages` is the component: the original's rects for the widgets built; frames 584x360 (the original's 584x424 holds more widgets) and 488x360.
Game Options OK also takes effect in the running game at once (draw options, day / night, a changed speed re-bases the tick clock `0x48bfaa`); the sound sliders are live.

| field | widget | reaches |
|---|---|---|
| `game_speed` 0..8 (4) | Game Speed slider | `window.run(speed=)` (`play` / shell games; `--speed N` overrides for a run) |
| `day_night` (on) | Day/Night changes | `TerrainView.set_time_flow` at the start of a `PlaySession` |
| `smoothing`, `shadows`, `animation`, `lighting`, `show_health`, `flying_damage` | the checks | `DrawOptions` (`engine.__main__.game_options`; Animation off forces Lighting off, as `0x442fb7`) |
| `sfx`, `music`, `speech` 0..100 | the three sliders, **live**, the file is written when the page is left; the SFX release plays `sfx[100]` | the buses (`Audio.apply_settings`) |
| `music_enabled` | Play / Stop | `Audio.set_music_enabled`; Play restarts the menu playlist |

Game Options **apply on OK** (the draft is a copy; Cancel, ESC and leaving discard it), OK saves the file. Not built (`options.NOT_BUILT`): Tips, the AutoCast / formation / retreat groups and the "Join" check (they need the in-game party options, `ai §12.8` /
`simulation 8.3a`, wired to the file), the track list and Acknowledgments check, the in-game menu's Save, Load and Quest Objectives entries (they stay disabled, [ui-layout 11.9](ui-layout.md)). A game started from the shell reads the file at its start; a change
made later affects the next game.

## 6. Videos (CONFIRMED: headers read from `video.res`; `movies.res` holds only shop / inn bitmap animations)

All eight files are **Smacker 2** (`SMK2`, standard, played with `smackw32.dll`): flags 0 (no ring frame, no Y-interlace), frame time -6666 = 66.66 ms = **15 fps**, **one audio track, 22,050 Hz, 16-bit stereo,
compressed** (6,272 bytes of decoded audio per frame, 94,080 uncompressed bytes in the header's size field).

| file | size | frames | length | fades (`.reg`) |
|---|---|---|---|---|
| `video\logos\publisher.smk` | 640x480 | 368 | 24.5 s | none |
| `video\logos\nival.smk` | 640x480 | 165 | 11.0 s | Fading1 frames 159-164 1.0 -> 0.0 |
| `video\intro\01.smk` | 640x360 | 773 | 51.5 s | in 0-5 (0.0 -> 1.0), out 767-772 |
| `video\teleport\01.smk` | 640x360 | 167 | 11.1 s | in 0-5, out 161-166 |
| `video\stars\01.smk` | 640x360 | 186 | 12.4 s | in 0-5, out 180-185 |
| `video\crown\01.smk` | 640x360 | 234 | 15.6 s | in 0-5, out 228-233 |
| `video\knights\01.smk` | 640x360 | 542 | 36.1 s | none |
| `video\druids\01.smk` | 640x360 | 542 | 36.1 s | in 0-5, out 536-541 |

The `.reg` next to each file (`Common/startx`, `starty` = 0, `nFadings`, `Fading<n>/startframe, endframe, startfade, endfade` floats; the reader knows `nPanaramings` / `Panaraming<n>` too, none installed) is parsed by
`0x4c4147-0x4c4467`; the fade engine is **CONFIRMED** (per-frame step `0x4c399a`, order at `0x4c39d1-0x4c3a5a`): after `SmackWait` succeeds, `0x4c4561` starts a record when its `startframe` equals the current frame (`smk+0x374`): `0x4c4840(len = endframe - startframe, startfade, endfade)` stores `fade = startfade` (`+0x33c`), `step = (endfade - startfade) / len` (float32, `+0x340`), the remaining frame count `len` (`+0x344`) and the active flag (`+0x34`); then `0x4c38d1` runs on the same frame: **`fade += step`, every byte of the 768-byte Smacker palette (`smk+0x6c`, 256 x RGB) -> `trunc(byte * fade)`** into a copy at `+0x38`, `len` -= 1, and at 0 the fade deactivates (`0x4c4890`); while active the copy is set with `SmackBlitSetPalette` (`0x6cf0f4`), otherwise the raw palette is set only when the Smacker palette changed (`smk+0x68`). So a fade-in record (0 -> 1, start 0, end 5) shows factors 0.2, 0.4, 0.6, 0.8, 1.0 on frames 0-4; a fade-out (1 -> 0, start 161, end 166) 0.8, 0.6, 0.4, 0.2, 0.0 on frames 161-165, and the last frame (166) keeps that black palette (nothing re-sets it); the 8-bit pixels are untouched, only the palette is scaled (a decoder does the same on the palette it passes to the blit). The panning records (`0x4c4618`) set the scroll steps `+0x360` / `+0x364`; none is installed. API: `SmackOpen(buffer,
0xff000, -1)` on the in-memory file (`0x4c3bee`; INFERRED from RAD's `smack.h` constants, not from the packed `smackw32.dll`: `0xff000` = the audio-track bits (all tracks, none of the pan / volume / preload / no-skip flags) and `-1` = `SMACKAUTOEXTRA`, the extra buffer allocated by the library; neither changes what is decoded, the files have one audio track), `SmackUseMMX`, `SmackSoundUseDirectSound`, per frame `SmackWait` / `SmackDoFrame` / `SmackBlit`; the surface must be 565 or 555 (else "Unsupported pixel format").
Chapter videos: `0x48f919(code)` plays `video\<cutpaths.txt line code>\NN.smk` for NN = 1, 2, ... while the file exists (only `01` is installed) and sets bit `code` of the seen mask; codes 0 intro, 1 teleport, 2 stars,
3 crown, 4 knights, 5 druids. Triggers: start-up (0), mission victory (`0x486cc8`, `ScenarioLeaveLocation`: after missions 10 -> 1, 30 -> 2, 70 / 80 -> 3, 110 -> 4 or 5, [triggers §11](triggers.md)), world-map entry (`0x487daf`), the
Cut Scenes list (`0x48a7fb`). **Not decoded in L0**: the engine only logs `video skipped: <name>`.

## 7. Tests

`test_engine_shell.py`: the graph (every legal edge works, every other raises, the close box quits from every screen), the main menu (mask -> button, hover / held / disabled drawing, sound on the press, action on the
release over the same button, a release elsewhere does nothing, centring at 800x600), a scripted run menu -> new game -> cancel -> options -> back -> exit that follows the graph, new game needing a hero, **no `World`
before the game screen** (`World.__init__` counted) and the game screen dropping it on exit, the golden screenshots per screen (`golden.json["shell"]`: startup, menu idle / hover / held / disabled / exit, new game idle /
hero hover / chosen / OK hover, the options pages game / hover / sound over black, the menu at 800x600). `test_engine_shell_options.py` (`OptionsPages` driven by events): frame sizes, OK / Cancel / ESC / Enter, Animation forcing Lighting, the slider range, live sound sliders, the SFX test
sound, Play / Stop, **persistence across a restart** through the real file, the options reaching `DrawOptions`, checked vs unchecked boxes. `test_engine_shell_loop.py`: the real pygame loop headless with scripted events
through a real mission (ESC -> Game Options OK, Sound Options Stop, End Quest) and back (display, fonts and loop survive the hand-over; the session files are written). The game screen's own goldens are `golden.json["interface"]` and `["ui"]`.

## Open questions

- PreCreate: the initial level highlight (INFERRED Easy), the second animation of the paint function (random point over the five widget rects, bitmap vector unknown), the hover cross-fade `0x4364f7`, the tips window layout (`0x4deca4`), the order of the hero vectors against the screen order; the character generator panel's child rects, attribute-roll rules and labels (L2), what `0x40d480` resets.
- The `SmackOpen` flag word `0xff000` is INFERRED (RAD's header from memory; `smackw32.dll` is packed).
- Game Options / Sound Options: the sound index of each text-button event (the slider and check-box looks, the OK / Cancel rects and ESC are answered).
- Whether the GOG build passes the CD check `0x62282c` (the menu would then have four disabled buttons), and the keyboard behaviour of the menu (INFERRED from the absent key handling, never run).
