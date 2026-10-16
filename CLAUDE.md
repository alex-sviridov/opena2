# Allods 2 recreation

Reverse-engineering and reimplementing Allods 2 / Rage of Mages 2 (Nival).
The company is legally entitled to recreate the game.

## Layout
- `allods2/` core library (formats, decoders, data models; no pygame)
- `allods2/game/` game layer (pygame), built on the core
- `docs/{formats,mechanics,...}/<name>.md` specs; each folder's README.md is its index
- `allods2/common.py` install paths (`ALLODS2_INSTALL` / `ALLODS2_DATA`, OUT)
- `tests/` · `tools/` thin CLIs over the package
- `samples/` original game files (English 1.30: samples/Allods2_en_251005/Allods2_en/)

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
  - **CONFIRMED**: checked in allods2.exe / a2mgr.dll via REA (build sha256
    in docs/formats/README.md, routine address given), or the decoder
    consumes every file in samples/ exactly.
  - **INFERRED**: anything else (data patterns, code shape, analogy).
  Never present a guess as a fact.
- Match the game exactly, including quirks; any "clean" API is a separate layer.
- Open questions: each spec ends with "Open questions"; every item is also
  one line in docs/open-questions.md (link + starting routine). Add the
  line when raised; when answered, update the spec and delete it from both
  places in the same change. Check that list when choosing the next task.

## Code and tests
- Library code is written from the specs, never pasted from decompiler output.
- Tests: `.venv/bin/pytest`. Game-file tests read samples/ (or
  ALLODS2_DATA) and skip when missing; synthetic tests build small streams
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
export FILE DEST [--palette P] [--index N | --sheet]`, `anim preview KEY DEST`, `anim preview-all
DEST`; contact sheets `tools/*_contact.py` → out/contact/.
- Sprites `.256/.16/.16a/*b.256`: CONFIRMED, 43,051 decode exactly. `*b.256`
  = 50 % edge-smoothing overlays (not shadows); mirrored blit twins; darken
  = UI drop shadows; effect 0x20 Invisibility + relation word. sprites.md
- Palettes: CONFIRMED, 2,973 in 2,928 files; `FUN_00425bee` shade tables (6
  modes, FADE16 = `.16a` alpha); human.pal = 16 player colours; code tables
  = text colours; effect id = 2·spell + 8; low-memory flag not reproduced
  (user decision). palettes.md
- Lighting: CONFIRMED day/night, terrain light, light map + stamps, object
  rows, shadows, options, fog draw (bilinear blend-table rows over relief
  quads, `draw_fog`). mechanics/lighting.md
- BMP: CONFIRMED (8-bit flips, 64k class doesn't; pack16; price bar;
  portrait canvas + crop table). bitmaps.md
- .reg: CONFIRMED; trailing-space names unreachable (units.reg File0). reg.md
- Units: CONFIRMED units.reg + frame layout, facing clockwise from up,
  Flip, events; 59/62 + 30/30 hero files; palette variant = data.bin
  monster param 30. units.md, animation.md §2
- Terrain: CONFIRMED incl. signed relief and displaced blit; all maps load
  every set; terrain.3d dead code. terrain.md
- Fonts: CONFIRMED (widths, cp866 remap forced on by a2mgr, `~`, `%[RGB]`,
  shadow, 0xC1 star; locale .txt via CharToOemA = cp1251→cp866
  `ansi_to_oem`). fonts.md
- PNG: CONFIRMED a2mgr paper-doll lookup, 160×240 blend (straight alpha,
  SSE precision), exe layer order `FUN_0046dd6a`, menu PNG blit. png.md
- Animation: CONFIRMED sources, layout, client/server timing (VERIFY IN GAME
  list §3.6), `allods2/anim` API for every animated class, whole-install
  check (546 sets; 668/695 files + 27 exclusions), combat handoff §5.3,
  suggested work §5.4; sight mask (exe + a2mgr), data-driven speeds, map
  flags, Blind/world-map/inn timing; chargen cube never drawn; world map
  can't open in this install (INFERRED). animation.md
- Install, binary triage, reversing plan: docs/inventory.md (no .res,
  music, .smk; data/version = SHA-1 manifest). .alm: 216 maps; container
  walks all; sections 1–3 CONFIRMED (tiles, heights, objects), rest open.
- Graphics overview: ranks 1–10 CONFIRMED. graphics-overview.md
- data.bin: CONFIRMED MFC archive, consumed exactly (`allods2.databin`,
  tools/validate_databin.py); monster/item/spell params, stat names =
  effect kinds, modifier text. Humans/structures open. databin.md
- Not started: saves, game layer.
- Next (docs/open-questions.md): .alm sections 0, 4–12 (server reader
  `FUN_0053ea3a`), data.bin humans/structures.
