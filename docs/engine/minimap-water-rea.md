# Minimap: water colour (REA check)

Question: "water on the minimap is white, is that correct?" Build sha256
`0eaa9673...b1c7` (GOG allods2.exe). Related: [rendering 12](rendering.md#12-minimap).

## 1. What the exe does

| Fact | Where | |
|---|---|---|
| The cell colour is one 16-bit word copied from the table: `v = cell & 0x1fff`, index `(v >> 4) + W * (H - 1 - (v & 0xf))` (`W`, `H` = bitmap width / height via vtable `+0x20` / `+0x24`, 52 x 14), written to the surface (`+0x60`) at `(y - 8) * w' + (x - 8)`. Nothing else is read in the loop: **no test of the tile type, no water special case, no height / shore / relief / neighbour term** | `FUN_004ab96c` `0x4abb53`-`0x4abc3a` | CONFIRMED |
| The cell word is the raw map word (`view-map +0xc`, getter `FUN_0041e8b0`), table = global `0x626cb0` | same | CONFIRMED |
| `0x626cb0` has 9 references: the builder (5), a size sum `FUN_0047e130` (`0x47e2fb`, memory estimate), `FUN_00476a6d` (`0x477e69`) and `FUN_00477eec` (`0x478cdb`, `0x478ce4`) = load / free of the bitmaps. No routine rewrites the table colours after the load | xrefs | CONFIRMED (xref list); load / free role of the two big routines INFERRED (not read in full) |
| The base surface is drawn with the plain blit (vtable `+0x18`, no colour key) at the panel; redrawn only when the fog dirty flag `view+0xdc` is set. Fog blocks use the OR of `0xc000` bits (0: panel pixel, `0x8000`: 50 % blend, else the base word). Dots and the camera rectangle come after. **Nothing recolours water, nothing animates** | `FUN_004ac414` | CONFIRMED |
| Light pass (`0x4ac030`-`0x4ac413`): `L = 0x60 - sum4 / 4`, `c := min(max, (c * L) >> 5)` per 5-6-5 channel. It only scales brightness (default daylight L = 50, x 1.56, clamped), so it cannot turn a colour white except by clamping a colour that is already near the maximum; a white word stays white | [rendering 12](rendering.md#12-minimap) | CONFIRMED |

So the only thing that decides the water colour is the table entry
`MiniMapData.bmp[13 - (v & 15)][v >> 4]`.

## 2. The data (GOG `graphics/interface/MiniMapData.bmp`, 24-bit, 52 x 14)

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

Water cells in the campaign maps use `v & 15` = 0..7 (never 8+), so they pick
rows 13..6: mostly the **white** entries (map 10: 270 water cells, `v & 15`
= 0..5 on 228 of them; map 60: 1128 water cells, 908 with `v & 15` = 1). Final image (after the light pass, k >= 0):
water pixels average about (224, 225, 228) on map 10 and (194, 199, 207) on
map 21, max (255, 255, 255): white / pale grey-blue.

## 3. Engine vs exe

`allods2/minimap.py` `minimap_rgb` (`table[13 - (v & 15), v >> 4]` after
`& 0x1fff`), `light_pass`, and `engine/view/minimap.py` match the exe rule
exactly; there is no water special case in either. Rendered
`out/minimap_10.png`, `_21`, `_60` show the lakes / sea as white blobs
(map 60 the south-east sea, map 10 a river / lake); map 32 has no water cells
(0). **Verdict: the white water is what the exe computes from the shipped
table (CONFIRMED rule, INFERRED that the shipped table is meant that way).**
No engine change is needed.

Notes that do not change the result:
- `13 - (v & 15)` for `v & 15` = 13..15 would index above the table (the exe
  reads memory before the pixel buffer; numpy wraps to row 13). Never occurs on
  the campaign maps (max 12). INFERRED harmless.
- `v >> 4` is at most 51 on the campaign maps (types <= 12); a larger type
  would run into the next table row in the exe (index not clamped) but would
  IndexError in the engine. Not reachable with the install.

## Open questions

- Is the white of rows 8..13 (low nibble 0..5 of a water cell) deliberate in the
  original art (water drawn as white "ice / foam") or a leftover of the artist's
  placeholder? Only a run of the original game (screenshot of the minimap over
  a lake) can answer; the code gives no reason to expect a different colour.
- What the water low nibble `v & 15` encodes (0..7 for water, 8..13 table rows
  blue): terrain.md covers the tile word; whether 6, 7 are shore variants is
  INFERRED from the darker table entries only.
