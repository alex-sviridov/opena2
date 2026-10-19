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
- `engine/` the game (world, sim, view, ui, `backend_pygame`; only the backend imports
  pygame-ce), built on the core; `allods2/assets.py` asset cache; docs/engine/
- `docs/{formats,mechanics,data,...}/<name>.md` specs; each folder's README.md is its index
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
  never read; section 11 keyed by structure uid, section 12 = circle zones. Unit struct: Mover/Brain/orders/
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
- Not started: saves, Scenario.dll, triggers (sections 7, 10-12).
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
- Items (F2) done: `allods2/formats/itemdefs.py` (162 definitions, `AssetCache.items()`, `data export items`, `tools/validate_items.py`)
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
  `engine/sim/pathfinding.py` (pure), `MoveTo` order, overlay `--debug paths` (F4), `tools/bench_pathfinding.py`
  (168 ms worst, 256x256; was 444), goldens `["paths"]`. Blocker wait (no swap: the first human size-1 unit turns to a walking friend and stops until re-ordered, 7.4) modelled; follow-target decoded (7.4: `follow_fallback`, `follow_distance`; not wired, no follow order yet). docs/engine/simulation.md §7
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
  attacker (run-away when it has no target), wimpy / withdraw HP thresholds flee 3 cells; `engine/sim/ai.py`, AI commands are `MoveUnits/AttackUnit/Stop(ai=True)` in the log,
  `Simulation(world, ai=True)`, `engine run` (`--no-ai`, F5 / `--debug ai` overlay), `tests/test_engine_ai.py`. Casters, special attacks, the second pool list: phase K list in ai.md.
- Status: E, F, G3b, G3c (fonts), H (H1-H3), I1, I2, I3 done. Next: I4 (spells and special attacks: `FUN_0056a981`, caster scan `FUN_0056bc7b` and the phase K list of docs/engine/ai.md, then
  structures as targets; the human stand-ground pass (group order 3) and the other group orders are in ai.md §14, order 3 implemented behind the AI switch). Also (docs/open-questions.md): town-scene animations, text conventions.
