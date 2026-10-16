# Allods 2 recreation

Reverse-engineering and reimplementing Allods 2 / Rage of Mages II:
Necromancer (Nival), **single player**, from the GOG release.
The company is legally entitled to recreate the game.

## Layout
- `a2res/` stand-alone `.res` library (stdlib only): `ResArchive`, `ResFS`,
  `DirFS`, `ChainFS`, `OS`; zero-copy `memoryview` reads
- `allods2/` core library (formats, decoders, data models; no pygame); every
  loader is `load(path, fs)` on game paths (`graphics/units/units.reg`)
- `allods2/formats/` decoded views of data files (`Map`); `allods2/alm.py` is the .alm container
- `allods2/game/` game layer (pygame), built on the core
- `docs/{formats,mechanics,...}/<name>.md` specs; each folder's README.md is its index
- `allods2/common.py` `INSTALL` (`ALLODS2_INSTALL`), `game_fs()`, `as_fs()`, OUT
- `tests/` · `tools/` thin CLIs over the package (`[INSTALL_DIR]` argument)
- `samples/allods2_en_gog/` the GOG install (exe 1.01, ten `.res` archives)
- Scope: single player (campaign, towns, world map, saves); the multiplayer
  network parts are out of scope

## Hard rules
- samples/ is read-only and never committed. Never copy game files, or data
  derived from them (exports, extracted sprites, decompiled listings), into
  the repo. Write exports to the gitignored `out/` or outside the repo.
- Use the venv: `python3 -m venv .venv && .venv/bin/pip install -e '.[game,dev]'`.

## Dependencies
- Core may use numpy and other well-known libraries (e.g. Pillow), never
  pygame; the game layer uses pygame. Python 3.10+.
- Declare every dependency in pyproject.toml: core in `dependencies`, pygame
  in the `game` extra, tooling in `dev`. Niche packages need approval first.

## Specs
- Every format, mechanism or subsystem gets docs/<area>/<name>.md with a
  byte layout table, the math, worked examples, and open questions. Keep
  specs compact: state each fact once and cross-link instead of repeating.
- Mark each fact:
  - **CONFIRMED**: checked in the GOG allods2.exe via REA (build sha256
    in docs/formats/README.md, routine address given), or the decoder
    consumes every file of the install exactly.
  - **INFERRED**: anything else (data patterns, code shape, analogy).
  Never present a guess as a fact.
- Match the game exactly, including quirks; any "clean" API is a separate layer.
- Open questions: each spec ends with "Open questions"; every item is also
  one line in docs/open-questions.md (link + starting routine). Add the
  line when raised; when answered, update the spec and delete it from both
  places in the same change. Check that list when choosing the next task.

## Code and tests
- Library code is written from the specs, never pasted from decompiler output.
- Tests: `.venv/bin/pytest`. Game-file tests read the install's archives
  (`tests/helpers.GFS`) and skip when missing; synthetic tests build small streams
  in code, one per spec rule, and always run.
- A decoder is done when its validate tool passes on the full install
  (e.g. `tools/validate_sprites.py`; animation API: `tools/validate_anim.py`).

## Session routine
- At the end of each session: update "Known so far" (one line per area:
  status, headline facts, spec; details belong in the spec).
- When wrapping up or after a major task: if MEMORY.md is over ~100 lines
  or the memory files total over ~25 KB, offer to compact it without
  losing information.

## Known so far
Details, routines and tools are in each spec; CLI: `python -m allods2 gfx
export FILE DEST [--palette P] [--index N | --sheet]`, `anim preview KEY DEST`,
`anim preview-all DEST`, `map info MAP`, `map render MAP DEST.png [--relief] [--layers terrain,objects,structures]`,
`res ls|list|extract`; contact sheets
`tools/*_contact.py` → out/contact/.
- .res / a2res: CONFIRMED (`FUN_004e2040` opener, lookup `FUN_004e9046`, mount
  `FUN_00481186`, manager `FUN_004e2b5d`): `.reg` entry tree, absolute file
  ranges; paths lower-cased (A–Z) before lookup; loose dirs cwd/temp/CD
  fallback + `update.lst` overrides; all 10 archives tile exactly. Mount
  0.15 s, every file read 0.35 s. res.md
