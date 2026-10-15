# Sprite files: `.256`, `*b.256`, `.16a`, `.16`

Binary: `allods2.exe`, English 1.30 build, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses below refer to that build and were read in REA (Ghidra 12.1.4).
Implementation: `allods2/graphics/sprites.py`, `allods2/graphics/canvas.py`.

All four formats share one container and differ only in the pixel stream.

## Container

| Offset | Size | Field |
|---|---|---|
| 0 | 1024 | Palette, **only if** trailer bit 31 is set: 256 × RGBQUAD `B, G, R, 0` ([palettes](palettes.md)) |
| … | 12 + n | Sprite record, repeated `count` times: `u32 width`, `u32 height`, `u32 size`, `u8 data[size]` |
| end − 4 | 4 | Trailer: `count | 0x80000000` (bit 31 = palette present) |

All integers are little-endian.

- **CONFIRMED** (`FUN_00426da9`): the constructor reads the trailer at `end − 4`,
  takes bit 31 as the palette flag and the low 31 bits as the count, and loads
  the file. It walks the records sequentially (`next = cur + 12 + size`); there
  is no offset table.
- **CONFIRMED** (`FUN_00480d20`): the loader picks the `.16a` subclass
  (`FUN_0042a71b`, vtable `0x5d5488`) when the path contains `.16a`; otherwise
  it uses the 256-colour class (vtable `0x5d53a8`). The subclass reuses the same
  constructor and overrides only the draw method.
- **CONFIRMED** (all files): every non-empty sprite file in the English install
  parses with this layout.
- **CONFIRMED** (data): 8 shipped `.256` files are 0 bytes, e.g.
  `cursors/move.256` and `equipment/*fighter/primary/0005002.256`. The game would
  stop with `FATAL ERROR: can't load` if it opened them.

## Shared cursor model

**CONFIRMED** (`FUN_00459614`, `FUN_004593a1`, `FUN_0045db6b`): every blitter
walks its stream with the same state:

- `p`: destination pointer, linear in the sprite's own width;
- `c`: column counter, compared with `width` **after every op**. When
  `c >= width`, `c` becomes 0 and one row is consumed. Overshoot stays in `p`,
  so it carries into the next row;
- `rows`: starts at `height`; drawing ends when it reaches 0.

"Skip `n` rows" adds `n·width` to `p` **without** touching `c`, so the column is
kept. If `n >= rows` the sprite ends.

**CONFIRMED** (all files): with this model every stream in the English install
is consumed exactly: 43,051 sprites (`tools/validate_sprites.py`).

## `.256`: 8-bit palette sprites

Control byte `b`, `n = b & 0x3F`:

| `b & 0xC0` | Meaning |
|---|---|
| `0x00` | `n` literal palette indices follow |
| `0x40` | skip `n` rows |
| `0x80`, `0xC0` | skip `n` transparent pixels |

**CONFIRMED** (vtables `0x5d53a8` for `.256`, `0x5d5488` for `.16a`; set by
`FUN_00426da9` / `FUN_0042a71b`): each draw method takes
`(x, y, frame, palette-or-level, …, mirror)` and picks the normal or the
mirrored blitter from its last argument:

| Slot | Method | Normal | Mirrored |
|---|---|---|---|
| `+0x18` (`.256`) | `FUN_00427014` opaque | `FUN_00459614` | `FUN_0045a64d` |
| `+0x18` (`.16a`) | `FUN_0042a740` alpha | `FUN_0045db6b` | `FUN_0045dee0` |
| `+0x1c` (both) | `FUN_00427260` darken | `FUN_00459d8c` | `FUN_0045ad81` |
| `+0x34`, `+0x38` | `FUN_004271d0`, `FUN_004270aa` 50 % | `FUN_00459926` | `FUN_0045a8e7` |

(`+0x14` `FUN_00427140` is another opaque entry; the darken pair has
low-memory twins `FUN_00459b5c` / `FUN_0045ab38`, not reproduced.)

- **CONFIRMED** (`FUN_00427014`, `FUN_00427140`, `FUN_004270aa`,
  `FUN_004271d0`; `FUN_00420440` = `table + row·0x100`, via a2mgr): the
  methods differ in where the 16-bit shade table comes from. `+0x18` (opaque)
  and `+0x38` (50 %) use the sprite's **own** table at `this+0x14`, which
  `FUN_00426be0(levels, mode, tint)` builds from the embedded palette
  (`this+0x20`). `+0x14` (opaque) and `+0x34` (50 %) take an **external**
  table as the argument after the row, `(x, y, frame, row, table, mirror)`.
  In both cases the "palette" argument is a row index.

