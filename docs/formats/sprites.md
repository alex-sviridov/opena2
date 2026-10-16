# Sprite files: `.256`, `*b.256`, `.16a`, `.16`

Code: `allods2/graphics/sprites.py`, `allods2/graphics/canvas.py`. All four
share one container and differ only in the pixel stream.

## Container

| Offset | Size | Field |
|---|---|---|
| 0 | 1024 | palette, **only if** trailer bit 31: 256 × `B, G, R, 0` ([palettes](palettes.md)) |
| … | 12 + n | record × `count`: `u32 width, u32 height, u32 size, u8 data[size]` |
| end − 4 | 4 | trailer `count \| 0x80000000` (bit 31 = palette) |

Little-endian. CONFIRMED:
- `FUN_00426da9` reads the trailer, takes bit 31 as palette flag and the
  low 31 bits as count, walks records sequentially (`next = cur + 12 +
  size`; no offset table).
- `FUN_00480d20` picks the `.16a` subclass (`FUN_0042a71b`, vtable
  `0x5d5488`) when the path contains `.16a`, else the 256-colour class
  (`0x5d53a8`); same constructor, only the draw differs.
- Every non-empty sprite file in the install parses. 8 `.256` files are 0
  bytes (e.g. `cursors/move.256`, `equipment/*fighter/primary/0005002.256`);
  opening them would stop with `FATAL ERROR: can't load`.

## Shared cursor model

CONFIRMED (`FUN_00459614`, `FUN_004593a1`, `FUN_0045db6b`): `p` =
destination pointer, linear in the sprite's width; `c` = column, compared
with `width` **after every op**: when `c >= width`, `c = 0` and one row is
consumed (overshoot stays in `p`, carrying into the next row); `rows`
starts at `height`, drawing ends at 0. "Skip `n` rows" adds `n·width` to
`p` without touching `c`; `n >= rows` ends the sprite. With this model all
43,051 sprites in the install are consumed exactly
(`tools/validate_sprites.py`).

## `.256`: 8-bit palette sprites

Control byte `b`, `n = b & 0x3F`: `b & 0xC0` = `0x00` → `n` literal
indices follow; `0x40` → skip `n` rows; `0x80`/`0xC0` → skip `n`
transparent pixels.

**Draw methods** (CONFIRMED; vtables `0x5d53a8` `.256`, `0x5d5488` `.16a`,
set by `FUN_00426da9`/`FUN_0042a71b`): `(x, y, frame, palette-or-level, …,
mirror)`; the last argument picks the normal or mirrored blitter:

| Slot | Method | Normal | Mirrored |
|---|---|---|---|
| `+0x18` (`.256`) | `FUN_00427014` opaque | `FUN_00459614` | `FUN_0045a64d` |
| `+0x18` (`.16a`) | `FUN_0042a740` alpha | `FUN_0045db6b` | `FUN_0045dee0` |
| `+0x1c` (both) | `FUN_00427260` darken | `FUN_00459d8c` | `FUN_0045ad81` |
| `+0x34`, `+0x38` | `FUN_004271d0`, `FUN_004270aa` 50 % | `FUN_00459926` | `FUN_0045a8e7` |

`+0x14` (`FUN_00427140`) is another opaque entry; the darken pair has
low-memory twins `FUN_00459b5c`/`FUN_0045ab38` (not reproduced).

- **Shade table source** (CONFIRMED `FUN_00427014`, `FUN_00427140`,
  `FUN_004270aa`, `FUN_004271d0`; `FUN_00420440` = `table + row·0x100` via
  a2mgr): `+0x18` and `+0x38` use the sprite's **own** table `this+0x14`,
  built by `FUN_00426be0(levels, mode, tint)` from the embedded palette
  (`this+0x20`); `+0x14` and `+0x34` take an **external** table after the
  row: `(x, y, frame, row, table, mirror)`. The "palette" argument is a
  row index in both.
- **Opaque** `FUN_00459614`. **50 %** `FUN_00459926`: per channel
  `dst = (src >> 1) + (dst >> 1)` (masked shifts on 16-bit pixels); the
  hero draw `FUN_00468640` uses it instead of opaque when the unit has
  effect `0x20`.
