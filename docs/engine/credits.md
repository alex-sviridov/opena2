# m2: the credits screen

Status: **m2 done** (`engine/shell/credits.py`, `tests/test_engine_credits.py`); **not yet watched in the window: VERIFY IN GAME (section 3)**.
Facts are CONFIRMED (REA / objdump of GOG `allods2.exe`, routine given) or **INFERRED**.

## 1. What the exe does

| Fact | Routine |
|---|---|
| Message `0x428` (main-menu CREDITS, or the campaign ending `0x41d` when `Var(0x300) >= 0x78`): music `music\credit.wav` (playlist `[credit]`), then the credits window | `0x48bee5` |
| Constructor loads `main\text\credits.txt` (CR-split, `FUN_00474585`); every line starting with `"` is a picture `main\graphics\logo\<name between the quotes>` (`nival.bmp` line 0, `monolith.bmp` line 127 in the GOG text) | `0x43c055` |
| Cursor hidden while the window runs, shown again after; the screen is cleared to black every tick | `0x43bbae`, `0x43bc07`, `0x43bdc1` |
| Scroll offset `+0x9c` starts at **480**; a tick needs `timeGetTime() - last >= 23` ms and does `offset -= 1` (about 43 px/s) | `0x43bb8a`, `0x43bd50`, `0x43bd5d` |
| First visible line `+0x98` = `|offset| / lineH` (0 while the offset is >= 0); lines drawn: `max(0, first - 10)` .. `min(first + 480 / lineH + 1, count)` (the 10-line margin keeps a tall picture alive) | `0x43bd7b-0x43be5e` |
| Line y = screen top + offset + i * lineH, `lineH` = font1 height; text centred on x + 320 (flag 2), font1; **highlight table `0x61fa80` for line 0 and for a line after an empty line, normal table `0x620928` otherwise**; a picture is centred on x + 320 by its width, top at the line y | `0x43beb3-0x43c00c` |
| The scroll ends when `first >= count` (everything scrolled off): `0x43c2d2` posts `0x445`, the window closes | `0x43c02b`, `0x43c2d2` |
| Close: `FUN_00493da0` (`Var(0x300) >= 0x78`) -> hall of fame `0x429`, else the main menu `0x421` ([shell 3.3](shell.md)) | |
| INFERRED: any key press or button press closes early (both handlers `0x43bc74` / `0x43bc95` call `0x43c2d2`) | |

## 2. Engine

`Credits` screen (graph: `menu` / `game` -> `credits` -> `menu`), `music = "credit"`, no cursor. Main menu button 3 is enabled. The last mission's ending (`Outcome.kind == "ending"`, after its chapter video) goes to `credits`.
`DECISION`: the hall of fame screen is not built, so the credits always lead to the menu (the hall entry is still recorded, `Shell.record_ending`). The tick uses an exact 23 ms accumulator (the exe takes the timer's granularity). Line height = `Font.line_height()` (INFERRED equal to the exe's font height call `0x402a90`).

## 3. VERIFY IN GAME

CREDITS opens on black with `credit` music; the Nival logo rises first, headings brighter than names, the Monolith logo centred, the end returns to the menu with menu music; a key / click ends it early; the arrow is hidden meanwhile; finishing the last mission (or a loaded ending) shows it.
