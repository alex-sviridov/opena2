# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Animation

- Town scenes: draw code and timing are resolved ([animation §4.11](formats/animation.md)).
  Left: the hover-region numbers of the fighter/mage/shopie sprites and
  the druid `man`/`woman` variant choice.
  [animation](formats/animation.md#open-questions)
- World-map Cross: where `+0x134` is reset to 0 on a new click.
  [animation](formats/animation.md#open-questions)

## data.bin

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0`
  users; column names known). [databin](formats/databin.md#open-questions)

## Progression

- Equipment effects of a loaded hero (the engine keeps `Unit.equipment` / `Unit.pack` but has no equip system): [saves §3.6](formats/saves.md#36-building-a-hero-from-a-record-fun_004ea6ab-confirmed-order).

## Items

- None open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block.
  [items](data/items.md#open-questions)

## Spells

- Spell panel leftovers: the tooltip filter `obj+0x24 in {0x17, 0x18}`, the Ctrl+A auto-cast spell (`FUN_0041a727`, cmd `0x46` sub 4), the `0x411` resets of the panel selection, the F-key table's persistence, scroll casts (`0x25`). Start `FUN_004167c2`. [spells](data/spells.md#11-open-questions)

## Combat (I1)

- AI casting (decoded and built, [ai §12](engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127)): the party-AI flag byte of a human player (player `+0x34` record `+0x20`, client command at `0x4f6945`) before `FUN_0056bc7b` can be built; whether `FUN_00519483` scales the book wrapper in place (`+9` range); `FUN_005551d6` in the revive `FUN_00510534`. [ai](engine/ai.md#open-questions)
- Main shell: which main-menu entry and which screen-state chain lead to state `0x425` (new single-player game; only known entry: state `0x438` index 6..9 of the widget `this+0x134`), and whether the Easy/Medium/Hard radios (panel `this+0x374`, resource `0x466`) share the screen with the name edit of town.txt tips 9/10 (INFERRED); needed before an engine new-game screen. [ai](engine/ai.md#101-difficulty-tweak-fun_00561bf9-0x561e200x561f0b-confirmed)
- AI: the group orders 1, 2, 5, `0x11`, `0x13`, `0xff`, the G / L / swarm commands and the scripted sub-commands 1-5, 10, 11, 14, 15, 17, 18 are built ([ai §14](engine/ai.md#14-the-other-group-orders-confirmed-fun_005700f3-dispatch-engine-implemented-see-the-end-of-this-section), §14.2); the Summon guard group and the sleeping-flag instants are built / agree ([ai §15](engine/ai.md#15-sleeping-squads-record-0x45--0x48-and-the-quest-that-sends-a-group-order-2)). Left: the word `+0xa0` read by the caster follow branch `FUN_00569968` (a spell-list unit under defend heals the leader; engine: plain scan); the quest generator and accept path of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2) (no quest system in the engine; shipped squads with creation bit 8; completion events `FUN_0057e87a`); (creature `+0x4c` flags, `FUN_0053a5a0` = mage, the `0x8000` RNG divisor and the difficulty tweak, including which single-player screen sets it (new game: Easy/Medium/Hard, saved in the save file), are answered in ai §6 / §10.1; the flee list is creature-only, hostile structures never trigger a flee, and the hidden flag `0x1000` is the Invisibility effect: answered in ai §4 / §9, engine `Unit.hidden` has no setter until the effect system). [ai](engine/ai.md#open-questions)

- Quest system (accept `FUN_0052f8e2`, board, rewards) and the meaning of quest events 5-0x11 (listeners listed in [combat §16.4](engine/combat.md#164-death-the-event-queue-and-the-trigger-runtime); start `FUN_0052e3eb`, senders in `0x57e5f0`-`0x57edda`).
- Effect system writers: the Bless / Curse chance (`Unit.bless` / `Unit.curse`), the Invisibility bit, durations ([combat §16.5](engine/combat.md#165-fun_005106d2-and-fun_00516b2f); start `FUN_0051ce12`, `FUN_00519db8`).

## Not started (from the reversing plan)

- Part 5 leftovers: event classes of unit `behaviour` bits 1, 2, 4, section 9 per-cell payload.
  [map](formats/map.md#open-questions)
- Section 12 music: the reader of the next-theme global `0x5f1a08` and the callers of `FUN_004754e9`; section 11
  inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)
- Unit struct: group AI, orders 0x16/0x1a, structure damage `0x516ea0`.
  [unit-struct](engine/unit-struct.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)).
  [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then
  `FUN_00559890` skips the refresh)? `FUN_005508a0` callers.
  [map](formats/map.md#open-questions)
- Saves ([saves](formats/saves.md#open-questions)): the server stream's object serialisers (`FUN_0052d16b`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, start `FUN_004ec732`) and its 11 option words; which server messages make the client rewrite the `.a2c` (message pump sites `0x411aa2`, `0x4122d7`, `0x41054f`, `0x414a9c`, `0x40ee51`), the `0xa00` settings block and the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c` and its writer's caller; save slot roles (`game9998/9999/0000`, `FUN_004f515d` -> `FUN_004e9816` at `0x4f723d`).
- Text conventions of `main/text/*.txt` (line lists, `#key` sections,
  `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Engine

- Day/night light recomputation in the engine. [architecture](engine/architecture.md#open-questions)
- Interface (G3b): how the exe clears a selection (right button `0x40f`, Esc? engine: right click);
  which bottom bar shows first; mouse-manager `+0x9c`; purpose of the 30 px top strip; `FUN_004b011e` (text vs
  human panel) and command-bar contents; hover brightness; structure pick rects; order command bytes and the squad
  voice. [ui-layout](engine/ui-layout.md#open-questions); start at `FUN_0040b2b8`, `FUN_004175c7`.
- Engine terrain scroll hitch (~27 ms per new cell row/column): pre-warm or flat-cell fast path.
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects](engine/rendering.md#open-questions) (answered: spell-area sprites, registered by [spells §4](data/spells.md#4-effect-handlers); drawing needs the spell system), unit invisibility / stone curse / hover, message 0x74 (flag 0x80); start at `FUN_004632a1`.
- [Engine object drawing](engine/rendering.md#open-questions): burnt ground, light-map lights on objects; start at `FUN_00404a2a`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, fog gate of the unit dots; start at `FUN_004ac414`.
- Movement and orders (H3) [simulation](engine/simulation.md#open-questions): the empty-list step, Haste vs the group byte, the type-100 message and the connection list are answered ([simulation §11](engine/simulation.md#11-exe-answers-follow-up-of-h1-h3)).
  Haste/Slow vs the group speed byte (phase I); the server's handling of the client's type-100 message (`FUN_004f515d`).
- Handoff to combat (phase I) [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i): the player commands `0x1b` (follow) and `0x1d` (patrol) and their client side (Brain mode 4 and the unit orders 8 / `0x11` / `0xa` are built for the scripted sub-commands, [ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), the other `0x17`..`0x1d` orders, voice, the consolidated VERIFY IN GAME list (§9 items 1-10).
- Order planning spike (H3 bench) [simulation §8.7](engine/simulation.md#87-tests-end-states-measured): a 20-unit order on the 256 x 256 map costs ~0.35 s in one tick (pure-Python planner, 0.46 s before the 7.5 re-expansion skip; still 5x the 62.5 ms tick); worker-thread or faster planner, results must stay bit-identical.
- Guarding computer-player groups [simulation](engine/simulation.md#open-questions): group order `0x12` handler `FUN_005728fa` (reader of `brain+0x16`) and the home-cell restart `FUN_0056c8af`/`brain+0x9c` (`FUN_0056ac5b` = the selected spell's range `B+0x78` when castable, else `u+0x12c`: answered, [ai §12.2](engine/ai.md#122-fun_0056acc8u-t-with-spells-the-attack-decision-of-every-group-handler-6)).
- Click to move (H3 research) [research §9](engine/click-to-move-research.md#9-open-questions): heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`), detection level `FUN_00556dcd` (the spell branches of the retreat post step, `FUN_0056cb8c` / `FUN_0056cef3` = the Teleport flee, are answered in [ai §12.6](engine/ai.md#126-human-owned-mages-the-players-units-and-the-flee-step)); the per-order voice slots (sound engine).
- Cell record effects ([unit-struct](engine/unit-struct.md#open-questions)): writer `FUN_0055ba36` found (callers `0x564280` map load, `0x57853b` scenario instant `FUN_0057847e`); left: which map section / instant feeds them and whether any campaign map uses one (engine has no cell effects).
- Phantom units (9 on blocked cells, never created by the server) and HP-0 units: engine keeps and draws them; decide with the phase H sim. [architecture §9](engine/architecture.md#9-world-state)
- Death/corpses/loot (I2) [combat §12.11](engine/combat.md#1211-open-questions): summon-cap job `+0x148` draw order (CMap iteration order, `0x545a60` hash; `FUN_0052bbb7`); item effects (`{castSpell=..}`) of dropped template equipment are lost in the 16-bit pile code (what the pile / pickup keeps for an item with effects: start `FUN_00529ac2`, `FUN_0052a71d`); sound tables (unit sound set entries, hero voices, UI sound `0x627740[0xf]`; [combat §12.11](engine/combat.md#1211-open-questions) 4).
- Triggers [triggers](engine/triggers.md#open-questions): where single player posts the ready message (`FUN_0041c50d`); `FUN_0055641c`; the by-name second loop of `FUN_00562518`; the free-cell test `FUN_005563ca` / `FUN_0055c5a0` of `FUN_00510089`; the window message `0x41d` and the mission-complete dialog (`0x486ddb`, Scenario variable `0x300`); the text of message `0xb6` values (`0x433` handler); Scenario.dll initial variables (`ScenarioNewGame`) and campaign use; the member loop of instant 22 (`FUN_005782ba` over a list `FUN_004f0568` changes); the item rules of `FUN_00529ae2` (instants 11, 12, 28), the hidden caster of instants 21 / 24 (`FUN_004f06ac`) and the cell record of instant 25 (documented no-ops until the effect system).
