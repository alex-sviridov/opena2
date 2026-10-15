# Allods 2 recreation

Reverse-engineering and reimplementing Allods 2 / Rage of Mages 2 (Nival).
The company is legally entitled to recreate the game.

## Layout
- `allods2/` core library (formats, decoders, data models; no pygame)
- `allods2/game/` game layer (pygame), built on the core
- `docs/{formats,mechanics,...}/<name>.md` specs; each folder's README.md is its index
- `tests/` · `tools/` thin CLIs over the package
- `samples/` original game files (English 1.30: samples/Allods2_en_251005/Allods2_en/)

## Hard rules
- samples/ is read-only and never committed. Never copy game files, or data
  derived from them (exports, extracted sprites, decompiled listings), into
  the repo. Write exports to the gitignored `out/` or outside the repo.
- Use the venv: `python3 -m venv .venv && .venv/bin/pip install -e '.[game,dev]'`.

## Dependencies
- Core may use numpy and other well-known, widely used libraries (e.g. Pillow).
  Core must not import pygame.
- The game layer uses pygame.
- Declare every dependency in pyproject.toml: core in `dependencies`, pygame in
  the `game` extra, tooling in `dev`. Adding a niche or little-known package
  needs approval first. Python 3.10+.

## Specs
- Every format, game mechanism, or other subsystem gets a spec in
  docs/<area>/<name>.md containing: a byte layout table, the math, worked
  examples, and open questions.
- Mark each fact:
  - **CONFIRMED**: binary (allods2.exe / a2mgr.dll), build sha256, routine
    address, checked in decompiled code via REA; or the decoder consumes every
    file in samples/ exactly.
  - **INFERRED**: anything else (patterns in data, the shape of code, analogy).
  Never present a guess as a fact.
- Match the game exactly, including quirks; any "clean" API is a separate layer.
- Open questions: each spec ends with an "Open questions" section, and every
  item is also listed in docs/open-questions.md (one line, link to the spec,
  starting routine). Add the line when the question is raised; when it is
  answered, update the spec and delete the line from both places in the same
  change. Check that list when choosing the next task.

## Code and tests
- Library code is written from the specs, never pasted from decompiler output.
- Tests: `.venv/bin/pytest`
  - Tests that use game files read them from samples/ (or ALLODS2_DATA) and
    skip when they are missing.
  - Synthetic tests build small streams in code, one per spec rule, and
    always run.
- A decoder is done when its validate tool passes on the full install
  (e.g. `.venv/bin/python tools/validate_sprites.py`).

## Session routine
- At the end of each session: update "Known so far" below.
- When wrapping up or after a major task: check the size of memory. If
  MEMORY.md is over ~100 lines or the memory files total over ~25 KB, offer to
  compact it, merging or removing only what can go without losing information.

## Known so far
- Sprites (.256, .16, .16a, *b.256): CONFIRMED, all 43,051 sprites decode
  exactly. *b.256 = edge-smoothing overlays (50 % blend, "Smoothing" option),
  NOT shadows. Draw vtables 0x5d53a8/.16a 0x5d5488: every blit has a mirrored
  twin (x+w-1 leftward, CONFIRMED; Canvas mirror=). Darken (+0x1c) = UI drop
  shadows only (lm/scrlbars/radiob.256). Effect 0x20 = unit hidden unless
  viewer relation bit 8, else 50 % (INFERRED Invisibility). docs/formats/sprites.md
- Palettes: CONFIRMED. BGR0 8-bit entries, 4th byte ignored. 2,973
  palettes in 2,928 files (tools/validate_palettes.py; contact sheet via
  tools/palette_contact.py). FUN_00425bee turns palettes into 16-bit shade
  tables (6 modes; FADE16 = the .16a alpha table). human.pal = 16 player
  colours (index 164 → per-player .16 text ramp). The code gradients and
  ramps are font colours. The low-memory flag DAT_0062c9b8 is legacy and
  not reproduced (user decision). docs/formats/palettes.md
- Lighting: CONFIRMED. Day/night (FUN_0047a208), terrain light map
  (FUN_004ad552), light map + stamps (FUN_004040e2/FUN_004063c5, projectile
  lights), object rows (FUN_00404ad1), shadows (FUN_0045a33f, shear from
  sun). Open: what units stamp, fog map, .alm heights. docs/mechanics/lighting.md
- BMP: CONFIRMED. docs/formats/bitmaps.md
- Inventory + binary triage + reversing plan: docs/inventory.md (tools/inventory.py
  -> out/inventory.csv). This install has NO .res, music, .smk; a2mgr maps
  .res paths to loose data/ files (INFERRED). data/version = SHA-1 manifest.
- .reg: CONFIRMED. Header = sig + root entry (type 0x11 sorted); 32-byte
  entries; root lookup strcmp, sections strnicmp(15) -> names with trailing
  spaces are unreachable (units.reg File0). allods2/reg.py, docs/formats/reg.md
- Units: CONFIRMED. units.reg parser FUN_0047f108 (Parent = unit ID
  inheritance), frames: stand 16|9, then (Begin+Move), Attack, Dying, bones/idle
  x 8|5 dirs; Flip mirrors (FUN_0045a64d); Dying = ID of type whose frames die.
  59/62 exact. allods2/units.py, docs/formats/units.md (tools/validate_units.py,
  tools/unit_contact.py)
- .alm maps: 216 from the allods2.eu maps pack in samples/.../maps/. Container
  (M7R header + 13 sections) walks to EOF on all; semantics open. docs/inventory.md §5.2
- Graphics overview: docs/formats/graphics-overview.md (tools/gfx_survey.py ->
  out/gfx/). Ranks 1-10 CONFIRMED (terrain flat only).
- Fonts: CONFIRMED. fontN.dat = u32 per glyph (char 0x20+g) = last ink column;
  advance = width + 2. Measure FUN_00461e19, .16 draw 0x4637f1 hooked by
  a2mgr Ordinal_125/126 (%[RGB] colour escapes), .16a draw FUN_00463bbd,
  '~' = hotkey underline, cp866 remap when DAT_0062c9c4 == 1.
  docs/formats/fonts.md (tools/validate_fonts.py, tools/font_contact.py)
- Sprite frames have no hotspot; FUN_00468640 centres on the anchor with
  unit-type offsets T+0x2c..0x38 (from units.reg, INFERRED). sprites.md
- CLI: python -m allods2 gfx export FILE DEST [--palette P]. Contact sheets:
  tools/sprite_contact.py, tools/font_contact.py, tools/palette_contact.py
  -> out/contact/.
- PNG: CONFIRMED. a2mgr Ordinal_102/103 try data\<path>.png before .256 for
  paper-doll layers; FUN_10010d70 draws only 160x240, float alpha blend into
  RGB565, channels >= 1. docs/formats/png.md (tools/validate_png.py)
- Terrain: CONFIRMED flat. Tiles u16: row v&0xf, strip (v>>4)&3, set
  (v&0x1fff)>>6 (0-12), 0x2000 dirt overlay; sets 8-11 = animated water.
  Loader FUN_0047b899, draw FUN_00404eb5, flat lit blit FUN_0045c757.
  allods2/alm.py reads the M7R container. docs/formats/terrain.md
  (tools/validate_terrain.py, tools/terrain_contact.py). Open: FUN_0045c8ce
  height-displaced blit, altitude -> vertex y.
- Not started: data.bin, saves, game layer.
- Next (see docs/open-questions.md): terrain heights (FUN_0045c8ce, altitudes -> vertex y), structures.reg
  and objects.reg animation, unit states/tick timing, data.bin.
