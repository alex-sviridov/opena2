# Palettes

Implementation: `allods2/graphics/palette.py`. Validation:
`.venv/bin/python tools/validate_palettes.py`. Contact sheet of every distinct
palette: `.venv/bin/python tools/palette_contact.py` writes
`out/contact/palettes.png`.

Binary references: `allods2.exe` English 1.30, sha256 `2a8bdf9d…fe43`, and
`a2mgr.dll` sha256 `6bc57ebb…7cc6`. Pseudocode was checked with REA (Ghidra 12.1.4).

## 1. Where palettes live

The install has no raw 768-byte (RGB) or 1024-byte palette files, and nothing
that looks like 768 or 1024 bytes plus a small header. **CONFIRMED** (data, by
a size scan of all 5,299 files). Every palette is 256 × 4-byte entries in one
of these containers:

| Source | Files | Palettes | Distinct | How the game reads it |
|---|---:|---:|---:|---|
| `.256` sprites (trailer bit 31) | 1,523 | 1,523 | 1,064 | first 0x400 bytes ([sprites](sprites.md)) |
| `*b.256` smoothing overlays | 394 | 394 | 4 | same; 391 are **all zero** |
| `.16a` sprites (trailer bit 31) | 782 | 782 | 760 | first 0x400 bytes |
| unit / projectile `.pal` | 163 | 163 | 129 | BMP-wrapped, seek 0x36, read 0x400 (§3) |
| `units/*/human.pal` | 3 | 48 | 32 | raw 16 × 0x400 (§4) |
| 8-bit `.bmp` (terrain, interface) | 63 | 63 | 10 | DIB colour table ([bitmaps](bitmaps.md)) |
| built in code | – | 5 + 14 ramps | – | FUN_00463d30 (§6) |
| **total from files** | 2,928 | 2,973 | 1,942 | |

These counts are **CONFIRMED** (data): `tools/validate_palettes.py` parses every
one of them and checks the rules below with no failures. The 6 `.256` and 3
`.16` files without trailer bit 31 carry no palette. Font `.16` sprites take
their colours from the caller.

## 2. Entry layout

| Offset | Size | Field |
|---|---|---|
| 4·i + 0 | 1 | blue |
| 4·i + 1 | 1 | green |
| 4·i + 2 | 1 | red |
| 4·i + 3 | 1 | reserved: never read by the game |

256 entries, 0x400 bytes. This is the Windows RGBQUAD layout.

- **CONFIRMED** (FUN_00425bee): red is read from `+2`, green from `+1` and
  blue from `+0`; `+3` is never read. The MFC-style `CDib::MakePalette`
  (FUN_004568f6) builds a GDI `LOGPALETTE` with `peRed = q[2]`,
  `peGreen = q[1]`, `peBlue = q[0]` and `peFlags = 0`.
- **CONFIRMED**: channels are 8-bit (0–255), not 6-bit VGA. FUN_00425bee
  converts each channel with `c >> (8 − bits)`, so it treats 255 as full
  scale. In the data, all non-zero palettes reach values above 63 and the
  low 2 bits are evenly distributed. No palette uses `×4` or `<<2|>>4`
  scaling, apart from one overlay whose values are coincidentally consistent
  with it.
- **CONFIRMED** (data): the reserved byte is 0 in every `.pal`, `human.pal`
  and BMP. It is non-zero in 101 `.16a` icons and 2 `.256` cursors
  (`cursors/attack.256`, `cursors/pickup.256`). This is leftover tool data
  and makes no difference, since the game ignores it. `Palette` keeps it so
  that files round-trip byte for byte.
- **No reserved colour indices.** Nothing in the palette code treats an
  index specially, except shade mode 0 (index 0 → 0). Transparency in
  sprites comes from RLE skips ([sprites](sprites.md)), not from a colour
  key. **INFERRED** (data): entry 0 is black in 1,912 of 1,917 `.256`
  palettes and in every `.pal`, `human.pal` and BMP. The other 5 have
  magenta (255, 0, 255) ×3 or near-black.

### Example

