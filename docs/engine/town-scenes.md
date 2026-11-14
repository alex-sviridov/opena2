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

- **Mouse**: only **left button press** (`0x201`, slot `+0x54`) acts; release (`+0x58`), double click, right button are default no-ops (vtable `0x5cfac8`, slots `+0x58`..`+0x64` = `0x437f10`..`0x437f40`). The action is on the **press**, not the release. A click first calls slot `+0xac` (`0x4cdda4`: sends the window `0x445`... the "play click" stub of the base; CONFIRMED it is `vtable+0x48(0x445,0,0)`). Slots: `+0x4c` = `WM_MOUSEMOVE`, `+0x54` = `WM_LBUTTONDOWN` ([click-to-move 1](click-to-move-research.md)).
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
| `0x10` | post `0x41f` (INFERRED: the same message ESC posts in the scene with no screen open, [shell 6](shell.md): the in-game / system menu) | same | same |
| 4 | none (the human trainer is not clickable) | none | speech `kaargwoman_%d` (`Var(0x300)`) |
| `0x200` | none | speech `druidinnkeeper_%d` (`Var(0x300)`) | speech `kaargwoman_%d` |
| `0x400` | none | none | speech `kaargman_%d` |
| `0x800` | none | none | speech `kaargguard_%d` |
| `0x1000` | none | speech `druidshopkeeper_%d` (`Var(0x300)`) | none |

`%d` = `Var(0x300)` read through `DAT_0062729c` (the chapter, [triggers](triggers.md)); the speech is played by `FUN_0041d15e` like `plagatguard` ([town-inn](town-inn.md) for the speech path). The speech ids are from the format strings at `0x5f7148`, `0x5f715c`, `0x5f752c`, `0x5f753c`, `0x5f754c`, `0x5f755c` (the `%d` suffix is read from the string label; the exact sound-file mapping of a chapter is the speech table, open). ESC / Enter do nothing in the scene.

## 3. Hover, highlight and animation flags

The hover (called by the move message and every step) stores the region in `+0xb4` (`[0x2d]`), sets the guard direction `+0xec = 1`, then acts per region. The flag word is `+0x208` (`[0x82]`); a region value `>= 0x10` (and the default case) is OR-ed into it, so **a region flag and the animation flag of the same bit are one thing**.

### 3.1 Human hover (`0x4cdbea`; jump table `0x4cdd86`, index bytes `0x4cdd9a`: -1 / 1 / 4 / 8 / default)

| region | effect |
|---|---|
| -1 | cursor reset; `+0xb0 = 0`, `+0xac = 0` (re-arms the shop sound) |
| 1 shop | each step **4 %** (`rand % 100 > 0x5f`) sets flag `1` (shopie) if clear; on **entering** (`+0xac == 0`): stop `+0x98`, play **`+0x94` (SFX\Town\Shop\enter.wav)**; draw `Shop_l.bmp` |
| 2 inn | flag `2` OR-ed **every step** (tavern anim loops while hovered); draw `Tavern_l.bmp` |
| 4 | **nothing** (no flag, no draw, no sound); resets nothing |
| 8 leave | `+0xec = (Var(0x301) == 0 ? -1 : 1)`; the gate / guards react (3.2); no flag |
| `0x10` | flag `0x10` (stars) |
| `0x200 0x400 0x800 0x1000` | OR-ed into the flags (only `0x200` baba / `0x400` dervish have a tick handler: `0x400` is already on; hovering a baba restarts nothing, the baba only needs the flag to be set) |

### 3.2 Human animations (tick `0x4cd606`, order: flag 1, flag 2, gate, flag 0x10, 0x40, 0x20, 0x80, 0x400, 0x200, 0x100, guards)

All steps advance **one frame per step (67 ms)**. `n` = frame count of the file set (measured on the install). Positions are `origin + (dx, dy)`; "BMP patch" = 24-bit `.bmp` drawn opaque (vtable `+0x18` of the 64k class, [bitmaps](../formats/bitmaps.md)); "sprite" = `.16a`, alpha sprite `+0x18` with the frame number.

