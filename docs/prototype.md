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
`Ctrl+A` auto-cast, `Tab` info panel picture / text, `Esc` menu, `Pause`. Options: `Ctrl+H` health bars, `Ctrl+L`
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
  `draw_fog` plus the 16-bit round trip (`tests/test_lighting.py`).

## Bugs found and fixed in the bug pass

*TODO after play* (one line each: report, test, cause, spec corrected or not).

- First smoke run: a replay without the fog gave another hash (the world dump holds the fog bits): the replay now runs with fog.
- First smoke run: fog drawing took 75 % of the frame time: layered cache and byte-table application, see Speed.

## Comparison with the original

*TODO after play.* Each row: fixed, VERIFY IN GAME or known gap. Seed list to check during the play-through (timing,
damage feel, AI, UI): the consolidated VERIFY IN GAME items of [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i),
[combat](engine/combat.md), [ai §13](engine/ai.md), [vision](engine/vision.md), the walk speed and swing timing, the
height of the damage numbers, the hit-reaction flee, the story window layout.

## Known differences and gaps

- No start menu or new-game screen: the shell exits after the end dialog ([triggers §12](engine/triggers.md#12-j3-win-and-lose-on-map-32)).
- No sound or music (the engine has no audio).
- No save / load; no campaign flow between missions ([campaign](engine/triggers.md#11-the-end-of-mission-flow)): hero recruit, roster carry-over.
- Interface: the Heads panel is only a picture (no hero windows), no town / shop windows, menu entries of later phases disabled.
- Spells: the Prismatic Spray chain is a counted no-op; structures cannot be targeted; spell effects have no drawing of their own.
- Triggers: instants 29 / 30 (spell durations), 37 (set music) and the unnamed kinds are counted no-ops
  (`not implemented:` lines in `engine.log`).
- Multiplayer is out of scope.

## Phase K backlog, by value

1. **Inventory and hero windows**: the Heads panel, hero window with the paper doll, stats and skills, item shops.
2. **More spells**: Prismatic Spray, structure targets, effect drawing (so a poisoned or blessed unit looks so), spell durations (instants 29 / 30).
3. **Full triggers**: the remaining check / instant kinds, variable references 8000-9999, unit names >= 11001.
4. **Campaign**: end-of-mission chain, hero recruit, roster carry-over, the campaign variables `0x301`-`0x30d`, world map and towns.
5. **Full UI**: start menu, new-game and options screens, in-game menu entries, town-scene animations, tooltips for every element.
6. **Sound and music**: sound events (message `0xfe` / `0xfd` / `0xfa`, projectiles 500+), music zones, squad voices.
7. **Save / load**: the `game%d.sav` writer / reader ([saves](formats/saves.md)); the server-stream object serialisers are open.
8. **Multiplayer**: out of scope for the single-player product; only if ever wanted.