- **Effect `0x20` = Invisibility** (`2·12 + 8`, [palettes §7](palettes.md);
  CONFIRMED map object loop `0x408763`–`0x4088e3`): `FUN_0046600b(0x20)`
  searches the unit's effect list (u32, id in high 16 bits; −1 if absent).
  If present, `FUN_00420610(owner)` on the viewing player (`view+0x9cc`;
  owner = `obj+0x14 → +4`) returns bit 8 of the viewer's relation word for
  that player (`FUN_00420660`). Bit clear → shadow (`+0x2c`, drawn when
  `DAT_005fb970`) and body (`+0x28`) are skipped. So players with the bit
  see the unit at 50 %, others nothing.
- **Relation word** (CONFIRMED): viewer's u16 for player `p` at
  `player+0x38 → +4`, `+2·p` (`FUN_00420640`/`FUN_00420660`). Received
  bits, from network updates in `FUN_0040dac9` (~`0x4149e6`): `8` = `p`
  shares vision with the viewer (`patch.txt` `0x46`/`0x47` "Player … shows
  to you his area of vision" on, `0x48`/`0x49` "… hides …" off); `0x20`
  alliance (`main.txt` `0x8e`–`0x91`); `0x40` war (`0x92`–`0x95`). The
  diplomacy dialog (`FUN_0048f03f`, `0x490720`) keeps those (`& 0x68`) and
  sets the viewer's own choices from four checkboxes (`dialogs.txt` `0x4f`
  "enemy alliance visible silent"): `1` enemy, `2` alliance, `0x10`
  visible, `4` silent (`FUN_00420c00` tests bit 4 to mute chat). The
  viewer's own slot is `0x3a` (includes bit 8): own invisible units show
  at 50 %.
- **Mirrored** (CONFIRMED `FUN_0045a64d`, `FUN_0045a8e7`, `FUN_0045dee0`):
  the normal twin writing each row from `x + w − 1` leftward (pointer
  starts at `dst + 2·(x + w) − 2`, −2 bytes per pixel; skips subtract
  too): a horizontal flip at the same `(x, y, w, h)`. Callers set `mirror`
  when folding a direction ([units](units.md)).
- **Darken** (CONFIRMED `FUN_00459d8c`, `+0x1c`): skips pixel bytes,
  scales the destination by `(16 − level)/16`: a **UI drop shadow**. All
  call sites, mirror 0: `graphics\interface\lm.256` (`DAT_00630e4c`) level
  6, 20 sites `0x4e412f`…`0x4e89af`; `scrlbars.256` (`DAT_00630e50`) 4, 12
  sites `0x4e2bb1`…`0x4e2fb0`; `radiob.256` (`DAT_00630e54`) 4, 6 sites
  (e.g. `FUN_004df77d`). Pattern: shadow at `(x + 5, y + 4)`, then the
  frame opaque at `(x + 1, y)` (4 px right and down). Globals loaded in
  `FUN_0047bedd`.
- **Shop price bar** (CONFIRMED `FUN_004b9a42`, loader `0x4bfc0f`): a
  fourth `+0x1c` call (level 8) targets a "Bitmap 64k" ([bitmaps](bitmaps.md))
  from lists at `+0x20ac` `+0xdc` (`graphics\interface\costm1…7.bmp`) and
  `+0xf0` (`costs1…7.bmp`), 60 × 10 each; on that class `+0x1c` is a no-op
  (`FUN_0042a830`, `ret 0x14`): **no shadow** (it would be at
  `(x − 3, y + 2)`). The bar is drawn with `+0x38` (colour key 0) at
  `(x, y)`:

  ```
  price = item attribute 1 (FUN_004be7e0 → FUN_0043bafa(1), u32)
  list  = costm if cell+0x18 == 2 else costs
  frame = min(trunc(log10(price)), count − 1)       # count = 7
  text  = (price + 1) / 2 if cell+0x18 == 2 else price
  ```

  1–9 gold → frame 0, 10–99 → 1, …, ≥ 10⁶ → 6. INFERRED: `+0x18 == 2` =
  the player's own items (sell price half, rounded up). Price 0 gives
  `__ftol(−∞) = 0x80000000`, out of range (not seen in data). Search
  bound: the 163 `call [reg+0x1c]` sites in `.text`, kept when the object
  is one of these globals or the five-argument push pattern matches
  (a site with pushes split by another call would be missed).