| anim | trigger | assets (`graphics\interface\`) | frames | step rule | draw pos | sound (slot) |
|---|---|---|---|---|---|---|
| tavern door | region 2 hover (flag 2, `0x4ccfbf`) | `townbirds\tavern\sprites.16a` (64x96) | 10 (0..9; load forces frame 0 = idle) | `+0x168` ++ per step; at `n` -> 0 and clear flag (re-set while hovered); sound at frame 0 | (+0x7c, +0x138), always drawn (frame `+0x168`) | stop `+0x94`, `+0x98`; play **`+0x90` Point.wav** |
| shopie | region 1 hover, 4 % per step (flag 1, `0x4cd51c`) | `townbirds\shopie\sprites.16a` (28x44) | 30 | `+0x1e0` ++; at `n` -> 0, clear flag | (+0x114, +0x128), always drawn | none (the shop hover sound is `+0x94`) |
| gate `0x4cd0ea` | every step | `town\door\T%.2d.bmp` (36x48 BMP patch) | 9 (0..8) | `Var(0x301) == 0`: frame fixed **8** (closed). Else cursor on region 8: `+0x1a0 -= 1` to 0 (sound **GateUp.wav** once on entering), off: `+= 1` to 8 (**GateDn.wav** once on leaving) | (+0xb4, +0x94) | slot `+0x78`, the path is set at play time |
| guards `0x4cce81` | hover 8 (dir `+0xec`) | `townbirds\guards\sprites.16a` (48x48) | 8 | frame `+0xe8 += dir`; clamps at 0 and `n-1` (dir reset to 0). Idle = `n-1` (the load sets it). Cursor on gate with `Var(0x301)==0` -> dir -1 -> frame falls to 0; cursor off or `Var != 0` -> dir +1. **Guard2.wav** when dir becomes +1 and `+0xf0 == 0` (then `+0xf0 = 1`); **Guard1.wav** when dir becomes -1 and `+0xf0 != 0` (then 0). `+0xf0`'s start value is not set by the ctor (heap) | (+0xb8, +0x9e) | `+0x7c` |
| stars (flag `0x10`, `0x4cd2ac`) | region `0x10` hover | `town\stars\S%.2d.bmp` (64x44 patch) | 9 | `+0x1c0` ++; frames 1..8 shown with sound **Stars.wav** (`+0x9c`) when it started from 0; at 9 the **global counter `0x628260`** ++ (reset to 0 at 10, which also zeroes `+0x1c0`), pointer cleared, flag cleared. So after the first full play the counter stays 9: every later start shows nothing for one step and counts; **every 10th start plays again** (a hover re-arms every step, so continuous hovering replays about every 10 steps + 9) | (+0x154, +0x120); frame 0 shown at load, then the pointer is 0 (nothing) | `+0x9c` |
| sign (flag `0x40`, `0x4cd05b`) | random **5 % per step** (`rand(100) > 0x5e`) | `town\sign\V%.2d.bmp` (40x32 patch) | 10 | `+0x184` ++ to 10, then clear; frame = list[`+0x184`] (0 shown at load) | (+0x168, +0xe8) | **Flag.wav** (`+0x8c`) at counter 0 |
| fluger (flag `0x20`, `0x4cd577`) | random **2 % per step** (`rand(100) > 0x61`) | `town\fluger\F%.2d.bmp` (64x64 patch) | 8 | `+0x1fc` ++ to 8, then clear | (+0x134, +0x40) | **Flugel.wav** (`+0x88`) at counter 0 |
| birds (flag `0x80`) | timer, see 3.3 | `TownBirds\Birds%d\sprites.16a` d=1..9 (552x92 each) | 57 | `+0xd8/+0xdc/+0xe0` ++ per step (one counter per flyer); a flyer draws while its counter < 57; when all `+0xc0` flyers are done the flag clears | window origin (positions are in the sprites), then `Town_add.bmp` (552x92 BMP) over it with the colour-key blit `+0x38` (`0` transparent; INFERRED role: sky overlay) | `+0x80` Birds1 (1 flyer) / `+0x84` Birds2 |
| horse (flag `0x100`) | timer, 3.3 | `TownBirds\HORSE%d\A%d\sprites.16a`, d = visit kind 1..5, a = 1..3 | 15 | `+0x140` ++ per step; at `n` -> -1, clear; frame -1 = draws frame 0 (idle) | `(+[0x4e], +[0x4f])` = table `0x5f66e0` (5 x (x, y)): (104,404) (104,404) (256,344) (448,400) (140,400) | by set (`+0x144`) k and frame f, in the **draw**: k0: f=14 `+0xa0` Horse2; k1: f=8 or 14 Horse2; k2: f=1 `+0xa8` Horse1, f=14 Horse2 (fires each draw while the frame matches); `+0xa4` Horse3 unused |
| baba (flag `0x200`) | timer, 3.3 | `...\BABA%d\A%d\sprites.16a`, d = visit kind 1..4, a = 1..2 | 31 (a1) / 32 (a2) | `+0x114` ++; at `n` -> -1, clear | `(+[0x43], +[0x44])` = table `0x5f6708`: (216,364) (308,424) (384,424) (580,384) | none |
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

## 4. Druid scene

Hover (`0x4cfd58`, the hit test is the human one): region 1 = shop, 2 = inn (tavern).

| region | effect |
|---|---|
| -1 | cursor reset; the three "entry sound" latches `+0x260 (=[0x98]) / +0xac / +0x264 (=[0x99])` cleared |
| 1 shop | draw `hili_shop.bmp` (152x164) at (+0x1a4, +0xe0). On **entering** from another region while the man animation is not the hover variant (`+0x2ec != 2`): stop `+0x248`, **man variant 2** (`+0x2ec = 2`, frame `+0x1e0 = -1`), flag `1`, run one step, play **Ddruid1.wav** (`+0x248`). Entry sound once (`+0xac`): stop `+0x254 / +0x258`, play **Denter2.wav** (`+0x250`) |
| 2 inn | draw `hili_tavern.bmp` (152x96) at (+0, +0xb8). Same for the woman (`+0x2a4`, frame `+0x168`, flag `2`, **Ddruid2.wav** `+0x24c`); entry sound **Denter1.wav** (`+0x254`) once (`+0x260`) |
| 8 leave | entry sound **Dout.wav** (`+0x258`) once (`+0x264`), stops the other two; no draw, no flag (the leave region is the bottom-left way out) |
| 4, `0x200`, `0x1000` | return at once (no flag, latches kept) |
| others | flags OR-ed |

**The man / woman variant (answers the old question).** `man\a%d%.4d.bmp` and `woman\a%d%.4d.bmp` (`a` = variant 1..3, frame 1..20 until the first missing file) are loaded into **three lists each** (`+0x2b0 + v * 0x14` man, `+0x268 + v * 0x14` woman; `0x4ce914`). Frame counts (install): man 19 / 19 / 20, woman 15 / 20 / 20. The animation state `+0x2ec` (man) / `+0x2a4` (woman) is the **variant index** (-1 idle). **Two starters** (CONFIRMED): (a) the hover above forces variant **2** (`a3`); (b) the ambient starter `0x4d00de`, every `rand(5000) + 3500` ms (`0xdac`) while idle: variant = 2 if the pointer is over that region, else **`rand(2)`** (a1 / a2); frame 0, flag, sound `Ddruid1` / `Ddruid2`. Which character is which region: the man's lists are the ones indexed by the shop state (`+0x2ec`), the woman's by the inn state (`+0x2a4`); the loader reads `woman` first and the lists in the object are `+0x268` (woman, state `+0x2a4`) then `+0x2b0` (man, state `+0x2ec`): **INFERRED** from the member order (man = shop, woman = inn; sprite sizes 48x72 / 84x128 and the places fit).
Step (`0x4cfbf6` man, `0x4cfb45` woman by symmetry, INFERRED for the woman's body): per 100 ms step frame ++ in the list of the current variant; at the list's count it resets, state -1, flag cleared. Positions: man: variant 0 / 1 -> (+0x150, +0xf4), variant 2 -> (+0x154, +0xe0) (`(v / 2)` terms: `+4 / -0x14`); idle (no animation): (+0x150, +0xf4), or (+0x154, +0xe0) frame 0 while the shop region is hovered. Woman: variant 0 / 1 -> (+0xa4, +0xc8), variant 2 -> (+0x98, +0xb8); idle (+0xa4, +0xc8), hovered (+0x98, +0xb8) frame 0. The man / woman bitmaps are opaque 24-bit patches.

| anim | trigger | assets | frames | rule | pos | sound |
|---|---|---|---|---|---|---|
| bug | every `rand(10000) + 10000` ms (`+0x304 / +0x308`, first stamp at load) | `town_druid\bug\sprites.16a` (640x268) | 183 = 3 x 61 | variant `rand(3)`; frame = variant * 61 + step, step ++ per step to 61, then hidden (`0x4cfc77`) | (0, +0xd4) | Dbug1 / 2 / 3 = `+0x21c` / `+0x220` / `+0x224` by variant |
| lizard | restarts **at once** whenever idle (`+0x318 == -1`) | `town_druid\lizard\sprites.16a` (100x120) | 42 | `rand(15)`: 0 -> seq 1 Dlizard2, 1 -> seq 2 Dlizard3, 2 -> seq 3 Dlizard4, else seq 0 Dlizard1 (12/15); the index table `0x5f68c8` (4 sequences, frames 1-based, `-1` ends) is in animation 4.11; step per 100 ms (`0x4cfcde`: ++ then test the end marker) | (0, +0x12c) | `+0x20c .. +0x218` |
| ambient | birds: global `0x628234` (first `rand(2000)+2000`, then each `rand(2000)+2000`): `Dbird` 1..3 by `rand(3)`; trees: global `0x628244`, `Dtree` 1..4 by `rand(4)`; wolf: `Dwolf1` every 60 000 ms; entry loop **`Dforest1.wav`** (`+0x244`, looped like the Crowd) | | | | | slots below |

Druid sound slots (`0x4cf2c0`, `this + 4 * idx`): `0x83..0x86` Dlizard1..4, `0x87..0x89` Dbug1..3, `0x8a..0x8c` Dbird1..3, `0x8d..0x90` Dtree1..4, `0x91` Dforest1, `0x92` Ddruid1, `0x93` Ddruid2, `0x94` Denter2, `0x95` Denter1, `0x96` Dout, `0x97` Dwolf1 (all `sfx\town_druid\`). Tick flags (`0x4d065b`): `1` man, `2` woman, `0x80` bug, `0x100` lizard. Draw order (`0x4cf65a`): townmain, hili_shop (hover 1 or man active), man, hili_tavern (hover 2 or woman active), woman, lizard, bug. Step 100 ms; no random rolls per step.

## 5. Kaarg scene

Hover (`0x4d244e`): 1 shop: draw `hili_shop.bmp` (40x76) at (+0x148, +0x100); entering plays **Kenter2.wav** (`+0x22c`), stops `+0x230`. 2 inn: `hili_tavern.bmp` (140x128) at (+0x1e0, +0xc4); entering plays **Kenter1.wav** (`+0x230`). 8: stops both. Regions 4, `0x200`, `0x400`, `0x800` return at once. Nothing else is region-driven: the NPCs animate **only from timers**.

| anim | assets (`town_kaarg\`) | frames | trigger (first delay at load; then) | step (`0x4d2f27`: flags `0x200` `0x4d2d87`, `4` `0x4d2dfc`, `0x400` `0x4d2ecc`, `0x800` `0x4d2e71`, always the gate `0x4d2c2c`) | draw pos | sound |
|---|---|---|---|---|---|---|
| girl 1 (flag `0x200`) | `girl1\g1000..g1030`, `g2000..g2029` (44x108) | variant 1: 31, variant 2: 30 | `rand(2000)+2000` after load; then `rand(5000) + 3500` ms; variant `rand(2)` (`+0x2c4`) | `+0x114` ++ to the list size, then flag clear, variant -1 | (+0xd8, +0x11c); idle = list 0 frame 0 | none |
| girl 2 (flag `4`) | `girl2\...` (68x104), same counts | 31 / 30 | same (`+0x2f8 / +0x2fc`), variant `+0x2f0` | `+0x2f4` ++ | (+0x104, +0x11c) | none |
| guard (flag `0x800`) | `guard\g0000..g0054` (72..76x68) | 55 | first `rand(2000)+2000`; then `rand(5000) + 7500` ms (`0x1d4c`) | `+0x1cc` ++ to 55 | frames 13..37: (+0x8c, +0x98); else (+0xb8, +0x9c) | footsteps by frame (`0x4d26a4`, gate latch `+0x258`): {5, 13, 21, 47, 55, 63}: `Ksteps21` if `rand(4) == 0` else `Ksteps2` (`+0x23c` / `+0x238`); {9, 17, 23, 51, 59}: `Ksteps11` / `Ksteps1` (`+0x244` / `+0x240`); {31, 69}: `Ksteps31` / `Ksteps3` (`+0x24c` / `+0x248`) |
| dervish (flag `0x400`) | `dervish\d0000..d0029` (112x148) | 30 | first `rand(500) + 4000`; then `rand(500) + 3700` (`0xe74`) | `+0x15c` ++ to 30 | (+0x1a0, +0x148) | none (the `Kman1.wav` below) |
| main gates | `maingates\m0000..m0010` (60x84) | 11 | region 8 hovered: `+0x1a0 += 1` to 10, **Kdoor1.wav** once on entering; else `-= 1` to 0 with **Kdoor2.wav** once on leaving | every step | (+0x98, +0x100) always drawn | `+0x78` |

(The guard frames 55..63 / 69 exceed the 55 frames: those branches never trigger; the set is copied from the source of the switch. CONFIRMED the switch, INFERRED that the upper values are dead.) Ambient (starters, every draw): **voices** `Kvox2/3/4` (`+0x20c / +0x210 / +0x214`) at `rand(3)+1` every `rand(2000)+2000` ms (process global `0x628224`, first value once per process); **birds** `Kbird1..4` (`+0x218..+0x224`) `rand(4)` every `rand(2000)+2000` (global `0x628240`); `Kman1.wav` (`+0x234`) every 45 000 ms; entry loop **`Kvox1.wav`** (`+0x228`, looped, `0x4d0d46`). The `+0x25c / +0x260` stamps are 0 at construction, so the first bird / `Kman1` fire on the first draw. Draw order (`0x4d1f6d`): townmain, hili_shop, hili_tavern, girl 1, girl 2, guard, dervish, gates. Step 100 ms. The scene starts with flags 0 (nothing runs until a timer fires).

## 6. Between visits (CONFIRMED)

| kept | where |
|---|---|
| per visit, new: human horse / baba / dervish kind | loader `0x4cb6c6` (kind `rand`, positions from the tables) |
| process-global: first-bird delay `0x628254`, druid birds / trees `0x628234 / 0x628244`, Kaarg voices / birds `0x628224 / 0x628240`, the step clocks, **stars play counter `0x628260`** (every 10th start plays) | `0x4cb05d`, `0x4cd2ac`, `0x4d00de`, `0x4d26a4` |
| none else: all animation state is re-initialised by the loader / load (`0x4ca7e2`: flags 0, gate frame, `+0x2e`, timers) | |

The scene is **rebuilt from the loader every opening** (`+0x80` runs the loader `+0xa0`), the objects live for the session ([town-hero 1](town-hero.md#1-purpose-and-entry--exit)). The music is started by the scene opener, not the scene (`0x48bbc0`; b14 human, b16 Kaarg, b15 druid: CONFIRMED earlier, [town-hero 1](town-hero.md#1-purpose-and-entry--exit)).

## 7. Implementation recipe (data a pure module can use)

Per scene a `SceneSpec`: `step_ms` (67 / 100), `patches` (static layers in draw order), `regions` (mask byte -> flag), `hover` (flag -> action), `click` (flag -> message / speech), `anims` (name, assets, frames, trigger, rule, pos, sound), `ambient`, `entry_loop`. Minimal tables:

```
REGION_OF_BYTE = {0x80: 2, 0x90: 1, 0xa0: 8, 0xb0: 0x10, 0xc0: 4, 0x20: 0x400, 0x40: 0x800, 0x50: 0x1000, 0x60: 0x200}   # everything else -1
CLICK = {   # region -> message / speech (press, left button)
  human: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d) if Var(0x301) else speech("plagatguard"), 0x10: 0x41f},
  druid: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d), 0x10: 0x41f, 0x200: speech("druidinnkeeper_%d" % Var(0x300)), 0x1000: speech("druidshopkeeper_%d" % Var(0x300))},
  kaarg: {1: 0x42a, 2: 0x42b, 8: (0x442, 0x42d), 0x10: 0x41f, 4: speech("kaargwoman_%d"), 0x200: speech("kaargwoman_%d"), 0x400: speech("kaargman_%d"), 0x800: speech("kaargguard_%d")}}   # %d = Var(0x300)
