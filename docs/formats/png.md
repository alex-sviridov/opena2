# `.png`: paper-doll layers and menu art (a2mgr.dll)

The original game has no PNG support. All 536 `.png` files in this install
come from the allods2.eu patch and are read only by `a2mgr.dll`
(sha256 `6bc57ebba86d4a2a7b8505bef9099c17652009fcb0f7a147fee6b2aa29077cc6`,
image base 0x10000000), through GDI+. Addresses were read in REA
(Ghidra 12.1.4). Implementation: `allods2/graphics/png.py`. Validation:
`tools/validate_png.py`. Contact sheet: `tools/sprite_contact.py` →
`out/contact/png.png`.

The file format is standard PNG (8-bit RGBA; two files are 16-bit per
channel). The interesting part is how a2mgr finds and draws these files.

| Folder | Files | Size | Use |
|---|---:|---|---|
| `graphics/equipment/{m,f}{fighter,mage}/` | 516 | all 160 × 240 RGBA | paper-doll layers (bodies `<n>.png`, items `primary/<id>.png`, `secondary/<id>.png`) |
| `locale/{en,ru}/graphics/mainmenu/` | 20 | various | a2mgr's own main-menu art, loaded by literal path (strings at 0x10063ea8…0x10064434) |

**CONFIRMED** (data, all files): every equipment PNG is 160 × 240, its name
is a number, and no `<name>.256` exists next to it. 482 of the 516 use
partial alpha.

## Lookup: PNG before `.256`

The exe builds paper-doll paths in its paper-doll loader (code at
0x46dd00–0x46e240; the function entry was not identified). a2mgr hooks it twice. **CONFIRMED**:

- **Items**, `jmp [0x6de54e]` at 0x46e014 → **Ordinal_102** (0x10011d60) →
  `FUN_100115c0(obj, slot, primary, secondary)`. For each of the 12 slots
  the exe has built `primary = "graphics\equipment\<body>\primary\" + name`
  and `secondary = "...\secondary\" + name`, where `<body>` is `mfighter\`,
  `mmage\`, `ffighter\` or `fmage\` (strings 0x5fb3f8…0x5fb418) and `name`
  is the item's picture name (`FUN_0043b811`, e.g. `0001008`).
- **Body**, `jmp [0x6de552]` at 0x46e1b0 → **Ordinal_103** (0x10011dc0) →
  `FUN_10011250`, which formats `data\%s%d.png` / `data\%s%d.256` with the
  body prefix and `obj[+0x28]` (the exe's own `sprintf` uses `%s%d.256`,
  0x5fb448).

Both then do the same thing per layer:

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

- The secondary layer is loaded only for slots 3, 8 and 9, and for slot 7
  when `obj[+0x1b8] & 2`. This is the same condition the exe uses
  (0x46e0cc).
- A layer that fails to load becomes a shared empty PNG layer (path `""`,
  `DAT_1007b824`) that draws nothing. **INFERRED**: this replaces the exe's
  `FATAL ERROR: can't load` for missing equipment art.
- **INFERRED**: because the PNG is tried first, a PNG would replace a
  `.256` of the same name. The shipped set never does this.

## Drawing a PNG layer

A PNG layer is an object with a2mgr's own vtable (`DAT_1007b820`), standing
in for an exe sprite: slot `+0x18` draws it, slot `+0x40` writes the hit mask.

### Blend: `FUN_10010d70` (`+0x18`)

**CONFIRMED.** Only if the image is exactly 160 × 240 (`0xa0` × `0xf0`);
otherwise nothing is drawn. The destination is the current 16-bit target
`DAT_0062571c`, indexed linearly over 0x9600 = 160 · 240 pixels, so it is
the paper-doll's own buffer (INFERRED from the stride). Source pixels are GDI+
32-bit ARGB (`B` in the low byte):

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

The output is always RGB565, whatever the surface format. No channel is
ever 0 where a layer is drawn. **INFERRED**: 0 marks "empty" in the doll
buffer. Whether GDI+ hands straight or premultiplied alpha
(`PixelFormat32bppARGB` vs `PARGB`) was not traced; the implementation
assumes straight alpha, which renders correctly. The float type is
single-precision in the decompiler output; x87 vs SSE rounding was not
checked (INFERRED).

### Hit mask: `FUN_10010d00` (`+0x40`)

**CONFIRMED**: for a 160 × 240 image, writes the byte argument into the
target buffer wherever `A > 0x7e`. **INFERRED**: this is the per-pixel
"which item is under the cursor" mask of the inventory screen.

## Worked example

Destination pixel white (31, 63, 31), source black with A = 128:
`t = 128/255 = 0.50196`, each channel `int(m · 0.49804)` = (15, 31, 15) →
`0x7BEF`. The same source over black: `int(0) = 0 < 2` → (1, 1, 1) = `0x0821`.

## Open questions

- Which exe routine draws the 12 layers and in what order (the code after
  0x46e21b), and how `.256` layers mix with PNG ones in the same buffer.
- Straight vs premultiplied alpha from GDI+ (`FUN_1000f220`, `FUN_1000fa90`).
- Whether any locale PNG has size or format rules (menu code not traced).
