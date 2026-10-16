# Palettes

Code: `allods2/graphics/palette.py`. Tools: `tools/validate_palettes.py`;
`tools/palette_contact.py` → `out/contact/palettes.png` (every distinct
palette).

## 1. Where palettes live

No raw 768/1024-byte palette files, nor anything that size plus a small
header (CONFIRMED, size scan of all 5,299 files). Every palette is 256 ×
4-byte entries in one of:

| Source | Files | Palettes | Distinct | How the game reads it |
|---|---:|---:|---:|---|
| `.256` sprites (trailer bit 31) | 1,523 | 1,523 | 1,064 | first 0x400 bytes ([sprites](sprites.md)) |
| `*b.256` smoothing overlays | 394 | 394 | 4 | same; 391 **all zero** |
| `.16a` sprites (trailer bit 31) | 782 | 782 | 760 | first 0x400 bytes |
| unit / projectile `.pal` | 163 | 163 | 129 | BMP-wrapped, seek 0x36, read 0x400 (§3) |
| `units/*/human.pal` | 3 | 48 | 32 | raw 16 × 0x400 (§4) |
| 8-bit `.bmp` (terrain, interface) | 63 | 63 | 10 | DIB colour table ([bitmaps](bitmaps.md)) |
| built in code | – | 5 + 14 ramps | – | `FUN_00463d30` (§6) |
| **total from files** | 2,928 | 2,973 | 1,942 | |

CONFIRMED: `tools/validate_palettes.py` parses all and checks the rules
below. The 6 `.256` and 3 `.16` files without bit 31 carry no palette
(fonts take colours from the caller).

## 2. Entry layout

Entry `i` at `4·i`: blue, green, red, reserved (never read). Windows
RGBQUAD, 0x400 bytes. Example: `0A 14 1E 00` at offset 4 → entry 1 =
RGB (30, 20, 10).

- CONFIRMED (`FUN_00425bee`): R from `+2`, G `+1`, B `+0`, `+3` unread.
  `CDib::MakePalette` (`FUN_004568f6`) builds a GDI `LOGPALETTE` with
  `peRed = q[2]`, `peGreen = q[1]`, `peBlue = q[0]`, `peFlags = 0`.
- CONFIRMED: channels are 8-bit, not 6-bit VGA (`c >> (8 − bits)` treats
  255 as full scale). All non-zero palettes exceed 63, low 2 bits evenly
  distributed; none uses `×4` or `<<2|>>4` scaling (one overlay is
  coincidentally consistent with it).
- CONFIRMED (data): reserved byte is 0 in every `.pal`, `human.pal` and
  BMP; non-zero in 101 `.16a` icons and 2 `.256` cursors
  (`cursors/attack.256`, `pickup.256`): leftover tool data, ignored.
  `Palette` keeps it for byte-exact round trips.
- **No reserved indices**: nothing treats an index specially except shade
  mode 0 (index 0 → 0); transparency comes from RLE skips. INFERRED
  (data): entry 0 is black in 1,912 of 1,917 `.256` palettes and every
  `.pal`, `human.pal`, BMP; the other 5 have magenta (255, 0, 255) ×3 or
  near-black.

## 3. Unit palettes: `palette.pal`, `palette2.pal`, …

CONFIRMED (`FUN_0047f108`): `units.reg` `Palette` count `N`; for
`i = 1..N` the file is `<unit dir>\palette<i>.pal`, digit dropped for
`i = 1`; open, **seek 0x36**, read 0x400. `FUN_004824cc` reads
`graphics\projectiles\projectiles.pal` and `projectile_.pal` the same way
→ 16-level `BRIGHT2` tables without tint, `DAT_00630efc`/`DAT_00630f00`.

CONFIRMED (data): all 163 are 8-bit BMPs, 14 + 40-byte header,
`bfOffBits = 0x436`; sizes 128², 160², 64² or 2²; `biClrUsed` 256 or 0.
INFERRED: the game ignores pixels and header fields, needing only the
54-byte header; `Palette.save(path, "pal")` writes a 16×16 BMP with pixel
i = index i.

## 4. `human.pal`: player colours