Bytes `0A 14 1E 00` at offset 4 → entry 1 = RGB (30, 20, 10).

## 3. Unit palettes: `palette.pal`, `palette2.pal`, …

**CONFIRMED** (`FUN_0047f108`, unit registry loader):

1. `units.reg` gives each unit a `Palette` count `N`.
2. For `i = 1..N` the file is `<unit dir>\palette<i>.pal`, except that the
   digit is dropped for `i = 1`: `palette.pal`, `palette2.pal`, ….
3. The game opens the file, **seeks to 0x36** and reads 0x400 bytes.

**CONFIRMED** (`FUN_004824cc`, projectile loader): `graphics\projectiles\projectiles.pal`
and `projectile_.pal` are read the same way (seek 0x36, read 0x400). Each
becomes a 16-level `BRIGHT2` shade table without tint, stored in
`DAT_00630efc` and `DAT_00630f00`.

**CONFIRMED** (data): all 163 such files are 8-bit BMPs with a 14 + 40-byte
header and `bfOffBits = 0x436`, so offset 0x36 is the colour table. Image
sizes are 128², 160², 64² or 2², and `biClrUsed` is 256 or 0.

**INFERRED**: the game ignores the BMP's pixel data and header fields. It
depends only on the header being exactly 54 bytes. `Palette.save(path,
"pal")` writes a 16×16 BMP whose pixel i is index i, which meets that rule.

## 4. `human.pal`: player colours

**CONFIRMED** (`FUN_0047f108`, `FUN_0048392f`): a raw 0x4000-byte file (16
palettes × 0x400, no header), read into `DAT_0062cb78`. Palette *p* is the
human sprite palette for **player colour p**:

- Each palette becomes a 16-level `BRIGHT2` shade table *with* the day/night
  tint (`FUN_00425bee(pal + p·0x400, 0x10, 2, 1)`).
- Palette 0 also becomes a 16-level `GRAY` table (`…, 0x10, 5, 0`).
- For rows `15 − k` (k = 0..7) of each table, the game caches the 16-bit
  value at byte 0x148, i.e. **index 164**, in `0x629c90 + p·0x20 + k·4`.
  It stores the value twice: once from a second table returned by
  FUN_00473550(p), and once from the default table.

**CONFIRMED** (data): in all three `human.pal` files, index 164 has a
different colour in each of the 16 palettes: blue (87, 120, 228), green,
red, orange, violet, yellow, teal and grey, then darker variants of the
same eight for p = 8..15. The palettes differ only in 55–59 scattered
indices between 4 and 225, so the player colour is **not** a contiguous
palette range. `humans/human.pal` differs from the identical
`heroes/human.pal` and `heroes_l/human.pal`.

**INFERRED**: the cached index-164 colours are the player colour at 8
brightness levels (rows 15..8 = 1/8 .. 8/8), probably for minimap dots or
selection marks.

## 5. Conversion: shade tables (`FUN_00425bee`)

The original game draws to **16-bit surfaces**. It never uses a hardware
palette for game graphics. Every palette becomes a *shade table* object
(vtable `0x5d5308`, constructor FUN_00425b0f):

| Offset | Field |
|---|---|
| +4 | `levels`: number of rows |
| +8 | `u16 rows[levels][256]`, allocated as `levels << 9` bytes |

**CONFIRMED** (`a2mgr.dll` Ordinal_37 at `0x1000a450`, reached through the
exe thunk FUN_00420440): `row(level)` returns `table + 8 → data + level·0x200`.

`FUN_00425bee(this, src_quads, levels, mode, use_tint)`, **CONFIRMED**. In the
formulas below, `c` is a source channel and `t` its tint byte (R `0x62c888`,
G `0x62c889`, B `0x62c88a`, or 0 when `use_tint == 0`). Integer division
truncates, and every result is clamped to 0..255:

