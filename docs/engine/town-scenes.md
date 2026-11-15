# Town mode: the three town scenes (L6 research)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)). Marks: **CONFIRMED** (routine address given) / **INFERRED**. Part of the L3 town spec ([town.md](town.md)); the open / leave messages are [town-hero 1](town-hero.md#1-purpose-and-entry--exit), the older art notes [animation 4.11](../formats/animation.md#411-town-scenes-townbirds-town_druid) (corrected here where they differ). Single player only. Assets are read from the install at run time, never copied; all offsets / names below are ours, routines and numbers are the exe's.

## 1. Class structure (CONFIRMED)

| | human (town 1) | druid (town 3) | Kaarg (town 2) |
|---|---|---|---|
| ctor / vtable | `0x4ca23c` / `0x5cfac8` | `0x4ce2b9` / `0x5cfb78` (calls the human ctor first) | `0x4d09ee` / `0x5cfc28` (calls the human ctor first) |
| loader (`+0xa0`) | `0x4cb6c6` | `0x4ce914` | `0x4d101a` |
| load / open (`+0x80`) | `0x4ca7e2` | `0x4ce641` | `0x4d0d46` |
| draw (`+0x2c`) | `0x4cb05d` | `0x4cf65a` | `0x4d1f6d` |
| **hit test** (`+0x94`) | `0x4cd8b7` | **same `0x4cd8b7`** | **same `0x4cd8b7`** |
| hover (`+0x98`) | `0x4cdbea` | `0x4cfd58` | `0x4d244e` |
| random starters (`+0x9c`) | `0x4cda92` | `0x4d00de` | `0x4d26a4` |
| tick (`+0xa8`) | `0x4cd606` | `0x4d065b` | `0x4d2f27` |
| sounds init (`+0x88`) | `0x4cdee4` | `0x4cf2c0` | `0x4d1c83` |
| entry loop sound (`+0x90`) | `0x4cdeca` (Crowd) | `0x4cf2a4` (Dforest1) | none; `0x4d0d46` plays Kvox1 itself |
| **mouse press** (`+0x54`) | `0x4cace7` | `0x4d06cc` | `0x4d2fa3` (region 8 branch at `0x4d3058`) |
| mouse move (`+0x4c`) | `0x4cacc2` (calls hover) | inherited | inherited |
| key (`+0x6c`) | `0x4cac8c`: Enter / ESC swallowed (return 1), rest to base | inherited | inherited |

