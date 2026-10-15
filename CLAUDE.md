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
  viewer relation bit 8, else 50 % (Invisibility, CONFIRMED). Relation word
  CONFIRMED: 8 = p shares vision with me, 0x20 alliance, 0x40 war (received);
  1 enemy, 2 ally, 0x10 visible, 4 silent (own choices); self = 0x3a.
  Draw slots +0x18/+0x38 use the sprite's own table, +0x14/+0x34 an external
  one. Projectile overlays (A16=0, Palette=1: goblin arrow, catap1/2) are
  drawn with their own all-zero palette = 50 % black, without the Smoothing check.
  Overlays of heroes/units/structures/objects use the main sprite's table.
  Effect id = projectile ID = 2*spell+8 (+9 secondary), spell n from the exe
  name table (spell.txt+1); server FUN_00523a7f, msg 0x88. allods2/spells.py.
  docs/formats/sprites.md, palettes.md §7
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
- BMP: CONFIRMED. 8-bit class flips rows; 64k class (FUN_0042769b) doesn't
  (blits read h-1-sy), packs BGR with masks from GetPixelFormat
  (FUN_004584cc) = palette.pack16; +0x38 colour key 0, +0x3c 16-bit add,
  +0x1c no-op. Shop price bar = costs/costm1-7.bmp, frame = log10(price).
  Message-log colours 0x5fb97c..990 (palettes §6). +0x2c flip used by
  FUN_0041f2d4 (info-window portrait canvas). docs/formats/bitmaps.md
- Inventory + binary triage + reversing plan: docs/inventory.md (tools/inventory.py
  -> out/inventory.csv). This install has NO .res, music, .smk; a2mgr maps
  .res paths to loose data/ files (INFERRED). data/version = SHA-1 manifest.
- .reg: CONFIRMED. Header = sig + root entry (type 0x11 sorted); 32-byte
  entries; root lookup strcmp, sections strnicmp(15) -> names with trailing
  spaces are unreachable (units.reg File0). allods2/reg.py, docs/formats/reg.md
- Units: CONFIRMED. units.reg parser FUN_0047f108 (Parent = unit ID
  inheritance), frames: stand 16|9, then (Begin+Move), Attack, Dying, bones/idle
  x 8|5 dirs; Flip mirrors (FUN_0045a64d); Dying = ID of type whose frames die.
  59/62 exact + 30/30 hero files (no dying blocks except unarmed/mage_st).
  Facing d clockwise from screen-up (0 up, 4 right, 8 down; step tables
  0x6023b0/0x6023f0, CONFIRMED); sprite dir 0 = d 8 = front view. Flip
  mirrors in place (hotspot not negated; all Flip types CenterX=Width/2).
  Events: AttackDelay/ShootDelay tick -> phase AttackAnim[delay]; client
  only (sound +0x64/+0x60, projectile +0x58/+0x5c); server ignores
  units.reg. Exceptions: Unit0 key, Unit33 file, sheep 5-phase dying.
  allods2/units.py, docs/formats/units.md, animation.md §2
  (tools/validate_units.py, tools/unit_contact.py, tools/anim_contact.py)
- .alm maps: 216 from the allods2.eu maps pack in samples/.../maps/. Container
  (M7R header + 13 sections) walks to EOF on all; semantics open. docs/inventory.md §5.2
- Graphics overview: docs/formats/graphics-overview.md (tools/gfx_survey.py ->
  out/gfx/). Ranks 1-10 CONFIRMED.
- Fonts: CONFIRMED. fontN.dat = u32 per glyph (char 0x20+g) = last ink column;
  advance = width + 2. Measure FUN_00461e19, .16 draw 0x4637f1 hooked by
  a2mgr Ordinal_125/126 (%[RGB] colour escapes), .16a draw FUN_00463bbd,
  '~' = hotkey underline. cp866 remap DAT_0062c9c4: exe reads data/main/id
  digit, a2mgr Ordinal_81 forces 1 (Font defaults cyrillic=True); typed
  input cp1251->cp866 FUN_0047a0f5. 0xC1 = font2 star glyph (a2mgr item
  tooltip FUN_1002c700: %[rgb] by stars + N stars). FUN_004627f6 = shadowed
  draw (slot 6 shadow table 0x62afb8). font5.ttf = a2mgr GDI+ widget font.
  docs/formats/fonts.md (tools/validate_fonts.py, tools/font_contact.py)
- Text colours: palettes.md §6 maps every code table to its users (grey14
  normal via 0x5fa5a0, grey17 highlight 0x5fa5a4, gold labels 0x5fa5a8, sage
  values, orange headers/hover, tan tooltip). Chat kinds 0 near, 1 ally,
  2 private, 3 shout (=), 4 lobby. Portrait crop table 0x5fcf70 (bitmaps.md).
