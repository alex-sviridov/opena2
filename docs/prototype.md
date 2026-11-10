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
| 4 | Full UI | shell: **start menu, options, new-game screen (placeholder start) built in L0** ([shell](engine/shell.md)); character creation, in-game menu entries, the campaign in one window: `shell`; town screens: `town`; cutscenes (5 codes + intro, Smacker): `cutscenes` | all 46 (shell); 5 (cutscene) | 4 + 6 + 3 | 2, 3, 5 |
| 5 | Save / load | `save`: `game%d.sav` or an own format (your decision); server stream serialisers open | all 46 | 3 (own) / 8 (.sav) | 4 |
| 6 | Campaign | `campaign` spine (**L1 done**): carry-over, recruit, Scenario.dll variables, the chain over the maps; the shell, the town and a play-through still use it | all 46; 2 for the variables | 4 | **1** |
| 7 | Multiplayer | out of scope | - | - | - |
| - | Sound | done (K11); **VERIFY BY EAR** pending | all 46 | - | your session |

## Next steps (L1-L3)

**L0 - The shell (done).** `python -m engine` starts as the original does: the three logo / intro videos (placeholders that log `video skipped: <name>`), the main menu from the original's bitmaps and hit mask, the new-game (PreCreate) screen, quit; the original's Game Options and Sound Options windows from the in-game menu (settings file); one state machine (`engine/shell/`), no World until the game screen. [docs/engine/shell.md](engine/shell.md). **Your play-test of the shell** (what to check): the menu hover / held / disabled look and the click sound, the new-game screen (heroes, difficulty, Cancel / OK), ESC -> Game Options / Sound Options in a mission (the checks and sliders; the menu has no options entry, as in the original), that a game started from the menu returns to the menu through ESC -> End Quest -> Exit to Main Menu, and the volume sliders by ear.

Prompt-sized, in the style of K5-K11. Headless = I can finish and verify it without you; play-test = it needs your session.

**L1 - Campaign spine (headless) (done).** `engine/campaign.py` (`CampaignGame`: new game, roster carry-over, recruits, the town stand-in, `start_mission` from the carried roster, the death hook), `engine/sim/campaign.py` fixed per triggers 11.5 (mission 21 by `Var(0x304)`, cases 50 / 60 / 70, the mercenary markers and the completion loop, `EnterInn` / `TalkTo` as pure methods), `party.place_party(roster=)`, `python -m engine campaign [--through N] [--hero MF|FF|MM|FM]`. Spec and DECISIONs: [docs/engine/campaign.md](engine/campaign.md). Tests: `tests/test_engine_campaign_spine.py` (29: 25 synthetic, 4 with the install; the chain twice with equal hash, the whole campaign).
Result (default hero, seed 1, 5 s): the chain plays **34 missions in unlock order and the oracle wins every one**, ending at chapter 120 with cutscene 4; not played: 51 and 83 (named by no case and no word: expected) and 75-77, 81, 85-87, 94-96 (the class slots of the other three classes; the default hero is a male fighter). Map 77 (oracle miss) is only offered to a male mage, `--hero MM`, and is completed anyway. Which maps change with the carried party: **none by the oracle** (result, tick and edits of all 34 maps equal the fresh-party runs) and **the six idle-lost maps stay lost** (the headless chain gains no XP, so the carried party is a level-1 party); the branches of maps 70 and 80 differ in the triggers that fire (map 70: 17, 20; map 80: 2-10 and the items) but not in the win. The mercenary path works (`hire=` policy: variants by chapter, deleted at the mission end, flags cleared). Open: [campaign 4](engine/campaign.md#4-open-questions).

**L2 - The campaign in one window (shell, minimal) (done, play-test pending).**
Goal: play the campaign from the first map without a command line.
Context: L1, docs/engine/ui-layout.md §11.4 / §11.6, the open question on the main-menu chain to state `0x425`.
1. REA: the character generator panel `+0x36c` (shell.md 3.3: what follows PreCreate; its child rects, the attribute-roll rules `FUN_004f254b`, the labels; `0x49183e` is only the creation call) and `0x40d480`; spec with CONFIRMED / INFERRED marks. The main menu, the state chain to `0x425` and the options windows are done in L0 ([shell.md](engine/shell.md)).
2. Build: the character generator panel replacing the L0 OK shortcut (the PreCreate screen itself is built in L0), the remaining options widgets (Tips, AutoCast, formation, retreat), the in-game menu's Game / Sound Options entries, the mission-complete / defeat dialogs wired to the L1 chain; between missions a plain list of the available locations and the party's stats stands in for the town until `town`.
3. Headless: widget, layout and golden-screenshot tests, a scripted menu run through the first three missions with the objective oracle. Then **your play-test** of the menus and the chain (what to check goes into prototype.md).
Commit.
Result: [chargen.md](engine/chargen.md) (REA: there is no dice; the panel is Accept / Reset / Back with +/- attribute buttons and four weapon / sphere classes), `engine/shell/chargen.py` (model `ChargenState` + screen), `engine/shell/locations.py` (the
stand-in between the missions: party, gold, the available missions, Main Menu), `GameScreen` campaign mode (victory -> `leave_mission` -> locations; defeat / menu -> main menu), every Game Options widget built (Tips, Join, AutoCast, formation / retreat /
AutoCast mode radios; the party options reach the mission as commands), [shell.md 3.4](engine/shell.md). Tests `test_engine_shell_campaign.py` (16), goldens `["shell"]` `chargen*`.
**Your play-test of L2** (what to check): `python -m engine`: NEW GAME -> pick a hero / level / name -> OK -> the generator: the attribute buttons (+ / - disabled looks, the pool number, free steps), the weapon / sphere icons (hover shine, selected glow;
bow / astral do nothing, as in the exe), Reset (25 x4, pool 100), Accept / Back, the hint text and its Close button, the sounds (`+_-`, class, button); then the between-missions dialog: mission 10 starts, win it (Mission Complete -> OK) and the list
offers the next missions with your party's level; ESC -> Game Options shows Tips, AutoCast, Formation, Retreat, Join and keeps them across a restart; a defeat or Exit to Main Menu returns to the main menu. Known gaps: no town / world map (stand-in), no
save, the credits after the last mission, the hint window is placed by us, the preview panel is a text list.

**L3 - Town mode spec (research, headless).**
Goal: everything needed to build the town screens, decided before any drawing.
Context: L1, L2, docs/engine/ui-layout.md §11.10, docs/formats/animation.md §4.11, docs/data/items.md §4, §12, §13.
1. REA of the town / hero-screen mode (`client+0x404 & 0x226`): the world-map screen `FUN_0048b419`, the hero screen windows (`FUN_0049a428`, `FUN_0049bd95`, `FUN_0049e187`), the shop and inn windows, the hero arrows (`0x414` / `0x415`), the town and shop speech triggers. Per window: layout per resolution, widgets, messages, the data it reads.
2. Spec `docs/engine/town.md`: windows, state machine (enter town, talk, shop, inn, world map, leave), what the headless side can test, a list of what only your eyes can judge; refine the effort of `town` and split it into build steps (L4...).
Headless: yes (research and layout goldens); the build steps after it need a play-test. Commit.

After L3: `save` (needs your format decision), then `cutscenes`.