- **Mouse**: only **left button press** (`0x201`, slot `+0x54`) acts; release (`+0x58`), double click, right button are default no-ops (vtable `0x5cfac8`, slots `+0x58`..`+0x64` = `0x437f10`..`0x437f40`). The action is on the **press**, not the release. The click on **shop, inn and the human leave gate** (regions 1, 2, 8 with `Var(0x301) != 0`; druid / Kaarg regions 1, 2, 8: three `call [vtable+0xac]` sites in each of `0x4cace7`, `0x4d06cc`, `0x4d2fa3`) first calls slot `+0xac` (`0x4cdda4` = `vtable+0x48(0x445, 0, 0)`: the scene's message handler `0x4cab95` hands `0x445` to the dialog base `0x4dc2b0`, which acts when the field **`+0x5c` is set**: **CONFIRMED `+0x5c` = "open" flag, ctor `0x4dbc50` clears it, `0x4dc232` (called by every scene's load `0x4ca7e2` / `0x4ce641` / `0x4d0d46`, after the loader, sounds init and entry loop) sets it to 1 and shows / enables the window, `0x4dc26d` clears it; so it is 1 while the scene is open** -> it calls the **close hook** (vtable `+0x84` = `0x4caaed`, the same for all three scenes, section 6) and **posts `0x44c`** ("child window closed", `PostMessageA` to the client): the client removes the window from the root and writes no mode bit ([town-hero 1](town-hero.md#1-purpose-and-entry--exit)). The menu click (`0x10`), the NPC speech clicks and the `plagatguard` refusal do **not** call `+0xac`: the scene stays open). **CONFIRMED: no sound is *started* anywhere in the chain, the click plays nothing** (it does stop every slot: section 6) (the old "play click stub" reading was wrong). Slots: `+0x4c` = `WM_MOUSEMOVE`, `+0x54` = `WM_LBUTTONDOWN` ([click-to-move 1](click-to-move-research.md)).
- **Step period**: the draw (`+0x2c`) is called every frame; once the wall clock (`timeGetTime`) passed **67 ms (`> 0x43`) human** / **100 ms druid and Kaarg** since the last step it runs `hover(cursor)`, then (human only) the two random rolls, then `tick`, then stamps the clock. The starters (`+0x9c`) run **every draw**. The clocks `0x62822c / 0x628238 / 0x628248` and the "first delay" globals below are **process globals**: they survive visits.
- **No tooltips, no captions, no text ids** in hover / draw / click of any scene (CONFIRMED by reading all three). The hover handler touches the cursor only for "nothing under the pointer" (`FUN_004739b0(DAT_00626cb8)`, INFERRED: back to the default arrow); a pointer over a region keeps the current cursor. Speech lines come only from the click handlers (section 3).
- Window origin: all draws are `origin + (dx, dy)` with `origin = (this[2], this[3])` (the centred 640x480 rect, as the other town windows); the mask test **subtracts the window origin** (`0x4cd915` calls `FUN_00437af0(&x, origin)` on the point; INFERRED subtraction) and indexes `mask[y * 640 + x]` (`shl 9 + shl 7`), so the hit regions follow the picture at 800x600 / 1024x768. The point must be inside the window rect (`FUN_0041e3d0`) else the result is -1.

## 2. Mask byte -> region (CONFIRMED, `0x4cd8b7`)

`townmask.bmp` is 8-bit 640x480 (the 8-bit class flips: top row first in memory, [bitmaps](../formats/bitmaps.md)). The reader maps the byte under the pointer (offset `byte - 0x20`, table `0x4cd9f1`, jump table `0x4cd9c9`):

| byte | region flag | other byte values -> `-1` (nothing) |
|---|---|---|
| `0x80` | `2` inn | |
| `0x90` | `1` shop | |
| `0xa0` | `8` leave | |
| `0xb0` | `0x10` | |
| `0xc0` | `4` | |
| `0x20` | `0x400` | |
| `0x40` | `0x800` | |
| `0x50` | `0x1000` | |
| `0x60` | `0x200` | |

The human mask has **dither noise** (single pixels of every value 0x01..0xc0 scattered over the area, 1-40 px per value; only `0x80 0x90 0xa0 0xb0 0xc0` have a real region, 5k-15k px); the reader returns whatever the pixel says, so a noise pixel of `0x20 / 0x40 / 0x50 / 0x60` yields a spurious `0x400 / 0x800 / 0x1000 / 0x200` (harmless: no handler; a faithful port keeps the quirk or snaps noise to 0). Dense-region boxes of the install's masks (measured on the files, top-down pixels, x0..x1 / y0..y1; CONFIRMED by data):

| town | byte | region | box | what is there (INFERRED by the art positions) |
|---|---|---|---|---|
| human | `0x80` | 2 inn | 128..212 / 326..411 | tavern building (Tavern_l + tavern sprite) |
| human | `0x90` | 1 shop | 255..333 / 262..346 | shop (Shop_l, shopie sprite) |
| human | `0xa0` | 8 leave | 157..244 / 93..219 | town gate (door frames, guards) |
| human | `0xb0` | 0x10 | 343..405 / 290..418 | stars patch |
| human | `0xc0` | 4 | 419..582 / 300..424 | trainer / school (Trener_l, loaded but never drawn) |
| druid | `0x80` | 2 inn | 121..167 / 190..272 | tavern door (hili_tavern, woman) |
| druid | `0x90` | 1 shop | 376..568 / 224..393 | shop (hili_shop, man) |
| druid | `0xa0` | 8 leave | 1..172 / 294..372 | way out, bottom left |
| druid | `0x60` | 0x200 | 167..199 / 203..268 | innkeeper figure |
| druid | `0x50` | 0x1000 | 339..388 / 254..366 | shopkeeper figure |
| Kaarg | `0x80` | 2 inn | 489..602 / 217..434 | inn (hili_tavern) |
| Kaarg | `0x90` | 1 shop | 324..369 / 255..340 | shop (hili_shop) |
| Kaarg | `0xa0` | 8 leave | 158..213 / 252..338 | main gates |
| Kaarg | `0xb0` | 0x10 | 1..148 / 5..452 | whole left strip |
| Kaarg | `0xc0` | 4 | 262..297 / 286..387 | girl 2 |
| Kaarg | `0x60` | 0x200 | 220..248 / 284..386 | girl 1 |
| Kaarg | `0x40` | 0x800 | 136..246 / 174..221 | guard |
| Kaarg | `0x20` | 0x400 | 420..518 / 335..477 | dervish / man |

### 2.1 Click table (press, left button; CONFIRMED)

| region | human `0x4cace7` | druid `0x4d06cc` | Kaarg `0x4d2fa3` |
|---|---|---|---|
| 1 shop | click sound stub, post `0x42a` | same | same |
| 2 inn | click sound stub, post `0x42b` | same | same |
| 8 leave | `Var(0x301) == 0`: speech **`plagatguard`** (`FUN_0041d15e`), nothing else; else post `0x442` (wParam 1) then `0x42d` | post `0x442` (wParam 1) + `0x42d`, **no `Var` test** | same as druid |
| `0x10` | post `0x41f` (**CONFIRMED** `FUN_004852d8` case `0x41f`: the scene menu window, section 2.2) | same | same |
| 4 | none (the human trainer is not clickable) | none | speech `kaargwoman%d` (`Var(0x300)`) |
| `0x200` | none | speech `druidinnkeeper%d` (`Var(0x300)`) | speech `kaargwoman%d` |
| `0x400` | none | none | speech `kaargman%d` |
| `0x800` | none | none | speech `kaargguard%d` |
| `0x1000` | none | speech `druidshopkeeper%d` (`Var(0x300)`) | none |

`%d` = `Var(0x300)` read through `DAT_0062729c` (the chapter, [triggers](triggers.md)), formatted into **`<name><chapter>`, no underscore** (format strings `0x5f7148`, `0x5f715c`, `0x5f752c`, `0x5f753c`, `0x5f754c`, `0x5f755c`; the old `_%d` was our misreading). **CONFIRMED (`FUN_0041d15e`, `FUN_004dc84c`)**: the click opens the **story window** ([ui-layout 11.5](ui-layout.md#115-on-screen-messages)) on the `town.txt` section `#<key>` (`kaargwoman30`, `druidinnkeeper100`, `plagatguard`, ...; sections exist for chapters 30..110 step 10, the druid ones for 60..110) and `FUN_004dc84c` voices each page: keys containing `keeper`, `man` or `guard` take the **town branch**, file `speech\town\%04d%c%sp%02d.wav` with `npc` = the page tag's `npc=`, the letter `t` (or the hero class `f / m / a / s` when the tag has an `iam*` condition or npc is 21), the code = the digits at the end of the key zero-padded to 3 (`plagatguard` has none: `000`), the page = `part`. Over the install: the 95 files of `speech/town` are **exactly** the names the rule gives for the keys above (chapters 30..110, the four hero classes, pages 1..4) and none of its names is missing (`tests/test_engine_townscene.py::test_install_every_town_voice_file...`). Section lookup is the substring search of `FUN_004dd05b`: a chapter value of 10 finds `#kaargwoman100` (voice `...010...` does not exist: silent), 20 / 120 find nothing. Built: the shell voices **page 1** (`Shell.speak_town`, `townscene.town_voice`) on the speech bus (`Services.speech`, `Director.speech`, priority `0x80`); the window and its text, and pages 2.. (Ok), are not built (DECISION).

#### 2.2 Message `0x41f`: the scene menu (CONFIRMED)

`FUN_004852d8` case `0x41f` builds `FUN_004407c2(1, 100, 100, 0x1b8, 0x154)` (440x340, snapped 392x296, modal) with five text buttons (texts `dialogs.txt` lines in `FUN_00474733`): **Save Game** (`0x22`, message `0x41a`, the save list `FUN_0043ebf6`), **Load Game** (`0x23`, `0x418`, `FUN_0043deaf`), **Sound Options** (`0x25`, `0x422`), **Abort Game** (`0x4d`, `0x41c`: with `game+0x404 == 0` the second window `FUN_00440a22`: **Exit to Main Menu** `0x2c` = `0x41e` (`FUN_0048f2e5` ends the game, then `0x421`), **Exit to Windows** `0x2d` = `0x10`, **Return to Game** `0x28` = `0x446`), **Return to Game** (`0x28`, `0x446`). It is the single-player counterpart of the mission menu `0x416` (`FUN_004400d7`: Save, Load, Game Options, Sound Options, Quest Objectives, End Quest, Return). ESC reaches it from the scene (**CONFIRMED** `FUN_00484a76` case `0x1b`: `game+0x404 == 0` (the screen mask is 0 in a scene, the inn / shop windows set their bit, [town 2](town.md)), `game+0x5d8 == 2` (single player, set by `FUN_0048c0e2` / `0x48db37`) and the CString `game+0x3d4` empty, `FUN_0043a170` = `CString::IsEmpty`; shell.md 3.5 had the test inverted). **`game+0x3d4` is never written**: a byte search of the whole image for the displacement `0x3d4` finds only the constructor (`0x481efc` at `0x482370`, default CString = empty), four `IsEmpty` tests (`0x484bc9` ESC, `0x487490` and `0x488226` in `FUN_004852d8`, `0x489c81` in `FUN_004891d8`) and one `LPCSTR` read (`0x48e9e0`, `FUN_004018a0` = `return *this`, the multiplayer start); the absolute address `0x627544` (game object `0x627170` + `0x3d4`, constructed at `0x480c8d`) is referenced nowhere. So in a single-player campaign the string is always empty and **ESC in a scene opens the menu `0x41f`**. The scene's own key handler `0x4cac8c` swallows Enter / ESC but is not in the way: the game handler runs first (a window-map entry `0x5cde1c`) and only *forwards* keys to the front window (`[game+0xcc]` vtable `+0x48(0x100, key, 0)` -> dialog `FUN_004d4769` -> slot `+0x6c`) for Enter / letters / ..., ESC only when the string is non-empty (never). The base key slot `0x4dc326` only handles Tab and the arrows. Built: `engine/shell/town.py` `SceneMenu` over the scene (Save / Load disabled: not built, DECISION; Sound Options = the shell's `OptionsPages`; Abort Game -> Exit to Main Menu = the shell's `menu`, Exit to Windows = `quit`).

Enter does nothing in the scene (swallowed by `0x4cac8c`); ESC opens the menu (above).

## 3. Hover, highlight and animation flags

The hover (called by the move message and every step) stores the region in `+0xb4` (`[0x2d]`), sets the guard direction `+0xec = 1`, then acts per region. The flag word is `+0x208` (`[0x82]`); a region value `>= 0x10` (and the default case) is OR-ed into it, so **a region flag and the animation flag of the same bit are one thing**.

### 3.1 Human hover (`0x4cdbea`; jump table `0x4cdd86`, index bytes `0x4cdd9a`: -1 / 1 / 4 / 8 / default)

| region | effect |
|---|---|
| -1 | cursor reset; `+0xb0 = 0`, `+0xac = 0` (re-arms the shop sound) |
| 1 shop | each step **4 %** (`rand % 100 > 0x5f`) sets flag `1` (shopie) if clear; on **entering** (`+0xac == 0`): stop `+0x98` (SFX\Town\School\Point.wav), play **`+0x94` (SFX\Town\Shop\enter.wav)**; draw `Shop_l.bmp` |
| 2 inn | flag `2` OR-ed **every step** (tavern anim loops while hovered); draw `Tavern_l.bmp` |
| 4 | **nothing** (no flag, no draw, no sound); resets nothing |
| 8 leave | `+0xec = (Var(0x301) == 0 ? -1 : 1)`; the gate / guards react (3.2); no flag |
| `0x10` | flag `0x10` (stars) |
| `0x200 0x400 0x800 0x1000` | OR-ed into the flags (only `0x200` baba / `0x400` dervish have a tick handler: `0x400` is already on; hovering a baba restarts nothing, the baba only needs the flag to be set) |

### 3.2 Human animations (tick `0x4cd606`, order: flag 1, flag 2, gate, flag 0x10, 0x40, 0x20, 0x80, 0x400, 0x200, 0x100, guards)

All steps advance **one frame per step (67 ms)**. `n` = frame count of the file set (measured on the install). Positions are `origin + (dx, dy)`; "BMP patch" = 24-bit `.bmp` drawn opaque (vtable `+0x18` of the 64k class, [bitmaps](../formats/bitmaps.md)); "sprite" = `.16a`, alpha sprite `+0x18` with the frame number.

| anim | trigger | assets (`graphics\interface\`) | frames | step rule | draw pos | sound (slot) |
|---|---|---|---|---|---|---|
| tavern door | region 2 hover (flag 2, `0x4ccfbf`) | `townbirds\tavern\sprites.16a` (64x96) | 10 (0..9; load forces frame 0 = idle) | `+0x168` ++ per step; at `n` -> 0 and clear flag (re-set while hovered); sound at frame 0 | (+0x7c, +0x138), always drawn (frame `+0x168`) | stop `+0x94` (Shop\enter), `+0x98` (School\Point); play **`+0x90` Point.wav** |
| shopie | region 1 hover, 4 % per step (flag 1, `0x4cd51c`) | `townbirds\shopie\sprites.16a` (28x44) | 30 | `+0x1e0` ++; at `n` -> 0, clear flag | (+0x114, +0x128), always drawn | none (the shop hover sound is `+0x94`) |
| gate `0x4cd0ea` | every step | `town\door\T%.2d.bmp` (36x48 BMP patch) | 9 (0..8) | `Var(0x301) == 0`: frame fixed **8** (closed). Else cursor on region 8: `+0x1a0 -= 1` to 0 (sound **GateUp.wav** once on entering), off: `+= 1` to 8 (**GateDn.wav** once on leaving) | (+0xb4, +0x94) | slot `+0x78`, the file is loaded at play time: the reload `FUN_004384f0` frees (stops) the previous file of the slot, so GateDn cuts a running GateUp and the reverse (3.6) |
| guards `0x4cce81` | hover 8 (dir `+0xec`) | `townbirds\guards\sprites.16a` (48x48) | 8 | frame `+0xe8 += dir`; clamps at 0 and `n-1` (dir reset to 0). Idle = `n-1` (the load sets it). Cursor on gate with `Var(0x301)==0` -> dir -1 -> frame falls to 0; cursor off or `Var != 0` -> dir +1. **Guard2.wav** when dir becomes +1 and `+0xf0 == 0` (then `+0xf0 = 1`); **Guard1.wav** when dir becomes -1 and `+0xf0 != 0` (then 0). `+0xf0` = **0 at the load** (CONFIRMED `0x4ca7e2`; the druid / Kaarg loads zero it too), so the first step (dir +1) plays Guard2 | (+0xb8, +0x9e) | `+0x7c`, loaded at play time like the gate; the clamp at either end frees the slot (`FUN_00438480` = stop + free), cutting the guard sound (3.6) |
| stars (flag `0x10`, `0x4cd2ac`) | region `0x10` hover | `town\stars\S%.2d.bmp` (64x44 patch) | 9 | `+0x1c0` ++; frames 1..8 shown with sound **Stars.wav** (`+0x9c`) when it started from 0; at 9 the **global counter `0x628260`** ++ (reset to 0 at 10, which also zeroes `+0x1c0`), pointer cleared, flag cleared. So after the first full play the counter stays 9: every later start shows nothing for one step and counts; **every 10th start plays again** (a hover re-arms every step, so continuous hovering replays about every 10 steps + 9) | (+0x154, +0x120); frame 0 shown at load, then the pointer is 0 (nothing) | `+0x9c` |
| sign (flag `0x40`, `0x4cd05b`) | random **5 % per step** (`rand(100) > 0x5e`) | `town\sign\V%.2d.bmp` (40x32 patch) | 10 | `+0x184` ++ to 10, then clear; frame = list[`+0x184`] (0 shown at load) | (+0x168, +0xe8) | **Flag.wav** (`+0x8c`) at counter 0 |
| fluger (flag `0x20`, `0x4cd577`) | random **2 % per step** (`rand(100) > 0x61`) | `town\fluger\F%.2d.bmp` (64x64 patch) | 8 | `+0x1fc` ++ to 8, then clear | (+0x134, +0x40) | **Flugel.wav** (`+0x88`) at counter 0 |
| birds (flag `0x80`) | timer, see 3.3 | `TownBirds\Birds%d\sprites.16a` d=1..9 (552x92 each) | 57 | `+0xd8/+0xdc/+0xe0` ++ per step (one counter per flyer); a flyer draws while its counter < 57; when all `+0xc0` flyers are done the flag clears | window origin (positions are in the sprites), then `Town_add.bmp` (552x92 BMP) over it with the colour-key blit `+0x38` (`0` transparent; INFERRED role: sky overlay) | `+0x80` Birds1 (1 flyer) / `+0x84` Birds2 |
| horse (flag `0x100`) | timer, 3.3 | `TownBirds\HORSE%d\A%d\sprites.16a`, d = visit kind 1..5, a = 1..3 | 15 | `+0x140` ++ per step; at `n` -> -1, clear; frame -1 = draws frame 0 (idle) | `(+[0x4e], +[0x4f])` = table `0x5f66e0` (5 x (x, y)): (104,404) (104,404) (256,344) (448,400) (140,400) | by set (`+0x144`) k and frame f, in the **draw**: k0: f=14 `+0xa0` Horse2; k1: f=8 or 14 Horse2; k2: f=1 `+0xa8` Horse1, f=14 Horse2 (fires each draw while the frame matches, but the slot play `0x438570` is skipped while that sound still plays, section 3.5: Horse2 is 41 ms, Horse1 535 ms); `+0xa4` Horse3 unused |
| baba (flag `0x200`) | timer, 3.3 | `...\BABA%d\A%d\sprites.16a`, d = visit kind 1..4, a = 1..2 | 31 (a1) / 32 (a2) | `+0x114` ++; at `n` -> -1, clear | `(+[0x43], +[0x44])` = table `0x5f6708`: (216,364) (308,424) (384,424) (580,384); **idle (-1) draws frame 0** (CONFIRMED `0x4cb05d`: the baba set pointer `+0xf4`.. is non-null from the load) | none |
| dervish (flag `0x400`) | **set at load and never cleared** | `...\DERVISH%d\sprites.16a`, d = visit kind 1..4 | 30 | `+0x15c = (+0x15c + 1) % n` every step (loops for the whole visit); sprite missing -> -1 | `(+[0x55], +[0x56])` = table `0x5f6728`: (224,364) (324,424) (392,420) (592,388) | none |
| fighter / mage / trainer | **dead**: `fighter`, `mage` sprites (11 frames each) and `Trener_l.bmp` are loaded and freed but never drawn nor ticked; their state functions `0x4cd36a` / `0x4cd443` are called once, by the loader | | | | | |

Visit kinds (`0x4cb6c6`, **new every visit**): horse `rand(5)`, baba `rand(4)`, dervish `rand(4)` re-rolled until it differs from the baba kind; the position `+0x4e..` follows the kind. (An older note said fighter / mage / shopie hover sprites: only the shopie and the tavern are live.)

### 3.3 Human random timers (CONFIRMED)

| what | rule | routine |
|---|---|---|
| baba | first deadline `rand(2000) + 2000` ms after load; on expiry: new delay `rand(5000) + 2000`, frame 0, set = `rand(2)` (a1 / a2), flag `0x200`. The deadline base is re-stamped **each animation step**, so the pause counts from the end of the last animation | `0x4ca7e2`, `0x4cda92`, `0x4cd73b` |
| horse | same, set `rand(3)`, flag `0x100` | `0x4cda92`, `0x4cd7d0` |
| birds | no flyer (flag `0x80` clear) and `now - +0x2e > D`; **D = `0x628254` is a process global**: first value `rand(2000) + 1000` once per process, then each start returns `rand(2000) + 1000`. Group `rand(3)` (files `3g+k`), count `rand(3) + 1`; counters zeroed; load stamps `+0x2e` | `0x4cb05d`, `0x4cae28` |
| crowd | `Crowd.wav` (`+0x74`) played **looped** (`0x45aa2f(.., loop=1, priority 0x80)`) once at load if not already playing | `0x4cdeca`, `0x4a0ff0` |
| gate speech / others | none | |

### 3.4 Human draw order (`0x4cb05d`)

1. `townmain.bmp` at the origin (opaque), 2. birds (3.2) + `Town_add`, 3. `Shop_l.bmp` (52x76) at (+0x108, +0x108) if hover = 1, 4. `Tavern_l.bmp` (28x64) at (+0x90, +0x14c) if hover = 2, 5. tavern sprite, 6. sign, 7. gate door, 8. stars, 9. shopie, 10. fluger, 11. guards, 12. horse, 13. baba, 14. dervish. No black fill is drawn: the area outside the 640x480 rect stays black like every town window. The three scenes also call `FUN_00456348(...)` / `FUN_00453788` around the draw (the surface clip), not content.

### 3.5 Sound slots and the draw order (CONFIRMED)

`FUN_00438570(slot)` = **play unless the slot's buffer is playing** (`FUN_0045a964` scans the channels for the buffer, status bit 1), `FUN_004385b0(slot)` = stop if playing; both do nothing for an empty slot (a file the install lacks). So no sound is started on top of itself; "stop X, play X" (the druid figures) restarts. Built in `SceneState.play` with the length of each wav (`SceneSpec.sound_ms`, read from the install); every stop of the three scenes is built as a stop event (3.6: `SceneState.take_events()` yields `(path, loop)` plays and `(path, STOP)` stops in order; `Services.stop(path)` -> `Director.stop_ui`). Draw order: `0x4cb05d` / `0x4cf65a` run the step (hover, human rolls sign 5 % / fluger 2 %, tick) **then** the starters (`+0x9c`) **then** the birds start, then draw (CONFIRMED, human and druid; the Kaarg draw has the same shape).

### 3.6 Every stop of the three scenes (CONFIRMED, REA of all callers; round 3)

Three kinds of cut exist: **stop** `FUN_004385b0` (stop if the slot's buffer plays; 18 callers in the image, six in the scenes: `0x4ccfbf`, `0x4cdbea`, `0x4cfb45`, `0x4cfd58`, `0x4d00de`, `0x4d244e`), **release** `FUN_00438480` (stop + free the slot; scene callers: the guards `0x4cce81`, the per-scene release-all `0x4ce00b` / `0x4cf4dc` / `0x4d1e36` = vtable `+0x8c`, and the reload) and **reload** `FUN_004384f0` (release, then load a new file; the gate / guard / Kaarg-gate slots use it at play time, the sounds init uses it to fill every slot). `FUN_0041f610` (the channel stop) is reached only from these, the channel allocator `0x45ab9c` and the ambience / speech code. The draws (`0x4cb05d`, `0x4cf65a`, `0x4d1f6d`), the Kaarg starters / tick bodies and the human stars / sign / fluger / birds / horse code contain **no stop**. A stop of a slot whose file the install lacks does nothing. Slot names are the sounds-init tables (human `0x4cdee4`: `+0x74` Crowd, `+0x80` Birds1, `+0x84` Birds2, `+0x88` Flugel, `+0x8c` Flag, `+0x90` Point, `+0x94` Shop\enter, `+0x98` School\Point, `+0x9c` Stars, `+0xa0` Horse2, `+0xa4` Horse3, `+0xa8` Horse1; `+0x78` / `+0x7c` empty until the first gate / guard play).

| # | routine / condition | stops (slot -> file) | then |
|---|---|---|---|
| 1 | human hover `0x4cdbea`, region 1 entering (`+0xac == 0`) | `+0x98` School\Point | play `+0x94` Shop\enter, latch |
| 2 | human tavern step `0x4ccfbf`, counter `+0x168 == 0` | `+0x94` Shop\enter, `+0x98` School\Point | play `+0x90` Point (the tavern door cuts a running shop-enter sound) |
| 3 | human gate `0x4cd0ea`, reload on entering / leaving region 8 | `+0x78` old file (GateUp <-> GateDn) via the reload | play the new one (always starts) |
| 4 | human guards `0x4cce81`, reload on dir change | `+0x7c` old file (Guard1 <-> Guard2) | play the new one |
| 5 | human guards `0x4cce81`, release when the frame reaches 0 or n-1 | `+0x7c` (whatever is loaded) | none. The first step (idle frame n-1, dir +1) plays Guard2 and **cuts it in the same call** (silent); gate hover with `Var(0x301) == 0` plays Guard1 and cuts it when the frame reaches 0; moving off plays Guard2 and cuts it at n-1 |
| 6 | druid hover `0x4cfd58`, region 1 variant start (`+0x2ec != 2`, entering) | `+0x248` Ddruid1 (empty in the install) | play `+0x248` |
| 7 | druid hover, region 2 variant start | `+0x24c` Ddruid2 (empty) | play `+0x24c` |
| 8 | druid hover, region 1 entering (`+0xac == 0`) | `+0x254` Denter1, `+0x258` Dout | play `+0x250` Denter2 |
| 9 | druid hover, region 2 entering (`+0x260 == 0`) | `+0x250` Denter2, `+0x258` Dout | play `+0x254` Denter1 |
| 10 | druid hover, region 8 (`+0x264 == 0`) | `+0x250` Denter2, `+0x254` Denter1 | play `+0x258` Dout |
| 11 | druid starters `0x4d00de`, shop figure timer fires on an idle figure | `+0x248` Ddruid1 | play it (restart) |
| 12 | same, inn figure | `+0x24c` Ddruid2 | play it |
| 13 | druid inn step `0x4cfb45`, `+0x168 == 0` | `+0x94` (a human slot the druid never loads: empty) | play `+0x90` (empty): no-ops |
| 14 | Kaarg hover `0x4d244e`, region 1 entering (`+0xac == 0`) | `+0x230` Kenter1 | play `+0x22c` Kenter2 |
| 15 | Kaarg hover, region 2 entering (`+0x250 == 0`) | `+0x22c` Kenter2 | play `+0x230` Kenter1 |
| 16 | Kaarg hover, region 8 (`+0x254 == 0`) | `+0x22c` Kenter2, `+0x230` Kenter1 | nothing (latch out) |
| 17 | Kaarg gate `0x4d2c2c`, reload on entering / leaving region 8 | `+0x78` old file (Kdoor1 <-> Kdoor2) | play the new one |
| 18 | load: the sounds init `0x4cdee4` / `0x4cf2c0` / `0x4d1c83` calls the release-all (`+0x8c`: `0x4ce00b` frees `+0x74..+0xa8`, `0x4cf4dc` `+0x20c..+0x25c`, `0x4d1e36` `+0x20c..+0x24c`) first | every slot incl. the **looped** Crowd (`+0x74`) / Dforest1 (`+0x244`) / Kvox1 (`+0x228`) | the init reloads the files, the load starts the entry loop again |
| 19 | **close** `0x4caaed` (vtable `+0x84`, click `+0xac` -> `0x445`; load-save from a scene) | the release-all `+0x8c` (as row 18): every slot | `+0x5c = 0`, hidden, `0x44c` posted |

- Latch rules (sections 3.1, 4, 5) make rows 1, 8-10, 14-16 fire once per entry; regions 4 / `0x200` / `0x400` / `0x800` / `0x1000` return before any stop.
- **Looping slots**: the only stops of a looped slot are the release-all of the load (row 18: a loop still running from the previous visit is cut and restarted) and the channel allocator `0x45ab9c` (a full mixer steals the lowest priority voice; the `VoiceMixer` models it). No hover / tick / starter / draw stops a loop.
- **CONFIRMED (round 4): the release-all is reached when the scene is closed** (row 19): the close hook `0x4caaed` calls vtable `+0x8c` (after deleting the story window and the art, `+0xa4` = `0x4cc4e5` frees the bitmaps / sprites), so **leaving by shop / inn / leave cuts every slot, the looped Crowd / Dforest1 / Kvox1 and any one-shot still running**. Built: `SceneState.release_all()` (a stop per path started since the load) from `TownScene.exit`. Exit to Main Menu from the scene (`0x41e` = `0x486dbd` -> `FUN_0048f2e5`, then `0x421`) and Exit to Windows do **not** run the close hook in the code read (no `0x445` to the scene; `0x421` = `FUN_0048b569` removes the mission views and window `0x3fc` only, the scene window stays a child with `+0x5c` = 1): INFERRED that the loop keeps playing under the main menu in the exe; we cut it (DECISION, `exit()` is shared). Loading a save from a scene (`0x419`, `0x4857a7`-`0x4858df`) does send `0x445` to the scene window of the current town first.
- Reload rule (rows 3, 4, 17): the file is chosen at play time and the buffer is new, so `play unless playing` never blocks it.

## 4. Druid scene

Hover (`0x4cfd58`, the hit test is the human one): region 1 = shop, 2 = inn (tavern).

The install has **no `Ddruid1.wav` / `Ddruid2.wav` and no `Dlizard1..4.wav`** (`sfx/town_druid` holds Dbird, Dbug, Denter, Dforest, Dout, Dtree, Dwolf): those slots are empty and silent (the exe loads missing files as empty slots).

| region | effect |
|---|---|
| -1 | cursor reset; the three "entry sound" latches `+0x260 (=[0x98]) / +0xac / +0x264 (=[0x99])` cleared |
| 1 shop | draw `hili_shop.bmp` (152x164) at (+0x1a4, +0xe0). On **entering** from another region while the shop figure (woman graphics) is not in the hover variant (`+0x2ec != 2`): stop `+0x248`, re-stamp `+0x2f0`, **variant 2** (`+0x2ec = 2`, frame `+0x1e0 = -1`), flag `1`, run one step, play **Ddruid1.wav** (`+0x248`). Entry sound once (`+0xac`): stop `+0x254 / +0x258`, play **Denter2.wav** (`+0x250`) |
| 2 inn | draw `hili_tavern.bmp` (152x96) at (+0, +0xb8). Same for the inn figure (man graphics; `+0x2a4`, frame `+0x168`, flag `2`, **Ddruid2.wav** `+0x24c`); entry sound **Denter1.wav** (`+0x254`) once (`+0x260`) |
| 8 leave | entry sound **Dout.wav** (`+0x258`) once (`+0x264`), stops the other two; no draw, no flag (the leave region is the bottom-left way out) |
| 4, `0x200`, `0x1000` | return at once (no flag, latches kept) |
| others | flags OR-ed |

**The two figures (CONFIRMED `0x4ce914`, `0x4cf65a`, `0x4cfd58`, `0x4d00de`, `0x4cfb45`, `0x4cfbf6`).** The loader fills **`+0x2b0 + v * 0x14` from `woman\a%d%.4d.bmp`** (state `+0x2ec`, frame `+0x1e0`, timer `+0x2f0 / +0x2f4`, flag `1`, region 1 = **shop**, `hili_shop`, Ddruid1) and **`+0x268 + v * 0x14` from `man\...`** (state `+0x2a4`, frame `+0x168`, timer `+0x2a8 / +0x2ac`, flag `2`, region 2 = **inn**, `hili_tavern`, Ddruid2): **the woman is the shopkeeper, the man the innkeeper** (the earlier "man = shop" was the member-order guess and wrong). `a` = variant 1..3, frame 1..20 until the first missing file; frame counts: woman (shop) 15 / 20 / 20, man (inn) 19 / 19 / 20. State = the variant index (-1 idle). Starters: (a) the hover forces variant **2** (`a3`), frame -1, re-stamps the timer, runs one step, plays the sound; (b) the ambient starter `0x4d00de` re-arms its timer (`rand(5000) + 3500`) **whenever it expires**, and only if the figure is idle starts it: variant 2 when the pointer is over its region, else `rand(2)`, frame 0, flag, sound. Step: `++`, at the list's count frame 0 / state -1 / flag cleared; the inn figure's body `0x4cfb45` is the same plus two sound calls (`+0x94` stop, `+0x90` play at frame 0) on slots the druid never loads = no-ops (the old "woman by symmetry" is settled). Draw: the hili patch when the region is hovered **or the state is 2** (not for 0 / 1); the figure: running = list[state] frame at `(0x150 + (v/2) * 4, 0xf4 - (v/2) * 0x14)` (shop) / `(0xa4 - (v/2) * 0xc, 0xc8 - (v/2) * 0x10)` (inn); idle = frame 0 of variant 2 at the hovered place when the pointer is on the region, else of variant 0. The patches are opaque: the bitmaps come from `FUN_00424e4b` (64k class) and are drawn with its `+0x18` (`FUN_004254ea`, opaque), the same call as `townmain`.

**Load `0x4ce641` (CONFIRMED).** Loader, sounds, flags 0, `+0x1a4 = 0`, `+0xf0 = 0`, then in this order: shop timer stamp = now, delay `rand(2000) + 2000`; inn timer stamp = now, delay `rand(2000) + 2000`; bird stamp `+0xb8` = now; tree stamp `+0x2f8` = now; wolf stamp `+0x2fc` = now; **bug** stamp `+0x304` = now, delay **`rand(5000) + 7000`** (later `rand(10000) + 10000`), bug frame `+0x310` = -1, bug variant `+0x30c` = -1, lizard state `+0x318` = -1, frame `+0x31c` = -1, region -1; then the entry loop. Nothing fires on the first draw (the old "stamps are 0" was wrong); the latches `+0x260 / +0xac / +0x264` are cleared by the sounds init `0x4cf2c0`. Bird / tree delays are the process globals `0x628234 / 0x628244` (first value `rand(2000) + 2000`, rolled once). The bug starter has no idle test (its delay outlasts the run), picks `rand(3)`, keeps the frame (-1 at the very first run: nothing drawn until the first step; 0 afterwards); the step `0x4cfc77` ends at 61 -> frame 0, variant -1. The lizard is drawn at frame 0 whenever it is idle.

**Hover latches (`0x4cfd58`, CONFIRMED).** `+0xac` shop, `+0x260` inn, `+0x264` out: entering shop / inn plays its Denter once (stopping the others) and clears the other two; region 8 plays Dout once, clears shop / inn; 4 / `0x200` / `0x1000` return at once (region stored, latches kept); every other region value (-1, `0x10`, ...) clears all three (and ORs its flag).

| anim | trigger | assets | frames | rule | pos | sound |
|---|---|---|---|---|---|---|
| bug | every `rand(10000) + 10000` ms (`+0x304 / +0x308`, first stamp at load) | `town_druid\bug\sprites.16a` (640x268) | 183 = 3 x 61 | variant `rand(3)`; frame = variant * 61 + step, step ++ per step to 61, then hidden (`0x4cfc77`) | (0, +0xd4) | Dbug1 / 2 / 3 = `+0x21c` / `+0x220` / `+0x224` by variant |
| lizard | restarts **at once** whenever idle (`+0x318 == -1`) | `town_druid\lizard\sprites.16a` (100x120) | 42 | `rand(15)`: 0 -> seq 1 Dlizard2, 1 -> seq 2 Dlizard3, 2 -> seq 3 Dlizard4, else seq 0 Dlizard1 (12/15); the index table `0x5f68c8` (4 sequences, frames 1-based, `-1` ends) is in animation 4.11; step per 100 ms (`0x4cfcde`: ++ then test the end marker) | (0, +0x12c) | `+0x20c .. +0x218` |
| ambient | birds: global `0x628234` (first `rand(2000)+2000`, then each `rand(2000)+2000`): `Dbird` 1..3 by `rand(3)`; trees: global `0x628244`, `Dtree` 1..4 by `rand(4)`; wolf: `Dwolf1` every 60 000 ms; entry loop **`Dforest1.wav`** (`+0x244`, looped like the Crowd) | | | | | slots below |

Druid sound slots (`0x4cf2c0`, `this + 4 * idx`): `0x83..0x86` Dlizard1..4, `0x87..0x89` Dbug1..3, `0x8a..0x8c` Dbird1..3, `0x8d..0x90` Dtree1..4, `0x91` Dforest1, `0x92` Ddruid1, `0x93` Ddruid2, `0x94` Denter2, `0x95` Denter1, `0x96` Dout, `0x97` Dwolf1 (all `sfx\town_druid\`). Tick flags (`0x4d065b`): `1` man, `2` woman, `0x80` bug, `0x100` lizard. Draw order (`0x4cf65a`): townmain, hili_shop (hover 1 or man active), man, hili_tavern (hover 2 or woman active), woman, lizard, bug. Step 100 ms; no random rolls per step.

## 5. Kaarg scene

Hover (`0x4d244e`, CONFIRMED): 1 shop: draw `hili_shop.bmp` (40x76) at (+0x148, +0x100); entering plays **Kenter2.wav** (`+0x22c`), stops `+0x230`. 2 inn: `hili_tavern.bmp` (140x128) at (+0x1e0, +0xc4); entering plays **Kenter1.wav** (`+0x230`). Latches `+0xac` shop / `+0x250` inn / `+0x254` out: entering a region clears the other two (so shop -> gate -> shop plays Kenter2 again); 8 latches out and only stops the enter sounds; regions 4, `0x200`, `0x400`, `0x800` return at once; any other region (-1, `0x10`) clears all three and ORs its flag. Load `0x4d0d46` (CONFIRMED): girl 1 / girl 2 / guard timers stamp now with `rand(2000) + 2000` in that order, dervish `rand(500) + 4000`, `+0xf0 = 0`, then Kvox1 looped. Nothing else is region-driven: the NPCs animate **only from timers**.

| anim | assets (`town_kaarg\`) | frames | trigger (first delay at load; then) | step (`0x4d2f27`: flags `0x200` `0x4d2d87`, `4` `0x4d2dfc`, `0x400` `0x4d2ecc`, `0x800` `0x4d2e71`, always the gate `0x4d2c2c`) | draw pos | sound |
|---|---|---|---|---|---|---|
| girl 1 (flag `0x200`) | `girl1\g1000..g1030`, `g2000..g2029` (44x108) | variant 1: 31, variant 2: 30 | `rand(2000)+2000` after load; then `rand(5000) + 3500` ms; variant `rand(2)` (`+0x2c4`) | `+0x114` ++ to the list size, then flag clear, variant -1 | (+0xd8, +0x11c); idle = list 0 frame 0 | none |
| girl 2 (flag `4`) | `girl2\...` (68x104), same counts | 31 / 30 | same (`+0x2f8 / +0x2fc`), variant `+0x2f0` | `+0x2f4` ++ | (+0x104, +0x11c) | none |
| guard (flag `0x800`) | `guard\g0000..g0054` (72..76x68) | 55 | first `rand(2000)+2000`; then `rand(5000) + 7500` ms (`0x1d4c`) | `+0x1cc` ++ to 55 | frames 13..37: (+0x8c, +0x98); else (+0xb8, +0x9c) | footsteps (`0x4d26a4`, only while the flag is set, the frame `+0x1cc` after the step's increment; latch `+0x258`, CONFIRMED): frames {5, 13, 21, 47}: `Ksteps21` if `rand(4) == 0` else `Ksteps2` (`+0x23c` / `+0x238`); {9, 17, 23, 51}: `Ksteps11` / `Ksteps1` (`+0x244` / `+0x240`); {31}: `Ksteps31` / `Ksteps3` (`+0x24c` / `+0x248`). Latch clear: roll, play (`0x438570`, play-unless-playing), latch = 1; any frame outside the sets clears the latch; so one fire per entry into a frame, however many draws it lasts |
| dervish (flag `0x400`) | `dervish\d0000..d0029` (112x148) | 30 | first `rand(500) + 4000`; then `rand(500) + 3700` (`0xe74`) | `+0x15c` ++ to 30 | (+0x1a0, +0x148) | none (the `Kman1.wav` below) |
| main gates | `maingates\m0000..m0010` (60x84) | 11 | region 8 hovered: `+0x1a0 += 1` to 10, **Kdoor1.wav** once on entering; else `-= 1` to 0 with **Kdoor2.wav** once on leaving | every step | (+0x98, +0x100) always drawn | `+0x78` |

(Switch `0x4d2a73`: `index = frame - 5`, `> 0x40` = latch clear; byte table `0x4d2beb` (65 bytes) -> 14-entry jump table `0x4d2bb3`; it also lists 55, 59, 63 (sets 1 / 2) and 69 (set 3) but the step `0x4d2e71` increments `+0x1cc` and wraps to 0 and clears the flag when it equals the frame count (`+0x264` object, `0x4019a0` = `[+8]`; 55 measured) **before** the starters of the same draw, and a fire sets it to 0: the starters only ever see 0..54, so 55 / 59 / 63 / 69 are dead, CONFIRMED by the code, the count 55 from the install.) Ambient (starters, every draw): **voices** `Kvox2/3/4` (`+0x20c / +0x210 / +0x214`) at `rand(3)+1` every `rand(2000)+2000` ms (process global `0x628224`, first value once per process); **birds** `Kbird1..4` (`+0x218..+0x224`) `rand(4)` every `rand(2000)+2000` (global `0x628240`); `Kman1.wav` (`+0x234`) every 45 000 ms; entry loop **`Kvox1.wav`** (`+0x228`, looped, `0x4d0d46`). **Initial state (CONFIRMED `0x4d09ee`, human ctor `0x4ca23c` -> `0x4ca58d`, load `0x4d0d46`, sounds `0x4d1c83`, draw `0x4d1f6d`, starters `0x4d26a4`)**: the scene object is `operator new(0x314)` (`0x401880` -> CRT malloc, not zeroed). Neither ctor (the Kaarg one zeroes only `+0x20c..+0x24c`, the sound slots; `0x4ca58d` zeroes the human fields, not `+0xb8 / +0x25c / +0x260`), nor the loader, nor the sounds init `0x4d1c83` (zeroes `+0x250 / +0xac / +0x254`, the latches) writes the **voice stamp `+0xb8`, bird stamp `+0x25c`, Kman1 stamp `+0x260`**; they are first written by the starters when the timer fires. So they hold a never-written value (a fresh heap page = 0, else garbage; both make `timeGetTime() - stamp > delay` true) and **voice, bird and Kman1 all fire on the very first draw** (one voice `Kvox2..4`, one `Kbird1..4`, `Kman1`; the process globals `0x628224 / 0x628240` are rolled by the starters' first run, `rand(2000)+2000`, only to be re-rolled). The object lives for the session and the loader does not touch these three, so a **reopening does not re-fire** them (the stamps keep their last value). All four NPC timers are **stamped `now` at the load** with their first delay rolled at the load, in this order: girl 1 (`+0x118 / +0x11c`) `rand(2000)+2000`, girl 2 (`+0x2f8 / +0x2fc`) `rand(2000)+2000`, guard (`+0x278 / +0x27c`) `rand(2000)+2000`, dervish (`+0x294 / +0x298`) `rand(500)+4000`; the load also sets flags `+0x208 = 0`, region `+0xb4 = -1`, the girl-2 frame / variant `+0x2f4 / +0x2f0 = -1` (the draw shows frame 0 while its flag is clear). Re-arm (starters): girl 1 / girl 2 `rand(5000)+3500` (`0xdac`; variant `rand(2)` in `+0x2c4` / `+0x2f0`), guard `rand(5000)+7500` (`0x1d4c`), dervish `rand(500)+3700` (`0xe74`); each fire stamps `now`, zeroes the frame and ORs the flag; **there is no idle test** (a due timer restarts a running animation; the delays outlast the runs). The step clock **`0x628248` is a process global** (stamped at the first draw ever, `0x4d1f6d`; step = `100 < now - clock`: hover `+0x98(cursor)`, tick `+0xa8` = `0x4d2f27`, re-stamp; then starters `+0x9c`, then the draws), so on a reopening the first draw runs a step at once. Draw order (`0x4d1f6d`): townmain, hili_shop, hili_tavern, girl 1, girl 2, guard, dervish, gates. Step 100 ms. The scene starts with flags 0 (nothing runs until a timer fires).

## 6. Between visits (CONFIRMED)

| kept | where |
|---|---|
| per visit, new: human horse / baba / dervish kind | loader `0x4cb6c6` (kind `rand`, positions from the tables) |
| process-global: first-bird delay `0x628254`, druid birds / trees `0x628234 / 0x628244`, Kaarg voices / birds `0x628224 / 0x628240`, the step clocks, **stars play counter `0x628260`** (every 10th start plays) | `0x4cb05d`, `0x4cd2ac`, `0x4d00de`, `0x4d26a4` |
| none else: all animation state is re-initialised by the loader / load (`0x4ca7e2`: flags 0, gate frame, `+0x2e`, timers) | |

The scene is **rebuilt from the loader every opening** (`+0x80` runs the loader `+0xa0`), the objects live for the session: `0x48bbc0` only does `AddChild(client+0x110 / 0x114 / 0x118)` + `vtable+0x80`, never `new` (CONFIRMED; no `delete` of a scene window anywhere, the `0x44c` handler only removes it from the root). **Teardown (CONFIRMED `0x4caaed`, `0x4dc2b0`, `0x4dc26d`)**: a click on shop / inn / leave sends the window `0x445`; with `+0x5c == 1` the base runs the close hook = `+0x204 = 0`, delete the story window `+0x200` if open, `+0xa4` (free the art: bitmaps, sprites, the timers' objects), `+0x8c` (**release-all: every sound slot stopped and freed, the loops included**), then `0x4dc26d` (`+0x5c = 0`, hide + disable the window, result `+0x60`), and posts `0x44c`; only then the click posts `0x42a` / `0x42b` / `0x442` + `0x42d`. The window is hidden, not destroyed; sounds do not outlive the visit. The music is started by the scene opener, not the scene (`0x48bbc0`; b14 human, b16 Kaarg, b15 druid: CONFIRMED earlier, [town-hero 1](town-hero.md#1-purpose-and-entry--exit)).

## 7. Implementation recipe (data a pure module can use)

Per scene a `SceneSpec`: `step_ms` (67 / 100), `patches` (static layers in draw order), `regions` (mask byte -> flag), `hover` (flag -> action), `click` (flag -> message / speech), `anims` (name, assets, frames, trigger, rule, pos, sound), `ambient`, `entry_loop`. Minimal tables:

```
REGION_OF_BYTE = {0x80: 2, 0x90: 1, 0xa0: 8, 0xb0: 0x10, 0xc0: 4, 0x20: 0x400, 0x40: 0x800, 0x50: 0x1000, 0x60: 0x200}   # everything else -1
CLICK = {   # region -> message / speech (press, left button)
  human: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d) if Var(0x301) else speech("plagatguard"), 0x10: 0x41f},
  druid: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d), 0x10: 0x41f, 0x200: speech("druidinnkeeper%d" % Var(0x300)), 0x1000: speech("druidshopkeeper%d" % Var(0x300))},
  kaarg: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d), 0x10: 0x41f, 4: speech("kaargwoman%d"), 0x200: speech("kaargwoman%d"), 0x400: speech("kaargman%d"), 0x800: speech("kaargguard%d")}}   # %d = Var(0x300)
