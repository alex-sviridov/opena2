# Allods 2 recreation

Reverse-engineering and reimplementing Allods 2 / Rage of Mages II:
Necromancer (Nival), **single player**, from the GOG release.
The company is legally entitled to recreate the game.

## Layout
- `a2res/` stand-alone `.res` library (stdlib only): `ResArchive`, `ResFS`,
  `DirFS`, `ChainFS`, `OS`; zero-copy `memoryview` reads
- `allods2/` core library (formats, decoders, data models; no pygame); every
  loader is `load(path, fs)` on game paths (`graphics/units/units.reg`)
- `allods2/formats/` decoded views of data files (`Map`); `allods2/alm.py` is the .alm container;
  `formats/saves.py` = `.a2c` characters, `famehall.dat`, `game%d.sav` (docs/formats/saves.md)
- `engine/` the game (world, sim, view, ui, `backend_pygame`, `coverage.py` + `objective.py` = the map report and the objective run; only the backend imports
  pygame-ce), built on the core; `allods2/assets.py` asset cache; docs/engine/
- `docs/{formats,mechanics,data,...}/<name>.md` specs; each folder's README.md is its index; `docs/coverage.md` = the map coverage report
  (generated block + K0 proposal; `python -m engine coverage`)
- `allods2/common.py` `INSTALL` (`ALLODS2_INSTALL`), `game_fs()`, `as_fs()`, OUT
- `tests/` · `tools/` thin CLIs over the package (`[INSTALL_DIR]` argument)
- `samples/allods2_en_gog/` the GOG install (exe 1.01, ten `.res` archives)
- Scope: single player (campaign, towns, world map, saves); the multiplayer
  network parts are out of scope

## Hard rules
- samples/ is read-only and never committed. Never copy game files, or data
  derived from them (exports, extracted sprites, decompiled listings), into
  the repo. Write exports to the gitignored `out/` or outside the repo.
- Use the venv: `python3 -m venv .venv && .venv/bin/pip install -e '.[engine,dev]'`.

## Dependencies
- Core may use numpy and other well-known libraries (e.g. Pillow), never
  pygame; only `engine/backend_pygame` uses pygame-ce (not `pygame`: the two
  cannot coexist). Python 3.10+.
- Declare every dependency in pyproject.toml: core in `dependencies`, pygame-ce
  in the `engine` extra, tooling in `dev`. Niche packages need approval first.

## Workflow
- Once a spec is written and committed, go ahead and implement it: no further
  questions, no plan-approval round. Decide sensibly and record assumptions in the spec.
- Reimplemented game logic must be checked against allods2.exe with REA (tell
  subagents to use it); do not rely on inference where the binary can answer.
- Delegate to subagents where it helps (implementation, review, research);
  prefer `model: sonnet` over opus.
- Run only one subagent at a time: wait for it to finish before spawning the next.

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
- Native planner (docs/engine/simulation.md 7.5): `engine/native/planner.c` is compiled on first use
  with `gcc -O2 -shared -fPIC` into the gitignored `engine/native/_planner.so` (rebuilt when the source is
  newer; no compiler = the pure-Python planner, silently). `ALLODS2_NATIVE=0` forces Python, `=1` requires
  native. Planner changes: edit both, then run the planner tests in both modes:
  `for m in 0 1; do ALLODS2_NATIVE=$m .venv/bin/pytest -q tests/test_pathfinding*.py tests/test_engine_pathing.py tests/test_engine_orders*.py; done`.
- A decoder is done when its validate tool passes on the full install
  (e.g. `tools/validate_sprites.py`; animation API: `tools/validate_anim.py`).

## Session routine
- At the end of each session: update "Known so far" (one line per area:
  status, headline facts, spec; details belong in the spec).
- Every phase K step ends with `.venv/bin/python -m engine coverage` (about 40 s, it includes the objective run): flip the status of what the step built in `engine/coverage.py`
  (`FEATURES`, `STEPS`), commit the regenerated `docs/coverage.md` and quote its first line (maps without a blocker, playable now, blocked) in the
  step's close-out, so progress shows as numbers.
- When wrapping up or after a major task: if MEMORY.md is over ~100 lines
  or the memory files total over ~25 KB, offer to compact it without
  losing information.

## Known so far
Details, routines and tools are in each spec; CLI: `python -m allods2 gfx
export FILE DEST [--palette P] [--index N | --sheet]`, `anim preview KEY DEST`,
`anim preview-all DEST`, `map info MAP`, `map render MAP DEST.png [--relief] [--layers terrain,objects,structures,units,items|all]`,
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
  rows, shadows, options (labels from patch.txt), fog draw; engine builds structure / missile lights and Light / Darkness vertex writes (`engine/view/lights.py`), clock = client `+0x408`. mechanics/lighting.md
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
  `english 0`; text loaders + CharToOemA). G3c done: Cyrillic remap always on (DECISION, English is ASCII), `allods2/text.py`
  (`decode_text`, `font_bytes`: cp1251 -> cp866, no ё glyph), `Font.wrap/layout_block` (our rule), `engine/backend_pygame/text.py`
  draws with font1-4 + game colour tables + shadow (replaces pygame's font), `python -m allods2 font sample`, `tools/font_contact.py`. fonts.md
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
  by `FUN_004a5dd2`; sections 5, 6, 8, 9: see "Map entities". map.md
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
  `sizeX × sizeY` + `Passability`/`BuildingPresent` bit masks (`FUN_005599df`
  registers present cells, `FUN_00550a96` stamps; index mod 32; bridges mask 0
  = walkable). `owner` = 1-based section 5 record index (CONFIRMED); dirt =
  server block bit 0x10 set by spell area effects (message 155). Draw order (`FUN_00406f43`): terrain, flat
  structures, then per cell structure → unit → object. `Map.structures`,
  `.placed_objects()`, `.passability(m, stats)`, `anim/scene.py`. Open: dirt meaning/clear.
  map.md part 4
- Engine G1 (skeleton) done: `engine/` world, sim (tick table CONFIRMED), view
  (Camera, coords, per-cell numpy compositing reusing `graphics.terrain`),
  ui (scroll), `backend_pygame` (surface cache, accumulator loop); `python -m
  engine run|screenshot`; screenshot equals `render_3d` pixel for pixel (tested);
  import boundaries enforced by `tests/test_engine_boundaries.py`. docs/engine/
- Engine G2a' (world state) done: `engine.world.World` with `objects` table (ids: structures
  `0x6000 + uid` CONFIRMED, section 3 cells `0x10000 + n`), spatial index, block layer with local
  recompute, `from_map`, `BuildReport`; `python -m engine world-info|world-dump` (no pygame);
  `tests/golden.json` + `tools/update_golden.py`. REA: a structure claiming a held cell loses it and
  all its later present cells (first wins, `FUN_00559890`/`FUN_005599df`; 16 cells in 30.alm,
  40.alm); `stamp_structures` follows. docs/engine/architecture.md section 9