| mode | rows | row r, channel value | Use |
|---|---|---|---|
| 0 `MASK` | 1 | index 0 → `0x0000`, others → `0xFFFF` | silhouette |
| 1 `PLAIN` | 1 | `min(c + t, 255)` | |
| 2 `BRIGHT2` | N | `(c + t)·k·2 / N`, k = N − r | units, human.pal, projectiles; N = 16 → row 0 = ×2, row 8 = ×1, row 15 = ×1/8 |
| 3 `BRIGHT32` | N | `(c + t)·k >> 5`, k = N − r | terrain, N = 0x60 → row 0 = ×3, row 64 = ×1 |
| 4 `FADE16` | 16 | `c·k >> 4` (or `c·k / 18` when `DAT_0062c9b8 ≠ 0`), k = r + 1, no tint | code ramps, smoke; row 15 = ×1 |
| 5 `GRAY` | N | `((r+g+b)·k·2 / 3) / N`, all channels, k = N − r, no tint | grey-out of human palette 0 and unit palettes |

Then `pack16`: `px = (R >> (8 − Rbits)) << Rshift | (G >> (8 − Gbits)) <<
Gshift | (B >> (8 − Bbits)) << Bshift`. The widths are `0x5fb960/964/968`
and the shifts `0x5fb958/95c` and `0x62c9bc`. **INFERRED**: these come from
the DirectDraw surface's pixel format, so they are 5-6-5 or 5-5-5.

Note the **row order**: in modes 2, 3 and 5 the brightest row comes first,
while in mode 4 the darkest comes first.

### Worked example

Index 1 = (100, 200, 3), mode 2, N = 16, no tint:

- row 0 (k = 16): (200, 400 → 255, 6)
- row 8 (k = 8): (100, 200, 3)
- row 15 (k = 1): (200/16, 400/16, 6/16) = (12, 25, 0)

Row 8 in 5-6-5 is `(100>>3)<<11 | (200>>2)<<5 | 3>>3` = `0x6640`.

### Callers (CONFIRMED)

| Caller | Source palette | levels, mode, tint |
|---|---|---|
| FUN_0047f108 / FUN_0048392f | `human.pal` × 16 | 16, BRIGHT2, yes. Palette 0 also 16, GRAY, no |
| FUN_0048392f via FUN_00426be0 | the palettes of three object registries (FUN_00422f70 / FUN_00422ff0 / FUN_00423030 lists) and one global; INFERRED: units, structures, objects | 16, BRIGHT2, yes |
| FUN_0047b899 / FUN_0048392f | terrain: the palette of the first tile of each of 32 tile slots | 0x60, BRIGHT32, yes |
| FUN_004824cc | `projectiles.pal`, `projectile_.pal` | 16, BRIGHT2, no |
| FUN_004824cc | `projectiles\smoke%d\sprites.256` (×2) | 16, FADE16, no |
| FUN_00463d30 | 5 code ramps (§6) | 16, FADE16, no |
| FUN_00473010 | a unit's palette when no table exists yet | 16, BRIGHT2, yes |
| FUN_00468640 (unit draw) | the unit's palette, under some unit state | 16, GRAY, no |

Terrain slot *s* (0..31) holds `tile{s/4 + 1}-{v + 4·(s mod 4)}.bmp` for v =
0..3. **CONFIRMED** (data): all 52 `tile*.bmp` share one palette, so a
single terrain palette is in effect. `dirt.bmp` has its own.

### GDI palettes

`CreatePalette` is called only from FUN_004568f6 (`CDib::MakePalette`, BMP
colour table → `LOGPALETTE`) and FUN_00456a13 (copies the system palette
with `GetSystemPaletteEntries` when a DIB has no colour table and the
display is palettised). `RealizePalette` / `SelectPalette` are MFC runtime
imports. `_SmackBlitSetPalette` is used for Smacker video, which this
install does not ship. **CONFIRMED** (imports and xrefs). The game itself
does not call `IDirectDrawPalette::SetEntries`, and no palette rotation or
colour cycling was found. **INFERRED**: none was found by xref search; this
is not proven absent.

## 6. Palettes built in code (`FUN_00463d30`)

**CONFIRMED.** Five 256-entry gradient palettes, entry i =
`(i·R / 255, i·G / 255, i·B / 255)`, each converted with 16 levels in mode 4:

