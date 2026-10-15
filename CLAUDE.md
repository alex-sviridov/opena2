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
  NOT shadows. Open: mirror variants, darkening blit's users. docs/formats/sprites.md
- Palettes: layout CONFIRMED; human.pal remap (FUN_00425bee) open.
  docs/formats/palettes.md
- BMP: CONFIRMED. docs/formats/bitmaps.md
- Inventory + binary triage + reversing plan: docs/inventory.md (tools/inventory.py
  -> out/inventory.csv). This install has NO .res, .alm, music, .smk; a2mgr maps
  .res paths to loose data/ files (INFERRED). data/version = SHA-1 manifest.
- .reg: header CONFIRMED (sig 0x31415926, FUN_004ed6cc); entry semantics open.
- Not started: data.bin, fonts .dat, maps (.alm, no samples), saves, game layer.
