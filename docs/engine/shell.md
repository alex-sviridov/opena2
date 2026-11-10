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
`0x4a815f`). `graphics\interface\sprites.16a` is also drawn at (480, 360) on every paint: **which sprite is open** (the engine does not draw it).

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

**PreCreate screen** (ctor `0x43270d`, 0x220 bytes, resource `0x466`; bitmaps in `graphics.res`, `graphics\interface\chrgen\PreCreate\`): `MainArea.bmp` (640x480 stained-glass hall) and the hit mask `Mask.bmp`
(24-bit, red channel): `0x14` / `0x28` / `0x3c` = difficulty 0 / 1 / 2 (Easy / Medium / Hard, written to `+0x20c`), `0x50` / `0x64` / `0x78` / `0x8c` = the four heroes, `0xa0` Cancel, `0xb4` OK, `0xc8` the name
plate; bitmaps `Heroes\h<1..4>on.bmp` (64x244 hover), `h<n>sel.bmp` / `h1sel2`, `h2sel1`, `h3sel4`, `h4sel3` (268x340 chosen portrait), `Levels\level<0..2>{on,l,lon}.bmp` (48x72, torch animations
`torch1`, `torch2`, 15 frames), `cancell.bmp` 64x76, `Okl.bmp` 80x76, `tablol.bmp` 312x84; default name `Master Oberic` (`0x5efba8`); sound `SFX\ChrGen\Ok.wav`. **INFERRED** by template matching the bitmaps
against `MainArea.bmp` (best-match error < 3 for the levels; the placement of the others by position): Cancel (16, 400), OK (548, 400), name plate (172, 396), levels at x 8 / 296 / 580, y 0, heroes at x 116 / 180 / 392 /
456, y 44, chosen portraits at x 112 (heroes 1-2) / 260 (heroes 3-4), y 44; suffix meaning (`on` = the idle picture, `l` = hover, `lon` = chosen) is INFERRED from those matches.
Not decoded: the name field's rect and edit rules, the caption lines, which hero is which, the confirm panel, the character screen `FUN_0049183e`.

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
| `newgame` | §3.3 PreCreate: heroes, difficulty, Cancel, OK (needs a hero) | `chrgen` | OK starts the first campaign map (`10`) with the difficulty (`selector + 1`, `ai.md 10.1`); L2 replaces this by the confirm panel, the character screen and the campaign chain |
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

**Look** (CONFIRMED sheets, INFERRED frames): `graphics\interface\scrlbars.256` (26 sprites, 24x24) for sliders and scroll bars, `radiob.256` (frames 0 / 1 radio off / on, **2 / 3 check box off / on**, 4 / 5 are 16x16)
drawn at (l + 1, t) with a darkened copy at (+5, +4) first (`0x4d757c`, `0x4d7e04`), caption to the right in font1. Check boxes, radios and sliders play **no sound**; the text buttons do (`0x4d5c86`, priority `0xdc`).
The engine draws a slider as the rail (frame 7, tiled) with the ball (frame 16) as the thumb: the exact frame map is **open**.

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
`0x4c4147-0x4c4467`; the fade engine `0x4c4561`, `0x4c4618`, `0x4c4840` ramps the brightness over the record's frames (**INFERRED** a linear ramp against black; the routine's body is not read). API: `SmackOpen(buffer,
0xff000, -1)` on the in-memory file (`0x4c3bee`; the flag word's meaning is open), `SmackUseMMX`, `SmackSoundUseDirectSound`, per frame `SmackWait` / `SmackDoFrame` / `SmackBlit`; the surface must be 565 or 555 (else "Unsupported pixel format").
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

- The main menu's decoration: which sprite of `graphics\interface\sprites.16a` is drawn at (480, 360) on every paint (`0x4a7b3f`).
- PreCreate: the name field's rect and edit rules, the caption lines (`main.txt`), the hero identities behind the four windows, the confirm panel `0x48f3f0`, `FUN_00493da0` (the flag that sends the credits on to the hall of fame).
- Fade routine `0x4c4840` (the maths) and the `SmackOpen` flag word `0xff000`.
- Game Options / Sound Options: the disabled look of widgets, the frame map of `scrlbars.256`, the sound index of each text-button event. (OK / Cancel rects and ESC answered.)
- Whether the GOG build passes the CD check `0x62282c` (the menu would then have four disabled buttons), and the keyboard behaviour of the menu (INFERRED from the absent key handling, never run).