### Example

Width 3, height 2, `81 02 05 06 83`: skip 1 (p 1, c 1); literal 5, 6
(p 3, c 3 → 0, rows 1); skip 3 (p 6, c → 0, rows 0, end). Row 0 =
`[·, 5, 6]`, row 1 empty. Row skip keeps the column: width 2, height 2,
`01 04 41 01 09` → `[4, ·]`, `[·, 9]`.

## `*b.256`: edge-smoothing overlays

Same stream as `.256`; `units/*/*/spritesb.256` and structures' `*b.256`,
one overlay per frame of the main file. CONFIRMED:

- Heroes load `<dir>\sprites.256` → `+0x1c0`, `<dir>\spritesb.256` →
  `+0x1c4` (`FUN_0046f688`). The hero draw (`FUN_00468640`) draws `+0x1c4`
  only via `+0x34` (50 %), **same frame index and palette argument** as
  the main sprite, positioned from its own size around the same anchor,
  only when `DAT_0062c930 != 0`.
- `DAT_0062c930` toggles with `O` + modifier (`DAT_0062c9a0`), showing
  `main.txt` message `0x6a + state`: "Smoothing is Off/On"
  (`FUN_0040c989`).
- Overlay pixels are sparse dots along edges and thin details (bow
  strings, arrows); with the main palette they look right, with their own
  dark.
- Heroes, structures, objects, backpack: drawn via `+0x34` with the
  **main sprite's** table; `FUN_00426be0` is never called on the overlay
  (its palette is never read). Each gated by `DAT_0062c930`:

  | Owner | Main / overlay | Main draw | Overlay table | Site |
  |---|---|---|---|---|
  | hero | `obj+0x1c0` / `+0x1c4` | `+0x34` | unit palette table | `FUN_00468640` (`0x469333`) |
  | other unit (type list `0x62cb40`, lazy `FUN_004807fd`) | `def+4` / `+8` (`FUN_00473090` / `FUN_004730c0`) | | unit palette table (`FUN_00473010`, or GRAY with effect `0x2c`) | `FUN_00468640` (`0x469670`) |
  | structure (`0x62caf8`, lazy `FUN_00482c92`) | `def+4` / `+8` (`FUN_00472e00` / `FUN_00472e30`) | `+0x18` own | `main+0x14` (`FUN_004205d0`) | `FUN_004669e8`, `0x467b93`, `0x467da1` |
  | object (`0x62cb60`, lazy `FUN_0047edf3`) | `def+4` / `+8` (`FUN_00420720` / `FUN_00420750`) | `+0x14`, table `main+0x14` | `main+0x14` | `0x4092d3`, `0x40946f` |
  | backpack (`DAT_00630e78` / `0x630e7c`) | globals | `+0x18` own | `main+0x14` | `0x4665e8` |

  Structures and objects also draw the overlay's **shadow** (`+0x3c`,
  lighter level `0x62c898`; main uses `0x62c894`) when Smoothing is on
  (objects also need shadows on, `DAT_005fb970`; `0x4090e7`, structures
  `0x466e7b`). Units draw the overlay's shadow with darken `+0x1c` at
  `0x62c898` (`0x46a6df`).
