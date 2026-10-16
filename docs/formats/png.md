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
pixels (INFERRED from the stride: the doll's own buffer). Source = GDI+
32-bit ARGB (`B` low byte):

```
for each pixel p (0 .. 38399):
    A = src >> 24;  r = (src >> 19) & 31;  g = (src >> 10) & 63;  b = (src & 0xff) >> 3
    if A == 0: continue
    if A == 255:
        R, G, B = max(r, 1), max(g, 1), max(b, 1)
    else:
        t = A / 255.0                         # float
        for each channel c with destination d and maximum m (31, 63, 31):
            v = int(d · (1 − t) + c · t)
            C = 1 if v < 2 else min(v, m)
    dst[p] = R << 11 | G << 5 | B             # RGB565
```

Always RGB565 whatever the surface; no channel is ever 0 where drawn
(INFERRED: 0 = "empty" in the doll buffer). Straight vs premultiplied
GDI+ alpha (`PixelFormat32bppARGB` vs `PARGB`) not traced; straight is
assumed and renders correctly. The float is single precision in the
decompiler; x87 vs SSE rounding unchecked (INFERRED).

Example: white (31, 63, 31) under black at A 128: `t = 0.50196`, each
channel `int(m · 0.49804)` = (15, 31, 15) = `0x7BEF`; over black:
`0 < 2` → (1, 1, 1) = `0x0821`.

### Hit mask: `FUN_10010d00` (`+0x40`)

CONFIRMED: for 160 × 240, writes the byte argument wherever `A > 0x7e`
(INFERRED: inventory "item under cursor" mask).

## Open questions

- Which exe routine draws the 12 layers and in what order (after
  `0x46e21b`), and how `.256` and PNG layers mix in one buffer.
- Straight vs premultiplied alpha from GDI+ (`FUN_1000f220`,
  `FUN_1000fa90`).
- Size/format rules for locale PNGs (menu code not traced).
