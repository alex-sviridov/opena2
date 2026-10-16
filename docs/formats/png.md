# `.png`: paper-doll layers and menu art (a2mgr.dll)

The original game has no PNG support. All 536 `.png` files come from the
allods2.eu patch and are read only by `a2mgr.dll` via GDI+. Code:
`allods2/graphics/png.py`. Tools: `tools/validate_png.py`;
`tools/sprite_contact.py` → `out/contact/png.png`.

Standard PNG (8-bit RGBA; two files 16-bit per channel):

| Folder | Files | Size | Use |
|---|---:|---|---|
| `graphics/equipment/{m,f}{fighter,mage}/` | 516 | all 160 × 240 RGBA | paper-doll layers (bodies `<n>.png`, items `primary/<id>.png`, `secondary/<id>.png`) |
| `locale/{en,ru}/graphics/mainmenu/` | 20 | various | a2mgr's own menu art, literal paths (strings `0x10063ea8`…`0x10064434`) |

CONFIRMED (data): every equipment PNG is 160 × 240, numerically named,
with no `<name>.256` beside it; 482 of 516 use partial alpha.

## Lookup: PNG before `.256`

The exe builds paper-doll paths at `0x46dd00`–`0x46e240` (function entry
not identified); a2mgr hooks it twice (CONFIRMED):

