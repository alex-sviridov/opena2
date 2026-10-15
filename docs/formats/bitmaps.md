# Bitmaps: `.bmp`

Implementation: `allods2/graphics/bmp.py`. Binary references are to
`allods2.exe` English 1.30 (sha256 `2a8bdf9d…fe43`).

## Layout

Standard Windows DIB:

| Offset | Size | Field |
|---|---|---|
| 0 | 14 | `BITMAPFILEHEADER` (`"BM"`, file size, pixel data offset) |
| 14 | 40 | `BITMAPINFOHEADER` (width, height > 0 = bottom-up, 1 plane, bpp, compression 0) |
| 54 | 1024 | colour table (8-bit only), RGBQUAD `B, G, R, 0` |
| offset | … | rows, bottom row first, each padded to 4 bytes |

- **CONFIRMED** (vtables `0x5d53f0` "Bitmap 64k colors", `0x5d5430` "Bitmap
  256 colors"): after loading, the bitmap classes flip the rows in place
  (`FUN_00427c09` for 16-bit, `FUN_004280d4` for 8-bit). This matches
  bottom-up storage.
- **CONFIRMED** (data): all 841 `.bmp` files under `data/graphics` are
  uncompressed and bottom-up: 778 are 24-bit, 63 are 8-bit.
- **INFERRED**: the "64k" class converts 24-bit files to the 16-bit screen
  format at load. The loader body has not been read yet.

### Example

`terrain/tile1-00.bmp` is 32 × 448: a vertical strip of 14 tiles of 32 × 32,
top tile first after flipping.

## Related

Unit `.pal` files are also 8-bit BMPs; the game reads only their colour table.
See [palettes](palettes.md).

## Open questions

- How the terrain strips are indexed by the map format (tile → strip row).
- The 24 → 16-bit conversion used by the "64k" class.