HOVER_PATCH = {human: {1: ("town/shop_l.bmp", 0x108, 0x108), 2: ("town/tavern_l.bmp", 0x90, 0x14c)},
               druid: {1: ("town_druid/hili_shop.bmp", 0x1a4, 0xe0), 2: ("town_druid/hili_tavern.bmp", 0, 0xb8)},
               kaarg: {1: ("town_kaarg/hili_shop.bmp", 0x148, 0x100), 2: ("town_kaarg/hili_tavern.bmp", 0x1e0, 0xc4)}}
ENTRY_LOOP = {human: "SFX/Town/Crowd.wav", druid: "sfx/town_druid/Dforest1.wav", kaarg: "sfx/town_kaarg/Kvox1.wav"}   # looped, priority 0x80
```

Anim rows are those of sections 3.2, 4, 5 (frames, positions, sounds, timers). Random: use the engine's seeded RNG; `rand(n)` = uniform 0..n-1 (the exe's `FUN_004a0fd0`). The scenes need an RNG, a monotonic ms clock, the `Var(0x300)` / `Var(0x301)` reads ([town 2](town.md#2-state-machine-of-a-visit-confirmed-edges-each-edge-names-its-routine)) and the sound player; everything else is data. Headless-testable: `REGION_OF_BYTE` on the three real masks (dense-region boxes of section 2), `CLICK`, the stars every-10th rule, the guard direction / sound rule, the Kaarg footstep switch (latch), the gate counter, the druid variant rule, the timers with a fake clock.

## 8. Open questions

2. The story window of an NPC click in the scene (text, Ok pages 2.. and their voices) is not hosted by `TownScene` yet: L7 built the window as `engine.inn.Dialogue` + `Inn._dialogue_ops` (town.md 5 "L7 as built"), reusable here; the Save / Load windows of the scene menu are not built.
3. Whether the exe keeps the scene's loop sound under the main menu after *Exit to Main Menu* from a scene (no close hook found on that path, 3.6; we cut it).
4. Play-test only: whether the dither noise of the human mask can be felt; animation speeds.

## 9. L6 round (REA + the build, 2026-11-14 / 15)

CONFIRMED (REA, `allods2.exe`):
- **Kaarg initial stamps / delays** (section 5, `0x4d09ee`, `0x4ca23c`, `0x4d0d46`, `0x4d26a4`, `0x4d1f6d`): voice / bird / Kman1 stamps never written before their first fire (all three fire on the first draw, not again on reopening); NPC first delays and re-arms as listed; step clock a process global; no idle test in the starters. Built (`Globals.kaarg_clock / kaarg_stamps / kaarg_step_seen`).
- **Guards `0x4cce81`**: the sound test is in the guards' tick on the direction the hover just set: `frame += dir`; `dir == 1 && +0xf0 == 0` -> Guard2, `+0xf0 = 1`; `dir == -1 && +0xf0 != 0` -> Guard1, `+0xf0 = 0`; then clamp. `+0xf0` is **0 at the load** (`0x4ca7e2`), so the first step plays Guard2.
- **Birds starter `0x4cae28`** returns the next delay `rand(2000) + 1000`; the draw `0x4caf00` stamps `+0xb8 = now` on every draw while flyers are up; `Town_add.bmp` (colour-key blit `+0x38`) is drawn only while flyers are up. The key is the 5-6-5 word `0x0000` (R < 8, G < 4, B < 8), applied in `Painter.keyed`.
- **Stars `0x4cd2ac`**: section 3.2's rule.
- **Order**: step (hover, rolls, tick) then starters, then draw (section 3.5). **Idle baba drawn at frame 0**; the human load rolls baba then horse first delays. **Sound slots**: play-unless-playing (3.5), so the horse sounds fire every draw but start once per frame unless the sample is shorter than the step. **Click**: no sound (2.1). **`.16a` layers** (bug, lizard, birds, guards, ...): created by `FUN_00427ecb`, drawn by `FUN_00427ef0` -> `FUN_0045889b` with the sprite's own FADE16 row 0: the standard `(a + 1) / 16` blend, nothing scene-specific (the renderer's `alpha_coverage` is it). **Druid patches**: opaque (section 4). **Kaarg**: hover latches and load stamps (section 5).

- **Stops (round 3, 3.6)**: every `FUN_004385b0` caller read, plus the release `FUN_00438480` and the reload `FUN_004384f0`. Built: `SceneState.stop / reload / release / take_events`; stop events -> `Shell.stop` -> `Services.stop` -> `Audio.stop` -> `Director.stop_ui(path)` (cuts the voices of that `ui` path that still play). Corrected: the guard sounds are cut at the clamp (the first step's Guard2 is silent); GateUp / GateDn and Kdoor1 / Kdoor2 cut each other.

Measured on the install: the Kaarg girls' second variant is numbered `g2001..g2030`; `Ddruid1/2.wav` and `Dlizard1..4.wav` do not exist (silent slots).

INFERRED (decisions of the build): the time spent outside the Kaarg scene is not counted by the stamps' clock (`Globals.kaarg_clock`; the exe's `timeGetTime` counts it, so after a long absence the exe fires the voice / bird at once, we a little later); the reopening runs a step on its first draw assuming > 100 ms away; the Save / Load entries of the scene menu are disabled; the human leave gate lives in `TownCore`.

**Round 4 (REA, 2026-11-15).** `+0x5c` = the open flag set by `0x4dc232` in every scene load (so the click's `0x445` runs the close hook `0x4caaed` and posts `0x44c`); the close = art freed + release-all of every sound slot + hidden, the object lives on; leaving a scene by shop / inn / leave cuts all its sounds. Built: `SceneState.release_all`, `TownScene.exit`.