- **Items**: `jmp [0x6de54e]` at `0x46e014` → **Ordinal_102**
  (`0x10011d60`) → `FUN_100115c0(obj, slot, primary, secondary)`; for each
  of 12 slots `primary = "graphics\equipment\<body>\primary\" + name`,
  `secondary = "...\secondary\" + name`, `<body>` = `mfighter\`,
  `mmage\`, `ffighter\`, `fmage\` (strings `0x5fb3f8`…`0x5fb418`), `name`
  = item picture name (`FUN_0043b811`, e.g. `0001008`).
- **Body**: `jmp [0x6de552]` at `0x46e1b0` → **Ordinal_103**
  (`0x10011dc0`) → `FUN_10011250`, formatting `data\%s%d.png` /
  `data\%s%d.256` from the body prefix and `obj[+0x28]` (exe's own
  `sprintf` `%s%d.256`, `0x5fb448`).

Per layer:

```
load_layer(path):                                  # path without extension
    if exists("data\" + path + ".png"):            # FUN_1000d170
        return png_layer("data\" + path + ".png")  # FUN_10010fa0
    s = cache.find("data\" + path + ".256")        # refcounted list at 0x1007b814
    if not s:
        s = SpriteFile(path + ".256")              # exe loader 0x426da9
        s.shade_table(1, 1, 0)                     # exe 0x426be0
        cache.add(s)
    return s
```

- Secondary layers only for slots 3, 8, 9, and 7 when `obj[+0x1b8] & 2`
  (same condition as the exe, `0x46e0cc`).
- A failed load becomes a shared empty PNG layer (path `""`,
  `DAT_1007b824`) drawing nothing (INFERRED: replaces the exe's `FATAL
  ERROR: can't load` for missing art).
- INFERRED: a PNG would override a same-named `.256` (never happens in
  the shipped set).

## Drawing a PNG layer

The layer object has a2mgr's vtable (`DAT_1007b820`) standing in for an
exe sprite: `+0x18` draws, `+0x40` writes the hit mask.

### Blend: `FUN_10010d70` (`+0x18`)

CONFIRMED. Only for exactly 160 × 240 (`0xa0` × `0xf0`), else nothing.
Destination = current 16-bit target `DAT_0062571c`, linear over 0x9600
pixels: the doll surface (§ Compositing). Source = GDI+ `LockBits` in
`PixelFormat32bppARGB` (`0x26200a`, **straight** alpha; CONFIRMED in all
three loaders `FUN_1000f220`, `FUN_1000fa90`, `0x1000fd5f`), `B` low byte:

```
for each pixel p (0 .. 38399):
    A = src >> 24;  r = (src >> 19) & 31;  g = (src >> 10) & 63;  b = (src & 0xff) >> 3
    if A == 0: continue
    if A == 255:
        R, G, B = max(r, 1), max(g, 1), max(b, 1)
    else:
        t = single(A / 255.0)
        for each channel c with destination d and maximum m (31, 63, 31):
            v = trunc(single(d · (1.0 − t) + double(single(c · t))))
            C = 1 if v < 2 else min(v, m)
    dst[p] = R << 11 | G << 5 | B             # RGB565
```

Always RGB565 whatever the surface; no channel is ever 0 where drawn
(INFERRED: 0 = "empty" in the doll buffer, which starts zeroed). SSE
(CONFIRMED): `d·(1 − t)` is double, `c·t` single, the sum is rounded to
single and truncated; all-single arithmetic differs in 845 of the
254·64·64 cases (A 65, d 51, c 0 → 38, not 37).

Example: white (31, 63, 31) under black at A 128: `t = 0.50196`, each
channel `int(m · 0.49804)` = (15, 31, 15) = `0x7BEF`; over black:
`0 < 2` → (1, 1, 1) = `0x0821`.

### Hit mask: `FUN_10010d00` (`+0x40`)

CONFIRMED: for 160 × 240, writes the byte argument wherever `A > 0x7e`
(INFERRED: inventory "item under cursor" mask).

## Compositing: `FUN_0046dd6a`

CONFIRMED. CUnit virtual `+0x88` (vtable `0x5d7780`; also CAirUnit's),
args `(file, surface, mask)`: zeroes the 16-bit `surface` and the byte
`mask`, builds the layers (§ Lookup; primary `P0…P11`, secondary `S…`,
body `B` = `obj[+0x28]` file), then calls each layer's draw `+0x18` at
(0, 0) into the surface. `.256` layers (shade table mode 1, 1 level,
[palettes](palettes.md)) write plain 16-bit pixels; PNG layers blend over
whatever is there, so later layers cover earlier ones in one buffer.

1. `graphics\infowindow\horse.bmp` when `obj[+0x24]` is 17…21.
2. Hero back `graphics\interface\heroback\backm.256` / `backf.256` (by
   `+0x1b8 & 4`) when `+0x1b8 & 1` and not `& 2` (loaded by
   `0x47d164`/`0x47d1d3`, globals `0x630e5c/60`).
3. Body type `+0x1b8 & 6`: 0 `mfighter`, 2 `mmage`, 4 `ffighter`,
   6 `fmage` (jump table `0x46ee29`). With `& 2` (mage):

   `P7 B P11 P9 S9 P3 S3 P6 P4 P0 P5 S7`

   otherwise (fighter), with `2h` = slot 0's item class (`FUN_0043ba17`:
   `bowman`, `archer`, `xbowman`, `axeman2h`, `swordsman2h`, `mage_st`):

   `B P11 P10 P6 P3 P4 P8 P9 [P0 if not 2h] P7 S3 P5 S8 S9 (P0 if 2h else P1)`

4. If `mask`: each layer's `+0x40` writes its id (slot + 1; body 0)
   where it covers (PNG: `A > 0x7e`), in the same order except: the mage
   list adds `P8` (id 9, between `P4` and `P0`) though `P8` is never
   drawn for mages; the fighter list has no `B`.
5. If `file`: `FUN_00427ac3` writes a 14 + 40 byte header, the pixels as
   24-bit, then the mask (INFERRED: a BMP dump).

Never drawn: `P2`, and for mages `P1`, `P8`, `P10`. `doll_layer_order`,
`doll_mask_order`.

## Menu PNGs (a2mgr)

CONFIRMED. `FUN_1000f220` loads any PNG GDI+ opens, any size, into a
32-bit straight ARGB copy (`+0` pixels, `+4` width, `+8` height). Only
`menunew.png` and `menulogo.png` use `data/locale/%s/…` (`%s` = `ru` or
`en` by byte `0x10078012`); the 16 widget images (check, radio, enter,
mfield, mb_*) are literal `data/locale/ru/…` paths, so every locale uses
the Russian art. `menunew` is drawn at the menu window's corner,
`menulogo` at `+163, +21` (`0x10028e1f`).

Blit `FUN_1000f790(x, y, sx, sy, w, h, hard)` (`FUN_1000f760` = whole
image at x, y): negative `x`/`y` become 0 with `sx`/`sy` = −x/−y
(ignoring the passed ones); `w`, `h` are cut to the image; nothing is
drawn if the rectangle misses the clip rectangle (`0x625768…774`) or
would cross the surface's right edge (pitch). Per pixel, RGB565:

```
if hard: A > 0x7f → 255, else skip;  else A == 0 → skip
A == 255: (r5, g6, b5)                               # no ≥ 1 rule
else:     C = trunc(min(single(d·(1.0 − t) + double(single(c·t))), m))
```

with `t` as in the doll blend. `blend_menu_png`.

## Open questions

None.
