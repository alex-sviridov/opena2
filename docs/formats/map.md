# Campaign maps (`.alm`, "M7R")

Code: `allods2/alm.py` (container), `allods2/formats/map.py` (`Map`,
`MapHeader`), `allods2/formats/passability.py` (part 3), `allods2/formats/objects.py` (part 4), `allods2/formats/entities.py` (part 5); CLI
`python -m allods2 map info|render`; tests `tests/test_map.py`,
`tests/test_passability.py`, `tests/test_entities.py`. 46 maps in `scenario.res` (`scenario/<n>.alm`, 80², 144²
or 256² cells). Reader: `FUN_00534ad4` (file → map object, 0x3b8 bytes),
runtime map builder `FUN_004a449c`. Part 1 is the container, part 2 the
header and terrain, part 3 heights and passability, part 4 objects (sections
3 and 4), part 5 players, units and items (sections 5, 6, 8, 9); the trigger sections
7 and 10–12 stay open.

## Part 1. Container

Summary; byte accounting in [inventory §5.2](../inventory.md#52-alm-maps-m7r0).
File header 20 bytes: `M7R\0`, u32 `0x14`, u32 `w·h·4 + 72`, u32 section
count (13; the game wants ≥ 3), u32 **version** (1300 in 41 maps, 1600 in 5;
the game rejects > 1600 with "Map version too new" and gates fields on it).
Then per section a 20-byte header `{tag, 0x14, size, id, extra}` + data.
CONFIRMED (`FUN_00534ad4`, reads header → `switch(id)`): the id selects the
decoder; the `tag` is 7 (37 maps) or 5 (9 maps), equal in all sections of
one file, stored as map object `+0x08` and used by nothing found; `extra`
is never read (varies per map, 0 in `74.alm`).

## Part 2. Header and terrain

### Section 0, General block (644 bytes + 16)

CONFIRMED (`FUN_00534ad4`, case 0, sequential 4-byte reads; version gates as
listed). **The section declares 644 bytes but the reader consumes 660**:
the last field is a 512-byte text buffer at +0x94, so its final 16 bytes
lie in the 16 bytes that follow section 0 (the old "section 0 quirk").
`alm.Section.tail` keeps them.

| Off | Type | `MapHeader` field | Meaning |
|---|---|---|---|
| 0x00 | u32 | `width` | cells; 80, 144 or 256 (CONFIRMED: equals `FUN_004a66b0` → runtime width) |
| 0x04 | u32 | `height` | cells; always = width in the campaign |
| 0x08 | f32 | `angle` | initial sun angle: π/4 (0.7854) in 26 maps, 0.7679 (44°) in 18, −π/4 (`31`), 0.6632 (`75`) |
| 0x0c | i32 | `field_0c` | 360 (44 maps) or 720 (`31`, `52`); copied to runtime map `+0x2c` (`0x4a456f`) and never read (bounded search, CONFIRMED); uninitialised in the loader's ctor |
| 0x10 | i32 | `ambient` | initial ambient light, 0–23 (21 in 26 maps) |
| 0x14 | i32 | `diffuse` | initial diffuse light, 54–64 (63 in 36 maps) |
| 0x18 | u32 | `tile_sets` | bit mask of tile sets 0–12 |
| 0x1c | u32 | `player_count` | records in section 5 (2–9; 7 in 13 maps) |
| 0x20 | u32 | `n_sec4` | entries of section 4 |
| 0x24 | u32 | `n_sec6` | records of section 6 |
| 0x28 | u32 | `n_sec7` | records of section 7 |
| 0x2c | u32 | `n_sec8` | records of section 8 |
| 0x30 | u32 | `n_sec10` | version > 1149; section 10, always 0 |
| 0x34, 0x38, 0x3c | u32 ×3 | `n_sec11` | version > 1229; three lists of section 11 (12, 0x54 and 12 bytes; the middle list is empty in all 46 maps) |
| 0x40 | u32 | `n_sec12` | version > 1299; entries of section 12 |
| 0x44 | 64 B | `name` | map name |
| 0x84, 0x88 | i32 ×2 | `field_84`, `field_88` | `field_84` (object `+0xd8`) is 1 in all 46: `FUN_005606aa` (`0x560947`) sets settings `+0x74` = `field_84 > 1` ("multiplayer game", read in about 60 places), so 1 = single-player map. `field_88` (`+0xdc`) is the map difficulty 1–4 (1 in 42 maps, 2 in `52`, 3 in `74`/`95`, 4 in `110`), copied to settings `+0x1cc` (`0x56099d`) and used only for `difficultylevel=%d` of the multiplayer server advert (`0x4ed138`). Both 1 when no section 0. CONFIRMED |
| 0x8c, 0x90 | i32 ×2 | `field_8c`, `field_90` | version > 1159; `field_8c` 0 in 38 maps, `field_90` 0 in 23 and 60,000,000 in 19 (the loader's reset default); the rest stray memory. Written to object `+0xe0/+0xe4`, copied by `FUN_0053440c`, **never read** (CONFIRMED, bounded search). Note object `+0x8c` is the loader's status code (1–6), not `field_8c`, and `+0x90` is the maximum of the units' `squad` |
| 0x94 | 512 B | `description` | description |

- **Text**: NUL-terminated, **cp1251** (`decode_text`); everything after the
  NUL is uninitialised editor memory (stack and heap fragments such as
  "Go away from ogre", pointers). 19 of 46 campaign maps have a name
  ("Adamantium mines", "Get Sword", …) and the same 19 a description (author credit
  "by Nozhnin Dmitry aka [DND]WildMaN …"); all are ASCII, so no cp1251
  byte occurs in the install, but the decoder is cp1251 because the game
  stores raw ANSI bytes (as the `main\text` files,
  [fonts](fonts.md#locale-text-chartooema)). Campaign briefings come from
  `main/text/mission%d.txt`, not from here.
- **Light fields** CONFIRMED overwritten: `FUN_004a5dd2` starts by copying
  the global ambient `0x6226c4`, diffuse `0x6226c8` and sun angle
  `0x6226d8` into runtime map `+0x1c/+0x1d/+0x20` (`0x4a5de1`–`0x4a5e07`),
  and the light map reads those. The file values (map `+0x18/+0x1c/…`
  copied by `FUN_004a449c` `0x4a44f0`–`0x4a4520`) only seed them before the
  first update ([lighting §1–2](../mechanics/lighting.md)). That they are
  angle / ambient / diffuse is INFERRED from the copy targets (types and
  the 0.7854 = π/4 range match).
- **`tile_sets`** CONFIRMED (data, all 46 maps): every set used in the Tiles
  block is in the mask (equal in 36 maps, a superset in 10). No selector of
  an "environment": the game ignores the mask and loads all 13 sets
  (`FUN_004a449c` stores `0x1fff`, [terrain](terrain.md#strip-files-fun_00476429mask));
  the mask is the editor's list of sets used.
- **Counts** CONFIRMED (data): section 5 is `76 · player_count` bytes, section
  6 `48 · n_sec6`, section 11 `12 · sum(n_sec11)`, section 10 empty, in all
  46 maps (all sizes and counts of sections 4, 7–9, 12 relate through
  variable-length records, left to later parts). Players: `player_count`
  records `{u32, u32, u32 (0 or 5000), name[32], u16 × 16}` (INFERRED:
  first record "Self"/"self" = the human; the u16 row is a relation row
  with 18 on the diagonal).
- `field_0c`, `field_8c`, `field_90`: stored, never read by the exe.

### Sections 1–3, fixed layers

CONFIRMED (sizes by data on all maps; copy by `FUN_004a449c`, [terrain
§ Altitudes](terrain.md#altitudes--runtime-height-map)):

| ID | Name | Size | `Map` attribute |
|---|---|---|---|
| 1 | Tiles | `w·h·2` | `terrain` (h, w) uint16, raw cell values |
| 2 | Altitudes | `w·h` | `heights` uint8 (the game reads them signed: `heights_i8`) |
| 3 | Objects | `w·h` | `objects` uint8 = object index + 1 |

Any other section stays raw: `Map.sections[id]` (bytes).

### Terrain cell → tile image

Cell layout, the strip file for each cell, water frames and the draw
geometry are in [terrain.md](terrain.md) (CONFIRMED; routines
`FUN_00404e0e` cell decode and draw, `FUN_00476429` strip loader,
`FUN_00457487`/`FUN_004575fe` blits). Recap: `v & 0xf` tile in strip,
`(v >> 4) & 3` strip, `(v & 0x1fff) >> 6` set 0–12, bit 13 dirt, bits 14–15
fog. Geometry: a square 32 × 32 cell, x = 32·column, y = 32·row − height
(heights displace the corners, no isometric projection), rows drawn top to
bottom; an 8-cell border surrounds the playable area (objects are only
copied for rows 8…h−5, columns 8…w−9; `FUN_0041c071` addresses cells 8…w−9).

**Dirt flag (CONFIRMED, new)**: `FUN_004a449c` ends by clearing bit 13
(`& 0xdfff`, `0x4a53f7`; the other load path does the same at `0x4a5cad`)
in every cell, so the 1,654 dirt cells in the files are never drawn. The
flag is set again at run time from a server message (type 155) that
run-length encodes the **block bit 0x10** over the playable area; the bit is
set by spell area effects, not by the map ([part 4](#the-run-time-dirt-flag)). The server's path finder, however, reads the
file's tiles with the bit still set and treats it as blocked
([part 3](#part-3-heights-and-passability)). `Map.runtime_terrain()` clears the bit; the
renderer does too unless `--dirt` is given.

Fog bits 14–15 are 0 in every file.

### Checks

`tests/test_map.py`: all 46 headers parse with consistent sizes and counts;
the tile sets used are within `tile_sets`; every cell resolves to a tile
except the 5 known cells of `74.alm`; synthetic maps (cp1251 text, version
gates, the 16-byte tail, sizes, raw sections, CLI) run without game files.

Renders for visual comparison: `python -m allods2 map render 10
out/maps/10.png [--relief]`. Flat = plain strip palette, no light (dark);
`--relief` = heights plus the terrain light with day/night off
(`daylight(0, False)`), the closest to the game; fog and
units are not drawn; objects and structures: `--layers terrain,objects,structures`
([part 4](#part-4-objects)).

## Part 3. Heights and passability

### Heights (section 2)

CONFIRMED (`FUN_004a449c`, `FUN_004065b1`, [terrain § Vertex table](terrain.md#vertex-table-fun_004065b1)):
**one signed byte per vertex**, not per cell: `H[y][x]` is the height of
the top-left corner of cell `(x, y)`, so the last row and column only
serve as corners. Value range in the 46 files **0..127** (min 0, max 127;
no negative value), by the test `test_layers_match_the_header_and_value_range`.
Unit: **1 pixel** of vertical screen offset (`y = 32·row − H`, see terrain.md;
renders `map render --relief`). Steps between neighbouring vertices reach
126 in the data, so cliffs of several tiles exist.

Uses (CONFIRMED, every reader of the height table found by scan):

| Use | Routine | Rule |
|---|---|---|
| Terrain draw | `FUN_004065b1` | corner y = `32·r − H` |
| Ground height under a unit (`unit+0x6c`) | `FUN_0046025d`, map copy `FUN_004a62fd` | below; unit and structure draws subtract it from y (`0x46346a`, [animation §4.2](animation.md#42-structures-and-bridges)) |
| Walking speed | `FUN_00559195` (server) | slope term below |
| Sight (line of sight) | `FUN_00552929`, `FUN_00552c28`, `FUN_00552af8` | below |
| Passability | none | the block layer never reads heights |

**Ground height of a unit** (`FUN_0046025d`): position `(x, y)` in 1/256
cell, footprint `sx × sy` cells (vtable `+0x20/+0x24`): `X = x − 0x80 +
sx·0x80`, `Y = y − 0x80 + sy·0x80`, `c = X >> 8`, `r = Y >> 8`, `fx = (X >> 3)
& 31`, `fy = (Y >> 3) & 31`; `a = H[r][c] + ((H[r][c+1] − H[r][c])·fx)/32`,
`b = H[r+1][c] + ((H[r+1][c+1] − H[r+1][c])·fx)/32`, `h = a + ((b − a)·fy)/32`
with C division (toward 0). A 1 × 1 unit at a cell centre stands at the mean
of the four corners. The map method `FUN_004a62fd` is the same with 256
steps (`fx = x & 0xff`, `>> 8`).

**Slope and speed** (`FUN_00559195`, only for walkers, `movementType` 1):
the step to the next cell (direction 0..7 from the table at `+0x58e98`)
uses `dh = clamp(H[here] − H[next], ±32)` on the two vertices at the cell
indices; with `v = speed · SpeedMultiplier` (`map.reg` Path Finding, 8):
`v += v·dh >> 6` (downhill faster, uphill slower: at most ±50 %), then
`v /= (cost(here) + cost(next)) >> 1` (cost layer below; 0 counts as 8),
clamped to 1..63. This is a speed, not a barrier: **there is no slope limit**;
6 horizontally adjacent walkable pairs on `83.alm` differ by more than 32
(largest 50, at (128,133)–(129,133)). Flyers use `speed`, unscaled.

**Sight** (`FUN_00552929`): a 41 × 41 window around the viewer. The
centre budget is `scanRange << ScanShift` (type `+0xa5`; `map.reg` Scanning,
7); each ring outward takes the budget of the neighbour towards the centre
minus a distance table and **`H[cell] − H[viewer]`** (higher ground costs
sight, lower ground gives some back); a cell is seen while the budget is
above 0. Inputs are therefore only the heights and the scan range;
objects are not consulted (the `FUN_00552c28` variant gates cells with
`FUN_00559536`, untraced). The exact tables are INFERRED from the
decompile and not reproduced (open question).

### Passability: derived, not stored

CONFIRMED (data): no section holds a passability layer; sections 1–3 are
the only per-cell blocks (`w·h` or `2·w·h`, [Part 1](#part-1-container)).
The server's path finder derives it when the map loads: `FUN_005606aa`
reads the file with `FUN_00534ad4` (the raw object: width `+0`, height `+4`,
tiles `+0xc`, **objects `+0x10`, heights `+0x14`**, no cell cleared) and passes it
to the path finder constructor `FUN_0054d2d9` → `FUN_00553d51` (tables) and
`FUN_00554626` (grid build). All grids use a **256-cell stride** (`index =
y·256 + x`, maps smaller than 256 leave the rest unused):

| Offset | Content |
|---|---|
| `+0x00000` | cost layer, u8 |
| `+0x10000` | block layer, u8 bit mask (static bits + dynamic stamps) |
| `+0x20000` | copy of the block layer after the static build (reset source) |
| `+0x30000` | u16 distances of the search |
| `+0x944f4` | heights, copy of section 2 |
| `+0x540a6` / `+0x54126` / `+0x54146` | tile shape table, set types, type costs |
| `+0x58eb8..bf` | playable rectangle: `(8, 8, w−9, h−9)` |

**Terrain type** (`FUN_0055494d`): from the cell value `v` (low 10 bits:
row `v & 15`, strip `(v >> 4) & 3`, set `(v >> 6) & 15`):

- water (`v & 0x300 == 0x200`, sets 8..11): type `Land` if row 4 of strip 1
  (the shore tile), `Water` for rows 0..7, 0xFF for rows ≥ 8; cost always 8;
- else row ≥ 14: type 0xFF, cost 8 (the 5 cells of `74.alm`);
- else the set gives two types `(a, b)` and the tile a **shape** 1..5; type =
  `b` for shapes 1–2, `a` for 3–5; cost = `cost[b]`, `(cost[a] + 3·cost[b]) >> 2`,
  `(cost[a] + cost[b]) >> 1`, `(3·cost[a] + cost[b]) >> 2`, `cost[a]` for
  shapes 1..5.

Type ids: 0 none, 1 Land, 2 Grass, 3 Flowers, 4 Sand, 5 Cracked, 6 Stones,
7 Savanna, 8 Mountain, 9 Water, 10 Road. Set types (a, b): 0 Grass/Land,
1 Cracked/Land, 2 Sand/Land, 3 Savanna/Land, 4 Stones/Land, 5 Cracked/Stones,
6 Flowers/Savanna, 7 Mountain/Stones, 12 Road/Land. The shape table (strips 0..3 × rows
0..13) and these pairs are in `passability.py` (values CONFIRMED from the
constructor's stores). Costs are read from `world/data/map.reg` `[Terrain]
Cost<Name>` (`FUN_004e6f9f`, defaults in the code); shipped: Land 8, Grass 8,
Flowers 8, Sand 14, Cracked 6, Stones 12, Savanna 8, Mountain 16, Water 8,
Road 6. The `Pass<Name>` keys of that file (Mountain, Water, Road = 1) are
**never read**: the strings are not in the exe.

**Block layer, static build** (`FUN_00554626`, in this order per cell, from
the raw file values; fog bits are 0):

1. `v & 0x2000` (the dirt flag, still set: the server does not clear it) → 1;
2. terrain type is Mountain → 1;
3. water (sets 8..11) → 1;
4. Objects block byte ≠ 0 → **5** (replaces the above; every object blocks,
   `objects.reg` has no passability field);
5. afterwards `FUN_00553b30` writes `0x1F` over the 8-cell border on all
   sides (square maps; a non-square map uses the 256 × 256 rims, not
   reproduced, no campaign map needs it).

Then the layer is copied to `+0x20000`. Data (46 maps): the playable-area
values are only 0, 1, 5; walkers can enter 21 % (maps 93–96) to 89 % of it.

**Who is stopped by what.** A mover of `movementType` m (data.bin monsters;
humans are −1 and take 1) may enter a cell when `block & mask == 0`
(`FUN_0055d010`; mask `*(mover+0x1c0)+5`, set by `FUN_00557a89` from the
vtable `+0x20` result, constructor default 0x41 `FUN_00551346`):

| m | Units (data) | mask | Stopped by |
|---|---|---|---|
| 1 | 155 monsters (walkers, catapults); humans (assumed) | `0x41` | bit 0 (water, mountain, dirt, object, border), bit 6 |
| 2 | Ghost, Bee (+ `.2`–`.5`) | `0x44` | bit 2 (objects, border), bit 6: crosses water, mountain, dirt |
| 3 | Bat_Sonic, Dragon, Succubus (+ `.2`–`.5`) | `0x82` | bit 1 (border), bit 7: only the map border and each other |

The mapping `movementType` → m is INFERRED (the vtable slot was not
followed per class; the type 2/3 split by name matches ghosts/bees and
fliers). The other bits are stamped at run time (INFERRED from `FUN_00550a96`:
bit `0x20` marks a cell with an occupant record; an object with a footprint
mask gets 5 on its solid cells and has bits 0 and 2 cleared, and the cost set
to Cracked, on the rest) and are not part of the file-derived grid.

API: `Map.block`, `Map.passability(movement_type)` (bool), `Map.cost(costs)`,
`Map.heights_i8`; `passability.costs_from_reg(map_reg)`. Overlay check: a red
(bit 0) / yellow (objects) / magenta (border) render of `10.alm` follows
the water/mountain shapes and the placed objects (`out/maps/10_block.png`,
local only).

### VERIFY IN GAME

- Can a walker enter the cell (27,10) of `10.alm` (object 47, block 5)?
  Predicted: no. Same for a cell whose object has no collision look (bushes).
- `71.alm` (8,9): dirt flag, no object (block 1). Predicted: **blocked** from
  the start of the mission; (16,9) has dirt and an object (block 5).
- `10.alm` (61,8): mountain tile, no object (block 1). Predicted: walkers
  stop, a Ghost/Bee crosses.
- Steep ground: `83.alm` (128,133)→(129,133) drops 50 units. Predicted:
  walkable, uphill about 22–50 % slower, no slope limit.
- Does a unit's sight really shrink behind a hill (higher `H` than the
  viewer along the ray)? Compare the fog around a unit on a ridge and in a
  hollow.
- Which type a unit `movementType` selects for humans (−1 in the data) and
  for the hero classes: assumed walker (1).

## Part 4. Objects

Code: `allods2/formats/objects.py` (`Structure`, `MapObject`, footprints),
`Map.structures`, `Map.placed_objects()`, `Map.passability(m, stats)`; scene
draw `allods2/anim/scene.py`; CLI `map render MAP DEST --layers
terrain,objects,structures`; tests `tests/test_objects.py`. "Objects" are two
separate things in the file:

| What | Section | Sprites | Placement |
|---|---|---|---|
| Trees, rocks, decorations (`objects.reg`, 192 IDs) | 3, one byte per cell = ID + 1 | `graphics/objects/<File>.256` | one cell each, no HP, no owner, always passable-blocking |
| Buildings, bridges, graves, camp fires (`structures.reg`, 179 IDs) | 4, list of 20-byte entries | `graphics/structures/<File>.256` | top-left cell of a W × TH footprint, HP, owner |

Units (section 6) and item groups (section 8) are [part 5](#part-5-players-units-items).

### Objects block (section 3)

Layout, window and the burning trees: [animation §1.7](animation.md#17-map-placement-of-objects)
(CONFIRMED). Counts: 76,393 non-zero cells in 46 maps, 75,228 inside the
loaded window (rows 8…h−5, columns 8…w−9), 1,165 outside (ignored by the
game). `Map.placed_objects()` lists the window cells as `MapObject(x, y,
id)`; `window=False` lists all. **ID → sprite table**: `graphics/objects/
objects.reg` (`Object<n>` records, `ID` = n; `File` → `Files/File<n>` →
`<name>.256`, loader `FUN_00478eb6`, [animation §1.2](animation.md)). IDs
without a sprite: the 7 burning trees (1, 4, 7, 10, 13, 16, 19: file absent
from the archives) and ID 208 (11 cells of `52.alm`, not in `objects.reg`
at all); all of them lie outside the window, so no loaded cell is
unresolved (test `test_every_object_id_resolves_or_is_excluded`).

**Placement, frame, draw order**: anchor = cell centre `(32X + 16, 32Y + 16
− relief)`, hotspot `CenterX/CenterY` ([animation §4.3](animation.md#43-objects),
CONFIRMED `0x4091a8`–`0x40922c`); relief = mean of the cell's four corner
heights, truncated toward 0 (`+0xc0`, [terrain](terrain.md#vertex-table-fun_004065b1),
`objects.cell_relief`); frame `Index + seq[(clock + X + X·Y) mod len]`.
**Footprint**: the one cell; it blocks every mover that is stopped by bit 0/2
(block 5, [part 3](#passability-derived-not-stored)).

### Structures (section 4)

Header field `n_sec4` = number of entries. CONFIRMED (`FUN_00534ad4` case 4,
`0x535310`–`0x53550e`, and the data: the entries tile the section exactly on
all 46 maps, 1,721 structures of which 21 bridges):

| Off | Type | `Structure` field | Meaning |
|---|---|---|---|
| 0x00 | i32 | `x` | 1/256 cell, always `cell·256 + 128`; the reader passes `>> 8`: top-left cell of the footprint |
| 0x04 | i32 | `y` | same |
| 0x08 | u32 | `type` | structure ID 1…179 (`structures.reg` `ID`, data.bin structures record `ID − 1`); `0x21` or bit `0x1000000` (11 entries are `0x1000021`, 10 plain `0x21`) = a sized bridge, the reader forces the ID to `0x21` |
| 0x0c | u16 | `intact` | 0 = the structure starts destroyed (HP 0), else full HP (values 0, 10, 100 in the files; the builder tests only zero, `0x4a4a5c`, so 10 and 100 are the same) |
| 0x0e | u32 | `owner` | 1…8, see below |
| 0x12 | i16 | `uid` | unique within a map (1…363; 33 maps are not 1, 2, 3 … in order, so the numbering is shared with other lists); the runtime object ID is `0x6000 + uid` |
| 0x14 | u32, u32 | `size` | **only if the type is `0x21` or has bit `0x1000000`**: width, height in cells (low 16 bits are used) |

The entry is handed to `FUN_0054c620` (x, y, type, `intact`, `owner`, `uid`) or
`FUN_0054c690` (+ width, height), which store it as `u16 x, y, type, intact,
owner` and `u32 uid` (+ `u16` sizes at `+0xa/+0xc`) in the list at map
`+0x390`. The runtime builder (`FUN_004a449c`, switch on the type at
`0x4a479b`, per entry `0x4a4761`–`0x4a4a8b`) creates the structure object
(class by type: `0x21` bridge 9 pieces, `0x25` bridge 14 pieces, else the
normal structure `FUN_00461403`), sets `+0x04 = 0x6000 + uid`, `+0x24 =
type`, position `+0x08/+0x0c = cell·256 + 0x80`, **max HP `+0x108` = data.bin
`healthMax` (a 0 becomes 1000), HP `+0x104` = max, or 0 when `intact == 0`**,
and a sight radius `+0x10a = scanRange << 8`. Type `0x25` never occurs in a
file (and would have no size: its entry has no extra bytes).

**Owner (CONFIRMED)**: the builder compares `owner` with field `+0x08` of
the run-time player objects (keyed by their `+0x04`; the last match among
keys ≥ 1 wins, default key 0) and stores the match at `obj+0x14`. That
`+0x08` is the **1-based index of the section 5 record**: the server creates
one player object per map player (`0x5612af`, `0x56130a`–`0x5613a9`) with
`+0x08 = mapPlayer + 0x04`, and the reader numbered those `index + 1`
(`FUN_00534ad4` case 5); the client gets it as byte 1 of the add-player
message (type 150, sender `0x504d39`: `+0x0a` index, `+0x0b` this value,
`+0x0c` the file's first u32, as `+0xa44 − 1`) and stores it again at
`+0x08` (`0x413f3d`–`0x413f4e`). Data agrees: `owner` ≤ `player_count` in all
1,721 entries and 136 of them match no id (e.g. `10.alm`: 3 = "Enemy", 8 =
"Skrakan"; `52.alm`: 2 "Humans", 4 "Os", 6 "Druid monsters"). The first u32
of the record (its "id") is carried separately: the server stores `id + 1`
at player `+0xa44` and sends it as byte 2 of that message.

**Which structures** (data): 1,721 entries use 152 of the 179 IDs, every one
resolves in `structures.reg` and data.bin and every sprite file exists; every
footprint lies inside the playable area (columns/rows 8…w−9/h−9), test
`test_every_structure_section_tiles_exactly_and_resolves`. data.bin's
`sizeX × sizeY` equals the picture's `TileWidth × TileHeight` for all but
**Cave (14: 3 × 3 vs 3 × 2) and Castle (57: 11 × 4 vs 11 × 5)**; the Cave's
`BuildingPresent` mask `0x3f` registers only its first 6 cells, which is the
picture's 3 × 2 (below).

### Footprint and blocking

CONFIRMED. A structure's server object holds its size at `+0x60/+0x61`, the
`Passability` mask at `+0x64` and the `BuildingPresent` mask at `+0x68`
(constructor `0x51ff33`: data.bin structure params 0, 1, 4, 5). Its last act
is `FUN_005599df`: for each cell of the `sizeX × sizeY` rectangle from the
top-left cell, bit `i = row·sizeX + col` (taken **mod 32**: `1 << (i &
0x1f)`) of `BuildingPresent` set → `FUN_00559890` stores the structure in
that cell's record (`+0xc`; it **fails if the cell already holds one**) and
refreshes the cell (`FUN_00550a53` → `FUN_00550a96`, also called from
`0x55c293`, `0x55c3f8`). The refresh, for a cell holding a structure, tests
the same bit of `Passability`:

- bit set (solid): block `|= 5` (bits 0 and 2, in the live and reset layers);
- bit clear: block `&= 0xFA` and the cost set to the type cost at `0x5414b`:
  the cost table is `+0x54146 + type` ([part 3](#passability-derived-not-stored)),
  so this is type 5, **Cracked** (CONFIRMED by the layout; 6). The cell
  stays free even if it was water, mountain or dirt.

`BuildingPresent` equals the full rectangle (`2^min(w·h, 32) − 1`) for 176 of the
179 structures. The exceptions: **Cave** (3 × 3, `0x3f` = 6 cells = the
picture's 3 × 2, so the client footprint is consistent), **Castle** (11 × 4,
`0x7f1ff7ff` for both masks; with the wrap, cells 32…43 reuse bits 0…11 and
bit 11 is 0) and **StoneHenge** (1 × 1, `Passability` 2, present `0xf`: the
cell is registered but free). In the files 5 present cells are claimed by two
structures (`30.alm` uids 31 and 37, `40.alm` uids 35 and 43).

**Double-claimed cells: the first structure wins (CONFIRMED, REA/objdump of
`FUN_00559890` and `FUN_005599df`).** `FUN_00559890` looks the cell record up
(hash `+0x54084`); if the record already holds a structure (`+0xc != 0`) it
returns 0 and stores nothing (`0x5598c2`). `FUN_005599df` returns 0 at the
first failure (`0x559a8d`) and so **stops: the remaining present cells of that
structure stay unregistered** (never stamped, never blocking); its caller, the
structure constructor (`0x5200b1`), ignores the result and the object lives on.
In the files this leaves unregistered: `30.alm` uid 31 two cells (held by uid 5) and uid 37
all 9 (its first cell is held by uid 27), `40.alm` uid 35 one cell and uid 43 four cells
(measured with the world engine, 16 cells in all). Structures are registered in
section 4 record order (INFERRED: the runtime builder `FUN_004a449c` walks the
list in order). Registration is in row-major order, bit `i` of `BuildingPresent`
(the same `i` counts absent cells). `FUN_005599df` is also called with a
record that exists but holds no structure (created earlier for a unit): that branch
stores the structure and does **not** refresh the cell (`0x5598cf`..`0x5598ef`);
at map load no such record is known to exist (INFERRED). Unregistering
(`FUN_00559aaf` -> `FUN_0055995a`) clears `+0xc` of every present cell without
checking the owner (a destroyed structure would free a neighbour's cell: not modelled).

**Refresh order (CONFIRMED, `FUN_00550a96`).** The refresh first rewrites the layers from
the two baseline bytes the cell record took when it was created (`FUN_005508a0` copies
the current layer values), so the result is "static block, then the structure":
the border (0x1F) and the object (5) are already in the baseline, a solid structure
cell ORs 5 (live and reset layer), a free one ANDs 0xFA (so a structure on the
border keeps bits 1, 3, 4: 0x1A) and sets the cost to the type-5 cost; an
occupant (`+0x20`) ORs 5; the dirt bit 0x10 saved at the start is OR-ed back.

**Ids (CONFIRMED).** Object ids are 16 bit (`+0x4` word). Structures get
`0x6000 + uid`, in the client builder (`0x4a48ab`, `0x4a511b`, `0x4a59fd`) and the server
constructors (`FUN_0052b284` `0x52b2ac`, `FUN_0052c1be` `0x52c1d7`: `+0x4 = +0x8 + 0x6000`).
Ids below 0x6000 are allocated dynamically in a 0x6000-bit map (`0x6c9628`, set
`FUN_004f8cec`, clear `FUN_004f8d3d`; both skip ids >= 0x6000), i.e. units and items. A section 3
cell has no id in the exe (it is layer data, not an object): the world engine's
`0x10000 + n` ids are ours. That the trigger sections 5-12 refer to structures by
`0x6000 + uid` and never to section 3 cells is INFERRED (those sections are still raw).

Sized bridges (VariableSize, constructor with a size) have mask 0, so their
whole `w × h` rectangle becomes walkable, including over water. Example: Goblin
Hut `3 × 2`, `Passability` 55 = `0b110111`: the cell (col 0, row 1), the door, is
free. Units and the cost layer are not reproduced.
`objects.stamp_structures`, `Map.block_with_structures(stats)`,
`Map.passability(m, stats)`: on `10.alm` it changes 63 playable cells
(`test_structures_stamp_into_passability`).

#### The run-time dirt flag

The **dirt flag is not the structure foundation**: only 11 of the 1,654
dirt cells in the files lie inside any footprint. CONFIRMED pipeline: the
server's block bit `0x10` is set by `FUN_00559c28(x, y)` (live and reset
layers), cleared by `FUN_00559ce5`, read by `FUN_00559cb3`. The setter's
callers are the **spell area-effect objects**: `FUN_00518024` picks by the
spell record's `Distribution system` (data.bin spell param 8; 4 = wall:
Wall of Fire, Wall of Earth …) the wall or the area routine
(`FUN_005182b6`, `FUN_005183a2`: all cells with `|dx| + |dy| ≤ radius + 1`
around the effect, radius at `+0x4d`), which call `FUN_005184bf` per cell:
`FUN_0055a325` adds the area effect to the cell, and when the flag argument is
set `FUN_00559c28` marks it. The flag is 1 when the effect list holds
`Effect_DirectDamage` and the effect record's byte `+0x5c` is non-zero. CONFIRMED meaning: `+0x5c` is the
damage-spread byte of the damage carrier (`FUN_00543040` ff. store min `+0x5b`, spread `+0x5c`, element
`+0x5d`), so the ground is scorched under area spells that deal damage ([spells](../data/spells.md#4-effect-handlers)). When a
player joins, `0x4f2326` sends message 155: `FUN_00559d70` run-length
encodes bit `0x10` over the playable area (first word = the bit of the first
cell, then alternating run lengths, rows from (8, 8)), and the client
(`FUN_0041c071`) turns it into tile flag `0x2000`. The static build never
sets bit `0x10`, so nothing is dirty at the start of a mission: the file's
flag only seeds block bit 1 (a leftover of the editor).

### Draw order and placement (structures)

CONFIRMED (view draw `FUN_00406f43`, REA/asm). Window origin `(vx, vy)` =
`view+0x5c/+0x60`, size `W × Hv` = `+0x64/+0x68`
([terrain](terrain.md)). **Every object pass** scans rows `y = −4 …
Hv+7` top to bottom and, in each row, columns `x = W+3 … −4` right to left,
but draws only inside `−3 ≤ x ≤ W+2`, `−3 ≤ y ≤ Hv+6` (the outer ring is
a no-op): **3 cells margin left, right and above, 7 below**. Per-cell
arrays (stride `W+6`, offset 3) hold one entity per layer:
`view+0x8c` ground units, `+0x90` flyers, `+0x94` structures and bridges,
`+0x98` backpacks, `+0x9c` corpses/units with flag `0x80`
(`FUN_00460591`, vtable `+0x38`). `S` below = `FUN_0041eb60` =
`obj+0x7c`, the entity's fog state: structures (`FUN_00461460`) 0 when a
footprint cell is in sight (`0xc000`), 1 explored (`0x8000`), 2 never
seen; units 0 in sight, else 1. The light row passed to each draw is
`view+0xb0[cell]` ([lighting §4](../mechanics/lighting.md#4-object-light-rows-fun_00404a2a-confirmed)).

Order (terrain `FUN_00404e0e`, then `FUN_00405cf4` lit-terrain redraw first):

| # | Pass (all cells in scan order) | Entities, gate |
|---|---|---|
| P0 | **shadows** (only with `DAT_005f17e8`) | structures (`+0x2c`, `S < 2`; bridges: empty stub) |
| P1 | flat structures | layer `+0x94`, record `Flat ≠ 0`, `S < 2`, `+0x28` |
| P2 | per cell: corpses (`+0x9c`), then backpacks (`+0x98`) | `S == 0`: shadow `+0x2c`, then draw `+0x28` |
| P3 | **per cell, in this order**: (a) non-flat structure slice (`S < 2`, `+0x28`); (b) ground unit `+0x8c` (`S == 0`: shadow, draw); (c) steam of a burning water cell; (d) **map object**: shadow main, shadow `b`, draw, `b` 50 % smoothing; (e) fire of a burning cell with an object; (f) cell effect `FUN_0040af69` mode 1 | |
| P4 | flyer shadows (`+0x90`, `S == 0`) | |
| P5 | list `FUN_00420140/60`: `+0x28(0,0,0)` per entry (projectiles, no cell) | |
| P6 | cell effects `FUN_0040af69` mode 0 (rows 0…Hv+3, cols 0…W−1) | |
| P7 | flyers `+0x90` draw (`S == 0`) | |
| P8 | overlays `+0x30` (layers `+0x94`, `+0x8c`, `+0x90`; rows −3…Hv+6, cols W+2…−3) | |

then fog ([lighting §3](../mechanics/lighting.md#3-light-map-view--0xa8-confirmed)).
Structure pieces call `FUN_00404d99` (selection rect registration, no pixels)
after the draw. Object gate: map-object byte ≠ 0 and `FUN_0040b117` = 0; it
returns 1 (skip) only when every fog vertex of the sprite's cell box is level
16 (black), so skipping is invisible. P3 order inside one cell: (a) before
(b) before (d); a structure therefore hides what stands behind it (smaller
row) and objects in front cover it. Shadows are drawn right before the
sprite they belong to, except structures (P0, before everything) and flyers
(P4). Pieces of one structure cell go bottom-up, each piece as main then
`b`. Shadow casters: structures, map objects, ground and flying units,
corpses, backpacks; **not** bridges and projectiles (`+0x2c` is a `ret`
stub). Shadow geometry: [lighting §5](../mechanics/lighting.md#5-shadows-confirmed).
Unit layers, filing, flyer passes P4/P7 and the unit shadow: CONFIRMED, [rendering §13](../engine/rendering.md#13-units-team-colours-piles-g3a); burning-cell effects stay INFERRED.

A structure is drawn once per footprint cell ([animation §4.2](animation.md#42-structures-and-bridges)):
cell `(c, r)` of the W × TH footprint draws the pieces of picture column `c` in
row `r + FH − TH` and, for `r == 0`, also the `FH − TH` rows above, bottom-up,
at `(32·(X0 + c), 32·(Y0 + row − (FH − TH)) − g)` with the ground height `g`
of the structure ([part 3](#heights-section-2), `objects.ground_height`: footprint
`W × TH`; sized bridges `w × h`). The client's
footprint is the picture's: vtable slots `+0x20/+0x24` (`0x4620fc`,
`0x46211d`) return `TileWidth`/`TileHeight` of the `structures.reg` record
(CONFIRMED), so the Castle is 11 × 5 on the client and 11 × 4 on the server
(the game's own mismatch); that the client registers exactly those cells in
its structure layer (`view+0x94`) is INFERRED. A destroyed structure
(`intact == 0`, not `Indestructible`) shows its destroyed block; animated
structures start at `seq[0]`. Examples (`10.alm`): `map render 10 out/maps/10.png
--layers terrain,objects,structures --relief` draws the tower at (67, 36) on
open ground and the wooden bridge over the lake at the left edge.

### Checks

`tests/test_objects.py`: entry/bridge/flag layout and exact tiling (synthetic),
window rule, footprint mask wrap, stamping rules, ground height and relief
(synthetic); on the install: every section 4 tiles on all 46 maps (1,721 / 21),
every type resolves in `structures.reg` and data.bin, footprints lie in the
playable area, the data.bin/picture size exceptions are exactly {14, 57}, every
object ID resolves or is in the documented exclusion list and placed objects
are inside the window, structures stamp into passability, and the scene draws.

## Part 5. Players, units, items

Code: `allods2/formats/entities.py` (`Player`, `Unit`, `Group`, `Member`, `ItemRecord`,
`template`), `Map.players`, `.units`, `.item_groups` (= `.items`), `.item_records`,
`.ground_groups`; draw `allods2/anim/scene.py`; CLI `map render … --layers units,items` or
`all`; tests `tests/test_entities.py`. Reader `FUN_00534ad4` cases 5, 6, 8, 9; the server
builds the units in `FUN_00561bf9` (called from the map start, `0x560b42`), the item groups
in `FUN_00564072`, the client mirrors the unit list in `FUN_004a449c` (`0x4a4a90`–`0x4a52fc`).
Order at map start: players, units, then groups and section 9 (units must exist first: a
group is tied to its unit by uid, `FUN_00565080`). Section 7 (3 lists of 0x31c-byte records, the
trigger scripts) and 10–12 stay raw. Runtime struct: [unit-struct](../engine/unit-struct.md).
Totals over the 46 maps: 251 players, 4,212 units, 51 item groups (32 carried, 19 on the
ground), 88 section 9 records; every section tiles exactly.

### Players (section 5)

`player_count` records of 76 bytes, CONFIRMED (`0x535513`–`0x535661`), read into 0x4c-byte
player objects (ctor `FUN_0043b6e0`); object `+4` = record number (1-based), the value that
`Unit.owner` and `Structure.owner` hold (resolved by `FUN_0051680d`, error "Can't resolve
player %d for unit %d").

| File | Size | Object | Field | Meaning |
|---|---|---|---|---|
| 0 | u32 | +0x0c | `colour` | **row of `humans/human.pal`** (0 blue, 1 green, 2 red, 3 orange, 4 violet, 5 yellow, 6 teal, 7 grey, 8–15 darker; [palettes §4](palettes.md)). CONFIRMED: the unit draw (`0x463bac`–`0x463c16`) takes `table[owner.+0xc]` for `Palette = 0` types only. Record 1 always 1; values 1–8, 10 in the files; colours repeat within 39 of 46 maps |
| 4 | u32 | +0x34 | `flags` | only bit 2 (value 2) is read, into server player `+0xa60` (`0x5613f6`–`0x561407`; users `0x52bb30`, `0x531fcf`, meaning UNKNOWN); the file's 0/1 never sets it. CONFIRMED |
| 8 | u32 | +0x10 | `money` | 0 for record 1, else 5000; the default player (no section 5) has 5000 (`0x536421`). Never read (CONFIRMED: the server player is created with 0 and `FUN_005612af` copies only name, colour and `flags`); dead data in this build |
| 12 | 32 B | +0x14 | `name` | cp1251, NUL-padded ("self", "Computer", "Enemy", "Neutral", …) |
| 44 | 16 × u16 | +0x38 | `relations` | diplomacy toward player `j + 1`, below |

Human or computer is **not** in the file: single player makes record 1 the human and every
other record a computer (`0x5613d0`–`0x5613ec`, session `+0x2c`). CONFIRMED.

**Relations.** The loader copies the low byte of word `j` into the server matrix
`0x66832c + id·0x46 + 0xa8c4 + j + 1` and forces the diagonal to 0x12 (`0x560a8a`–`0x560b24`).
Bits of `M[a][b]` (a's stance toward b): 0x01 war, a may attack b (`0x51a301`), 0x02 alliance
(`0x512a20`), 0x10 a shares its vision with b (`0x5022a5`). The files use 0 (neutral), 1
(war), 2 (alliance) off the diagonal, 18 (alliance + vision) on it, and 16 once (`10.alm`,
record 8). Not symmetric in 116 of 1,248 pairs. Words past the player count are non-zero for
3 players (ignored).

**Team colour link** (C4): `Player.colour` → `UnitSet.palette(player=colour)`
(`scene.Scene.unit_palette`); monsters (`Palette > 0`) ignore it.

### Units (section 6)

`n_sec6` records of 48 bytes, CONFIRMED (`0x535681`–`0x535ab3`), read into 0x54-byte map-unit
objects (list at map `+0x3a4`; only `FUN_00561bf9` and the client loop read it).
Version 1300 layout:

| File | Size | Object | Field | Meaning |
|---|---|---|---|---|
| 0, 4 | i32 ×2 | +0, +4 | `x`, `y` | 1/256 cell. The server places the unit on cell `x >> 8`, `y >> 8` (`FUN_00510089`, spiral search for a free cell) with sub-cell 0x80/0x80 (`FUN_0054f9b9`); every file value has sub-cell 128 |
| 8 | u16 | +8 | `type` | units.reg ID (1–26 humans and the catapult, 64–107 monsters). The server ignores it; the client picks the view class from it (`units.reg[id]+0x124 ≠ 0` → hero view `FUN_0046bfa6`, else `FUN_00462a4a`, `0x4a5050`). Equals the data.bin `typeID` except NPC variants (editor copy). All 53 ids resolve |
| 10 | u16 | +0xc | `tier` | 1–6, read and never used (CONFIRMED: no reader of object `+0xc`); matches the record name's `.N` suffix (INFERRED) |
| 12 | u32 | +0x48 | `flags` | bit 0x10 = human (data.bin humans, 0x254-byte object), else monster (0x208). 605 humans flagged; 5 catapults (type 26) are monsters |
| 16 | u32 | +0x50 | `behaviour` | bits 1, 2, 4, 8 → booleans at creature `+0x194`, `+0x19c`, `+0x198`, `+0x1a0` (`0x561f0f`–`0x561f77`); only bit 8 occurs (8 units of `10.alm`). CONFIRMED by scanning every access: bit 8 (`+0x1a0`) = **summoned creature, no loot** (death handler `FUN_00510a70` skips the loot roll and empties the pack) **and no XP** (`FUN_005128cb`); the summon/clone spells set it (`FUN_00519db8`). Bits 1, 2, 4 (`+0x194`, `+0x19c`, `+0x198`) are read only by the event generator `FUN_005303ed` (candidate classes of three message events); the AI never reads any of them |
| 20 | u32 | +0x10 | `server_id` | key into data.bin: monsters group 5 where `serverID` (param 55) matches, humans group 6 where `serverID` (param 24) matches (`FUN_004fd62f` / `FUN_004fd5ad`); the unit is then built from that record's name. 4,212 / 4,212 resolve (`entities.template`) |
| 24 | u32 | +0x14 | `owner` | 1-based section 5 record, 1..player_count in all 4,212 units |
| 28 | u32 | +0x44 | `group` | 1-based section 8 group (0 = none; read as −1 / index − 1, −1 again if ≥ `n_sec8`); at load the unit's uid is written into the group (`0x535a3e`–`0x535a7c`). 32 units |
| 32 | u32 | +0x1c | `field_32` | read and never used (10 in 4,199 units): CONFIRMED unused by both consumers; meaning UNKNOWN |
| 36, 38 | u16 ×2 | +0x20, +0x22 | `hp`, `max_hp` | HP overrides, 0xFFFF = keep the data.bin value; 3,914 units use neither, 293 both |
| 40 | u32 | +0x3c | `uid`, `stamp` | low 16 bits = scenario unit number (object id `0x6000 + uid`, same space as structures, [part 4](#structures-section-4); unique per map); high 16 bits non-zero editor stamp, unused |
| 44 | u32 | +0x40 | `squad` | per-owner squad number, 0–38: the server finds the owner's squad (`player+0x28`, 0x50-byte object, `+0x1c` = number) or creates it (`FUN_0052ae43`) and adds the unit; squad members share walk speed. The map keeps the maximum at map `+0x90` |

**Defaults vs overrides** (CONFIRMED, `0x561d0f`–`0x562264`): everything comes from the data.bin
record found by `server_id` (stats, mana, speed, damage, spells, equipment strings). The
record overrides only HP: max HP `+0x96` ← `max_hp`, HP `+0x94` ← `hp` (if `hp` is 0xFFFF,
HP = max HP); a human (flag `0x10`) whose `hp == max_hp` is reset to "default" (the recomputed maximum, [progression §6](../data/progression.md#6-hero-start)). Level, mana and equipment
are not in the record.

**Difficulty** (CONFIRMED, `FUN_00561bf9` `0x561e20`–`0x561f0b`; settings `+0xd8` = game option,
set to selector + 1 by the new-game dialog `0x48972f`, default 2; labels easy / normal / hard
INFERRED): runs only when settings `+0x74` is 0 (single player) and the mode is not 2.
Mode 1: max HP = trunc(max HP × 0.5) (`0x5d1b00`), HP = max HP, brain `+0x44` (low-HP threshold,
compared at `0x56cb28`) `>>= 1`. Mode 3: words `+0xa6` and `+0xbe` += 50, max HP = trunc(max HP ×
1.5) (`0x5d1b08`), HP = max HP. It runs before the HP override, so overrides are not scaled. The
client copy `FUN_004a449c` (`0x4a4f2b`–`0x4a5017`, constants `0x5cea60` 0.5 / `0x5cea58` 1.5)
scales HP only for easy and has no brain shift; damage taken is scaled too (`FUN_00502019`
`0x5021b5`: × 0.5 easy, × 1.5 hard).

**Facing**: no field. The creature constructor sets the mover angle byte (`0x50e2ac`–`0x50e2db`)
to `0x40 + rand(0..128)` (256 = full circle, 0 = up, clockwise), i.e. D2 direction
`angle >> 4` = 4–11 (right, down, left; the draw reads `obj+0xc4 >> 4`, [animation
§2.2](animation.md#22-directions); the client direction is `(angle + 8) >> 4`, 4–12). CONFIRMED for
monsters and heroes: `FUN_005143e4` → `FUN_00512133` → `FUN_0050dc2b` → `0x50e173`, nothing
overwrites it. The client view's `+0x70` starts at 0 and takes the server's byte from the creation
message (`0x40f0e3`, `0x40f8f7`); that the creation message carries it is INFERRED. `scene.draw_scene` draws
units at a fixed `UNIT_FACING = 8` (front view).

**Type → animation set.** `Unit.type` → `load_unit_set(type)` (units.reg ID → file, e.g. 66
`monsters\ogre`). Palette: `Palette = 0` types use `human.pal[owner colour]`; others
`palette<k>.pal` with `k = face − 1`, `face` = data.bin monster param 30 (1–7, never above the
type's `Palette`; INFERRED mapping, the test checks the bound). The id table lives in
`graphics/units/units.reg` (data), the `serverID` table in `world/data/data.bin`.

### Item groups (section 8) and records (section 9)

There is **no list of items lying on the map** and no inventory in the unit record: items come
from section 8 groups, which `FUN_00564072` instantiates after the units exist.

Section 8, `n_sec8` groups (CONFIRMED, `0x535e74`–`0x536014`, tile exactly): `u32 n`, `u32
carrier` (`+0x3c`), `i32 x`, `i32 y` (1/256 cell, `+0x40`/`+0x44`; equal to the carrying
unit's position), `u32 extra` (`+0x48`, version ≥ 0x3dd; 0 in 43 groups, 100 / 5000 / 10000 in
8), then `n` members of `u32 code`, `u16 slot` (always 0), `u32 record`.
The file's `carrier` is overwritten when a unit's `group` points at the group (the unit's
uid); a group no unit links to keeps 0 and is a **sack on the ground** at (x, y)
(`Map.ground_groups`: 19). CONFIRMED (`FUN_00564072`, the loop at `0x5645d8`–`0x564b14` is inside it): a ground
group builds a 0x24-byte pack (`FUN_005299b3`), adds each item (`FUN_00529ac2`, identical items
stack) and places it with `FUN_0052ab07(cell, pack, extra, 0)`; **`extra` is the gold lying in that pile**
(`pile +0x3c += extra`; merged with an existing pile on the cell). A carried group adds its items to the
unit's pack (creature `+0x7c`) and ignores `extra` (`92.alm` group 1); `slot != 0` would equip (vtable
`+0x44`, never in the data). The 8 non-zero `extra` groups are pure gold piles of the ground
(100 in `63.alm`, 5000 in `41.alm`, 10,000 in `42.alm` and `93.alm`).

Item code (`FUN_004fbf01` → factory `FUN_004fbf99`, CONFIRMED): class = `(code >> 8) & 15`;
class 0xE = special item, index = `code & 0xFF`; otherwise quality = `(code >> 5) & 7`, material =
`code >> 12`, index = `code & 0x1F` (`entities.decode_item`). The factory (CONFIRMED):

| Class | Object (ctor) | data.bin list | Records | Index base |
|---|---|---|---|---|
| 1 | 0x88 B (`FUN_00528a07`) | weapons (`0x68f540`) | 27 | 1 (1 BareHands, 2 Dagger … 27 Plasma Sword) |
| 2 | 0x6c B (`FUN_00528084`) | shields (`0x68f518`) | 9 | 1 |
| 3–13 | 0x6c B (`FUN_005275d2`) | armour (`0x68f52c`) | 30 | 1; only the index selects, the record's `Slot` is the real slot (ring 4, amulet 5, helm 6, mail 7, cuirass 8, bracers 9, gauntlets 10, boots 12) |
| 0xE | 0x54 B (`FUN_00522ee0`) | special items (`0x68f554`) | 96 | 1 (potion, scroll, book, quest items by name) |
| 0, 15 | none | — | — | the member is skipped |

Quality and material index data.bin's 7 qualities and 16 materials. The test checks that
every code's index is in range and that the armour record's `Slot` equals the code's class (37
distinct codes in the install: 17 special, 20 weapon/shield/armour). Item definitions proper
(what a Dagger is) are phase F.

Section 9: `u32 count` of its own (not in the header), then per record: `u32 head`
(version > 989; overwritten with the member index of the claiming member), `u32 a`, `u32 b`,
6 flag bytes, `u32 c`, `u32 n`, `n` × (`u16 id`, `u32 value`); 26 + 6n bytes, tile exactly
(`0x536023`–`0x5361ac`). Object layout: head `+0` (overwritten by the claiming member's
index), group pointer `+4` (0 until a member claims the record), `a` `+8`, `b` `+0xc`, kind
`u16 +0x10`, `u16 +0x12` / `+0x14` (min, max damage, or a uid), `c` `+0x16` (`u16` spell id, `u16`
second value), pairs at `+0x1a`. CONFIRMED (`0x56465x`–`0x5648e0`) for a **claimed** record
(`a = b = 0`, a member's `record` points at it; with `a`/`b` set the item is silently skipped):
effect objects are added to the item: kind 1–5 → elemental damage (effect `0x2b + kind`, min and
max from the two bytes; `Crystal Long Sword` of `102.alm`: fire 30); `c` low ≠ 0 → `castSpell`
(0x29), or `teachSpell` (0x2a, adds the spell to the unit's spellbook) for books; each pair
`(id, value)` → effect `id`, **data.bin stat index** (1 price, 2 body, 5 spirit, 11 manaRegen,
12 toHit, 16 absorbtion, 19 scanRange, 23/25 protections …; `(1, 9000000)` is the price of the
19 quest items), id 41 remapped to `0x31` (flat damage bonus: INFERRED reading). An **unclaimed**
record is, by kind: bit 4 → building caster object (`FUN_0050da58`; the structure with uid
`+0x12`, spell id `c`, origin `a`/`b`; 72.alm 27 records, `81.alm` 3), bit 8 → spellbook entry of unit uid
`+0x12` (`FUN_0051c29e`; none in the install), `a`/`b` ≠ 0 with kind < 4 → a 6-byte per-cell
payload registered on the server grid (`FUN_0055ba36`, meaning UNKNOWN; `76.alm`, `93`–`96`), else
ignored (3 editor leftovers).

### Drawing

`map render MAP DEST --layers all` (or `units`, `items`) and the engine ([rendering §13](../engine/rendering.md#13-units-team-colours-piles-g3a))
follow the exe: a unit is filed under the cell of `pos - 0x80 + size * 0x80` (`size` = `TileSize`) and sorts per cell structure →
unit → object; it stands at `(X·32 >> 8, Y·32 >> 8 − ground height)` (vertex-bilinear, `objects.ground_height(size)`) in its
`idle` frame at clock `--clock`, direction 8 (the render has no facing); flyers (`Z ≠ 0`) draw last, 16 px raised. A pile is
the backpack sprite (`graphics/backpack/sprites.256`, `FUN_00461292`), frame = `min(5, floor(log10(total)))` with
total = gold + sum of the items' `+0x1c` (`FUN_0052a895`, sent in message 0x7a; CONFIRMED): 100 gold
→ frame 2, 5000 → 3, 10000 → 4; the item `+0x1c` is its price ([items](../data/items.md#4-price)), but the engine does not use it yet, so item piles are not framed (frame 0). Groups on one cell
are one pile. Sacks of dead monsters are runtime objects (`FUN_00510a70` → `FUN_005109f5`), not map data.

**Placement at load** (CONFIRMED): the server places a unit with `FUN_00510089(cell, r = 0)`, which tries only the file cell
(not a spiral; with `r != 0` it makes random tries, then a raster scan) and deletes the unit when the cell is not free for its
movement-type mask in the static and the live layer (error line, no relocation). 9 of 4,212 units sit on such a cell; the client copy
(`FUN_004a449c`) uses the file position regardless. HP 0 in the file (4 units): see [architecture §9](../engine/architecture.md#9-world-state).

### Checks

`tests/test_entities.py`: record layouts and size checks, exact tiling of sections 8 and 9
(synthetic); on the install: record counts equal the header (251 / 4,212 / 51 / 88), every
owner is a player, group links unique and ≤ `n_sec8`, sub-cell 128, all 4,212 units resolve to a
data.bin record and a units.reg file (53 ids), monster palette index ≤ `Palette`, item codes
inside the data.bin ranges, section 9 links in range, and the scene draws units and sacks.

### Handoff to game data (phase F)

Id tables the next phases need, all present in data: units.reg (type → sprites; `Palette`,
`Dying`), data.bin monsters/humans (`serverID` → record: stats, equipment strings, `face`),
data.bin qualities / materials / armour / shields / weapons / special items / stat names
(item codes and section 9 stat ids), `humans/human.pal` (colour rows). Item definitions, equipment strings and the
item `+0x1c` price: [items](../data/items.md).

## Open questions

- Dirt: the caller of `FUN_00559ce5` (clear), and when the mark disappears.
- Line of sight: the distance tables (`+0x22000` steps, `+0x28000`
  `ftol` of a power of `dx² + dy²`) and the `FUN_00559536` gate of
  `FUN_00552c28`; callers (`FUN_00552929` has no direct caller: vtable?).
- Whether the world-map-load order really creates cell records only through structures
  (a record made earlier by a unit makes `FUN_00559890` skip the refresh, see part 4);
  whether section 7 names structures (section 11 does: keyed by structure uid, CONFIRMED `FUN_00561422`).
- Block bits 3–7 and the dynamic stamping (`FUN_00550a96`,
  `FUN_0055c500`), the per-class `movementType` result (vtable `+0x20`),
  (the search itself is answered: [simulation §7](../engine/simulation.md#7-pathfinding-phase-h2)).
- Section 7 (trigger lists, 0x31c-byte records), 10, 11, 12 (the reader `FUN_00534ad4`
  cases 7, 10–12 are in the exe).
- Part 5: the event classes of `behaviour` bits 1, 2, 4 (`FUN_005303ed`); section 9 per-cell
  payload (`FUN_0055ba36`, records with `a`/`b` ≠ 0 and kind < 4; 30 records in `76`, `93`–`96`);
  (note: `FUN_005303ed` is the quest generator, [items §14](../data/items.md#14-quests-and-the-item-upgrade-message-0x38)).
  Answered in [items](../data/items.md): gold pickup (hero `+0x3c`, never `Player.money`, §12), `+0x1c` = price,
  the `(41, v)` remap to `0x31` (= 49 `damageBonus`; a pair cannot carry castSpell).
- Section 12 (28-byte circle zones with four `-1`-or-number values, consumer `0x475500` picks
  one at random into `0x5f1a08`: INFERRED music/ambience zones; users of the global untraced);
  sections 7 and 11 key slots by coded numbers 8000–9999 and structure uids.
