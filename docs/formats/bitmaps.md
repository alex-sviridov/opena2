# Bitmaps: `.bmp`

Code: `allods2/graphics/bmp.py` (`load_bmp`; `Bitmap.rgb16(bits)`,
`Bitmap.key_mask(bits)` for the 64k class).

## Layout

Standard Windows DIB: 14-byte `BITMAPFILEHEADER` (`"BM"`, size, pixel
offset); 40-byte `BITMAPINFOHEADER` (height > 0 = bottom-up, 1 plane, bpp,
compression 0); at 54 the 1024-byte colour table (8-bit only, RGBQUAD
`B, G, R, 0`); rows bottom first, padded to 4 bytes.

- CONFIRMED (vtable `0x5d5430` "Bitmap 256 colors", `FUN_004280d4` called
  at `0x428074`): the 8-bit class flips rows in place after loading
  (memory top row first).
- CONFIRMED (vtable `0x5d53f0` "Bitmap 64k colors", constructor
  `FUN_0042769b`): the 24-bit class does **not** flip; its blitters read
  source row `h − 1 − sy`, so pictures still come out upright. Its `+0x2c`
  (`FUN_00427c09`) flips rows in place (portrait canvas below).
- CONFIRMED (data): all 841 `.bmp` under `data/graphics` are uncompressed
  and bottom-up: 778 24-bit, 63 8-bit.

Example: `terrain/tile1-00.bmp` (8-bit, 32 × 448) = 14 tiles of 32 × 32,
top tile first after flipping.

## The "Bitmap 64k" class (24-bit files)

CONFIRMED (`FUN_0042769b`): reads the two headers, then exactly `w·h·3`
pixel bytes in chunks ≤ `0x16800`, converted by `FUN_004274d4` into
`u16 pixels[w·h]` at `this+0x10 → +8` after a `u32 w, u32 h` prefix;
`bfOffBits` and row padding are ignored (never matters: all 778 files have
`bfOffBits = 54` and `3w ≡ 0 mod 4`). Bytes `B, G, R` per pixel →
`pack16` ([palettes §5](palettes.md)):

```
px = (R >> (8 − Rbits)) << Rshift
   | (G >> (8 − Gbits)) << Gshift
   | (B >> (8 − Bbits)) << Bshift
```

CONFIRMED (`FUN_004584cc`): the six values come from the primary surface's
`IDirectDrawSurface::GetPixelFormat` (vtable `+0x54`): for the low 16 bits
of `dwRBitMask`/`dwGBitMask`/`dwBBitMask`, `shift = lowest set bit`
(`FUN_00457b9c`), `bits = highest − shift + 1` (`FUN_00457bd4`) →
`0x5fb958/95c/62c9bc` (shifts), `0x5fb960/964/968` (widths); skipped when
the R mask is 0; then rebuilds the shade tables (`FUN_00457939`,
`FUN_0045752b`, `FUN_00463d30`). INFERRED: on current systems/a2mgr
5-6-5 → `(11, 5, 0)`, `(5, 6, 5)`. Example: `B, G, R = 0x40, 0x80, 0xff`
→ `0xf800 | 0x0400 | 0x0008 = 0xfc08`.

Draw methods (vtable `0x5d53f0`), all clipping to `0x625768…774`, writing
`DAT_0062571c` with pitch `DAT_00625708`, reading source row
`h − 1 − sy`; rect forms take `(x, y, sx0, sy0, sx1, sy1)`:

| Slot | Method | Blit | Effect |
|---|---|---|---|
| `+0x18` | `FUN_00427d3a` | `FUN_00458bad` | opaque, whole bitmap |
| `+0x34` | `FUN_00427d8b` | `FUN_00458bad` | opaque, source rect |
| `+0x38` | `FUN_00427dd5` | `FUN_00458e9a` | colour key: `0x0000` skipped (5-6-5: every colour with R < 8, G < 4, B < 8) |
| `+0x3c` | `FUN_00427e1f` | `FUN_00458d28` | `dst = (dst + src) & 0xFFFF`: plain 16-bit add, overflow carries into the next field |
| `+0x14`, `+0x1c` | `FUN_0042a820`, `FUN_0042a830` | — | no-ops (`ret 0x18`, `ret 0x14`); sprites put darken at `+0x1c` (e.g. the shop price bar, [sprites](sprites.md)) |
| `+0x20`, `+0x24` | `FUN_00427e8f`, `FUN_00427ea4` | | width, height |