CONFIRMED (`FUN_0047f108`, `FUN_0048392f`): raw 0x4000 bytes (16 × 0x400,
no header) → `DAT_0062cb78`. Palette *p* = human sprite palette for
**player colour p**:

- each → 16-level `BRIGHT2` table *with* tint
  (`FUN_00425bee(pal + p·0x400, 0x10, 2, 1)`); palette 0 also → 16-level
  `GRAY` (`…, 0x10, 5, 0`);
- for rows `15 − k` (k = 0..7) the 16-bit value at byte 0x148 (**index
  164**) is copied into both `0x629c90 + p·0x20 + k·4` and `+ k·4 + 2`
  (CONFIRMED asm `0x480446`–`0x4804d2`: same table and row; the
  decompiler's extra argument is spurious).

CONFIRMED (data): in all three files index 164 differs per palette: blue
(87, 120, 228), green, red, orange, violet, yellow, teal, grey, then
darker variants for p = 8..15. Palettes differ only in 55–59 scattered
indices between 4 and 225: player colour is **not** a contiguous range.
`humans/human.pal` differs from the identical `heroes/` and `heroes_l/`
copies. CONFIRMED: only `humans/human.pal` is used, by every unit and
hero: the exe's one `human.pal` string (`0x5fc858`) is opened by
`FUN_0047f108` (`0x480380`) into the 16 player tables (list `0x62cb28`);
a2mgr holds no palette path; `heroes*/human.pal` and `heroes*/palette.pal`
are never opened (hero folders are not units.reg files).

Result: a **16-entry colour table per player** in the `.16` font format
([sprites](sprites.md)): slot `s` = player colour × `(s // 2 + 1)/8`.
`FUN_0047ab33` installs `0x629c90` as a text-colour table (§6).
Implementation: `player_text_ramp(rgb)`.

## 5. Conversion: shade tables (`FUN_00425bee`)

The game draws to **16-bit surfaces**, never a hardware palette. Every
palette becomes a *shade table* (vtable `0x5d5308`, constructor
`FUN_00425b0f`): `+4` levels (rows), `+8` `u16 rows[levels][256]`
(`levels << 9` bytes). CONFIRMED (a2mgr Ordinal_37 `0x1000a450`, via exe
thunk `FUN_00420440`): `row(level)` = `table + 8 → data + level·0x200`.

`FUN_00425bee(this, src_quads, levels, mode, use_tint)` (CONFIRMED); `c` =
source channel, `t` = tint byte (R `0x62c888`, G `0x62c889`, B
`0x62c88a`, 0 without tint); integer division truncates; results clamped
0..255:

| mode | rows | row r, channel | Use |
|---|---|---|---|
| 0 `MASK` | 1 | index 0 → `0x0000`, others `0xFFFF` | silhouette |
| 1 `PLAIN` | 1 | `min(c + t, 255)` | |
| 2 `BRIGHT2` | N | `(c + t)·k·2 / N`, k = N − r | units, human.pal, projectiles; N = 16: row 0 ×2, 8 ×1, 15 ×1/8 |
| 3 `BRIGHT32` | N | `(c + t)·k >> 5`, k = N − r | terrain, N = 0x60: row 0 ×3, 64 ×1 |
| 4 `FADE16` | 16 | `c·k >> 4`, k = r + 1, no tint | every `.16a` sprite and font, code gradients, smoke; row 15 ×1 |
| 5 `GRAY` | N | `((r+g+b)·k·2 / 3) / N` all channels, k = N − r, no tint | grey-out of human palette 0 and unit palettes |

Then `pack16`: `px = (R >> (8 − Rbits)) << Rshift | (G >> (8 − Gbits)) <<
Gshift | (B >> (8 − Bbits)) << Bshift`; widths `0x5fb960/964/968`, shifts
`0x5fb958/95c`, `0x62c9bc` (from the surface pixel format, 5-6-5 in
practice, [bitmaps](bitmaps.md)). **Row order**: modes 2, 3, 5 brightest
first; mode 4 darkest first.

**Low-memory variant, not reproduced** (user decision). CONFIRMED: when
`GlobalMemoryStatus().dwTotalPhys` < 24,000,000, `FUN_0045752b` sets
`DAT_0062c9b8 = 1`: mode 4 divides by 18, blend tables shrink 0x10000 →
0x2000 entries, `FUN_00487a00` allocates a half-size buffer, shadow
blitters switch variants. Legacy 1999 memory saver.

**FADE16 is the `.16a` alpha table** (CONFIRMED): `.16a` palettes are
converted in mode 4 by `FUN_004313db` (chrgen cube), `FUN_004364c3`
(chrgen), `FUN_00474320` (global map), `FUN_00463a16` (fonts) and others.
The blitter adds pixel word `a << 9 | index << 1` to row 0 → row `a`,
column `index`: `colour·(a+1)/16`, destination × `(15 − a)/16`.

Worked example: index 1 = (100, 200, 3), mode 2, N 16, no tint: row 0 →
(200, 255, 6); row 8 → (100, 200, 3); row 15 → (12, 25, 0). Row 8 in
5-6-5: `(100>>3)<<11 | (200>>2)<<5 | 3>>3` = `0x6640`.

### Callers (CONFIRMED)

| Caller | Source palette | levels, mode, tint |
|---|---|---|
| `FUN_0047f108` / `FUN_0048392f` | `human.pal` × 16 | 16, BRIGHT2, yes; palette 0 also 16, GRAY, no |
| `FUN_0048392f` via `FUN_00426be0` | three object registries (`FUN_00422f70`/`FUN_00422ff0`/`FUN_00423030` lists) and one global; INFERRED units, structures, objects | 16, BRIGHT2, yes |
| `FUN_0047b899` / `FUN_0048392f` | terrain: first tile of each of 32 slots | 0x60, BRIGHT32, yes |
| `FUN_004824cc` | `projectiles.pal`, `projectile_.pal` | 16, BRIGHT2, no |
| `FUN_00482125` (projectile type, lazy) | own `.256` + `b.256` palettes if `Palette ≠ 0`, `A16 = 0`; `.16a` palette if `A16 = 1` | 16, BRIGHT2, yes; `.16a`: 16, FADE16, no |
| `FUN_004824cc` | `projectiles\smoke%d\sprites.256` ×2 | 16, FADE16, no |
| `FUN_00463d30` | 5 code gradients (§6) | 16, FADE16, no |
| `.16a` loaders (`FUN_004313db`, `FUN_004364c3`, `FUN_00463a16`, `FUN_00474320`, …) | embedded `.16a` palettes, incl. fonts | 16, FADE16, no |
| interface/equipment loaders (`FUN_004478af` `subobj.256`, `FUN_0046dd6a`, `FUN_0047bedd`, …) | embedded `.256`/BMP | 1, PLAIN |
| `FUN_00473010` | a unit's palette when no table exists yet | 16, BRIGHT2, yes |
| `FUN_00468640` (unit draw) | unit palette, when the unit has effect 0x2c | 16, GRAY, no |

Terrain slot *s* (0..31) = `tile{s/4 + 1}-{v + 4·(s mod 4)}.bmp`, v 0..3.
CONFIRMED (data): all 52 `tile*.bmp` share one palette; `dirt.bmp` has
its own.

### GDI palettes

`CreatePalette` only in `FUN_004568f6` (`CDib::MakePalette`) and
`FUN_00456a13` (copies the system palette via `GetSystemPaletteEntries`
when a DIB has no colour table on a palettised display);
`RealizePalette`/`SelectPalette` are MFC imports; `_SmackBlitSetPalette`
is for Smacker video (absent). CONFIRMED (imports, xrefs). No
`IDirectDrawPalette::SetEntries`, no palette rotation/colour cycling found
(INFERRED: xref search, not proof).

## 6. Palettes built in code (`FUN_00463d30`)

CONFIRMED. Five 256-entry gradients, entry i = `(i·R/255, i·G/255,
i·B/255)`, 16 levels mode 4: `0x62a6f0` (185, 159, 73) gold →
`DAT_0062b088`; `0x629848` (255, 255, 116) yellow → `DAT_0062af8c`;
`0x62ab10` (0, 0, 0) black → `DAT_0062b064`; `0x62a2c8` (65, 47, 20)
brown → `DAT_0062b048`; `0x629e90` (101, 39, 61) purple → `DAT_0062b000`.

Fourteen 16-entry tables of 16-bit colours, i = 0..15 (`/` truncates):

| Table | RGB |
|---|---|
| `0x62afb8` | (8, 8, 8) constant |
| `0x629c48` | (17i, 17i, 17i) |
| `0x62aaf0` | (14i, 14i, 14i) |
| `0x62af58` | (185i/15, 159i/15, 73i/15) |
| `0x62af38` | (107i/15, 154i/15, 120i/15) |
| `0x62afd8` | (255i/15, 255i/15, 64i/15) |
| `0x62b068` | (255i/15, 64i/15, 64i/15) |
| `0x62a6d0` | (64i/15, 255i/15, 64i/15) |
| `0x62a2a8` | (160i/15, 120i/15, 50i/15) |
| `0x62af98` | (139i/15, 65i/15, 32i/15) |
| `0x62af18` | (150i/15, 90i/15, 0) |
| `0x62b028` | (141 − 61i/15, 126i/15, 49i/15) |
| `0x62b008` | (255 − 175i/15, 252i/15, 98i/15) |
| `0x629c68` | ((15−i)·160/15 + 32, (15−i)·148/15 + 32, (15−i)·88/15 + 32) |

**They are text colours** (CONFIRMED). Gradients colour **`.16a`
fonts** (glyph index → gradient position, alpha → FADE16 row): e.g.
`FUN_0042bc1b` formats a number and calls font `DAT_0062af90` with
`DAT_0062b088.row(0)` (gold); brown (`DAT_0062b048`) in `FUN_00461429`,
`FUN_004affc1`; black in `FUN_00463d18`; `FUN_004627f6` draws strings
twice with an offset (shadow, [fonts](fonts.md#drop-shadow-fun_004627f6)).
16-entry tables colour **`.16` fonts** (`FUN_004593a1`).

**Message-log colours** (CONFIRMED `FUN_0047ab33`, `FUN_0040dac9`, key
handler `0x40d2a5`): six current text-colour pointers
`0x5fb97c…0x5fb990`. A modified key toggles `DAT_0062c9e0`, calls
`FUN_0047ab33(state)`, shows `patch.txt` `0x55 + state` "Standard /
Alternative message colors". Messages go to the log (`view+0xa28`,
`FUN_004021fe`) with a table and lifetime in ms:

| Slot | Standard (0) | Alternative (1) | Used for |
|---|---|---|---|
| `0x5fb97c` | `0x629c48` grey 17i | `0x629cd0` | system/status messages, e.g. option toggles (2000 ms); 42 users |
| `0x5fb980` | `0x62aaf0` grey 14i | `0x629d70` | "Picked up N pieces / N gold" (`main.txt` `0x55`–`0x59`; 3000 ms) |
| `0x5fb984` | unchanged | `0x62afd8` | chat kinds 0 and 4 (10000 ms) |
| `0x5fb98c` | unchanged | `0x629cb0` | chat kind 1 |
| `0x5fb988` | unchanged | `0x629d10` | chat kind 2 |
| `0x5fb990` | unchanged | `0x629c90` | chat kind 3 |

Chat (`0x413cd8`) uses those four only in state 1 with sender flag
`+0x41c & 1`; otherwise the sender's player ramp `0x629c90 +
32·player[+0xc]` (§4). A chat line of kind ≠ 4 is dropped when the viewer
has "silent" (bit 4) set for the sender. **Quirk**: state 0 resets only
the first two slots; all six start as `0x629c48` (`0x62aaf0` for the
second), so after Alternative and back the chat slots keep Alternative
colours.

**Chat kinds** (CONFIRMED): sent by `FUN_0041cb2c(text, kind, target)`;
the in-game input (`0x48f167`…`0x48f2f1`, widget 0x445) picks the kind
from the first character; a2mgr's `g_altchat` (Ordinal_87, `0x100039a0`)
prefixes kinds 1–3 with `patch.txt` 0xdf–0xe1:

| Kind | Typed as (`help.txt`) | a2mgr tag | Sent by |
|---|---|---|---|
| 0 | `text`: everyone nearby | none | no prefix |
| 1 | `-text`: all allies | `[ally] ` | `-` when `FUN_0049a950` (INFERRED name match) returns −1 |
| 2 | `-name text`: one player | `[private] ` | `-` + name; `target` = that player |
| 3 | `=text`: all players | `[shout] ` | `=` |
| 4 | chat box of "Create or Join Game" / map select | none | `FUN_00454540` (Enter in input from `FUN_0044faad`, `dialogs.txt` 0x85); shown even when the sender is silent |

### Which text uses which table

CONFIRMED (every reference outside `FUN_00463d30`/`FUN_0047ab33`). Three
never-written `.data` pointers are constants: `0x5fa5a0` → `0x62aaf0`,
`0x5fa5a4` → `0x629c48`, `0x5fa5a8` → `0x62af58` (`0x5fa5ac` →
`0x62afd8`, no reader). Routine lists CONFIRMED; roles INFERRED from the
drawn strings, except where code shows them (shadow, tooltip, drop-down
hover, flying damage).

| Table | Routines (+ pointer reads) | Used for |
|---|---:|---|
| `0x62afb8` (8, 8, 8) | 1 | `.16` drop shadow: font slot 6 (`FUN_00463a06`), under nearly all text via `FUN_004627f6` |
| `0x62aaf0` grey 14i | 28 (+ 96 of `0x5fa5a0`) | **normal** UI text: dialog widget labels, buttons, lists (font1; Options, Save/Load, network and modem setup, lobby, Victory), input boxes, "Drop money", hero creation, log slot `0x5fb980`, font3 hotkey numbers (`FUN_004cec31`, `F%d`), quest list (`FUN_004e78fa`), inventory (`FUN_0049fc52`) |
| `0x629c48` grey 17i | 21 (+ 18 of `0x5fa5a4`) | **highlighted** variant (selected entry, hovered button), system slot `0x5fb97c`, FPS counter (`FUN_00406fea`), in-game options panel (font2, `FUN_00450f0b`), identify prompt (`FUN_004c353c`) |
| `0x62af58` gold | 13 (+ 6 of `0x5fa5a8`) | panel **labels** (font2): unit info (`FUN_0046fe90`: Body, Agility, …, Health, Mana), inventory/shop (`FUN_0049fc52`), quest panel (`FUN_004b746f`, `FUN_004b8b61`), kill stats (`FUN_004316ad`), tips (`FUN_004e6f45`), "No units selected"; menu/list items in widget classes (`FUN_004dfd32`, `FUN_004dd88a`, …) |
| `0x62af38` sage | 3 | **values** beside gold labels: unit info numbers (`%d/%d`, stats), quest panel numbers |
| `0x62af18` orange | 3 | unit info headers ("Skills"/"Resistance", `main.txt` 0x1b/0x1c); **hovered** drop-down item (`FUN_004dfd32`: gold → orange) |
| `0x62a2a8` tan | 1 | **tooltip** text (`FUN_0042a1e9`: brown frame, font2, one line per `#` part) |
| `0x629c68` inverted ramp | 2 | body text (font2) of the framed message box `FUN_00475245`/`FUN_00475c73` (three frame sprites, font4 title; INFERRED sign/scroll window) |
| `0x62b068` red | 7 | "HIRED" in taverns (`FUN_0049f25e`, `FUN_004a46a1`, `FUN_004a6be6`); some inventory text (`FUN_0049fc52`), quest list (`FUN_004e78fa`), `FUN_004478af` |
| `0x62afd8` yellow | 1 (+ `0x5fb984`) | chat kinds 0, 4 with Alternative colours |
| `0x62a6d0` green | 0 live | only the flying-damage quirk |
| `0x62af98`, `0x62b028`, `0x62b008` | 0 | built, never referenced |

**Quirk** (CONFIRMED `FUN_0040dac9` `0x412f22`–`0x412f5e`): with "Flying
damage" on (`view+0xabc`, `main.txt` 0x66/0x67) the HP handler picks green
(HP ≥ max/2), yellow (≥ max/4) or red into a local (`ebp−0x47c`) that is
**never read**; the number (`FUN_004617aa`) uses the player ramp
`0x629c90 + 32·player`.

## 7. Palette effects

### Day/night tint (`FUN_0047a208`), CONFIRMED

With day/night on (`DAT_0062c938 ≠ 0`), game time sets the tint added to
every palette in modes 1–3; off → (0, 0, 0). Formula table (with the other
lighting parameters it sets): [lighting §1](../mechanics/lighting.md).
`FUN_0041f200` re-evaluates every 20 game minutes, then calls
`FUN_004ad552` (terrain light map) and **`FUN_0048392f`**, which rebuilds
every tinted table (human, unit, terrain, structure, object): time of day
is applied at conversion, not per pixel. Implementation:
`lighting.daylight(minutes)`, `daylight_tint(minutes)`,
`shade_table(rgb, levels, mode, tint)`.

### Others

- **Brightness levels** (modes 2/3) replace per-pixel lighting; rows come
  from light maps ([lighting](../mechanics/lighting.md)). CONFIRMED.
- **Hover highlight**: `FUN_00468640` forces row 0 (×2) for the unit
  stored at view `+0x994` when flag `+0x40c` is 0 (CONFIRMED code;
  INFERRED: unit under the cursor).
- **Grey-out** (mode 5): `FUN_00468640` uses a 16-level GRAY table of the
  unit's palette with **effect 0x2c** = Stone Curse (CONFIRMED).
  `FUN_0046600b` looks up an effect id (high 16 bits of u32 entries).
- **Effect 0x20** (Invisibility): visibility check and 50 % blit
  ([sprites](sprites.md)); the 50 % blit is `+0x34`, `FUN_004271d0` →
  `FUN_00459926`: `dst = (dst >> 1 & m) + (src >> 1 & m)`, `m =
  0x62c9c0` = channel masks without top bits (0x7BEF for 5-6-5); its
  shadow uses the lighter level `0x62c898`.
- **Effect ids = projectile type ids** (`projectiles.reg` `ID`), both from
  the spell number. CONFIRMED:
  - Spell numbers: exe name table `0x603190`, entries `0x32 + n`: 0
    `unused_spell_0`, 1 `fire_arrow`, 2 `fire_ball`, …, 12 `invisibility`,
    …, 18 `stone_curse`, …, 29 `slow` (`spell.txt` order + 1).
  - Server builder `FUN_00523a7f` switches on the spell (`0x523ea0`,
    table `0x525bb8`, 30 cases); effect object (vtable `0x5db3c8`)
    `+0xc = n`, `+0xe = 2n + 8`; secondary projectile `2n + 9` (e.g.
    `0x523e73`). Invisibility (case 12, `0x525613`) → `0x20`; Stone Curse
    (18, `0x52539a`) → `0x2c`.
  - `FUN_00526afe` attaches it: bit `1 << n` into `unit+0x144`; bless
    (20) and curse (28) cancel. Announced by `FUN_0050d132`: message
    `0x88` with unit id (`msg+0xa`) and `effect+0xe` (`msg+0xc`).
  - Client (`FUN_0040dac9` case `0x88`, `0x4155f6`) adds/replaces
    `id << 16 | 0xffff` in the effect list `unit+0x130`, sets
    `unit+0x114 = 1`. The projectile tick `FUN_00471643` adds the same
    entry when a homing projectile `0x10 … 0x42` reaches its target.

  So `effect id = 2·spell + 8 (+1)`. Data (CONFIRMED): every
  `projectiles.reg` ID ≥ 10 fits: 10 `firebolt` = fire_arrow, 12/13
  `fireball`/`fireexpl` = fire_ball, 15 `firewall`, 20/21
  `poison_d`/`poison` = poison_cloud, 23 `Meteor` = blizzard, 30 `chain`
  = prismatic_spray, 40 `meteorit` = diamond_dust, 43 `wall` =
  wall_of_earth, 56 `healing` = heal, 64 `Curse`. IDs 1–8 = arrows,
  catapult shots, steam (not spells). Invisibility (32) and Stone Curse
  (44) have no sprite. Code: `allods2.spells`.
- No team-colour range swap (player colours are whole palettes, §4). No
  screen palette fades in the palette code; fades use FADE16 tables or
  video `.reg` metadata (INFERRED).

## Open questions

None.
