# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Animation

- Town scenes: draw code and timing are resolved ([animation §4.11](formats/animation.md)). Left: the hover-region numbers of the
  fighter/mage/shopie sprites and the druid `man`/`woman` variant choice. [animation](formats/animation.md#open-questions)
- World-map Cross: where `+0x134` is reset to 0 on a new click. [animation](formats/animation.md#open-questions)

## data.bin and items

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0` users; column names known). [databin](formats/databin.md#open-questions)
- Items: none open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block. [items](data/items.md#open-questions)

## Progression

- Equipment effects of a loaded hero (the engine keeps `Unit.equipment` / `Unit.pack` but has no equip system). [progression](data/progression.md#open-questions)

## Combat and death

- Dialog latch `[this+0x3e8]` of the defeat dialog: who resets it (callers of `FUN_00505347`). [combat §12.11](engine/combat.md#1211-open-questions) 1
- Summon-cap job `+0x148` draw order: the `unit+4` ids of map units and heroes that fix the `CMap` bucket order (`0x545a60`; `FUN_0052bbb7`); engine uses first-appearance order. [combat §12.11](engine/combat.md#1211-open-questions) 2
- Item effects (`{castSpell=..}`) of dropped template equipment are lost in the 16-bit pile code; what pile / pickup keep (start `FUN_00529ac2`, `FUN_0052a71d`). [combat §12.11](engine/combat.md#1211-open-questions) 3
- Sound tables (unit sound set entries, hero voices, UI sound `0x627740[0xf]`, the hit sound set); the engine has no audio. [combat §12.11](engine/combat.md#1211-open-questions) 4
- Structure damage `FUN_00516ea0` (attacks on structures); wire format of `FUN_005040c4`. [unit-struct](engine/unit-struct.md#open-questions)

## AI

- Caster follow branch `FUN_00569968`: the word `+0xa0` (a spell-list unit under defend heals the leader; engine: plain scan). [ai](engine/ai.md#open-questions)
- AI casting ([ai §12](engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127)): the party-AI flag byte of a human player (player `+0x34` record `+0x20`, client command at `0x4f6945`) before `FUN_0056bc7b` can be built; whether `FUN_00519483` scales the book wrapper in place (`+9` range; also [spells](data/spells.md#11-open-questions)); `FUN_005551d6` in the revive `FUN_00510534`. [ai](engine/ai.md#open-questions)
- Quest side of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2): the quest generator and accept path (no quest system in the engine; shipped squads with creation bit 8; completion events `FUN_0057e87a`). [ai](engine/ai.md#open-questions)
- Quest system (accept `FUN_0052f8e2`, board, rewards) and the meaning of quest events 5-0x11 (listeners in [combat §16.4](engine/combat.md#164-death-the-event-queue-and-the-trigger-runtime); start `FUN_0052e3eb`, senders in `0x57e5f0`-`0x57edda`). [combat](engine/combat.md#open-questions) 1

## Spells

- [Effects](engine/effects.md#open-questions): the Prismatic Spray chain (`FUN_00519c04` -> `FUN_00579ddf`: the hit reaction first, the caster group's pool `FUN_00571c4d`, distance `FUN_00579d62`, the `min(7, L/20 + 2)` nearest within the range, dying units scored `<< 8`; spell 11 stays a counted no-op); the structure branch of the carriers (`vtable +0x34`, `FUN_00559b7f`); the human scan's recompute triggers besides the stat switch; the client effect messages (`FUN_005044ba`, `FUN_00504498`, `FUN_005045a5`).
- Spell panel leftovers: the tooltip filter `obj+0x24 in {0x17, 0x18}`, the Ctrl+A auto-cast spell (`FUN_0041a727`, cmd `0x46` sub 4), the `0x411` resets of the panel selection, the F-key table's persistence, scroll casts (`0x25`). Start `FUN_004167c2`. [spells](data/spells.md#11-open-questions)

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): where single player posts the ready message (`FUN_0041c50d`); `FUN_0055641c`; the by-name second loop of `FUN_00562518`; the free-cell test `FUN_005563ca` / `FUN_0055c5a0` of `FUN_00510089`; the window message `0x41d` and the mission-complete dialog (`0x486ddb`, Scenario variable `0x300`); the text of message `0xb6` values (`0x433` handler); Scenario.dll initial variables (`ScenarioNewGame`) and campaign use; the member loop of instant 22 (`FUN_005782ba` over a list `FUN_004f0568` changes); the item rules of `FUN_00529ae2` (instants 11, 12, 28) and the hidden caster of instants 21 / 24 (`FUN_004f06ac`) and the effect-duration instants 29 / 30, documented no-ops (the effect system exists now: [effects](engine/effects.md)).
- Scenario event classes: unit `behaviour` bits 1, 2, 4 and the three scenario booleans `+0x194` / `+0x198` / `+0x19c` (`FUN_005303ed`). [map](formats/map.md#open-questions), [unit-struct](engine/unit-struct.md#open-questions)

## Movement and orders

- Player commands `0x1b` (follow / defend) and `0x1d` (patrol), pickup `0x21`, use `0x24`, cast at a cell `0x1f`, town: simulation side built ([ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), no engine command or UI issue yet; the squad voice; the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`); the per-order voice slots. [research §9](engine/click-to-move-research.md#9-open-questions)

## Interface

- Main shell: which main-menu entry and screen-state chain lead to state `0x425` (new single-player game; only known entry: state `0x438` index 6..9 of the widget `this+0x134`); needed before an engine new-game screen. [ui-layout](engine/ui-layout.md#open-questions), [ai §10.1](engine/ai.md#101-difficulty-tweak-fun_00561bf9-0x561e20-0x561f0b-confirmed)
- Which bottom bar shows first; mouse-manager `+0x9c`; purpose of the 30 px top strip; `FUN_004b011e` (text vs human panel) and command-bar contents; hover brightness; structure pick rects; squad voice samples. [ui-layout](engine/ui-layout.md#open-questions); start at `FUN_0040b2b8`, `FUN_004175c7`.

## Rendering and engine

- Day/night light recomputation in the engine. [architecture](engine/architecture.md#open-questions)
- Renderer speed: `build_draw_list` is the next target for 30 fps at 1024x768; terrain scroll hitch (~27 ms per new cell row/column): pre-warm or flat-cell fast path. [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; the engine releases only its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects](engine/rendering.md#open-questions): drawing (the simulation side is built: [effects §6.4](engine/effects.md#64-cell-effect-slots)); the cell record feeders are known ([unit-struct](engine/unit-struct.md#cell-record-effect-confirmed)). Unit invisibility / stone curse / hover, message 0x74 (flag 0x80); start at `FUN_004632a1`.
- [Engine object drawing](engine/rendering.md#open-questions): burnt ground, light-map lights on objects; start at `FUN_00404a2a`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, fog gate of the unit dots; start at `FUN_004ac414`.

## Formats and not started

- Section 12 music: the reader of the next-theme global `0x5f1a08` and the callers of `FUN_004754e9`; section 11 inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)). [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then `FUN_00559890` skips the refresh)? `FUN_005508a0` callers. [map](formats/map.md#open-questions)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections, `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Saves

- Saves ([saves](formats/saves.md#open-questions)): the server stream's object serialisers (`FUN_0052d16b`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, start `FUN_004ec732`) and its 11 option words; which server messages make the client rewrite the `.a2c` (message pump sites `0x411aa2`, `0x4122d7`, `0x41054f`, `0x414a9c`, `0x40ee51`), the `0xa00` settings block and the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c` and its writer's caller; save slot roles (`game9998/9999/0000`, `FUN_004f515d` -> `FUN_004e9816` at `0x4f723d`).
