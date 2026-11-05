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

- None open ([progression](data/progression.md#open-questions)).

## Combat and death

- Sound tables (unit sound set entries, hero voices, UI sound `0x627740[0xf]`, the hit sound set); the engine has no audio. [combat §12.11](engine/combat.md#1211-open-questions) 1
- Structure damage `FUN_00516ea0` (attacks on structures); wire format of `FUN_005040c4`. [unit-struct](engine/unit-struct.md#open-questions)

## AI

- Retreat of a unit that can cast Teleport (`FUN_0056cb8c`, range `unit+0xa5`; engine flees on foot); the game start does not send the option messages `0x46` (`FUN_0048c8a3`). [simulation 8.3a](engine/simulation.md#83a-retreat-key-r-bar-button-8-and-the-retreat-mode-ctrl-w)
- Party options message `0x46`: sub `0x80` (`FUN_00578910`) is not built; the registry default of `AutoCasting` on a first run. [ai](engine/ai.md#open-questions)
- Caster follow branch `FUN_00569968`: the word `+0xa0` (a spell-list unit under defend heals the leader; engine: plain scan). [ai](engine/ai.md#open-questions)
- AI casting ([ai §12](engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127)): whether `FUN_00519483` scales the book wrapper in place (`+9` range; also [spells](data/spells.md#11-open-questions)); `FUN_005551d6` in the revive `FUN_00510534`. [ai](engine/ai.md#open-questions)
- Quest side of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2): the quest generator and accept path (no quest system in the engine; shipped squads with creation bit 8; completion events `FUN_0057e87a`). [ai](engine/ai.md#open-questions)
- Quest system (accept `FUN_0052f8e2`, board, rewards) and the meaning of quest events 5-0x11 (listeners in [combat §16.4](engine/combat.md#164-death-the-event-queue-and-the-trigger-runtime); start `FUN_0052e3eb`, senders in `0x57e5f0`-`0x57edda`). [combat](engine/combat.md#open-questions) 1

## Spells

- [Effects](engine/effects.md#open-questions): the Prismatic Spray chain (`FUN_00519c04` -> `FUN_00579ddf`: the hit reaction first, the caster group's pool `FUN_00571c4d`, distance `FUN_00579d62`, the `min(7, L/20 + 2)` nearest within the range, dying units scored `<< 8`; spell 11 stays a counted no-op); the structure branch of the carriers (`vtable +0x34`, `FUN_00559b7f`); the human scan's recompute triggers besides the stat switch; the client effect messages (`FUN_005044ba`, `FUN_00504498`, `FUN_005045a5`).
- Backpack window leftovers: item tooltip property lines (`FUN_0043901f`), weapon-swap lock (`+0x78` in {3, 7, 8}), "new" twinkle (`FUN_004a285a`), text flag 8, message `0x463` / `0x46e`, open sound, releases over the minimap / heads / window 8, gold cell and drop of the hero-screen lists (phase K). [ui-layout 11.13](engine/ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked) (`FUN_004a2bba`, `FUN_004b028d`)

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): the item rules of `FUN_00529ae2` (instants 11, 12, 28); the hero recruit `FUN_004f312a` (Var(0x305) at a mission end), the roster carry-over `FUN_004ebd5f` and the campaign variables `0x301`-`0x30d` / the markers at `0x214`; the UI sounds of the `0xfe` / `0xfd` / `0xfa` messages. Instants 29 / 30 stay documented no-ops (the effect system exists now: [effects](engine/effects.md)).
- Scenario event classes: unit `behaviour` bits 1, 2, 4 and the three scenario booleans `+0x194` / `+0x198` / `+0x19c` (`FUN_005303ed`). [map](formats/map.md#open-questions), [unit-struct](engine/unit-struct.md#open-questions)

## Movement and orders

- Player commands `0x1b` (follow / defend) and `0x1d` (patrol), use `0x24`, cast at a cell `0x1f`, town: simulation side built ([ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), no engine command or UI issue yet (the item commands `0x21` pickup, `0x22` move item, `0x23` drop gold are built: `PickUp`, `MoveItem`, `DropGold`; no click or window issues them yet - the pickup cursor mode and the hero window are phase J); the squad voice; the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`); the per-order voice slots. [research §9](engine/click-to-move-research.md#9-open-questions)

## Interface

- Main shell: which main-menu entry and screen-state chain lead to state `0x425` (new single-player game; only known entry: state `0x438` index 6..9 of the widget `this+0x134`); needed before an engine new-game screen. [ui-layout](engine/ui-layout.md#open-questions), [ai §10.1](engine/ai.md#101-difficulty-tweak-fun_00561bf9-0x561e20-0x561f0b-confirmed)
- Chat input line (the former "30 px top strip", `FUN_0043b219`): does a single-player server echo the client chat message `0x91` (consumer not found); Enter gate view `+0x80`; capture `ClipCursor` rect with an open bar; hover brightness; structure hover (rect cell slot, cursor flags `0x20` / `0x800`); info-panel quest markers (`main` `0x159`-`0x15e`, `FUN_004180c6`); squad voice samples. [ui-layout](engine/ui-layout.md#open-questions); start at `FUN_0040b2b8`, `FUN_004175c7`.
- Spell book window leftovers: colour key of SpellBook / SpellBack / caps, rounding of the level-4 veil `FUN_004565cd`, `view+0x14` at 800x600, map-row recompute `FUN_0041b121`, Space hero-dead branch `FUN_0041ab96`, the left release's cell cast `FUN_0041918e` (table `0x5f1810`). [ui-layout 11.12](engine/ui-layout.md#1112-spell-book-window-bottom-bar-id-3-class-fun_004c61e7-vtable-0x5cf918-confirmed-unless-marked)
- Heads / hero arrows: receivers of messages `0x414` / `0x415` (the hero windows `FUN_0049a428` / `FUN_0049bd95` / `FUN_0049e187`?) and the hero list `FUN_00472460` flags. [ui-layout](engine/ui-layout.md#open-questions)
- Text windows (pause, failed): justified paragraph drawing (`FUN_0045e01d`, `FUN_0045da67`), the scroll bar (`FUN_004da54d`), the failed window's reason string (`0x6227b0[msg - 2]`), the text-window key handler (ESC / Enter, `FUN_004dc595`), the complete path with chapter var `>= 0x78`. [ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)
- Tooltip leftovers: box corner blits (`DAT_00626cac`), option byte `mgr+0xa0`, clip globals `DAT_00621414/18`, tooltip font, hide path `FUN_00427ea5`. [ui-layout 11.6b](engine/ui-layout.md#116b-tooltips-mouse-manager-fun_004268c4-bar-fun_004ad61c-box-fun_0042787b--fun_00427999)
- Story window leftovers: `FUN_0041d8bb` (second unit list), portrait crop orientation, consumers of the `sound:` / `tune:` / `tips:` tag keys (message `0x45b`). [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages) (`FUN_004dd226`)
- Info-panel knowledge table: character-file load / write-back (`Knowledge(blob)` / `to_blob`) and the exact engine mapping of client relation bit 8 (`FUN_0041e860`). [ui-layout](engine/ui-layout.md#open-questions) (`FUN_004ea6ab`, `0x4141fa`)
- Info panel: whether the new-game name field accepts `|`. [ui-layout open questions](engine/ui-layout.md#open-questions)
- Message list: quest-event lines need a quest system (none in the engine), alternative message colour tables `0x61fb08` / `0x61fba8`. [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)

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

- Saves ([saves](formats/saves.md#open-questions)): the server stream's object serialisers (`FUN_0052d16b`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, start `FUN_004ec732`) and its 11 option words; the `+0x2f` byte; whether single player ever uses a stored character's items (VERIFY IN GAME); `famehall.dat` fields `b`, `c`; slot `game0000.sav` (read by the server start when `server+0x1ac != 0`, writer unknown) and `game9998.sav` (no sender).
- Phase K save/load UI and writers: the Save / Load / Delete dialogs (`FUN_0043ebf6`, `FUN_0043deaf`, list `FUN_0043dc54`), the `game%d.sav` writer `FUN_0048dc9f` (+ loader `FUN_0048db37`), the mission-start auto-save `game9999.sav` "Restart last mission" (message `0x442` from `FUN_0048c8a3(0)`), the `famehall.dat` write at exit; single player never writes a `.a2c` ([ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)).
- Fog of war ([vision](engine/vision.md#open-questions)): corpse visibility (`flag 0x80`, arrays `+0x98`/`+0x9c`), the unit step's vtable `+0x44` callers, message `0xaa` value 2; start at `FUN_00468762`.