- **Projectiles differ** (`FUN_00482125` loader, `FUN_00471fee` draw):
  `A16 = 0` reads `<File>.256` → `def+4` and `<File>b.256` → `def+8`;
  `A16 = 1` reads `<File>.16a`, `def+8 = 0`. With `Palette ≠ 0`
  (`def+0x28`) **both** get own tables from their own palettes
  (`FUN_00426be0(16, BRIGHT2, 1)`); draw = `+0x18` main, `+0x38` (50 %,
  own table) overlay, **not** gated by `DAT_0062c930`. `Palette = 0`: main
  only, `+0x14` with `projectiles.pal` (`DAT_00630efc`). Data (`A16 = 0`):
  `archer`, `xbowman`, `orc` `\arrow` have `Palette` 0 (no overlay);
  `goblin\arrow`, `catap1`, `catap2` `\sprites` have `Palette` 1 and
  all-zero overlay palettes, which **are** used: BRIGHT2 with `c = 0`
  leaves the tint `t·k·2/16`, taken when the type is first loaded (the
  day/night rebuild `FUN_0048392f`, `0x483d7e`, refreshes only `def+4`).
  By day the tint is 0, so the overlay draws as 50 % black, Smoothing or
  not. The one non-zero projectile overlay, `firebolt\spritesb.256`, is
  never loaded (`A16 = 1`).

`to_rgba(kind="smooth")` gives these pixels alpha 128.

## `.16`: 4-bit sprites (fonts)

CONFIRMED (`FUN_004593a1`): control bytes as `.256`; a literal run of `n`
**bytes** holds up to `2n` pixels, low nibble first, values 0–15 index a
16-entry colour table from the caller. A zero high nibble ends the run
early: pixel count odd, counter `+= 2n − 1`, remaining bytes of the run
are read as control bytes. Font files carry no palette and decode exactly.

Example: width 4, `02 03 81`: run of 2 bytes; `03` → pixel 3, high nibble
0 ends the run (counter 3); `81` = skip 1 → counter 4, row done →
`[3, ·, ·, ·]`. At width 2 the stream ends after `03` (3 ≥ 2 closes the
only row).

## `.16a`: 16-bit sprites with alpha

CONFIRMED (`FUN_0045db6b`): little-endian 16-bit words, tested in order:
`v & 0x4000` → skip `v & 0x3FFF` rows (so `0xC000 | n` is a row skip);
`v & 0x8000` → skip `v & 0x3FFF` pixels; else `v` literal pixel words.
Pixel word: bits 1–8 palette index, 9–12 alpha `a` (0–15), bits 0 and
13–15 always 0 (CONFIRMED: 0 of 1,694,423 words set them; the word is a
byte offset into a table of 2-byte entries).

Blend (CONFIRMED `FUN_0045db6b` + table builder `FUN_0045752b`):

```
dst = premul[pixel_word] + table[1 + a][dst]
table[k][x] = x * (16 - k) / 16      per channel, 17 tables, k = 0..16
```

`premul` = the palette's FADE16 table ([palettes §5](palettes.md)), passed
as `row(0)` (a2mgr `Ordinal_37`); the word selects row `a`, column
`index` → `colour·(a+1)/16`. So `src·(a+1)/16 + dst·(15−a)/16`: `a = 15`
opaque, `a = 0` coverage 1/16 (`alpha_coverage()`, `Canvas.draw_16a`).
The low-memory mode divides by 18 (not reproduced).

Example: width 2, height 2, `8001 0001 1FFE 8002`: skip 1; literal
`0x1FFE` = index 255, alpha 15, row done; skip 2, row done → row 0
`[·, (255, 15)]`, row 1 empty.

## Placement: no hotspot in the file

Only `w, h, size` per frame (CONFIRMED). Callers centre each frame on an
anchor; units: `x = obj+0x64 − ((CenterX − Width/2) + w/2)` etc., with
`T+0x2c..+0x38` = `Width, Height, CenterX, CenterY` from `units.reg`
([units](units.md#placement)); the `*b.256` overlay uses the same formula
with its own frame size.

## Tools

- `python -m allods2 gfx export FILE DEST [--palette P]`: one PNG per
  frame (`DEST/<stem>_NNN.png`); `P` = unit `.pal`, `.bmp`, or
  `human.pal:N` for player N.
- `tools/sprite_contact.py` → `out/contact/{256,b.256,16a,16}.png`: first
  frame of ~100 files per type on a checkerboard.
- `tools/validate_sprites.py`: stream consumption over the install.

## Open questions

None at present.
