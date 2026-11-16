# Minimap: water colour (REA check)

Question: "water on the minimap is white, is that correct?" Build sha256
`0eaa9673...b1c7` (GOG allods2.exe). Related: [rendering 12](rendering.md#12-minimap).
**Answer: no, it was an engine bug (row order of the table), fixed: the exe reads picture row `v & 15` from the top, water comes out blue (section 4).**

## 1. What the exe does

| Fact | Where | |
|---|---|---|
| The cell colour is one 16-bit word copied from the table: `v = cell & 0x1fff`, index `(v >> 4) + W * (H - 1 - (v & 0xf))` into the buffer, which is **bottom-up** (section 4) (`W`, `H` = bitmap width / height via vtable `+0x20` / `+0x24`, 52 x 14), written to the surface (`+0x60`) at `(y - 8) * w' + (x - 8)`. Nothing else is read in the loop: **no test of the tile type, no water special case, no height / shore / relief / neighbour term** | `FUN_004ab96c` `0x4abb53`-`0x4abc3a` | CONFIRMED |
| The cell word is the raw map word (`view-map +0xc`, getter `FUN_0041e8b0`), table = global `0x626cb0` | same | CONFIRMED |
| `0x626cb0` has 9 references: the builder (5), a size sum `FUN_0047e130` (`0x47e2fb`, memory estimate), `FUN_00476a6d` (`0x477e69`) and `FUN_00477eec` (`0x478cdb`, `0x478ce4`) = load / free of the bitmaps. No routine rewrites the table colours after the load | xrefs | CONFIRMED (xref list); load / free role of the two big routines INFERRED (not read in full) |
| The base surface is drawn with the plain blit (vtable `+0x18`, no colour key) at the panel; redrawn only when the fog dirty flag `view+0xdc` is set. Fog blocks use the OR of `0xc000` bits (0: panel pixel, `0x8000`: 50 % blend, else the base word). Dots and the camera rectangle come after. **Nothing recolours water, nothing animates** | `FUN_004ac414` | CONFIRMED |
| Light pass (`0x4ac030`-`0x4ac413`): `L = 0x60 - sum4 / 4`, `c := min(max, (c * L) >> 5)` per 5-6-5 channel. It only scales brightness (default daylight L = 50, x 1.56, clamped), so it cannot turn a colour white except by clamping a colour that is already near the maximum; a white word stays white | [rendering 12](rendering.md#12-minimap) | CONFIRMED |

So the only thing that decides the water colour is the table entry
`MiniMapData.bmp[13 - (v & 15)][v >> 4]`.

## 2. The data (GOG `graphics/interface/MiniMapData.bmp`, 24-bit, 52 x 14; "table row" = `13 - (v & 15)` of the old, mirrored reading, see 3 / 4)

Column `v >> 4` = `4 * type + sub`, so the terrain type `(v >> 6)` owns four
columns: water types 8..11 are columns **32..47** (CONFIRMED by the
decoder: every campaign map's types are 0..12). Rows are `13 - (v & 15)`;
`v & 15` on the campaign maps is 0..8, 11, 12 (water cells only 0..7).

| `v & 15` (water) | table row | colours in columns 32..47 |
|---|---|---|
| 0, 1, 2, 3, 4, 5 | 13..8 | **(255, 255, 255)** in every water column (6 of 14 rows are pure white) |
| 6, 7 | 7, 6 | (41, 39, 48) / (37, 46, 67), dark grey-blue |
| 8..13 | 5..0 | blues (26..38, 43..63, 60..116), e.g. (26, 63, 116), (29, 59, 101), (33, 53, 87); a few grey entries |

No non-water column has a white entry (checked: 0 white entries outside
columns 32..47). The land entries are all dark / brown / green (sum < 400).

Water cells in the campaign maps use `v & 15` = 0..7 (never 8+), so under the
old reading they picked rows 13..6: mostly the **white** entries (map 10: 270 water cells, `v & 15`
= 0..5 on 228 of them; map 60: 1128 water cells, 908 with `v & 15` = 1). Final image (after the light pass, k >= 0):
water pixels average about (224, 225, 228) on map 10 and (194, 199, 207) on
map 21, max (255, 255, 255): white / pale grey-blue (the old, wrong picture).

## 3. Engine vs exe (as found, before the fix)

`allods2/minimap.py` indexed the **top-down** decoded image with `13 - (v & 15)`; the exe's `H - 1 - (v & 15)` addresses a **bottom-up** buffer
(section 4), so the engine read the mirrored row. Lakes and the sea came out white (rows 8..13 of the picture), which the first round of this note
took for the exe's result ("CONFIRMED rule, INFERRED art"): the static table check below decides it the other way.

## 4. The row order (CONFIRMED, static) and the fix

- The table object is made at `0x477e39` by the ctor `FUN_00424e4b` = the **"Bitmap 64k" class (24-bit files)**, stored in `0x626cb0`
  ([bitmaps](../formats/bitmaps.md): pixels are converted in file order, **no flip**, the blitters read source row `h - 1 - sy`). Buffer row 0 is therefore the
  picture's bottom row, and `H - 1 - (v & 15)` is the picture row **`v & 15` counted from the top**. (The earlier note and the minimap design spec assumed "the
  loader flips DIB rows": that is the 8-bit class.)
- Read that way the table makes sense: picture rows 0..7 hold the variants the campaign maps use (`v & 15` is 0..8, 11, 12 on land, **0..7 on water**), and
  rows 8..13 are repeats / unused values. Water columns 32..47, rows 0..7 (top-down): (38, 43, 60), (33, 53, 87), (38, 43, 60), (29, 59, 101), (33, 53, 87),
  (29, 59, 101), (37, 46, 67), (41, 39, 48): a dark blue-grey ramp. The pure-white (255, 255, 255) entries are exactly rows 8..13 of the water columns, which no
  water cell selects (water `v & 15` <= 7): placeholder filler. Under the old reading the water cells fell on exactly those filler rows, which is the white lake.
- Fix: `allods2/minimap.py` `load_color_table` returns the table in **memory order** (bottom row first; `rgb[::-1]`), the `table[13 - (v & 15)]` rule stays. Map 10's
  lake is blue, goldens `["minimaps"]` regenerated (land colours change too: the nibble picked the mirrored row before).

Notes that do not change the result:
- `13 - (v & 15)` for `v & 15` = 13..15 would index above the table (the exe
  reads memory before the pixel buffer; numpy wraps to row 13). Never occurs on
  the campaign maps (max 12). INFERRED harmless.
- `v >> 4` is at most 51 on the campaign maps (types <= 12); a larger type
  would run into the next table row in the exe (index not clamped) but would
  IndexError in the engine. Not reachable with the install.

## Open questions

- None. (Whether the original screenshot shows these exact blues is VERIFY IN GAME: map 10's lake dark blue-grey, no white.)
