# Bitmaps: `.bmp`

Implementation: `allods2/graphics/bmp.py` (`load_bmp`; `Bitmap.rgb16(bits)` and
`Bitmap.key_mask(bits)` for the 64k class). Binary references are to
`allods2.exe` English 1.30 (sha256 `2a8bdf9d…fe43`).

## Layout

Standard Windows DIB:

| Offset | Size | Field |
|---|---|---|
| 0 | 14 | `BITMAPFILEHEADER` (`"BM"`, file size, pixel data offset) |
| 14 | 40 | `BITMAPINFOHEADER` (width, height > 0 = bottom-up, 1 plane, bpp, compression 0) |
| 54 | 1024 | colour table (8-bit only), RGBQUAD `B, G, R, 0` |
| offset | … | rows, bottom row first, each padded to 4 bytes |

- **CONFIRMED** (vtable `0x5d5430` "Bitmap 256 colors", `FUN_004280d4`):
  the 8-bit class flips the rows in place after loading (called at
  `0x428074`), so its memory is top row first.
- **CONFIRMED** (vtable `0x5d53f0` "Bitmap 64k colors", constructor
  `FUN_0042769b`): the 24-bit class does **not** flip. Its blitters read
  source row `h − 1 − sy` instead (below), so the picture still comes out
  top row first. Its `+0x2c` method (`FUN_00427c09`) flips the rows in
  place (see "Off-screen canvases" below).
- **CONFIRMED** (data): all 841 `.bmp` files under `data/graphics` are
  uncompressed and bottom-up: 778 are 24-bit, 63 are 8-bit.

## The "Bitmap 64k" class (24-bit files)

**CONFIRMED** (`FUN_0042769b`): the loader reads the 14-byte file header and
the 40-byte info header, then exactly `w·h·3` pixel bytes in chunks of up
to `0x16800`. It converts each chunk with `FUN_004274d4` into
`u16 pixels[w·h]` at `this+0x10 → +8`, after a `u32 w, u32 h` prefix. It
ignores `bfOffBits` and row padding. **CONFIRMED** (data): all 778 24-bit
files have `bfOffBits = 54` and `3w ≡ 0 (mod 4)`, so the quirk never shows.

Per pixel, the bytes are `B, G, R` (`FUN_004274d4`):

```
px = (R >> (8 − Rbits)) << Rshift
   | (G >> (8 − Gbits)) << Gshift
   | (B >> (8 − Bbits)) << Bshift
```

This is `pack16` in [palettes §5](palettes.md), the same formula the shade
tables use.

**CONFIRMED** (`FUN_004584cc`): the six values come from the primary
surface. `IDirectDrawSurface::GetPixelFormat` (vtable `+0x54`) fills a
`DDPIXELFORMAT`. With `mask` = the low 16 bits of `dwRBitMask`,
`dwGBitMask` or `dwBBitMask`, the code sets `shift = lowest set bit`
(`FUN_00457b9c`) and `bits = highest set bit − shift + 1`
(`FUN_00457bd4`). The results go to `0x5fb958 / 95c / 62c9bc` (shifts)
and `0x5fb960 / 964 / 968` (widths). The step is skipped when the R mask
is 0. It then rebuilds the shade tables (`FUN_00457939`, `FUN_0045752b`,
`FUN_00463d30`). **INFERRED**: on current systems, and with a2mgr, the
format is 5-6-5, giving `(11, 5, 0)` and `(5, 6, 5)`.

Draw methods (vtable `0x5d53f0`). All of them clip to `0x625768…774`,
write to `DAT_0062571c` with pitch `DAT_00625708`, and read source row
`(h − 1 − sy)`:

| Slot | Method | Blit | Effect |
|---|---|---|---|
| `+0x18` | `FUN_00427d3a` | `FUN_00458bad` | opaque, whole bitmap |
| `+0x34` | `FUN_00427d8b` | `FUN_00458bad` | opaque, source rect `(sx0, sy0, sx1, sy1)` |
| `+0x38` | `FUN_00427dd5` | `FUN_00458e9a` | colour key: pixels equal to `0x0000` are skipped. In 5-6-5 that is every source colour with R < 8, G < 4, B < 8 |
| `+0x3c` | `FUN_00427e1f` | `FUN_00458d28` | additive, `dst = (dst + src) & 0xFFFF`: a plain 16-bit add, so channel overflow carries into the next field |
| `+0x14`, `+0x1c` | `FUN_0042a820`, `FUN_0042a830` | none | no-ops (`ret 0x18`, `ret 0x14`) |
| `+0x20`, `+0x24` | `FUN_00427e8f`, `FUN_00427ea4` | | width, height |

The arguments are `(x, y, sx0, sy0, sx1, sy1)` for the rect forms. The
sprite classes put their darken blit at `+0x1c`; here that slot does
nothing. One example is the shop price bar ([sprites](sprites.md)).

### Example

`terrain/tile1-00.bmp` (8-bit) is 32 × 448: a vertical strip of 14 tiles of
32 × 32, top tile first after flipping.

24-bit pixel `B, G, R = 0x40, 0x80, 0xff` on a 5-6-5 surface:
`(0xff >> 3) << 11 | (0x80 >> 2) << 5 | (0x40 >> 3) = 0xf800 | 0x0400 | 0x0008 = 0xfc08`.

