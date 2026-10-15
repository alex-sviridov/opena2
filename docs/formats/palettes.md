# Palettes

Implementation: `allods2/graphics/palette.py`. Binary references are to
`allods2.exe` English 1.30 (sha256 `2a8bdf9d…fe43`), see [sprites](sprites.md).

## Layout

| Offset | Size | Field |
|---|---|---|
| 4·i + 0 | 1 | blue |
| 4·i + 1 | 1 | green |
| 4·i + 2 | 1 | red |
| 4·i + 3 | 1 | reserved (0) |

256 entries, 1024 bytes. This is the BMP RGBQUAD layout.

- **CONFIRMED** (data): the embedded palette of
  `units/monsters/bat/sprites.256` is byte-identical to the colour table of
  `units/monsters/bat/palette.pal`, which is a BMP colour table.
- **CONFIRMED** (data): decoding sprites with B, G, R order gives plausible
  colours (brown bats, orange cloaks, silver chains); R, G, B order does not.

### Example

Bytes `0A 14 1E 00` at offset 4 → entry 1 = RGB (30, 20, 10).

## Embedded sprite palettes

The first 1024 bytes of a sprite container whose trailer has bit 31 set;
see [sprites](sprites.md).

## Unit palettes: `palette.pal`, `palette2.pal`, …

**CONFIRMED** (`FUN_0047f108`, unit registry loader):

1. `units.reg` gives each unit a `Palette` count `N`.
2. For `i = 1..N` the file is `<unit dir>\palette<i>.pal`, except that the
   digit is dropped for `i = 1`: `palette.pal`, `palette2.pal`, ….
3. The game opens the file, **seeks to 0x36** and reads 0x400 bytes.

**CONFIRMED** (data): these files are 8-bit BMP images with a 54-byte header,
so offset 0x36 is the start of the colour table.

**INFERRED**: the game ignores the BMP's pixel data and header fields; it
depends on the header being exactly 54 bytes.

## `units/humans/human.pal`

**CONFIRMED** (`FUN_0047f108`): a raw 0x4000-byte file (16 palettes × 1024
bytes, no header), read into `DAT_0062cb78`. Each palette is passed to
`FUN_00425bee(pal + i·0x400, 0x10, 2, 1)`, and palette 0 also to
`FUN_00425bee(pal, 0x10, 5, 0)`. For shade levels `15 − k` (k = 0..7), the
loader caches entry `0x148/2` of each converted palette in a table at
`0x629c90`.

**Open:** what `FUN_00425bee`'s arguments mean. **INFERRED**: this is probably a
16-entry player-colour range remap.

## Conversion to screen pixels

**CONFIRMED** (`FUN_00420440`): in this build, palette conversion jumps to
`a2mgr.dll` `Ordinal_37` (the community patch), which is not analysed yet. The
original game drew to 16-bit surfaces. Channel widths and shifts are globals at
`0x5fb958…0x5fb968`, and `FUN_0045752b` builds blend tables from them.

The Python implementation works in RGB888 and ignores the 16-bit rounding.
