# Minimap (G2c) design

Goal: a minimap that looks like the original's and navigates (click/drag centres the camera).
Decision of 2026-10-16: **small and cheap**, not a bit-exact copy of the exe's image.
Facts are marked CONFIRMED (GOG allods2.exe 1.01 via REA) / INFERRED / DECISION.

## 1. How the exe does it (docs/engine/rendering.md "Minimap" holds the same table)

- Generated at load, **no data in the .alm**. Builder `FUN_004ab96c` (called from `FUN_004ab896`)
  fills two 16-bit surfaces on the minimap view object: `+0x60` base image, `+0x64` fogged copy;
  `+0x68` = scale shift `k`. CONFIRMED.
- Colour per cell: `v = cell & 0x1fff` (dirt and fog bits off), `pixel = table[13 - (v & 0xf)][v >> 4]`
  in memory order of `graphics\interface\MiniMapData.bmp` (52x14, 24 bit; the loader flips DIB rows,
  so the row in `Bitmap.rgb` is `13 - (v & 0xf)`). A fixed colour per strip id and tile row, not an
  average of the tile art. Cells `8 <= col < w-8`, `8 <= row < h-8` only. CONFIRMED
  (`0x4abb45`-`0x4abc3a`); max strip id 51 and row 13 in every map checked.
- Scale from the longer side `m = max(w, h)` (full size, border included): `m > 144` -> `k = -1`
  (image `(w-16)>>1`, 2x2 average), `m > 80` -> 0, `m > 48` -> 1, else 2; image
  `((w-16) << k, (h-16) << k)`. So the 80x80 and 144x144 campaign maps both give 128x128. CONFIRMED
  (`0x4abc44`-`0x4abd82`).
- Base image never depends on passability, objects or units. **Hypothesis 4 (rebuild when passability or
  objects change) is refuted**: only fog changes the picture (dirty flag `view+0xdc`, redrawn at most
  every 10 view-clock ticks). CONFIRMED (`FUN_004ac414`).
- Draw `FUN_004ac414`: image centred on the panel point `(0x48, 0x52) = (72, 82)` from the widget
  origin (`origin = FUN_004d3a23(this+8)`); offset `x = 72 - (w16 << k)/2`, `y = 82 - (h16 << k)/2`. CONFIRMED.
- Fog (not drawn by the engine yet; no fog in the world): per image cell the four fog bits (`0xc000`) of
  cells `(c, r), (c+1, r), (c, r+1), (c+1, r+1)` are OR-ed; `0` -> pixel of surface `DAT_00626be0`
  (unexplored), `0x8000` -> 50% blend with it (explored, not visible), else the base pixel. CONFIRMED.
- Overlay: every minimap object (list `FUN_00420140`) draws itself (vtable `+0x34`, args origin and `k`);
  then the **camera rectangle**, a one-pixel white outline (`FUN_004569a3`) from
  `((cam_col - 8) * s, (cam_row - 8) * s)` size `(view_cols * s, view_rows * s)` minus one, `s = 2^k`
  (`/2` for `k = -1`). CONFIRMED. Units are drawn by those objects: not implemented (no units yet).
- A last pass at `0x4ac030`-`0x4ac413` adjusts channels with the pixel-format shifts: unidentified,
  not reproduced (open question).

## 2. Design

| Piece | Layer | Content |
|---|---|---|
| `allods2/minimap.py` | 2 (numpy, no pygame) | `scale_shift(w, h)`, `minimap_size(w, h)`, `load_color_table(fs)`, `minimap_rgb(cells, table)` -> `(H, W, 3)` uint8 |
| `engine/view/minimap.py` | 6 | `MinimapGeometry(w, h)` (size, `s`, `cell_to_pixel`, `pixel_to_cell`, `camera_rect`), `Minimap(world, table)` (base image built once, `invalidate()`, `image(camera)` with the camera rectangle) |
| `engine/ui/minimap.py` | 5 | `MinimapPanel(geometry, origin)`: `contains`, `press`, `drag` -> `camera.move_to` (view state, never a command) |
| `engine/backend_pygame/window.py` | 7 | draws the panel, routes mouse down/motion |
| `python -m engine minimap MAP DEST.png` | CLI | headless base image |

DECISIONS (deviations from the exe, all in the cheap direction):
- `k = -1` takes every second pixel instead of the 2x2 average; `k >= 0` repeats pixels (nearest).
- No final channel pass, no fog, no unit dots yet. Colours are 24-bit RGB straight from the table.
- Camera rectangle uses continuous world position: `col = cam.x / 32`, `row = cam.y / 32` (relief
  height ignored), size `view / 32`; the rectangle is clipped to the image.
- Click -> cell `(px / s + 8, py / s + 8)`; the camera is centred on world `(32 * col, 32 * row)`
  (height ignored, then clamped by the camera).
- Panel origin constant `PANEL_ORIGIN = (8, 8)` px from the window's top-right corner: INFERRED until the
  interface frame (G3b); the exe's centre point is `(72, 82)` inside the panel (CONFIRMED).
- The image is built once per `Minimap`; `invalidate()` exists for terrain edits. No World hook,
  because nothing in the world changes the picture.

## 3. Tests

Size rule for every map of the install (and synthetic sizes at each threshold); pixel <-> cell round
trip for each `k`; synthetic world: pressing a minimap pixel moves the camera to the expected cell, drag
follows, clicks outside the panel are ignored; camera rectangle pixels; synthetic colour lookup (table
index rule, border cropped, dirt/fog bits ignored); golden hashes for maps 10, 20, 52
(`tests/golden.json["minimaps"]`, `tools/update_golden.py`); boundary test still passes.

## Open questions

- The last channel pass `0x4ac030`-`0x4ac413`; the contents of surface `DAT_00626be0`; what draws
  the minimap objects (vtable `+0x34`) and which objects register.