- Sprite frames have no hotspot; FUN_00468640 centres on the anchor with
  unit-type offsets T+0x2c..0x38 (from units.reg, INFERRED). sprites.md
- CLI: python -m allods2 gfx export FILE DEST [--palette P]. Contact sheets:
  tools/sprite_contact.py, tools/font_contact.py, tools/palette_contact.py
  -> out/contact/.
- PNG: CONFIRMED. a2mgr Ordinal_102/103 try data\<path>.png before .256 for
  paper-doll layers; FUN_10010d70 draws only 160x240, float alpha blend into
  RGB565, channels >= 1. docs/formats/png.md (tools/validate_png.py)
- Terrain: CONFIRMED incl. relief. Tiles u16: row v&0xf, strip (v>>4)&3, set
  (v&0x1fff)>>6 (0-12), 0x2000 dirt overlay; sets 8-11 = animated water.
  Loader FUN_0047b899, draw FUN_00404eb5 (rows top->bottom), flat blit
  FUN_0045c757. Heights: .alm section 2 copied verbatim to map+0x10, read
  as SIGNED bytes; vertex y = 32*row - H (FUN_00406658), x never moves;
  FUN_0045c8ce stretches each tile column between edges stepped by table
  T[n][k] (FUN_0045752b). a2mgr Ordinal_65 = grid overlay only.
  allods2/alm.py, allods2/graphics/terrain.py (render, render_3d),
  docs/formats/terrain.md. Tools: validate_terrain, terrain_contact,
  tile_contact (out/contact/tiles_<set>.png), terrain_render (out/terrain3d/).
- Animation sources (part 1): CONFIRMED. All timing/phase data is in the
  .reg files (no text configs, no sprite-header fields). Loaders: structures
  FUN_00482e99 (table 0x62caf8; grid W*FullHeight pieces + (Phases-1)*A
  AnimMask cells [+ W*FH destroyed], all 179 exact), objects FUN_0047e4a0
  (list 0x630d90; frame = Index + seq[(clock+X+X*Y) % len]), projectiles
  FUN_004824cc (table 0x62cb10; frame = phase + Phases*dir, 16|9 dirs, no
  time array: phase = tick/2 % Phases, flight time hard-coded FUN_0046c4f1).
  Units' sequences are at T+0x3c/0x54/0x6c (lengths +0x50/0x68/0x80).
  Heroes: FUN_0046f688 maps sprite folder name -> units.reg ID. Tick:
  msg 0x401 -> FUN_0040bdc1 (view clock +0xa88 ++, every object's vtable
  +0x3c); period 1000/rate, rate 8..32 by speed 0..8 (FUN_00492068).
  Unit tick FUN_0046b5ef sets state/phase/events. Move phase is
  distance-driven: odometer += sqrt(step^2), seq[(odo/16) % len]. Action
  durations: msg loop FUN_0040dac9 (0x6b move/0x6d turn = server byte,
  attack/shoot/cast = AttackAnim seq length, dying = 2*DyingPhases); death
  stage from HP (<=0,-10,-20,-40,-600). Default speed 4 (16 ticks/s),
  profile GameOptions/Speed. Dying heroes use unarmed/mage_st sprites.
  .alm section 3 = object layer (byte = object index + 1, CONFIRMED); tile
  bits 0xc000 = run-time visibility gating animation (INFERRED fog).
  docs/formats/animation.md
- Animation timing (part 3): CONFIRMED. One timeGetTime fixed-step loop
  FUN_0048e7d0: server step FUN_004f967a, client msgs, client tick, all
  once per tick (re-base every 16 ticks). Rules: water clock>>2, projectile
  age/2, dying 2 ticks/frame then corpse held; every unit action runs
  obj+0xa8 ticks then idle. Server walk FUN_00563185: v = speed *
  SpeedMultiplier(8) +-slope / avg terrain Cost (map.reg), ticks/cell =
  ceil(256/v), diag x0.707; turn FUN_00560444 ceil(diff/8); attack cadence
  +0x134 + +0x135 (hero 8+4, weapon params 12/13). Hero speed FUN_0051d2a7;
  speed effect kind 17 FUN_00527122. VERIFY IN GAME list in animation.md §3.6
- Not started: data.bin, saves, game layer.
- Next (see docs/open-questions.md): sprite/animation open questions one
  by one (user request), implement animation (structures/objects/
  projectiles/units), server hit timing, data.bin,
  .alm sections 0, 4-12.