- **CONFIRMED** (`FUN_00459614`): the opaque blit.
- **CONFIRMED** (`FUN_00459926`): the 50 % translucent blit, per channel
  `dst = (src >> 1) + (dst >> 1)` (done as masked shifts on 16-bit pixels).
  The hero draw (`FUN_00468640`) uses it instead of the opaque blit when the
  unit has effect `0x20`.
- **CONFIRMED** (map object loop, `0x408763`–`0x4088e3`): effect `0x20` also
  hides the unit. `FUN_0046600b(0x20)` searches the unit's effect list
  (u32 entries, id in the high 16 bits; −1 if absent). When the effect is
  present, the loop calls `FUN_00420610(owner)` on the viewing player
  (`view+0x9cc`; owner = `obj+0x14 → +4`), which returns bit `8` of the
  viewer's u16 relation word for that player (`FUN_00420660`). If the bit
  is clear, the unit's shadow (`+0x2c`, drawn when `DAT_005fb970`) and body
  (`+0x28`) are both skipped. So players with the bit see the unit at 50 %;
  everyone else sees nothing. **INFERRED**: this is the Invisibility spell
  ([palettes §7](palettes.md)).
- **CONFIRMED** (relation word): the viewer's u16 word for player `p` lives
  at `player+0x38 → +4`, `+2·p` (`FUN_00420640` / `FUN_00420660`). Bit `8`
  means **`p` shares its vision with the viewer**. When a network update
  changes the word, the message handler `FUN_0040dac9` (around `0x4149e6`)
  prints `patch.txt` lines `0x46`/`0x47`, "Player … shows to you his area of
  vision", when bit 8 turns on, and `0x48`/`0x49`, "… hides from you his area
  of vision", when it turns off. In the same handler, bit `0x20` is
  alliance (`main.txt` `0x8e`–`0x91`, "is now / is no longer in alliance
  with you") and bit `0x40` is war (`0x92`–`0x95`). The diplomacy dialog
  (`FUN_0048f03f`, `0x490720`) keeps those three received bits (`& 0x68`)
  and sets the viewer's own choices from its four checkboxes, which are
  labelled in `dialogs.txt` `0x4f` "enemy alliance visible silent": `1`
  enemy, `2` alliance, `0x10` visible, `4` silent (`FUN_00420c00` tests bit 4
  to mute chat). The word for the viewer's own slot is set to `0x3a`, which
  includes bit 8, so players always see their own invisible units at 50 %.
- **CONFIRMED** (`FUN_0045a64d`, `FUN_0045a8e7`, `FUN_0045dee0`): every mirrored
  blitter is its normal twin with the row written from `x + w − 1` leftward
  (pointer starts at `dst + 2·(x + w) − 2`, steps −2 bytes per pixel; skips
  subtract too). The stream, the cursor model and the blend are unchanged, so
  the result is a horizontal flip at the same `(x, y, w, h)`. Callers set
  `mirror` when they fold a direction past the midpoint ([units](units.md)).
- **CONFIRMED** (`FUN_00459d8c`; vtable `+0x1c`): a darkening blit that skips
  the pixel bytes and scales the destination by `(16 − level) / 16`. It is a
  **UI drop shadow**. All call sites found, each with mirror = 0:

  | Sprite | Level | Sites |
  |---|---|---|
  | `graphics\interface\lm.256` (`DAT_00630e4c`) | 6 | 20, `0x4e412f`…`0x4e89af` |
  | `graphics\interface\scrlbars.256` (`DAT_00630e50`) | 4 | 12, `0x4e2bb1`…`0x4e2fb0` |
  | `graphics\interface\radiob.256` (`DAT_00630e54`) | 4 | 6, e.g. `FUN_004df77d` |

  Pattern (`FUN_004df77d`): shadow at `(x + 5, y + 4)`, then the same frame
  opaque at `(x + 1, y)`, i.e. the shadow sits 4 px right and 4 px down.
  The three globals are loaded in `FUN_0047bedd`
  (`FUN_00426da9("graphics\interface\….256")`).
- **CONFIRMED** (`FUN_004b9a42`, loader `0x4bfc0f`): a fourth `+0x1c` call
  with level 8 is **not a sprite**. It is the shop price bar, a "Bitmap
  64k" (`FUN_0042769b`, [bitmaps](bitmaps.md)) from the lists at
  `+0x20ac` `+0xdc` (`graphics\interface\costm1…7.bmp`) and `+0xf0`
  (`costs1…7.bmp`), 60 × 10 each. On that class `+0x1c` is a no-op
  (`FUN_0042a830`, `ret 0x14`), so the bar has **no shadow**. The bar is then
  drawn through `+0x38`, the colour-keyed blit (pixel 0 transparent), at
  `(x, y)`. The shadow call would have gone at `(x − 3, y + 2)`. Frame and
  text:

  ```
  price = item attribute 1 (FUN_004be7e0 → FUN_0043bafa(1), u32)
  list  = costm if cell+0x18 == 2 else costs
  frame = min(trunc(log10(price)), count − 1)       # count = 7
  text  = (price + 1) / 2 if cell+0x18 == 2 else price
  ```

  So 1–9 gold → frame 0, 10–99 → 1, …, ≥ 10⁶ → 6. **INFERRED**: `+0x18 == 2`
  marks the player's own items (sell price = half, rounded up). With price 0,
  `log10` gives −∞ and `__ftol` gives `0x80000000`; the game would then
  index out of range. Not seen in data.
  Search bound: the 163 `call [reg+0x1c]` sites in `.text`, kept when the
  object is one of these globals or the five-argument push pattern matches;
  a site whose pushes are split by another call would be missed.

### Example

Width 3, height 2, stream `81 02 05 06 83`:

| Byte(s) | Op | p | c | rows |
|---|---|---|---|---|
| `81` | skip 1 pixel | 1 | 1 | 2 |
| `02 05 06` | literal 5, 6 | 3 | 3 → 0 | 1 |
| `83` | skip 3 pixels | 6 | 3 → 0 | 0 (end) |

Result: row 0 = `[·, 5, 6]`, row 1 = `[·, ·, ·]`.

Row skip keeps the column: width 2, height 2, `01 04 41 01 09` →
row 0 = `[4, ·]`, row 1 = `[·, 9]`.

## `*b.256`: edge-smoothing overlays

Same stream as `.256`. Files: `units/*/*/spritesb.256` and structures'
`*b.256`, one overlay per frame of the matching main file.

- **CONFIRMED** (`FUN_0046f688`): heroes load `<dir>\sprites.256` into object
  field `+0x1c0` and `<dir>\spritesb.256` into `+0x1c4`.
- **CONFIRMED** (`FUN_00468640`, hero draw): the `+0x1c4` sprite is drawn only
  through vtable `+0x34`, the 50 % translucent blit `FUN_00459926`. It uses the
  **same frame index and the same palette argument** as the main sprite, and
  is positioned from its own width and height around the same anchor. It is
  drawn only when `DAT_0062c930 != 0`.
- **CONFIRMED** (`FUN_0040c989`, `main.txt`): `DAT_0062c930` is toggled by the
  `O` key with a modifier held (`DAT_0062c9a0`), and the game then shows
  message `0x6a + state` from `locale/<lang>/main.txt`: "Smoothing is Off" /
  "Smoothing is On".
- **CONFIRMED** (data): overlay pixels are sparse dots along edges and thin
  details (bow strings, arrows). They render plausibly with the main sprite's
  palette; with their own embedded palette they come out dark.
- **CONFIRMED** (heroes): the hero overlay is drawn through `+0x34`, which
  takes the main sprite's external table, and `FUN_00426be0` is never called
  on `+0x1c4`. So the overlay's embedded palette is never read for heroes.
- **CONFIRMED** (projectiles, `FUN_00482125` loader, `FUN_00471fee` draw):
  projectile overlays are different. For a `projectiles.reg` entry with
  `A16 = 0`, the loader reads `<File>.256` into `def+4` and `<File>b.256`
  into `def+8`. With `A16 = 1` it reads `<File>.16a` and sets `def+8 = 0`.
  When `Palette ≠ 0` (`def+0x28`), it builds **both** sprites' own tables from
  their own embedded palettes (`FUN_00426be0(16, BRIGHT2, 1)`). The draw then
  calls `+0x18` on the main sprite and `+0x38` (50 %, own table) on the
  overlay. It does **not** check `DAT_0062c930`. With `Palette = 0` it draws
  only the main sprite, through `+0x14` with `projectiles.pal`
  (`DAT_00630efc`).

  | Projectile (`A16 = 0`) | `Palette` | Overlay palette | Overlay drawn |
  |---|---|---|---|
  | `archer`, `xbowman`, `orc` `\arrow` | 0 | none | no |
  | `goblin\arrow` | 1 | all zero | yes, as 50 % black |
  | `catap1`, `catap2` `\sprites` | 1 | all zero | yes, as 50 % black |

  So in these three cases the all-zero palette **is** used. With `c = 0`,
  BRIGHT2 leaves only the tint, `t·k·2 / 16`, and the tint is the one in
  effect when the projectile type is first loaded. The day/night rebuild
  (`FUN_0048392f`, `0x483d7e`) only refreshes `def+4`. By day the tint is 0,
  so every overlay pixel is black and halves the destination, whether or not
  Smoothing is on. The one non-zero projectile overlay,
  `firebolt\spritesb.256`, is never loaded, because firebolt has `A16 = 1`.
  (CONFIRMED data: `projectiles.reg`, the six files.)

`to_rgba(kind="smooth")` gives these pixels alpha 128 to match the 50 % blend.

## `.16`: 4-bit sprites (fonts)

**CONFIRMED** (`FUN_004593a1`): control bytes as in `.256`. A literal run of `n`
**bytes** holds up to `2n` pixels, low nibble first. Pixel values 0–15 index
a 16-entry colour table passed by the caller (the text colour).

A zero high nibble ends the run early. The pixel count is then odd, the
counter advances `2n − 1`, and any bytes left in the run are read as control
bytes.

**CONFIRMED** (data): font files carry no palette (trailer bit 31 clear) and
decode exactly.

### Example

Width 4, stream `02 03 81`: literal run of 2 bytes; byte `03` → pixel 3, high
nibble 0 ends the run (counter 2·2 − 1 = 3); `81` is then a control byte:
skip 1 → counter 4 = width, row done. Result `[3, ·, ·, ·]`.
At width 2 the same stream ends after `03`, because counter 3 ≥ 2 closes the
only row.

## `.16a`: 16-bit sprites with alpha

**CONFIRMED** (`FUN_0045db6b`): the stream is little-endian 16-bit words, tested
in this order:

| Test | Meaning |
|---|---|
| `v & 0x4000` | skip `v & 0x3FFF` rows (so `0xC000 | n` is a row skip) |
| `v & 0x8000` | skip `v & 0x3FFF` transparent pixels |
| otherwise | `v` literal pixel words follow |

Pixel word:

| Bits | Field |
|---|---|
| 1–8 | palette index |
| 9–12 | alpha level `a` (0–15) |
| 0, 13–15 | always 0: **CONFIRMED** (data), 0 of 1,694,423 pixel words in the install set them. The blitter uses the whole word as a byte offset into a table of 2-byte entries, which is why bit 0 is 0. |

Blend, **CONFIRMED** (`FUN_0045db6b` + table builder `FUN_0045752b`):

```
dst = premul[pixel_word] + table[1 + a][dst]
table[k][x] = x * (16 - k) / 16      per channel, 17 tables, k = 0..16
```

So the destination is scaled by `(15 − a)/16`.

**CONFIRMED**: `premul` is the sprite palette's FADE16 shade table
([palettes §5](palettes.md)). The draw passes `row(0)`, which a2mgr
`Ordinal_37` returns. The pixel word is a byte offset into it, so it
selects row `a` and column `index`, giving `colour · (a + 1)/16`. The blend
is therefore `src·(a+1)/16 + dst·(15−a)/16`: `a = 15` is opaque and `a = 0`
has coverage 1/16. This is what `alpha_coverage()` and `Canvas.draw_16a`
implement. (The legacy low-memory mode divides by 18; it is not
reproduced.)

### Example

Width 2, height 2, words `8001 0001 1FFE 8002`:
skip 1 pixel → literal 1 word `0x1FFE` = index 255, alpha 15 → c = 2, row
done → skip 2 pixels → row done. Result row 0 = `[·, (255, 15)]`, row 1 empty.

## Placement: no hotspot in the file

The container stores only `w`, `h`, `size` per frame: there is no hotspot or
offset field (CONFIRMED, `FUN_00426da9` and all files). Callers centre each
frame on an anchor themselves:

- **CONFIRMED** (`FUN_00468640`, hero draw): with `T` the unit-type record and
  `width(f)` / `height(f)` the frame size (class vtable slots `+0x20` /
  `+0x24`, `FUN_00426c16` / `FUN_00426c41`):

  ```
  x = obj[+0x64] − ((T[+0x34] − T[+0x2c] / 2) + width(f) / 2)
  y = obj[+0x68] − ((T[+0x38] − T[+0x30] / 2) + height(f) / 2) − obj[+0x6c] − obj[+0x10]
  ```

  The `*b.256` overlay uses the same formula with its own frame size.
  **INFERRED**: `T[+0x2c..+0x38]` come from the unit's `units.reg` entry (a
  per-type centre offset), `obj[+0x6c]` is height above ground. This
  belongs to the unit-animation work (overview rank 10).

## Tools

- `python -m allods2 gfx export FILE DEST [--palette P]`: one PNG per frame
  (`DEST/<stem>_NNN.png`). `P` is a unit `.pal`, a `.bmp`, or
  `human.pal:N` for player N.
- `tools/sprite_contact.py` → `out/contact/{256,b.256,16a,16}.png`: the first
  frame of ~100 files per type, labelled, on a checkerboard.
- `tools/validate_sprites.py`: stream consumption over the whole install.

## Open questions

- How structures and objects draw their `*b.256` overlays. Their loaders
  (`0x47eec1`, `0x4808cb`) store the overlay at `entry+8`, but
  `FUN_00426be0` is only called on `entry+4`, so presumably they use an
  external table (`+0x34`).