- Engine G2b (object drawing) done: `engine/view/drawlist.py` (`build_terrain_items`, `build_draw_list` ->
  `DrawItem`s sorted by the exe's pass order P0 shadows, P1 flat, P3 per cell structure/object, window
  x -3..W+2, y -3..Hv+6, two shadow levels 0x6226cc/0x6226d0, frame-0 shadow quirk, no owner remap), backend
  `SpriteCache` + numpy half/shadow blends, `DebugFlags` F1/F2/F3, `engine run|screenshot` options
  (`--no-shadows --no-light --no-smoothing --no-objects --debug`); pixel parity with `map render --relief` at
  shadows/light off; goldens `tests/golden.json["screenshots"]`; fog, burnt ground, lights not drawn.
  docs/engine/rendering.md
- Engine G2c (minimap) done: exe builds it at load, no .alm data (`FUN_004ab96c`): colour = 52x14
  `MiniMapData.bmp[13 - (v & 15)][v >> 4]` per cell, 8-cell border cut, scale `k` from the longer side
  (>144 -1, >80 0, >48 1, else 2; 80/144 maps = 128 px), camera rectangle white outline, fog and units drawn
  later (`FUN_004ac414`); picture never depends on passability/objects. Cheap variant: `allods2/minimap.py`,
  `engine/view/minimap.py`, `engine/ui/minimap.py` (click/drag = camera), `engine run` shows it top right,
  `python -m engine minimap MAP DEST.png`; no fog/units/final pass; goldens `["minimaps"]`. rendering.md §12
- Map entities done: section 5 players (76 B: `colour` = human.pal row, `money`, name, 16 relation words:
  1 war, 2 alliance, 0x10 vision; human = record 1 only), section 6 units (48 B: x/y, `server_id` -> data.bin
  `serverID` (humans group 6 when `flags & 0x10`, else monsters), `owner` = 1-based player, HP overrides, uid,
  squad; no facing: the ctor draws 0x40 + rand(128), heroes too; `behaviour` bit 8 = summoned, no loot/XP), section 8
  groups = item packs (carried via unit `group`, 19 ground sacks, `extra` = pile gold), section 9 = item
  properties (stat id, value), item codes -> data.bin weapons/shields/armour/special (`decode_item`); 4,212
  units resolve. Header `field_84` = multiplayer flag, `field_88` = difficulty (adverts), `field_0c/8c/90`
  never read; sections 7, 10-12: see "Triggers". Unit struct: Mover/Brain/orders/
  states/equipment slots in docs/engine/unit-struct.md. `Map.players/.units/.item_groups/.ground_groups`, `map render --layers all`; runtime unit
  struct (monster 0x208, human 0x254) docs/engine/unit-struct.md. map.md part 5