- Sprites `.256/.16/.16a/*b.256`: CONFIRMED, 43,947 decode exactly. `*b.256`
  = 50 % edge-smoothing overlays; mirrored blit twins; darken = UI drop
  shadows; effect 0x20 Invisibility + relation word. sprites.md
- Palettes: CONFIRMED, 2,854 in 2,809 files; `FUN_00425bee` shade tables (6
  modes, FADE16 = `.16a` alpha); human.pal = 16 player colours; code tables
  = text colours; effect id = 2·spell + 8; low-memory flag not reproduced
  (user decision). palettes.md
- Lighting: CONFIRMED day/night, terrain light, light map + stamps, object
  rows, shadows, options (labels from patch.txt), fog draw. mechanics/lighting.md
- BMP: CONFIRMED (8-bit flips, 64k class doesn't; pack16; price bar;
  portrait canvas + crop table). bitmaps.md
- .reg: CONFIRMED (17 files): reader/writer, +0x14 = garbage bytes, sort pass
  bug (only roots sorted), INI compiler; saves use .reg. reg.md
- Units: CONFIRMED units.reg + frame layout, facing clockwise from up,
  Flip, events; 59/61 + 30/30 hero files; bones stride = BonePhases;
  palette variant = data.bin monster param 30. units.md, animation.md §2
- Terrain: CONFIRMED incl. signed relief, displaced blit, grid overlay
  `DAT_00622800`; all 46 campaign maps load every set; the file's dirt bit
  13 is cleared on load (`FUN_004a449c`), dirt arrives from the server. terrain.md
- Fonts: CONFIRMED (widths, `~` underline, shadow, char map off: main\id
  `english 0`; text loaders + CharToOemA). fonts.md
- Paper doll: CONFIRMED `.256` layers `FUN_004688f7`, layer order. paperdoll.md
- Animation: CONFIRMED sources, layout, client/server timing (VERIFY IN GAME
  list §3.6), `allods2/anim` API for every animated class, whole-install
  check (549 sets; 671/740 files + 69 exclusions, 44 open: town scenes,
  world-map Cross), world-map flags, sight mask (exe variant), data-driven
  speeds, combat handoff §5.3, suggested work §5.4. animation.md
- data.bin: CONFIRMED MFC archive, consumed exactly; column names per group
  (`DataBin.columns`) name every param incl. humans/structures. databin.md
- Install, triage, plan: docs/inventory.md. .alm: 46 campaign maps;
  container walks all; header (section 0, `FUN_00534ad4`: size, version,
  players, tile-set mask, cp1251 name/description, counts) and layers 1–3
  CONFIRMED, `Map.load` + `map info|render`; light fields are overwritten
  by `FUN_004a5dd2`; sections 5–12 raw. map.md
- Heights/passability: CONFIRMED heights = signed byte per vertex, 0..127,
  1 px each, no slope limit (speed ±50 %, sight). No stored passability: the
  server path finder derives a block layer (`FUN_00554626`: water, mountain
  type, file dirt flag → 1, any object → 5, 8-cell border 0x1F) and costs
  (`map.reg`); mover masks 0x41 / 0x44 / 0x82 by movementType. `Map.block`,
  `.passability(m)`, `.cost()`, `.heights_i8`; map.md part 3
- Map objects: CONFIRMED section 3 = per-cell `objects.reg` IDs (trees,
  rocks; 192 IDs, 7 burning trees + ID 208 have no sprite, all outside the
  loaded window); section 4 = structures, 20-byte entries (cell x/y in 1/256,
  type = `structures.reg`/data.bin ID, `intact`, `owner`, `uid`; sized bridges
  +8 bytes; 1,721 entries tile all 46 maps). Footprint = data.bin
  `sizeX × sizeY` + `Passability` bit mask (`FUN_00550a96`, index mod 32;
  bridges mask 0 = walkable). Draw order (`FUN_00406f43`): terrain, flat
  structures, then per cell structure → unit → object. `Map.structures`,
  `.placed_objects()`, `.passability(m, stats)`, `anim/scene.py`. Owner
  matching and dirt source open. map.md part 4
- Not started: saves, Scenario.dll, item names, game layer.
- Next (docs/open-questions.md): .alm sections 5–12 (server reader
  `FUN_00534ad4`), town-scene animations, text conventions.