| Table | (R, G, B) at i = 255 | Shade table stored in |
|---|---|---|
| `0x62a6f0` | (185, 159, 73), gold | `DAT_0062b088` |
| `0x629848` | (255, 255, 116), yellow | `DAT_0062af8c` |
| `0x62ab10` | (0, 0, 0), black | `DAT_0062b064` |
| `0x62a2c8` | (65, 47, 20), brown | `DAT_0062b048` |
| `0x629e90` | (101, 39, 61), purple | `DAT_0062b000` |

The same routine writes fourteen 16-entry tables of 16-bit colours directly,
for i = 0..15 (`/` truncates):

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

**Open:** what draws with these tables. **INFERRED**: the gradient
palettes are effect tints (glows, fire, magic) for 8-bit sprites drawn as
intensity, and the 16-entry ramps are UI bars or minimap colours.

## 7. Palette effects

### Day/night tint (`FUN_0047a208`), CONFIRMED

When day/night is enabled (`DAT_0062c938 ≠ 0`), game time `t` (minutes,
FUN_0041f200 passes `(clock >> 4) + 360`) sets the tint added to every
palette in modes 1–3. With `h = (t / 60) mod 24` and `m = t mod 120`:

| Hours | Tint (R, G, B) |
|---|---|
| 06–17 | (0, 0, 0) |
| 22–01 | (0, 12, 48), night blue |
| 02–03 | (24m/120, 12, 48 − 48m/120) |
| 04–05 | (24 − 24m/120, 12 − 12m/120, 0) |
| 18–19 | (24m/120, 0, 8m/120) |
| 20–21 | (24 − 24m/120, 12m/120, 8 + 40m/120) |

All divisions truncate. The curve is continuous at every boundary (to within 1 unit
of truncation); for example, at 22:00 it reaches (0, 12, 48). The same
routine sets terrain lighting parameters (`0x62c88c`, `0x62c890`,
`0x62c894`, `0x62c898`, and a light angle `0x62c8a0` = ±π/4 or a sweep).
These are not palette data. When disabled, the tint is (0, 0, 0).

FUN_0041f200 re-evaluates this every 20 game minutes and then calls
**FUN_0048392f**, which rebuilds every tinted shade table: human, unit,
terrain, structure and object. The time of day is therefore a palette
effect applied at conversion time, not a per-pixel blend.

Implementation: `daylight_tint(minutes)`, `shade_table(rgb, levels, mode, tint)`.

### Others

- **Brightness levels** (modes 2/3) replace per-pixel lighting. Which row
  is drawn (terrain height and slope shading, fog of war) is chosen by
  the renderer. **Open.**
- **Grey-out** (mode 5): FUN_00468640 draws a unit through a GRAY table when
  `FUN_0046600b(…) ≥ 0`, which is some unit state. **INFERRED**: petrified,
  or a similar effect.
- No team-colour **range swap**: player colours are whole alternate
  palettes (§4).
- No palette fades of the screen were found in the palette code. Fades
  use FADE16 tables or the video `.reg` fade metadata. **INFERRED**.

## Open questions

1. What `DAT_0062c9b8` is. It switches FADE16 to `/18`, halves the buffer
   allocated in FUN_00487a00, and is read by the blend-table builder
   FUN_0045752b. Possibly a 15- vs 16-bit display flag.
2. The draw-time row selection for BRIGHT2 / BRIGHT32 tables (lighting).
3. The users of the code gradient palettes and the 16-entry ramps (§6).
4. The second table from FUN_00473550(p) in the index-164 cache (§4).
5. Which unit state triggers the GRAY draw in FUN_00468640.
6. Why 391 smoothing overlays embed an all-zero palette. **INFERRED**: the
   overlay draw uses the main sprite's palette ([sprites](sprites.md)), so
   the embedded palette is never used. The three non-zero ones are
   `interface/radiob.256` (not an overlay), `projectiles/firebolt/spritesb.256`
   and `units/monsters/star/spritesb.256`.
