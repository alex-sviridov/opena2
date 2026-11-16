# m3: the hall of fame screen

Status: **m3 done** (`engine/shell/hall.py`, `tests/test_engine_hall.py`, golden `hall` / `hall_ok_hover`); **not yet watched in the window: VERIFY IN GAME (section 4)**.
Facts are **CONFIRMED** (read in `allods2.exe`, GOG 1.01, routine addresses) or **INFERRED**; engine choices are **DECISION**.

## 1. What the exe does (REA)

Main menu button 6 posts `0x429`. The window is class vtable `0x5cd288` (ctor `0x45b695`, resource id `0x4b0`, stored at `game+0x11c`; show `0x48b16d` -> slot `0x80` = `0x45bb82`, which sets the screen mask bit `0x1000`).

- **Pictures:** `main\graphics\famehall\hall.bmp` (640x480, at the screen origin), `graphics\interface\Docs\OK\Ok_l_off.bmp` and `Ok_l_on.bmp` (44x32, loader `0x45bc8e`), click sound `SFX\ChrGen\Ok.wav` (`0x45bea2`).
- **Table (`0x45b90e` layout, `0x45c159` paint):** one row per entry of the hall object (`client+0x598`, list at `+0x10`, up to 10). Row i: `y = 0x91 + trunc(i * 1.5 * H)` (`0x5cd310` = 1.5; H = the line height of font4, `DAT_00620dc8`, 17 px in the install: step 25, 51, 76 ...). Three columns, all font4 with shadow 1 (`0x45d536`, offset 1):
  | column | x | width | text | alignment | colour table |
  |---|---|---|---|---|---|
  | rank | `0x91` | 25 | `"%d."` (`0x5f1094`), i + 1 | left | brown gradient `0x620e80` (65, 47, 20) |
  | name | `0xaf` | 200 | entry `+0` (CString) | left | the same brown |
  | score | `0x181` | 100 | `"%d"` (`0x5f1098`) of entry `+4`, then `FUN_00475263` = a comma every three digits | **right** at `0x181 + 100 = 0x1e5` | purple gradient `0x620e38` (101, 39, 61) |
- **OK button:** no child with a picture; a rect (560, 416) size 44x32 (`+0xa8`, `0x45b7ce`; a zero-rect text button with id `0x445` is also created). Move (`0x45bf50`): inside the rect `+0xc4` = `Ok_l_off` (button up) or `Ok_l_on` (left button down), outside none; the picture is drawn at the rect's top-left after the background (`0x45c1e2`). Press (`0x45c023`): inside -> the click sound and `Ok_l_on`. Release (`0x45c0d3`): inside -> `0x45c3d7` = message `0x445` (close).
- **Close:** the child-closed handler `0x489505` clears bit `0x1000` and posts `0x421` (the menu). Corrects [shell 1](shell.md): the hall's screen-mask bit is `0x1000` (`0x40` is the credits, handler `0x489cf4`).
- **Keys:** slot `0x6c` = `0x4dc326` (Tab / arrows): no Esc / Enter handling of its own (INFERRED: nothing closes it by key). **No music call** in the show path: the playing music is left alone.
- **Credits -> hall:** closing the credits (`0x489d17`) posts `0x429` when `FUN_00493da0` (`Var(0x300) >= 0x78`) is true, else `0x421`.

## 2. Engine

`engine/shell/hall.py` (screen `hall`, edges `menu -> hall`, `credits -> hall`, `hall -> menu`); main-menu button 6 is enabled; `Shell.campaign_finished()` is `FUN_00493da0` on the running campaign's variables; `Credits.close()` picks hall or menu (a campaign ending always reaches the hall, with its fresh entry from `Shell.record_ending`). The screen reads `Shell.load_hall()`.

- **DECISION:** Esc and Enter close the screen like every other dialog (the exe has no key close; the mouse OK is exact). `music = None` (as the exe).
- **Fixed on the way:** the install's own `famehall.dat` is a loose file the game file system does not list, so the first run used to start with an empty hall; `famehall._install_copy` reads it from `fs.install`.
- INFERRED: the name column is not clipped (the exe draws it whole; 200 px is the widest the layout allows, the install's names fit).

## 3. Tests

`tests/test_engine_hall.py` (columns, row step, thousands separators, hover / held / release, outside release, Esc, credits routing, install fallback), `tests/test_engine_shell.py` (graph), goldens `hall`, `hall_ok_hover`.

## 4. VERIFY IN GAME

1. Main menu -> HALL OF FAME: the parchment with the ten install entries (Diamond 70,006 ... Nick 0), brown rank and name, purple right-aligned score.
2. Hover OK (bottom right): the lit seal; hold: the pressed seal and the click; release over it: back to the menu; release outside: stays.
3. Finish the campaign (or load a late save and open the credits): credits end -> hall with the new entry; a fresh menu CREDITS -> menu.
4. Compare the row spacing and the colours with the original's screen if you can.
