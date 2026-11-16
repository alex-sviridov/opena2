# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## data.bin and items

- Items: none open. Related and not started: the `Scenario.dll` state machine beyond the shop table and the save block. [items](data/items.md#open-questions)

## Progression

- None open ([progression](data/progression.md#open-questions)).

## Combat and death

- Sound ([sound](formats/sound.md#open-questions)): the unreferenced / missing speech names (59 expected names without a file, 90 files the rule never produces), the zone theme draw `rand(3)` range, the host window of the `0x467` track-change message.
- Audio K11 ([audio](engine/audio.md#open-questions), starting routines `FUN_0041da16`, `FUN_0041b311`): what `view+0x1b8` bits 1 / 0x10 and `view+0x188` are (the three selection arrays of the order voice); the `0xb9` diplomacy line and the cheat-code activation / other codes (`message` sub 5 / 6); by ear: the DirectSound pan law and the 74 % default against the real mixer, the exact gapless music switch.

## Campaign

- L1 ([campaign](engine/campaign.md#4-open-questions)): how close the grind phase's XP is to a player's (an upper bound; only a play-through tells).

## AI

- (answered K5b) Quest side of [ai §15.2](engine/ai.md#152-the-quest-that-sends-a-group-order-2): the quest system is multiplayer only (no quest is generated in single player, [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38)); nothing to build.
- (answered K5b) Quest system (accept `FUN_0052f8e2`, board, rewards), quest events: multiplayer only, see [items §14](data/items.md#14-quests-and-the-item-upgrade-message-0x38); the engine needs none.

## Spells

- Backpack window leftovers (K5b answered: text flag 8, message `0x46e`, the doll item on the cursor, Ctrl+F): the open sound, releases over the minimap / heads / window 8, the window `0x4ba` of message `0x463` (map 10), the hero-screen lists' gold cell (phase K, hero_ui). [ui-layout 11.13](engine/ui-layout.md#open-questions)

## Town mode

- Town scenes ([town-scenes 8](engine/town-scenes.md#8-open-questions), starting routine `0x41d15e` story window): the scene's NPC click opens the story window (`engine/shell/storywin.py`, page 1 voiced, Ok pages; speakers = roster heroes / dummy doll only, the scene has no person list); whether the exe keeps the scene loop under the main menu after Exit to Main Menu (no close hook on that path).

- **Guessed for now (town.md 7), still to verify:** info panel position at 800x600 / 1024x768; `backinv*` colour meaning (which of g / b / s a cell takes); the map path-edge tracer (the shop's numbers, grid draw, shelf rects and prices are answered: town-shop 9).


- Inn dialogue ([town-inn 5](engine/town-inn.md#5-open-questions)): the left sheet's derived stat rows for a person (the exe shows every `FUN_0046aa1d` row at detail 7; the engine shows the template's four attributes / HP / mana / defence: a world-free `CombatStats` builder is missing).
- Hero panels = the Inn windows ([town-hero 8](engine/town-hero.md#8-open-questions)): the info panel's name / book / mode rows in the campaign inn and its final rect at 800x600 / 1024x768 (`0x49e451`, ctor `0x4adf45`: the shift `640 - width` is CONFIRMED, the mission-time rect and mode flag are run-time state); (figure cells and "HIRED": answered in L7, town-inn 6).

## Triggers and scenario

- [Triggers](engine/triggers.md#open-questions): (the owner race of the `Var(0x301)` readers: answered, all human scene; the shop's `window+0x160` and `Var(0x302)` are answered in [town-shop](engine/town-shop.md)); (the hire price: none, answered). Instants 29 / 30 stay documented no-ops (the effect system exists now: [effects](engine/effects.md)).

- Shop windows ([town-shop 8 / 9](engine/town-shop.md#9-l8-rea-round-2026-11-15), built in L8): the Yes / No shopkeeper clips, shelf highlights and shelf-turn animations (`0x4baa98`, `0x4bae3e`, `0x4baf3f`, `0x4bb040`), the shop tooltips (`0x4b37f7`, `0x4bb2c4`, `0x4bccf8`), the equip path of a drop on the doll (server `0x4f5d27`; refused for now), the insert order of a returned item inside its shelf (`0x52151c`) and the two lists per block, the pack region's hover rule (`+0x144`), the druid / Kaarg animation tables, a lost mission's DLL shop update (the L1 flow).

## Movement and orders

- Player commands `0x1b` (follow / defend) and `0x1d` (patrol), use `0x24`, cast at a cell `0x1f`, town: simulation side built ([ai §14.2](engine/ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed)), no engine command or UI issue yet (the item commands `0x21` pickup, `0x22` move item, `0x23` drop gold are built: `PickUp`, `MoveItem`, `DropGold`; the pickup click issues `PickUp` (K5, [items](engine/items.md)); the pack window issues the others); the squad voice; the consolidated VERIFY IN GAME list. [simulation](engine/simulation.md#open-questions), [simulation §9](engine/simulation.md#9-handoff-to-combat-phase-i)
- Click to move: heap block after the `+0xb8` table (`FUN_00582a10`; last-row read of `FUN_00417f31`); the per-order voice slots. [research §9](engine/click-to-move-research.md#9-open-questions)

## Interface

- Chat input line (built, [ui-layout](engine/ui-layout.md#open-questions)): the relation test `FUN_0054fb7f` against `0x69049c` in the server echo; the open-book cast branch of the chooser has no drag override. Squad voice samples: see [audio](engine/audio.md). Start at `FUN_0040b2b8`, `FUN_004175c7`. (Cheat byte, chat row composition, `ClipCursor`: answered, [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages).)
- Spell book window leftovers: colour key of SpellBook / SpellBack / caps, rounding of the level-4 veil `FUN_004565cd`, `view+0x14` at 800x600, map-row recompute `FUN_0041b121`, the dispatcher's use of table `0x5f1810` to reach the decoded cell cast `FUN_0041918e`. [ui-layout 11.12](engine/ui-layout.md#1112-spell-book-window-bottom-bar-id-3-class-fun_004c61e7-vtable-0x5cf918-confirmed-unless-marked)
- Heads panel: the extra panel's 24 rows at 800x600 (INFERRED black) and TextBackL's strip position at 1024. [ui-layout](engine/ui-layout.md#open-questions), [town-hero 8](engine/town-hero.md#8-open-questions) (`FUN_00472460`; the unit flags are answered)
- Text windows (pause, failed): the scroll bar's sprite file (class `0x5d00e8`, paint `0x4da80f`, structure decoded) and the first-line indent field `+0x80` (INFERRED 0). [ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)
- Tips window of the mission message `0x45b` (`tips:`): the receiver builds it (rect (10, 20, 370, 188)); no install mission uses the tag, so not built (the town / shop / inn / chargen / new-game callers are all built). [ui-layout 11.5](engine/ui-layout.md#115-on-screen-messages)
- Info-panel knowledge table: character-file load / write-back (`Knowledge(blob)` / `to_blob`) and the server's composition of the relation word whose bit 8 the client reads (`FUN_0041e860`, client side answered). [ui-layout](engine/ui-layout.md#open-questions) (`FUN_004ea6ab`)
- Message list: quest-event lines (multiplayer only, no work).
- Backpack: what releases over the minimap / heads panel / window 8 do, the hero-screen lists' gold cell, window `0x4ba` of message `0x463`. [ui-layout 11.13](engine/ui-layout.md#1113-backpack-window-bottom-bar-id-2-class-fun_004a2bba-vtable-0x5ce978-confirmed-unless-marked)

## Rendering and engine

- [Engine drawing](engine/rendering.md#open-questions): the Lightning / Prismatic Spray bolts (28 / 30) are built and CONFIRMED ([effects §11](engine/effects.md): ShootDelay spawn, ShootOffset origin, the exact line).  Fire explosion (projectile 13), its lights, steam and burnt ground are built (CONFIRMED `FUN_0046c1d0`, `FUN_005045a5`).  (Burning trees: resolved, [rendering](engine/rendering.md#open-questions).)  Fog gating of burning-cell fire/steam, explosions and bolts: resolved (none; steam needs Lighting, fire needs a map object).  Renderer speed: only a dirty-rectangle re-fog remains, blocked by the screen-anchored fog quads under horizontal scroll ([architecture](engine/architecture.md), round 5).
- K9 drawing (arrows, status effects, flights, Teleport, the lens: built, CONFIRMED), leftovers in [rendering](engine/rendering.md#open-questions): a move / turn message arriving during a cast or attack animation replaces it (CONFIRMED: `0x6b` / `0x6d` start unconditionally), so the ShootDelay event would not fire (not modelled; the busy test of attack / shoot / cast and the busy clock are built and answered), and the by-eye VERIFY IN GAME list of [Arrows and shots](engine/rendering.md#arrows-and-shots-k9) (not compared yet).
- (answered) Unit flag `+0x1b8 & 0x80` at the mission start: `FUN_0052be01` sends nothing, see [rendering](engine/rendering.md#open-questions).
- Renderer speed: the densest 1024x768 view is now ~19.5 ms mean (terrain layer cache and per-object item memo; was 26.5), still 11 ms, scrolling ~26 ms; shadow batching was measured and gives nothing (cost is per covered pixel, overlapping pairs). A static-scene cache is left. [architecture](engine/architecture.md#open-questions)
- Who deletes a structure object in single player (the unregister `FUN_005200bd` is its destructor; the engine never removes one, so the cell-clearing quirk is not modelled). Starting point: the vtable slot holding the deleting destructors (`0x5d12ac`, `0x5d12ec`). [architecture](engine/architecture.md#open-questions)

## Formats and not started

- Section 12 music: answered in [sound §5](formats/sound.md#5-music-confirmed-unless-noted) (`0x4754e9` picks the nearest zone and writes `0x5f1a08`); left: nothing for the music (never reset after use, sound §5); section 11 inn / shop fields (multiplayer only). [map](formats/map.md#open-questions)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections, `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Saves

- Saves ([saves](formats/saves.md#open-questions)): the item armour block of the accumulators (saves 6.12), the cell records' carrier slot pointers after a load, player / item field meanings (saves 6.6 / 6.9).
- Saves, L10c ([saves 7](formats/saves.md#open-questions), starting routine `FUN_004ec732` / `ScenarioLoad` `0x10003686`): the INFERRED parts of the town save (one player / one group, derived unit blocks, Item `+0xc`, player `0x24` block); VERIFY IN GAME against an original town save.
- Save / Load / Delete windows (L10d, [save-ui](engine/save-ui.md#open-questions)): the list / scroll-bar look and colours (`FUN_004d82f8`, `FUN_004da54d`; flat boxes now), whether the in-game menu closes under the window; VERIFY IN GAME list: [save-ui 5](engine/save-ui.md#5-verify-in-game-users-real-game-check).
- Saves, L10f ([save](engine/save.md#open-questions)): the Hall of Fame screen is built (m3, [hall](engine/hall.md)) and the credits (m2) (the hall entry is added, [save 8](engine/save.md#8-famehalldat-l10f-enginefamehallpy)); the exe's main-menu return after a failed load is not copied (the engine keeps the running game); VERIFY IN GAME: [save 10](engine/save.md#10-verify-in-game-one-list-the-users-real-game-check).
- Mission saves, L10e-B ([saves 7.1](formats/saves.md#71-l10e-b-the-mission-save-mapping-enginemissionsavepy-tests-testenginemissionsavepy-testenginemissionsaveshellpy), starting routine `FUN_004ec732` / `FUN_0048c2e9`): built and tested here; VERIFY IN GAME that its own mission saves load through the derived path and the DECISION words (group `+0x1c`, unit `+0x44`) do no harm. Single player never writes a `.a2c` ([ui-layout 11.4](engine/ui-layout.md#114-in-game-menu-pause-freeze)).
- [Items K5](engine/items.md#open-questions): the client sound of the item notice `FUN_00504b3a` / gold message `0x67`; `unit +0xe4` (the pack index of message `0x21`, INFERRED 0x7FFF); several selected units on a pickup.

## Structures

- Using a structure ([structures](engine/structures.md#open-questions)): verify in game the use-walk stop cells, a far use click failing (structures 2.1, answered in the exe) and that the hovered well's panel redraws as the charges fall (8.1).
- Cutscenes, m1 ([cutscenes](engine/cutscenes.md#open-questions), [REA notes](engine/cutscenes-rea.md#open-questions)): the audio channel order / cache markers are checked by stream ends only; the list's double click / wheel (`0x5cffc8`), the 640x360 blit rectangle, frame dropping in `smackw32.dll`, message `0x436`, town 2 / 3 leave codes; VERIFY IN GAME: [cutscenes 7](engine/cutscenes.md#7-verify-in-game-nothing-watched-yet).
- Shop, second round ([shop-rea2](engine/shop-rea2.md#8-tooltips-confirmed-where-read)): whether the window load resets the selected shelf at each opening, whether the keeper bitmaps are colour-keyed on black, the stock panel's item tooltip (`0x4b37f7`), the Kaarg fire bitmap order (lite / burn / cicle INFERRED), `FUN_004a0fd0(2)` = `rand() % 2` (INFERRED); the shelf / keeper tooltips are not built; VERIFY IN GAME: the human shelf clips, idle and Yes / No clips, the Kaarg brazier, price numbers.
- Item sparkle ([item-new-rea](engine/item-new-rea.md)): where the client reads wire bit `0x40` (the pickup mark), whether trades / hero-death drops / script items also write server `+8`; `PickupWatch` still counts `Item.new`, which nothing clears.
- Minimap water ([minimap-water-rea](engine/minimap-water-rea.md)): white is the exe's result from the table; whether it is intended art needs an original screenshot.