HOVER_PATCH = {human: {1: ("town/shop_l.bmp", 0x108, 0x108), 2: ("town/tavern_l.bmp", 0x90, 0x14c)},
               druid: {1: ("town_druid/hili_shop.bmp", 0x1a4, 0xe0), 2: ("town_druid/hili_tavern.bmp", 0, 0xb8)},
               kaarg: {1: ("town_kaarg/hili_shop.bmp", 0x148, 0x100), 2: ("town_kaarg/hili_tavern.bmp", 0x1e0, 0xc4)}}
ENTRY_LOOP = {human: "SFX/Town/Crowd.wav", druid: "sfx/town_druid/Dforest1.wav", kaarg: "sfx/town_kaarg/Kvox1.wav"}   # looped, priority 0x80
```

Anim rows are those of sections 3.2, 4, 5 (frames, positions, sounds, timers). Random: use the engine's seeded RNG; `rand(n)` = uniform 0..n-1 (the exe's `FUN_004a0fd0`). The scenes need an RNG, a monotonic ms clock, the `Var(0x300)` / `Var(0x301)` reads ([town 2](town.md#2-state-machine-of-a-visit-confirmed-edges-each-edge-names-its-routine)) and the sound player; everything else is data. Headless-testable: `REGION_OF_BYTE` on the three real masks (dense-region boxes of section 2), `CLICK`, the stars every-10th rule, the guard direction / sound rule, the gate counter, the druid variant rule, the timers with a fake clock.

## 8. Open questions

1. The woman's body `0x4cfb45` was taken by symmetry with the man's `0x4cfbf6` (INFERRED) and which of man / woman belongs to which region rests on the member order (section 4).
2. The guard-sound start value `+0xf0` (heap; the build starts it at 1, section 9). *(The `Town_add.bmp` role is answered in section 9.)*
3. The speech-id to file mapping for the NPC click lines (`druidinnkeeper_%d`, `kaarg*_%d`; the chapter value ranges) and what message `0x41f` does in a scene (INFERRED = ESC menu).
4. The load routines' initial timer stamps of the druid scene (`0x4ce641`, only the Kaarg and human ones were read).
5. Play-test only: the retrigger of the horse sounds (one call per draw while the frame matches), whether the dither noise of the human mask can be felt.

## 9. L6 round (REA + the build, 2026-11-14)

CONFIRMED (REA, `allods2.exe`):
- **Guards `0x4cce81`**: the **sound test is in the guards' tick**, on the direction the hover just set: `frame += dir`; `dir == 1 && +0xf0 == 0` -> Guard2, `+0xf0 = 1`; `dir == -1 && +0xf0 != 0` -> Guard1, `+0xf0 = 0`; then clamp (`< 0` -> 0, `>= n` -> `n - 1`, dir 0). The hover sets `dir = 1` at every call, so a cursor off the gate with the latch at 0 plays Guard2 on the next step.
- **Birds starter `0x4cae28`** (flag `0x80`, group `rand(3)`, count `rand(3) + 1`, Birds1 for one flyer else Birds2, counters zeroed) **returns the next delay `rand(2000) + 1000`**, and the **draw `0x4caf00` stamps `+0xb8 = now` on every draw while the flyers are up** (so the next delay counts from the end of the flight); a flyer draws while its counter `< n`, the flag clears when all are done. **`Town_add.bmp` (vtable `+0x38`, colour-key blit at the origin) is drawn only while flyers are up** (answers the old open question: it is the foreground layer that covers the birds).
- **Stars `0x4cd2ac`**: exactly the section 3.2 rule: sound at counter 0, `++`, `< 9` shows frame = counter (S01..S08), else global `++` (10 -> counter and global 0), nothing shown, flag clear.

Measured on the install (frame counts equal the spec's numbers; one correction): the Kaarg girls' second variant is numbered **`g2001..g2030`** (30 files, not `g2000..g2029`); variant 1 is `g1000..g1030`.

INFERRED (decisions of the build, each marked in `engine/townscene.py`): the order inside one draw is step then starters (a started animation shows its first frame in the draw that starts it); the guard latch `+0xf0` starts at 1 (guards up, no spurious sound on the first step); the idle baba is not drawn (the horse and the dervish are, CONFIRMED for the horse); the horse sounds fire once per frame arrival (the exe fires every draw the frame matches); the Kaarg footstep sets above 55 are dead; druid / Kaarg entry latches are cleared by region -1 (Kaarg by analogy with the druid); the druid man and woman have separate ambient timers (`rand(5000) + 3500`, first one from the load), the druid birds / trees / wolf stamps are 0 at construction like the Kaarg ones (fire on the first draw); the click sound stub of shop / inn plays nothing; `0x10` reports ("menu",) and the shell ignores it until the menu step.