## Off-screen canvases (info-window portrait)

CONFIRMED (`FUN_004278ac`): `new Bitmap64k(w, h)` = blank canvas, same
layout; vtable `+0x28` (`FUN_00426c87`) makes it the render target
(`DAT_0062571c` = pixels, `0x625704`/`0x625700` = size, pitch
`DAT_00625708 = w·2`).

CONFIRMED (`FUN_0041f2d4`; the only `+0x2c` user among the 42
`call [reg+0x2c]` sites, heuristic scan matching each site's object
against where `FUN_0042769b`/`FUN_004278ac` results are stored). Result →
widget at `0x4e52a6`, `widget+0x5c`, drawn with `+0x18`/`+0x38` at
`0x4e3d6e`…`0x4e3e46`:

1. Allocate `panel` (88 × 108) and `pic` (160 × 240).
2. Load `graphics\infowindow\<name><n>.bmp` into `pic`: `name` = type's
   `InfoPicture` (record `+0xf8`, stored by the units.reg parser at
   `0x47fd4e`), `n` = `obj+0x28`, digit dropped for 1 (`goblin.bmp`,
   `goblin2.bmp`, …). Objects with flags `+0x1b8 & 0x11` draw themselves
   into `pic` (vtable `+0x88`). Loaded with `FUN_00427945` (bottom-up)
   and **flipped** (top row first).
3. Target `panel`, clear its 0x4a40 bytes (88·108·2).
4. Flip `t_back.bmp` (`DAT_00630b8c`, loaded `0x47d107`), blit its rect
   (`+0x34`), then `pic`'s same rect (`+0x38`, colour key) to `(8, 7)`,
   flip `t_back.bmp` back. Rect `(0x24, 0x8c)–(0x6c, 0xe8)`, or
   `(k2, 0x90 − k1)–(k2 + 0x48, 0xf0 − k1)` with a per-type crop
   `k1 ≠ −1` (below).
5. Draw `t_border.256` (`DAT_00630e58`) with sprite `+0x18` at `(0, 0)`.

### Portrait crop table

CONFIRMED (`FUN_0041f2d4` at `0x41f52e`): the rect starts
`(−1, −1, −1, −1)` (`FUN_00420330`); for `type = obj+0x24` (units.reg
`ID`) in 0x40–0x66 the pair `(k2, k1) = (i32 [0x5fcd70 + 8·type],
i32 [0x5fcd74 + 8·type])`; the base lies inside a string, but for these
types the reads land in a 39-entry table at **`0x5fcf70` + 8·(type −
0x40)**. `k1 = −1` → default rect. Values (ID unit k2, k1): 0x40 goblin
30, 72; 0x41 orc 26, 23; 0x42 ogre 10, 44; 0x43 — −1; 0x44 troll 15, 21;
0x45 ghost 32, 21; 0x46 bat −1; 0x47 dragon 7, 49; 0x48 mainnecro, 0x49
bee −1; 0x4a squirrel 8, 72; 0x4b–0x4e leg, turtle, … −1; 0x4f goblin_s
30, 72; 0x50 orc_s 23, 31; 0x51 orc_sh 43, 7; 0x52–0x58 zombies 37, 28;
0x59–0x5c skeleton f1–f4 37, 24; 0x5d–0x60 skeleton a1–a4 37, 15; 0x61,
0x62 skeleton m3, m4 35, 15; 0x63 necromant 35, 14; 0x64 druid 35, 21;
0x65 orc_good 32, 18; 0x66 troll_good 15, 21. Names are units.reg `File`
folders. Other types (heroes, humans, the later wolf 0x67, spider 0x68)
use the default. Goblin rect: `(30, 72)–(102, 168)`.

Blitters read source row `h − 1 − sy` and write downward, so with
top-first sources the panel ends up **bottom-up** like a loaded bitmap
and later `+0x18`/`+0x38` draws show it upright; the default rect shows
`pic` rows 8–99, columns 36–107. **Quirk**: the sprite blit in step 5
writes top row first, so `t_border.256` appears **vertically mirrored**
(nearly symmetric: 672 of 9,504 mask pixels differ from the mirror).

Unit `.pal` files are 8-bit BMPs of which only the colour table is read
([palettes](palettes.md)).

## Open questions

None.
