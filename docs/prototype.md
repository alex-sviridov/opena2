# Prototype (phase J4)

Status: **tooling ready, play-through pending** (this page is completed after the map has been played; sections marked *TODO after play*).
Spec: [2026-11-05-prototype-j4-design](superpowers/specs/2026-11-05-prototype-j4-design.md).

## Run it

```sh
.venv/bin/python -m engine play 32
```

Map 32 (`scenario/32.alm`, 80 x 80) starts as the game starts it: the map script runs, the main hero stands at the drop
cell, monsters think, fog of war is on, difficulty Medium, 640x480 (`--size 800x600` / `1024x768`, `--speed 0..8`,
`--difficulty 1|2|3`, `--seed N`). A story window opens first (Enter / click closes it); the simulation is frozen while
any dialog is open.

Ends: win = the swordsman (`CH_SwordCarrier`) is killed; loss = he reaches the point (71, 13) after the brigands are
down to two, or the hero dies ([triggers §12](engine/triggers.md#12-j3-win-and-lose-on-map-32)). The end dialog's button
leaves the game.

**Session files** are written to `~/.allods2/sessions/32-<date>-<time>/` (`--out DIR`, `ALLODS2_SESSIONS=root`):

| File | Content |
|---|---|
| `session.json` | map, seed, difficulty, engine git id, your commands by tick (rewritten every ~10 s and at exit) |
| `final.json` | why it ended (`quit`, `victory`, `defeat`, `crash`, `interrupted`), final tick, result, world hash |
| `engine.log` | `engine.*` log (`not implemented: ...` reports) and the traceback after a crash |

```sh
.venv/bin/python -m engine replay ~/.allods2/sessions/32-... --verify   # headless; exit 1 on another hash
```

When reporting a problem send the session folder and say roughly what you did at which game time.

## Controls

Mouse: left click selects, drag = rubber band (Shift toggles), left click on ground / enemy orders move / attack with the
selection, right click cancels a pending mode or deselects, right drag or the screen edge scrolls, the minimap orders
moves (own units selected) or moves the camera. Keys: `M` / `A` / `D` / `S` arm the move / attack / defend / swarm modes, `T`
stand ground, `R` retreat, `G` guard, `L` stand still, `C` arms a cast, `Ctrl+F` formation, `Ctrl+W` retreat mode, `B` / `Q`
spell book (`F4`-`F12` arm a spell, `Ctrl+F<n>` binds), `I` / backquote backpack (drag items: equip, use, drop), `Space` both,
`Ctrl+A` auto-cast, `Tab` info panel picture / text, `Esc` menu, `Pause`. `Enter` opens the chat line (type, `Enter` sends, `Esc`
cancels); in the pause / failed / complete dialogs `Enter` acts as in the original. `Space` with a dead hero does nothing (as in single player). Options: `Ctrl+H` health bars, `Ctrl+L`
damage numbers, `Ctrl+O` smoothing. Developer overlays: `F1`-`F3`, `Shift+F4` / `Shift+F5`.

## What works

- Everything in [engine/README.md](engine/README.md) up to J3: world and map objects, terrain / lighting / fog drawing,
  units and animation, movement and the original path finder, melee combat with the exact hit formula, death / loot / XP /
  regeneration, monster AI, spells (damage, effects, summons) for monsters and heroes, gear, the map script (triggers) with
  win and lose, the interface (info panel, command bar, spell book, backpack, dialogs, story windows).
- Determinism: a session is `seed + commands`; `replay --verify` reproduces the final world hash (tested in
  `tests/test_engine_session.py`).
- Speed (reference machine, software drawing): a still frame costs about 16 ms (was 100 ms), a frame while scrolling about 28 ms.
  The fog pass is the cause: it is built once per camera / fog state as layers of blend rows (`lighting.fog_layers`, quads memoised
  by shape) and applied on the frame words with byte tables (`apply_fog_layers_rgb`); both are bit-identical to the reference
  `draw_fog` plus the 16-bit round trip (`tests/test_lighting.py`).  Later numbers and the `fog_plan` form: [architecture](engine/architecture.md#open-questions).

## Bugs found and fixed in the bug pass

*TODO after play* (one line each: report, test, cause, spec corrected or not).

- First smoke run: a replay without the fog gave another hash (the world dump holds the fog bits): the replay now runs with fog.
- First smoke run: fog drawing took 75 % of the frame time: layered cache and byte-table application, see Speed.

## Comparison with the original

*TODO after play.* Each row: fixed, VERIFY IN GAME or known gap. Seed list to check during the play-through (timing,
damage feel, AI, UI): the consolidated VERIFY IN GAME items of [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i),
[combat](engine/combat.md), [ai §13](engine/ai.md), [vision](engine/vision.md), the walk speed and swing timing, the
height of the damage numbers, the hit-reaction flee, the story window layout.

Same as the original, not bugs: two enemies (or any two units) can share one cell and are drawn as one unit ([simulation §11.4b](engine/simulation.md)); a hero
is drawn from its equipment (orange cloak, [animation §1.3](formats/animation.md)).

## Known differences and gaps

- No start menu or new-game screen: the shell exits after the end dialog ([triggers §12](engine/triggers.md#12-j3-win-and-lose-on-map-32)).
- Sound and music play through pygame.mixer ([audio.md](engine/audio.md), K11): not yet judged by ear (VERIFY BY EAR list); no town / shop speech (no towns yet).
- No save / load; no campaign flow between missions ([campaign](engine/triggers.md#11-the-end-of-mission-flow)): hero recruit, roster carry-over.
- Interface: the Heads panel is only a picture (no hero windows), no town / shop windows, menu entries of later phases disabled.
- Spells: structures are not modelled as spell targets (attack orders on structures are accepted and fought like creatures);
  the Prismatic Spray chain, Lightning / Spray bolts and the Fire Ball explosion (lights, steam, burnt ground, burning trees)
  are built, but the status effects of units other than Invisibility and Stone Curse (poisoned, blessed, hasted, ...) have no drawing of their own.
- Triggers: 37 (set music) and the unnamed kinds are not implemented
  (`not implemented:` lines in `engine.log`).
- Multiplayer is out of scope.

## Phase K backlog, by evidence (K12, 2026-11-10)

The first list was by value (written before K0); this one is by data and docs. Evidence, effort guesses and the reasoning: [coverage.md](coverage.md#re-plan-with-the-objective-run-k12-2026-11-10).
At K12: **45 of 46 maps reach "Mission Complete" in the objective run** (`python -m engine objective`; map 77 needs a fight the oracle cannot play), 46 of 46 have no known
blocker, 0 are blocked, no in-mission gap is known. What is left is around the maps.

| # | Feature | State | Maps | Effort (guess) | Order |
|---|---|---|---|---|---|
| 1 | Inventory | pack, equip, use, pickup, wells, scrolls built (K5, K5b, K8); **hero screen, shops, inn missing: town modes only** (a mission's Heads panel is a bare picture) | 0 in a mission, 46 via the campaign | in `town` | 3 |
| 2 | Ranged, spells, caster AI | built (K1-K3, K9, the Prismatic Spray chain included); left: busy-caster animation, lens border | casters 42, shooters 36: polish | - | done |
| 3 | Full triggers and dialogs | 55 of 55 kinds built, 444 of 448 message sections found; unused: variable references, unit names >= 11001, the tips window | 0 | - | done |
| 4 | Full UI | shell (start menu, character creation, options, in-game menu): `shell`; town screens: `town`; cutscenes (5 codes + intro, Smacker): `cutscenes` | all 46 (shell); 5 (cutscene) | 4 + 6 + 3 | 2, 3, 5 |
| 5 | Save / load | `save`: `game%d.sav` or an own format (your decision); server stream serialisers open | all 46 | 3 (own) / 8 (.sav) | 4 |
| 6 | Campaign | `campaign` spine: carry-over, recruit, Scenario.dll variables (maps 70 and 80 read variables no map writes); the party of every map is fresh today | all 46; 2 for the variables | 4 | **1** |
| 7 | Multiplayer | out of scope | - | - | - |
| - | Sound | done (K11); **VERIFY BY EAR** pending | all 46 | - | your session |

## Next steps (K13-K15)

Prompt-sized, in the style of K5-K11. Headless = I can finish and verify it without you; play-test = it needs your session.

**K13 - Campaign spine (headless).**
Goal: a campaign object that carries the party from mission to mission, so a map starts as the game starts it.
Context: read CLAUDE.md, docs/coverage.md (K12), docs/engine/triggers.md §9 and §11, docs/formats/saves.md §4, docs/data/items.md §13, `engine/sim/campaign.py`, `engine/party.py`, `engine/objective.py`.
1. REA (mark CONFIRMED / INFERRED): `FUN_004f312a` (the recruit of Var(0x305)), `FUN_004ebd5f` (the carry-over, against saves §4), the writers of Var(0x309) / Var(0x30a) in Scenario.dll (TalkTo), the hero-death variables (0x213 + id).
2. Build `engine/campaign.py` (layer 4, no windows): new game (fresh hero from attributes and school, `FUN_004f254b`), `leave_mission(result)` = the Outcome chain of triggers §11, roster carry-over with items and levels, the recruits, `start_mission(n)` building the world from the carried roster instead of the fresh party (the DECISION in `enable(party=)` is replaced for campaign runs; `play MAP` keeps the fresh party).
3. `python -m engine campaign [--through N]`: chains the missions in unlock order with the objective run as the driver; prints per map the party's levels and gear, the result and the ticks; fails when a mission cannot be reached from the unlock table.
4. Report: which maps change with the carried party (the six idle-lost maps, the branches of maps 70 and 80), and whether any map is unreachable in the campaign order. Tests: unlock order, carry-over round trip, recruit, deterministic chain hash. Regenerate the coverage report; update docs and CLAUDE.md.
Headless: yes, fully. Commit.

**K14 - The campaign in one window (shell, minimal).**
Goal: play the campaign from the first map without a command line.
Context: K13, docs/engine/ui-layout.md §11.4 / §11.6, the open question on the main-menu chain to state `0x425`.
1. REA: the main menu and the state chain to the new-game screen, the character screen `FUN_0049183e` (layout, widgets, the attribute budget), the options screen; spec with CONFIRMED / INFERRED marks.
2. Build: start menu, character creation (name, four attributes, school), options (the audio flags, speed), the mission-complete / defeat dialogs wired to the K13 chain; between missions a plain list of the available locations and the party's stats stands in for the town until `town`.
3. Headless: widget, layout and golden-screenshot tests, a scripted menu run through the first three missions with the objective oracle. Then **your play-test** of the menus and the chain (what to check goes into prototype.md).
Commit.

**K15 - Town mode spec (research, headless).**
Goal: everything needed to build the town screens, decided before any drawing.
Context: K13, K14, docs/engine/ui-layout.md §11.10, docs/formats/animation.md §4.11, docs/data/items.md §4, §12, §13.
1. REA of the town / hero-screen mode (`client+0x404 & 0x226`): the world-map screen `FUN_0048b419`, the hero screen windows (`FUN_0049a428`, `FUN_0049bd95`, `FUN_0049e187`), the shop and inn windows, the hero arrows (`0x414` / `0x415`), the town and shop speech triggers. Per window: layout per resolution, widgets, messages, the data it reads.
2. Spec `docs/engine/town.md`: windows, state machine (enter town, talk, shop, inn, world map, leave), what the headless side can test, a list of what only your eyes can judge; refine the effort of `town` and split it into build steps (K16...).
Headless: yes (research and layout goldens); the build steps after it need a play-test. Commit.

After K15: `save` (needs your format decision), then `cutscenes`.