- Engine G3a (units) done: `World.players/units/items` from the map in record order (unit id `0x6000 + uid` CONFIRMED,
  piles `0x30000 + group`, one pile per cell), units never touch the static block layer (dynamic blocking = phase H),
  `Simulation` advances `world.tick` and units idle (animation clock = tick, tested at 30/60 fps); drawn per the exe
  (REA): filing cell `pos - 0x80 + size*0x80`, P3 structure < unit < object, flyers (`Z != 0`) shadow P4 unsheared + sprite P7
  16 px up, shadows, team colour `human.pal[owner colour]`, backpack piles P2; minimap unit dots (palette entry 164 of the
  owner's row, no fog yet); pixel parity with `map render --layers all` (E5 now follows the exe), goldens. Facing: file has none,
  exe `0x40 + rand(128)` (engine: hash of uid). Also answered: exe scrolls whole cells within the 8-cell border; cell effects =
  spell-area sprites (fire/earth wall, poison cloud); server drops units on blocked cells (9 in the install), HP-0 walkers stay
  corpses; ShadowY +-20000 has no gate. docs/engine/rendering.md §13, architecture.md §9
- Saves done (docs/formats/saves.md, `allods2/formats/saves.py`): `.a2c` = chunk file (magic `0x04507989`; identity / stats / settings / 12 equipped items / pack / hotkeys; checksum `h=2h+b`, xor stream cipher keyed by the chunk flags, byte RLE) read by `FUN_004ea6ab`, the network hero record; **single player keeps the party in server memory** across missions (`FUN_004ebd5f` end-of-mission: effects cleared, summons deleted, heroes HP / mana to max, gold and XP kept), an existing `.a2c` only supplies attributes / school / class to the creation message `0x48`; `game%d.sav` = `0x26677342`, version `0x0BAD0002`, word-RLE server stream (tick `+4` then block `+0` counters resume as saved) + client tail (description, `.reg` tree, mission list, ScenarioSave block = 1024 variables + shop table + locations, 9 hotkeys); `famehall.dat` decoded exactly; `engine/party.py place_party(record=)`. The creature / map serialisers inside the server stream are open. Scenario.dll state machine beyond the shop table still open.
- Triggers (map sections 7, 10-12) decoded, engine subset built (docs/engine/triggers.md, map.md part 6): section 7 = instants / checks (796-byte records:
  type, id, 10 args with kinds int/group(squad no.)/player/unit(uid, 10001+k = party hero k)/X/Y/const/item/building(uid)) + 184-byte triggers (3 check pairs with
  ops == != > < >= <=, 4 instants, once flag); compiled at map start (`FUN_00562745`, quirks: failed refs map to slot / instant 0), evaluated in the group pass
  (`tick & 15 == 6`, after the wake, before the handlers: checks `FUN_00574899`, triggers `FUN_00574ba1`, instants `FUN_00574f3f`); "killed" = state 0x10, no
  "attacked" event (HP / Brain mode 5); victory / defeat `FUN_004f856a` at the end of every 16-tick block (dying main hero, fail cause, complete counter; messages
  0xb4 / 0xb5); section 10 repop (unused), 11 = multiplayer inns / shops + signposts (`Pointer` runs an instant), 12 = music zones. `allods2/formats/scenario.py`,
  `tools/validate_scenario.py`, `engine/sim/triggers.py` (`triggers.enable(world, map)`, `Simulation(triggers=True)`; unimplemented kinds counted), tests
  `test_scenario.py`, `test_engine_triggers*.py`. Party at the drop cell (`FUN_004f2c83`, `engine/party.py`, `triggers.enable(.., assets=)`, `--party`); roster of later maps = server memory / saves (saves.md); every instant and group sub-command of the exe is built (items, teleport, defence, formation, attack / defend / patrol / follow unit orders: ai.md §14.2); the scripted casts (21, 24) and traps (25, plus the section 9 cell records of maps 76, 93-96) are built (`engine/sim/traps.py`: Teleport records teleport at the step end, spell records make a hidden caster in the transient list `server+0x2c` cast at whoever enters, every time; effects.md §10; Teleport now ends with the stand `FUN_0056dba1`), the spell-duration instants (29, 30) and check 25 are built (K7: effects.md §6.5); placement search `FUN_00510089` + exact free-cell test (`engine/sim/place.py`: clamp to [8, size-9], footprint of live + static layer, stamps only; triggers.md §10), ready message = first server step's drain (§9.1), by-name hero loop (§9.5), end-of-mission flow + Scenario.dll start values (all 0, Var 0x300 = 10; `engine/sim/campaign.py`, §11, `test_engine_place.py`, `test_engine_campaign.py`); open: hero recruit `FUN_004f312a`, roster carry-over, campaign variables 0x301-0x30d.
- Engine G3b (interface, cursor, selection) done: `engine/ui/layout.py` (three modes, one table citing exe routines),
  original cursors (`choose_cursor`: 8 arrows by the screen-border rule, select, pickup), rectangle picking (exe: per-object
  `Selection` rect, last registered first, 3x3 box; drag > screenW*10/640 px, overlap > 10 px^2), `SelectUnits` command +
  selection system + `Simulation.log`/`replay`, HP bar with `Ball.bmp` caps, info panel, scroll one cell per tick, camera
  8-cell border, minimap flush at (W-160, 0); `run` always shows the interface, `screenshot --interface [--select]`; golden
  `["interface"]`. Selection is a per-object flag in the exe (engine: per-player tuple, DECISION); right click clears (DECISION).
  docs/engine/ui-layout.md, rendering.md §14, architecture.md §5, 8
- Unit stats (F1) done: the only source is data.bin groups 5 (monsters, `serverID` p55) and 6 (humans, p24);
  `allods2/formats/unitstats.py` names all params (464 types, every map unit resolves), `AssetCache.unit_stats()`,
  `Unit.stats`, `data export units`, `world-info --units`; REA: p33 = dyingTime, p34-36 AI thresholds, p37 XP
  (killed `+0x1c`×0.5), p38-44 loot (chance, gold base+spread, item value range, flags), humans-only serverID
  reduction; golden `["units"]`. docs/data/units.md
- Items (F2) done (equip / use / drop / pickup: Gear K4 below): `allods2/formats/itemdefs.py` (162 definitions, `AssetCache.items()`, `data export items`, `tools/validate_items.py`)
  and `itemgen.py` (generator, shop stock, loot). CONFIRMED: exe rounding `ftol(x+0.5)` of param x material x quality, price
  = base + effects, masks regenerate the 395 named class items, itemname.pkt cross-checks all prices, equipment strings parsed.
  docs/data/items.md
- Spells (F2b) done: `allods2/formats/spelldefs.py` (29 spells, `AssetCache.spells()`, `data export spells`, `tools/validate_spells.py`);
  REA: record n at `0x68f5cc`+n*0x20, sphere 1-5 fire..astral, level = skill-30+Mind, scaling m=L/30+1, damage `0x516f6f`, behaviour = per-number
  switch `FUN_00519db8` + data-driven carriers (missile/point/area), sound 500+projectile id; prototype spell = Fire Arrow. docs/data/spells.md
- Progression (F3) done: no single level, six skill words (0 general, 1-5 schools) each with its own XP pool; curve `thr[n] = trunc(1.1^n)` capped at
  skill 100; XP per melee hit, per damaging spell and a kill credit when the victim dies (scaled by Mind, repeat-kill and off-school reductions); a skill-up changes to-hit/min damage,
  spell level, max HP/mana via the recompute (`derived_vitals`, used by `World` for all 605 campaign humans; never the template HP/mana); 6 hero templates;
  `formats/progression.py`, `AssetCache.progression()`, `Unit.skills/xp`, golden `["progression"]`. Data close-out: all tables and map
  references resolve (`tests/test_data_integration.py`, explicit exclusions). docs/data/progression.md, docs/data/overview.md (tables + handoff to movement and combat)
- Simulation (H1) done: tick CONFIRMED (fixed step, 8-32 ticks/s by speed 0..8) and the update order inside `server.step` (commands first,
  then carriers, area effects, creatures in creation order `FUN_0052b459`); unit states/orders documented, movement implemented
  (`engine/sim/movement.py`, `Unit.mover`): step length `FUN_00559195` (speed x8 / mean cost, +-height, clamp 1..63, diagonal x0.707),
  cell-to-cell steps in 1/256, occupied cell changes when the offset crosses the boundary (~mid step), no gap between cells, turning (<=45 deg snaps,
  else `rate`/tick, no movement while turning), human turn rate = speed stat (recompute copies it), runtime human speed = integer Reaction rule
  (templates' p6 rounded by hand), walk animation by odometer (`frame_at(odometer=)`), `FollowPath` debug order,
  `python -m engine run MAP --debug-move UID X,Y ...`, replay hash test. docs/engine/simulation.md
- Pathfinding (H2) done: not A*: a label-correcting wave fill (`FUN_0054d76e`, levels limited to `dist + min(5, dist/4)`, unbounded for the
  human player's units to a free cell; costs 2/3 or terrain cost for walkers, no corner rule, strict `<`) and a backward walk with the exe's
  tie rule (`<=` orthogonal, `<` diagonal), unreachable -> cheapest labelled cell of the first ring around the target; two layers: a static
  plan (re-planned on target change or after 16 hops) and 3-4 cell dynamic hops over the live layer (every 32 ticks or when empty);
  `engine/sim/pathfinding.py` (pure; optional bit-identical C port `engine/native/planner.c` via ctypes, `ALLODS2_NATIVE`), `MoveTo` order, overlay `--debug paths` (Shift+F4), `tools/bench_pathfinding.py`
  (worst 256x256: Python 132 ms, native 6.9 ms; was 444), goldens `["paths"]`. Blocker wait (no swap: the first human size-1 unit turns to a walking friend and stops until re-ordered, 7.4) modelled; follow-target decoded (7.4: `follow_fallback`, `follow_distance`; not wired, no follow order yet). docs/engine/simulation.md §7
- Orders (H3) done: click to move, REA-checked (docs/engine/click-to-move-research.md): left release dispatches on the cursor chosen at release
  (move; attack over ground = move), right release = cancel pending mode / deselect, right drag scrolls, minimap left click = move; no Stop
  message (T = cmd 0x18, order 0xc), no click marker, "No way" text; every command makes a new group, formation Off/Auto/On = rigid translation
  around the truncated centroid (no free-cell search), group pass at `tick & 15 == 6` ends arrivals and restarts parked and failed units (a failure leaves brain+0x50 at 0); commands
  `MoveUnits`/`Stop`/`SetFormation`, `engine/sim/orders.py`, `engine/ui/orders.py`; 46-map integration (`ALLODS2_ALL_MAPS=1`), 30/60/144 fps
  replay hash, goldens `["orders"]`, `tools/bench_orders.py`. docs/engine/simulation.md §8-9, spec docs/superpowers/specs/2026-10-18-click-to-move-design.md
- Melee attack (I1) done, REA-checked ([combat](docs/engine/combat.md), design docs/superpowers/specs/2026-10-18-combat-design.md): `AttackUnit` (cmd `0x19`)
  sets order 3 + mode 0 and **the unit starts at the next `tick & 15 == 6`** (group-pass executor), melee ground units and ghosts cannot attack flyers;
  Brain mode 5: in range = facing equal to the octant and reach gap <= range, else the follow driver `FUN_0055574d` (`movement.follow_drive`); swing:
  hit `windup` ticks after the start, then recovery (+ hero delay + `rand(0..3)`) + 2 ticks; `take_hit` `FUN_00516f6f` exact (`T + rand(0..200) - 100 > D`
  or roll >= 90, sure-hit flag, absorption, percent resistance by weapon type, elemental / second parts), monster stats = template + equipped weapon
  (byte merge), human stats = recompute + equipment (`engine/sim/combatstats.py`); the RNG is the MSVC CRT LCG owned by the world (`engine/rng.py`, seed per
  game, [simulation §10](docs/engine/simulation.md#10-rng)); damage numbers are the original's default-on "Flying damage" option (Ctrl+L), `--debug combat` logs
  blows, `--seed`, `--debug-attack`. Not modelled: AI reaction, scans, spells, structures, Bless / Curse sources.
- Death, XP, loot, regeneration (I2) done, REA-checked ([combat §12-13](docs/engine/combat.md), design docs/superpowers/specs/2026-10-18-death-design.md): HP <= 0 starts the dying
  countdown at the unit's own creature tick (`dying_time - 1`, orders cleared, defence halved, selection dropped); the unit keeps blocking until state `0x10` at `T0 + D`, **but a ground unit
  is removed only at HP <= -10** (bodies at HP -9..0 wait for hits or the 64-tick HP drain, HP 0 forever), flyers / ghosts get HP -1000; attackers keep swinging at the body and stop at the
  first executor pass (`tick & 15 == 6`) after the removal; corpses (`World.corpses`) decay 1 HP / 32 ticks (bones at -11 / -21 / -41, gone at -601), no fade; loot at removal (gold `base +
  rnd(spread)` with chance `p/101`, one generated item, carried items, a pile on the unit's cell); XP per hit and `0.5 * victim.xp` kill credit to the last hitter only, level-ups
  recompute max HP / mana (`engine/sim/{death,vitals,xp}.py`); regeneration at `tick & 15 == 12` (HP per unit every 64 ticks, mana every 16, x3 after 80 ticks without a step; humans
  100 / 50); HP/mana bars for hovered units, mana bar, info panel mana / level / XP; `--debug combat` logs removal, loot and level-ups.
- Monster AI (I3) done, REA-checked ([ai](docs/engine/ai.md)): there is **no per-monster aggro radius or leash**; the squads (map `squad` per owner) of every computer player run
  group order `0x12` (`FUN_005728fa`) at `tick & 15 == 6` (every 16 ticks, all groups in the same tick): sight flood `FUN_00552c28` (scan range in cells, `light = (scan << 7) + 64`
  minus 128/181 per step minus height difference, rings 1..19) of every member plus the attacker cell a hit reveals for 21 passes -> hostile living pool (relation bit 1), pruned
  to the squad radius (reach, >= 20, +3..5 after the first pass) round the centroid -> each member takes the lowest `FUN_005711ea` score (cells * 256 + facing change, class table) ->
  attack (mode 5), else back to its own start cell (anchor), where it looks around (mode `0xb`, `rand` per tick); a hit stores the cell 10 beyond the victim on the ray from the
  attacker (run-away when it has no target), wimpy / withdraw HP thresholds flee 3 cells; `engine/sim/ai/`, AI commands are `MoveUnits/AttackUnit/Stop(ai=True)` in the log,
  `Simulation(world, ai=True)`, `engine run` (`--no-ai`, Shift+F5 / `--debug ai` overlay), `tests/test_engine_ai.py`. Casters and special attacks: see "AI casting" below.
  Group orders built (ai.md §14.1, `tests/test_engine_group_orders.py`): guard 1 / hold 2 / swarm 5 / wander `0x11` / still `0x13` / empty `0xff` handlers via `ai.run_group`, commands `Guard` (G) / `StandStill` (L) / `Swarm`, scripted `ai.set_group_order`; wander members walk to their own old `brain+0xa`, not the picked cell (exe quirk); a fresh group record starts at order 0, not `0xff`.
  Summon / Control Spirit build units (`spells.summon_release` / `raise_release`: a private guard / stand-ground command group, master key `+0x148`, the cap job `minion_job`; group order bytes, not Brain modes). Spell casts (I4a, combat.md §14, spells.md §9c, spec/plan 2026-10-19): `CastSpell` (cmd 0x1e) -> order 0xd -> group pass -> Brain mode 8 (melee approach test) -> brain order 2, states 0xd on the swing's phase machine
  (`spells.cast_tick`; mana spent at phase 0 for a mage's learned spell, windup `+0x134`, recovery + complication), missile `Carrier` (flight `trunc(dist)/speed`, delivered `max(N,1)` ticks after the release, carriers run BEFORE the
  creature pass), damage through `take_hit_detail`; a mage's staff `castSpell` is a branch of the melee swing (free, level = count). `tests/test_engine_spells_*.py`, `tests/spell_helpers.py`. Cell casts and AI casts: "AI casting" below; effects: phase K.
  Cast view/UI (I4b, combat.md §14): `Carrier.start/flight/aim`, `drawlist._carriers` (pass 6, missile + 6-point trail drawn after the body, `.16a` alpha via `sprites.blend_alpha`, `AssetCache.projectile_set`),
  cast animation = the attack action at the cast start, `C` arms the cast mode, click on a unit sends `CastSpell`; no command bar button yet (J1). Spell panel data side (spells.md 9e, `engine/ui/spellbook.py`, `tests/test_engine_spellbook.py`): 24 slots (table `0x5f8124`), the enable mask `view+0x148` = the book's slots of the selection with **no mana test**, F4-F12 hotkey table (Ctrl+F binds the selected slot, F arms the cast cursor with the book closed; debug overlays now Shift+F4/F5), tooltip fields per slot (Speed = Haste, Sight = Light/Darkness, wrapper level wraps as a byte), Stop/any order never interrupts a cast. `tests/test_engine_spell_draw.py`, `test_engine_alpha.py`, `test_engine_spell_ui.py`.
  Close-out (I4c, combat.md §14.1): goldens `["casts"]` (`tests/spell_scenarios.py`, `test_engine_spells_golden.py`), real-map fight on map 73 with the 30 / 60 fps replay (`test_engine_spells_maps.py`), `tools/bench_fight.py`, handoff §15.
- AI casting (K1) done, REA-checked ([ai §12](docs/engine/ai.md), spells.md §9d): `FUN_0056acc8` rolls the monster's three slots (one `rand15` per used slot vs `p * 0x147`, last pass wins,
  Teleport only beyond 2 cells) -> `FUN_0056a981` (target by spell number: enemy / its cell / self / cell ahead / free cell near it); a **computer-owned** mage (`+0x4c & 4`) picks a random affordable
  offensive spell 1..28 (`FUN_0057a769`; mind >= 60: 30 % rethink -> mode 5), idle mages heal themselves / the first wounded ally, Shield themselves, buff a random friend at full mana (`FUN_0056c592`,
  `FUN_0057a999`, Curse quirk); AI casts set `brain+0x60` so mode 8 / 9 repeat the cast until the next pass; monsters get mana, skills (`spell_power` / `skill*`), book (slots / mask) and the mage flag
  (staffs replace their melee hit). Cell cast `CastSpell(cell=)` = cmd `0x1f` -> order `0xe` -> mode 9 -> state `0xe`. Releases built: damage, Heal (revive), Drain Life, and (K2) every
  effect spell; only the Prismatic Spray chain stays a counted no-op (`World.unbuilt_casts`). Not built: the Teleport flee.
  `tests/test_engine_ai_casting.py`, `test_engine_ai_casting_maps.py` (map 73).
- Player-owned casters (K3) done, REA-checked ([ai §12.8](docs/engine/ai.md), spells.md 9c.5, 9e): message `0x46` is the party-options message (sub 1 retreat, 2 formation, **3 the party-AI byte** Retreat (R / bar button 8, cmd `0x14`, order `0x16`, flee 3 cells from hostiles within 10 every pass) and the retreat mode (Ctrl+W, `0x46`/1, wimpy = maxHP x 10/30 %) CONFIRMED and built ([simulation 8.3a](docs/engine/simulation.md)).
  `0x4f6945`, **4 Ctrl+A** `0x4f694d`); the byte = registry `AutoCasting` (options dialog / hotkey): `8` heal, `0x10` Bless + Haste, `0x20` protections + Invisibility, `1/2/4` friend kinds (own / allied /
  neutral); `Player.autocast` (default 0), `SetAutoCast`; the scan `FUN_0056bc7b` = `ai.human_scan` (idle human mage, and after the melee mode 5 of a mage with range < 2: the mode-0 quirk is applied);
  Ctrl+A toggles `brain+0x78` = `Unit.auto_spell` (`SetAutoSpell`, `OrderInput.auto_cast`), read by the range `combat.attack_range` (`FUN_0056ac5b`) and `ai.selected_cast` (`FUN_0056b059`);
  scroll casts `CastScroll` (`0x25` / `0x26`, `Unit.pack` scrolls, `spells.scroll_cast`, `spellbook.scroll_slot_mask`). Answered: tooltip filter = drawn mage body (`mage` / `mage_st`, not applied),
  the `0x411` reset is sent once at the game view's build, the F-key table is saved in the savegame (block 5). `tests/test_engine_human_autocast*.py`, `test_engine_scrolls.py`.
- Spell effects (K2) done, REA-checked ([effects](docs/engine/effects.md)): effect objects (class `0x5d1178`: id = spell number, kind = stat, flags, value, u16 ticks; >= 0x2581 never counts down)
  in the list `unit+0x20`, mask `+0x144` (`1 << id`; the stat-class bits are the client mask `+0x150`); apply `FUN_0051ce12` merges the same id (max value, max time, never stacks; Bless /
  Curse cancel each other), the effect pass runs first in every creature tick (`FUN_0051cc9f`: Poison every 8 ticks, expiry undoes), stat switch `FUN_0051d436` (monsters: direct
  speed / absorption, **protections never reach a monster**; humans: bonus words through the recompute); Light lowers monsters' scan, Darkness humans'; Stone Curse = brain order 4
  (frozen); point / area (diamond, wall tables, lifetime pulses on the ground occupant, Fire Ball once over the square / size^2) / field carriers; cell record slots (cost `<< 2` per
  slot, Wall of Earth blocks, fire burns poison, Light and Darkness annihilate); area hits declare war only after 11 hits / half HP. `engine/sim/effects.py`, `Unit.effects/effect_mask/fx`,
  `World.cell_fx`; spell damage XP now goes to the mage's sphere. Tests `test_engine_effects*.py`. Open: Prismatic Spray chain, structures as targets, effect drawing.
- Gear (K4) done, REA-checked ([items §15](docs/data/items.md#15-equip-use-pack-and-ground-items-confirmed-engine-sim-gearpy)): packs, piles and slots hold **item objects with their effect lists** (`saves.Item` = code + wire modifiers; piles `Item.mods`,
  `Unit.carried_mods`, section 9 records at load), so a dropped `{castSpell=..}` staff keeps its spell; human put `FUN_00512573` (**the server does test fighter / mage** `suitable_for`; refused items return to the pack), weapon / shield / armour
  equip (`FUN_005290cc` / `FUN_0052846b` / `FUN_00527a13`: two-handed pushes the shield, armour slot = class `Slot`, humans only), use `FUN_00523613` (potions), pack insert / take (stack rule `FUN_005234c2`), load `+0x90`/`+0x92` (speed
  penalty `load / (Body*10+1)`), messages `0x22` / `0x23` / `0x21` (`MoveItem`, `DropGold`, `PickUp`; pickup = order 2, Brain mode 7, state 2); `engine/sim/gear.py`, `combatstats.human_stats(gear=)` (attributes, skills, HP / mana / speed / scan
  modifiers), `party.apply_record` equips a record hero, every human template gives identical stats through a loadout (tested). Summon cap: the `unit+4` free-id bitmap (`engine/netids.py`: piles, heroes, minions) and the `CMap` order
  (`spells.cmap_order`) make the per-master draw order exact ([combat §12.6](docs/engine/combat.md)). `tests/test_engine_gear*.py`, `test_engine_netids.py`, `test_engine_minions.py`.
- Engine J1 (minimal UI) done ([ui-layout §11](docs/engine/ui-layout.md#11-j1-minimal-ui)): `engine/ui/{widgets,info,bar,modal,messages,game}.py` (pure: the widget table as data, info-panel readers, command-bar cells, dialogs, `ModalStack`, `GameUi`) and `backend_pygame/{panels,interface,text,window}.py`: two-mode info panel (picture = paper doll via `Canvas.draw_256` / `infowindow` bmp, text = the exe's font2 rows by exact measure `draw_text_exact`, TAB), command bar with disabled / pressed overlays, ESC / disk button = menu -> End Quest -> Exit (debug ESC-quit gone), Pause key notice, **any dialog freezes the sim (`acc = 0`, no burst)**, story windows from script messages, mission complete / failed dialogs, gold / item pickup and level-up lines, "No way" only with `--trace`, `--hero-name`; debug overlays stay off by default. Goldens `["ui"]` + `["interface"]` (`tools/update_golden.py --only interface,ui`), `tests/test_engine_ui_*.py`. DECISIONs: hostile units show all rows, phase-K menu entries disabled, Retreat sends nothing; bar-cell tooltips (hover timer 500 ms, ui-layout 11.6b) added afterwards. Spell book window built afterwards ([ui-layout 11.12](docs/engine/ui-layout.md)): opens by the info button / B / Q / Space / `C` (F-keys arm without opening), leaving the cast mode closes it, 24 always-listed slots (2x12, SpellBack over disabled, veil on the selected, `F<n>` / `A` labels), double click = instant self-cast of 10 slots, right click deselects; `engine/ui/book.py`, goldens `book_open*`. Backpack window built after that ([ui-layout 11.13](docs/engine/ui-layout.md)): the pack strip of the single selected hero (I / backquote / Space / pack button; 5 / 7 / 9 cells, arrows scroll one item), drag = carried item (replaces the pointer), release on the info panel / double click equips, uses or arms a scroll cast (`CastScroll`), release in the map drops at the hero's feet, the equipment slots are the paper doll's hit mask (`paperdoll.hit_mask`); `engine/ui/pack.py`, goldens `pack_open*`.
- Engine J2 (fog of war) done, REA-checked ([vision](docs/engine/vision.md)): the player's fog is **client state** (tile bits `0x4000` seen / `0x8000` explored, `FUN_0040c129` refresh every 32 ticks, a moving own unit reveals at once `FUN_00460ae0`), only the viewer's own units and structures reveal (`FUN_0041e860`, bit 8 of the per-player word; allied vision unused), the client sight mask `FUN_00403ca0` (41x41, sight/2 + 64, soft height cost, 7-cell border) is not the server flood; hidden = **not drawn** (units, shadows, piles, never-seen structures; explored structures frozen), so pick rects are never registered and a foe in fog cannot be hovered, selected or clicked (combat.md 15 corrected; the server has no sight test), projectiles are only darkened by the overlay; minimap blocks (unseen = panel picture, explored = 50 % blend) and dots need a seen cell; only cheat `#show map` toggles fog; saves keep bit `0x8000`. `allods2/vision.py` (mask, tile helpers), `engine/sim/vision.py` (`enable`, `vision_system`, `Simulation(vision=True)`), `engine/view/fog.py`, overlay `draw_fog_pass` (16-bit 565), `engine run` fog on (`--no-fog`), `screenshot --fog`; goldens `["fog"]`, `tests/test_engine_vision*.py`. Not built: save/load of the fog, `#show map` key, structure dots on the minimap, frozen-animation exactness of explored structures, corpse rule (DECISION).
- Hero look done, REA-checked (animation.md 1.3, rendering.md 2): party heroes (`xp.is_hero`) are drawn from `heroes` (mage) / `heroes_l` (fighter, no slot-8 armour) / the armour material's folder (`material.reg`) + the weapon's `heropicture.txt` name (`_` with a shield; dying = `unarmed` / `mage_st`), re-picked from the equipment every frame (`FUN_0046a215`), so the orange cloak shows; map humans keep their units.reg set (`engine/herolook.py`). Two units can share a cell in the exe too (no test at step start / border, simulation 11.4b); the view keeps one slot per cell and layer, so the pair looks like one unit (CONFIRMED `FUN_0040403b` / `FUN_00463093`).
- Sound and music (K10) done ([sound](docs/formats/sound.md), `allods2/formats/sound.py` + `soundtable.py`, `python -m allods2 sound export-all DEST` / `data export sounds`): every one of the 1,599 audio files is a standard RIFF `.wav` (560 PCM 16-bit, 1,039 MS ADPCM mono, 22,050 Hz, 3 at 44,100; music = 21 stereo PCM files, **no CD audio, no custom format**), all decode with no leftover byte (ADPCM: 512-byte blocks, 1012 frames, `fact` = true length, 9 empty files); the exe plays them through DirectSound (16 voices per sound, positional volume / pan computed by the game, ADPCM decoded by the Windows ACM; `FUN_0045ade7`, `0x45a3f4`, `0x45aa2f`); ids = `sfx.reg` `Sfx<n>` (200 keys, 8 point to missing files), unit sound sets = `units.reg` `Sound` (5 ids), hero voices = `sfx/characters/<bank>/` with variants probed 1..4, speech names `talk\%04d%c%sp%02d`, music = playlists per screen with map-zone themes (`0x4754e9`, `0x5f1a08`), `Music.ini` is editor-only; `tests/test_sound.py`, golden `["sound"]`. Engine side: K11 below.
- Status: E, F, G3b, G3c (fonts), H (H1-H3), I (I1-I4), J1, J2, J3 done (J3: win / lose on map 32, triggers.md §12). J4 (the play-through of map 32) waits for the user's session. Phase K started: AI casting (K1), spell effects (K2), player-owned casters (K3), gear (K4), the map coverage report (K0, [docs/coverage.md](docs/coverage.md)) and the click pickup (K5, [docs/engine/items.md](docs/engine/items.md): the pickup cursor issues `PickUp` at the click cell, the script's item instants share the hero's pack, the info panel lists carried quest items; maps 21 / 40 / 63 / 72 / 80 / 91 / 102 debug-run; **41 of 46 maps without a blocker**, 12 playable now, 5 blocked) done. K5b: the `P` key (`PickAll`, order 0x1a, Brain mode 12), the doll item leaving doll and hero sprite while carried, vertical text flags; the lore / rotationSpeed effects and the quest system answered (no-ops / multiplayer only). K6 done ([structures](docs/engine/structures.md): `UseStructure` cmd 0x24, order 0xf, Brain mode 15, state 0xf toggles switch / altar HP 0 <-> 1 which check 21 reads; the exe toggles the first structure within Chebyshev 2 of `(x-1, y-1)`, not the clicked one (`World.use_clicked` debug); no passability change; maps 96 and 103 solved by scripted uses, `tests/test_engine_structures.py`; **43 of 46 maps without a blocker**, 15 playable now, 3 blocked). K7 done ([effects §6.5](docs/engine/effects.md): check 25 `FUN_005777d3` is a live read of the cell record's slot, instant 29 `FUN_00578696` sets a carrier's unsigned lifetime, instant 30 `FUN_0057871f` an effect's ticks; maps 93-95 solved by scripted casts, `tests/test_engine_tilefx.py`; **46 of 46 maps without a blocker**, 20 playable now, 0 blocked). K8 done ([structures §0](docs/engine/structures.md): wells = lookup B, 3 charges, Potion Big Healing / Mana through `gear.use_item`; signposts run instant `+0x6c` (> 0) at every use via `World.pointers`; graves, nothing; the only server message of a use is `0x82`, **no sound or text exists**; a switch use also runs lookup B; `tests/test_engine_structures_k8.py`, 33 maps' structures used; **46 of 46 maps without a blocker, 46 playable now, no gameplay gaps**). K9 done ([rendering: Arrows and shots, Status effects](docs/engine/rendering.md#arrows-and-shots-k9); REA `FUN_00466e18`, `FUN_0046c1d0`, `FUN_0046707e`, `FUN_004608de`, `FUN_0046cb7b`: the shooters' arrows / bolts / stones (ids 1-6) are client `World.arrows`, stepped after the creature pass (`(T - p) / steps_left`, facing `direction16`, start = ShootOffset point, altitude 0, no shadow, **nothing drawn on impact**), the Sonic lens (id 7) is a `"lens"` draw item, Teleport / Drain Life are `World.flashes`, the spell flights of unit-target casts are client `Arrow`s made at the cast action's ShootDelay tick (`spell=True`, ShootOffset start, altitude 0, age 0, own trail; the server carrier is independent); **status effects need no drawing**: the exe makes the buff sprites with lifetime 0 and removes them in the same step, only Invisibility / Stone Curse change a unit, no panel icon; all client state, world-dump hashes unchanged, `tests/test_engine_arrows*.py`, golden `["arrows"]`; **46 of 46 maps without a blocker, 46 playable now**). K11 done ([audio](docs/engine/audio.md); `engine/audio/` pure: `SoundEvent`s in `World.sound_events` (not hashed; sim emits swing / cast / spell object / Blizzard / hurt / death / skill-up), `Director` (fog gating, hurt throttle, hero voice cooldowns 3000 / 2000 ms shared stamp, order voices from the command log, own audio RNG), `VoiceMixer` (16 voices, 16 copies per sound, strict priority steal), positional mix `0x41b1f8`, `MusicState` (mission playlist, zone themes every 16 ticks, victory stop), `Ambience` (river / fire-wall loops, tree one-shots), settings file outside the repo; `backend_pygame/audio.py` = pygame mixer + `MusicPlayer`; flags `--mute --sfx-volume --music-volume --speech-volume --no-audio`; `python -m engine replay SESSION --audio-log out/audio_log.csv`; K11 research corrected sound.md: no footsteps, no impact / pick-up / gold sounds, `0xdc` is a priority, hero voices use the speech bus; **nothing listened to yet: VERIFY BY EAR list in audio.md**). K12 done (docs/coverage.md "Re-plan"; `engine/objective.py`, `python -m engine objective`, `tests/test_engine_objective.py`: a headless oracle works back from the triggers that run instant 4 and makes their conditions true by world edits (kill, bring the hero, give the item, set a switch) through the real trigger pass: **45 of 46 maps reach Mission Complete**, map 77 needs a fight (its escort dies to the leader's squad); it teleports, so it proves the script side only, not walkability or the puzzles of 93-96 / 103; the coverage report has the three levels and a `Win by script` column; 46 of 46 without a blocker, no in-mission gap known). The inventory / hero windows are town-mode only (the mission Heads panel is a bare picture), the Prismatic Spray chain is built (effects §11). Remaining backlog by evidence: campaign (the party of every map is fresh; maps 70 / 80 read campaign variables no map writes), shell, town, save / load, cutscenes (docs/prototype.md). Next: **K13 campaign spine (headless)**: REA of the recruit `FUN_004f312a`, `FUN_004ebd5f` and the Scenario.dll TalkTo writers of Var 0x309 / 0x30a; `engine/campaign.py` (new game, carry-over, recruits, `start_mission` from the carried roster); `python -m engine campaign` chains the missions with the objective run; then K14 the campaign in one window (shell, play-test) and K15 the town spec (prototype.md "Next steps"). The play-through of map 32, the playability check of the maps and the VERIFY BY EAR list wait for the user's session; `save` needs the user's format decision (own format or game%d.sav). Also (docs/open-questions.md): town-scene animations, text conventions.