## Off-screen canvases (info-window portrait)

**CONFIRMED** (`FUN_004278ac`): `new Bitmap64k(w, h)` allocates a blank
canvas with the same layout. Making it the render target is vtable `+0x28`
(`FUN_00426c87`): it sets `DAT_0062571c` to the pixels, `0x625704` /
`0x625700` to the size, and the pitch `DAT_00625708` to `w·2`.

**CONFIRMED** (`FUN_0041f2d4`). A heuristic scan of the 42
`call [reg+0x2c]` sites found no other that involves a 64k bitmap: it
matched each site's object against the fields and globals that
`FUN_0042769b` / `FUN_004278ac` results are stored in. The result goes to the widget at `0x4e52a6`, `widget+0x5c`, and is drawn with
`+0x18` / `+0x38` at `0x4e3d6e`…`0x4e3e46`):

1. Allocate `panel` (88 × 108) and `pic` (160 × 240) canvases.
2. Load `graphics\infowindow\<name><n>.bmp` into `pic`. `name` is the
   type's `InfoPicture` (type record `+0xf8`, stored by the units.reg parser
   at 0x47fd4e), `n` is `obj+0x28`, and for `n = 1` the digit is dropped
   (`goblin.bmp`, `goblin2.bmp`, …). Objects with flags `+0x1b8 & 0x11` draw
   themselves into `pic` instead (vtable `+0x88`). The bitmap is loaded
   with `FUN_00427945` (the same bottom-up load as the constructor) and
   **flipped**, so it is top row first.
3. Make `panel` the render target and clear the 0x4a40 bytes at
   `DAT_0062571c` (the panel is 88·108·2 = 0x4a40 bytes).
4. Flip `t_back.bmp` (`DAT_00630b8c`, loaded at `0x47d107`), blit its rect
   `+0x34` and then `pic`'s same rect `+0x38` (colour key) to `(8, 7)`, then
   flip `t_back.bmp` back. The rect is `(0x24, 0x8c)–(0x6c, 0xe8)`, or
   `(k2, 0x90 − k1)–(k2 + 0x48, 0xf0 − k1)` when the unit has a per-type
   crop offset with `k1 ≠ −1` (table below).
5. Draw `t_border.256` (`DAT_00630e58`) with the sprite blit `+0x18` at
   `(0, 0)`.

### Portrait crop table

**CONFIRMED** (`FUN_0041f2d4` at 0x41f52e). The rect starts as
`(−1, −1, −1, −1)` (`FUN_00420330`). If `type = obj+0x24` (the units.reg
`ID`) is in 0x40–0x66, its first two ints are set to the pair
`(k2, k1) = (i32 [0x5fcd70 + 8·type], i32 [0x5fcd74 + 8·type])`. The code
indexes from 0x5fcd70 (inside a string), but for these types the reads land
in a 39-entry table at **`0x5fcf70` + 8·(type − 0x40)**. Then `k1 = −1`
selects the default rect.

| ID | Unit | k2, k1 | | ID | Unit | k2, k1 |
|---|---|---|---|---|---|---|
| 0x40 | goblin | 30, 72 | | 0x52–0x58 | zombies | 37, 28 |
| 0x41 | orc | 26, 23 | | 0x59–0x5c | skeleton f1–f4 | 37, 24 |
| 0x42 | ogre | 10, 44 | | 0x5d–0x60 | skeleton a1–a4 | 37, 15 |
| 0x43 | — | −1, −1 | | 0x61, 0x62 | skeleton m3, m4 | 35, 15 |
| 0x44 | troll | 15, 21 | | 0x63 | necromant | 35, 14 |
| 0x45 | ghost | 32, 21 | | 0x64 | druid | 35, 21 |
| 0x46 | bat | −1, −1 | | 0x65 | orc_good | 32, 18 |
| 0x47 | dragon | 7, 49 | | 0x66 | troll_good | 15, 21 |
| 0x48, 0x49 | mainnecro, bee | −1, −1 | | | | |
| 0x4a | squirrel | 8, 72 | | | | |
| 0x4b–0x4e | leg, turtle, … | −1, −1 | | | | |
| 0x4f | goblin_s | 30, 72 | | | | |
| 0x50 | orc_s | 23, 31 | | | | |
| 0x51 | orc_sh | 43, 7 | | | | |

Unit names are the units.reg `File` folders. Types outside 0x40–0x66
(heroes, humans, and the later wolf 0x67 and spider 0x68) always use the
default rect `(0x24, 0x8c)–(0x6c, 0xe8)`. Example: the goblin rect is
`(30, 72)–(102, 168)`.

The blitters read source row `h − 1 − sy` and write destination rows
downward. With top-first sources (steps 2 and 4), the panel therefore ends
up **bottom-up**, like a loaded bitmap, and the later `+0x18` / `+0x38`
draws show it upright. With the default rect, the panel shows `pic` rows
8–99 and columns 36–107.

**Quirk** (follows from the code): the sprite blitter in step 5 writes top
row first, so `t_border.256` appears **vertically mirrored** on screen. The
frame is nearly symmetric (672 of 9,504 mask pixels differ from the mirror
image), so this is hard to see.

## Related

Unit `.pal` files are also 8-bit BMPs; the game reads only their colour table.
See [palettes](palettes.md).

## Open questions

None.
