# L10: save / load with the original `game%d.sav` format

Status: **L10 done (L10f closed: robustness, original-file tolerance, `save-info` / `save-diff`, `famehall.dat`, headless glue run; the user's real-game check is the "VERIFY IN GAME" list below)**. **L10b done** (container + typed client tail + MFC archive layer, `allods2/formats/saves.py`, `mfc.py`; saves.md 7); **L10c done** (typed server stream `allods2/formats/serverstream.py`, town saves `engine/savegame.py`, `CampaignGame.to_save / from_save`, `tests/test_savegame_town.py`; saves.md 7 "Engine mapping"); **L10d done** (town-mode Save / Load / Delete windows and the slot folder: [save-ui.md](save-ui.md), `engine/saveslots.py`, `engine/shell/saveload.py`; mission-kind saves are the hook `MissionSaveCodec`); **L10e-A done** (mission-branch codec, saves.md 6.12); **L10e-B done** (the `World` <-> mission-save mapping `engine/missionsave.py`, saves.md 7.1; shell: `MissionSaveCodec`, mission menu Save / Load, auto-saves `game9999` / `game9998`; tests `test_engine_missionsave*.py`; needs the real-game check below). Goal: the engine reads every save the original GOG game writes and writes saves the original
loads, for single player: the Save / Load / Delete dialogs, the manual slots, the auto-saves `game9999.sav` ("Restart last mission")
and `game9998.sav` ("Abort mission and return to town"). Byte layouts known so far: [formats/saves.md](../formats/saves.md) §6
(container, server stream head, client tail, Scenario.dll block, MFC layer, player, group and unit serialisers: §6.4-6.8); L10a rounds 2-4: every object serialiser of the stream is decoded in §6.9-6.11; only field meanings and the option-word consumers stay open) and L10a is **closed**.

## 1. Constraints and the verification problem

* The install holds no `.sav` (only `famehall.dat`), and there is no Wine / DOSBox here. **No byte of a real save can be compared.**
  Verification therefore rests on (a) REA on both directions of every serialiser (reader and writer must agree field by field),
  (b) a round-trip oracle: parse -> write is byte-exact on synthetic files built from the layout, (c) a **loader-in-the-exe check**
  with REA's debugger tools (Frida / GDB / Rizin debug on `allods2.exe` under no emulator is not possible; if REA cannot run the
  exe, the item stays INFERRED and the VERIFY IN GAME list below is handed to the user: save in the original, load here, and
  the reverse).
* Every fact is marked CONFIRMED / INFERRED (CLAUDE.md). Match the exe's quirks (checksum windows, RLE peek) exactly.
* GOG single player only; multiplayer headers are out of scope (read: refuse with a clear message).

## 2. Two kinds of save, built in this order

| Kind | Server state | What the engine needs | Difficulty |
|---|---|---|---|
| **Town save** (loaded flag 0: between missions, saved in the town / world map) | players, hero units with items, spell book, statistics, gold; **no map** | `CampaignGame` <-> stream, Scenario.dll block (vars, shop table, location list), client tail | moderate, fully derivable |
| **Mission save** (loaded flag 1: `game9999`, `game9998`, manual saves in a mission) | the above + map state, every creature / effect / structure, script state, groups | `World` <-> stream | large: the undecoded serialisers |

`game9999.sav` is written at mission entry (a mission-start state), `game9998.sav` at the leave click of a town scene; both are
mission-kind saves. A mission-start save is still reconstructible from the map + party (stage L10d) before the full `World` codec
(L10f) exists: that gives "Restart last mission" early.

## 3. Steps (prompt-sized, one subagent at a time, `model: sonnet`, REA mandatory)

**L10a - REA: the stream body (research, headless; first pass done, rest open: saves.md 6.9).** Decode with REA, per routine, byte layout + CONFIRMED marks, into
`docs/formats/saves.md` new §6.4-6.9: `FUN_004ec732` (11 option words; meaning), `FUN_0052d16b` + vtable `[0]` of
`[server+0x7c]+0xc` (players, groups, unit lists), the creature / unit serialiser reached from it (items via `FUN_005241bf`,
effects list `unit+0x20`, brain `+0x1c0/+0x1c4`, orders), `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008` (map dynamic layer),
`FUN_0057468d` (script state), `FUN_0052d5b2`, `FUN_0053bbd0`, `FUN_0057a951`, the structure and ground-item serialisers.
Also: `game0000.sav` writer, the date field of the list, the `0x2f` byte, mission list `FUN_004a8f96` meaning. Update the Open
questions in both places. Output = spec only, no code.

**L10b - Container + client tail codec (headless). DONE** (`tests/test_saves_l10b.py`; multiplayer files raise `MultiplayerSave`; MFC reader/writer = L10e-0's byte layer). Extend `allods2/formats/saves.py`: full typed `ClientTail` (the `.reg` tree
keys of §6.3, mission list, Scenario.dll block, hotkeys), byte-exact round trip, error messages as the exe ("Invalid save file",
"Outdated save file"). Tests: synthetic, one per rule.

**L10c - Town save <-> `CampaignGame` (headless). DONE.** Typed server stream for loaded-flag-0 saves: players, party units
(`engine/party.py` record path, items through the `.a2c` item codec), gold, statistics, spell books; Scenario block <-> `Campaign`
(variables, `Campaign.shop`, location list). `CampaignGame.to_save()/from_save()`; invariant test: save -> load -> `visit_towns`
oracle continues identically, world-dump hashes unchanged.

**L10d - Dialogs and slots (shell, play-test). DONE for town saves ([save-ui](save-ui.md)); the mission-start `game9999` / `game9998` auto-saves and mission-kind load wait for L10e / L10f (`savegame.MissionSaveCodec`).** REA: Save / Load / Delete windows (`FUN_0043ebf6`, `FUN_0043deaf`, list
`FUN_0043dc54`, slot naming `FUN_0043ece0`, description patches `0x37` / `0x5f`), the in-game menu entries, main-menu Load Game.
Build in `engine/shell/` over a pure `SaveSlots` model (directory scan `game*.sav`, `9999 - slot` numbering, hidden auto-saves,
description, date). Saves go in a settings-side directory (not the repo, not the install). Town saves first; mission-start
`game9999` from the map + party (no creature serialiser needed). Goldens + scripted run.

**L10e - Mission state codec (headless, large).** Per L10a layouts: `World` <-> server stream (creatures, items, effects, orders,
brains, groups, structures, ground items, tile effects, fog bit, script state, tick counters, RNG state). Split further by the
spec's object families. Invariants: save -> load -> N ticks == N ticks without a save (world-dump hash equal) for every
playable map at several ticks; the objective oracle still wins after a mid-mission reload.

**L10f - Full flow + compatibility pass.** Load of every kind from the menu and the town; `Restart last mission` and `Abort
mission and return to town`; `famehall.dat` write at exit; corrupted / outdated / multiplayer files refused cleanly; `docs/prototype.md`
and `CLAUDE.md` status. **User play-test** (VERIFY IN GAME): (1) save in the original game, load here, compare party / map /
script state; (2) save here, load in the original; both for a town save, a mission-start save and a mid-mission save.

## 4. Decisions made (assumptions, recorded per workflow)

* Format = the original byte-for-byte (user decision); no own-format fallback.
* Slots live in a directory the shell setting names (default beside the settings file); the install is never written.
* Loader tolerance: a higher version loads (as the exe), fields the engine does not model are kept as raw bytes and written
  back unchanged, so a load -> save of an original file preserves what we do not understand.
* Order: town saves (L10c) before mission saves (L10e) because they are verifiable and unblock the menu early.

## 5. L10e split by object family (checklist; each item = decode leftovers with REA, codec, round-trip test)

All families share the MFC layer of [saves 6.4](../formats/saves.md#64-mfc-archive-layer-of-the-server-stream-confirmed-unless-noted) (object tags, counted lists, raw-pointer keys, XOR words). Layouts decoded in saves 6.5-6.9; "needs" = leftovers.

- [x] L10e-0 MFC archive codec (`allods2/formats/mfc.py` + the class table in `serverstream.py`): tags exactly as saves 6.10, class table (`Player`, `Unit`, `Humanoid`, `Building`, `SpellEffect`, `VirtualCaster`, `Sack`, `Item`, `Effect`, `Spell`), MFC counts, counted lists, old-pointer map; synthetic tests.
- [x] L10e-1 Players + groups (6.6, 6.7): typed in `serverstream.py` (`Player`, `Group`; groups inline, CONFIRMED); the 11 option words are written 0 (6.11); the `group+0x20` object is typed as a `CList<u16>` (INFERRED).
- [x] L10e-2 Items, Effects, Spells (L10c): `Item` / `Effect` / `Spell` / `Spellbook` / `Pack` typed and mapped to `saves.Item` (`savegame.item_object` / `stored_item`); `SackObj` typed, not wired (needs the flag-1 branch).
- [~] L10e-3 Units (6.8, 6.9, 6.12): codec complete (`Unit` / `Humanoid`, every raw block named in `serverblocks.py`: Position in the object base, mover, brain, skills / defence / bonus blocks, group AI record, embedded `CList`s, load-time pointer fix-ups CONFIRMED); the mapping to `engine` `Unit` fields is the table `serverblocks.UNIT_MAP` + the field notes; open = the `World` <-> stream code (L10e-B), unnamed bytes stay raw.
- [x] L10e-4 Buildings / structures (`BuildingObj`) and ground items (`SackObj` + item lists): typed and wired to the flag-1 branch (`Mission.buildings`, `.sacks`), round trips tested; the Building fields are named (saves.md 6.12).
- [x] L10e-5 Spell effects and virtual casters: `SpellEffectObj`, `VirtualCasterObj` typed and wired (`Mission.effects`, `.casters`); the 6 bytes of a caster = effect6 (CONFIRMED object, saves.md 6.12).
- [x] L10e-6 Map dynamic layer: `MapLayer` = sparse u32 list + the `CMap` of 60-byte cell records (`CELL_RECORD` fields CONFIRMED from effects.md) + pointer key; `cmap_order` helper (INFERRED).
- [x] L10e-7 Script state: `ScriptState` (values, fired flags, 0x30 / 400 blocks, the 70 x 70 relation matrix, counters) and the unit container + back-references (L10c); the mapping to the engine's trigger runner is L10e-B.
- [x] L10e-8 Tick counters, `0xbadface1` pair (read, ignored by the loader), the 400-byte debug block, the even pad (town and mission streams).
- [x] L10e-B (was 9) Integration: `World` <-> stream (`engine/missionsave.py`; saves.md 7.1): players, groups, units, structures, piles, carriers, casters, cell records, script state, counters, RNG tail field, fog runs, client state; the engine extension (`Engine/Blob`) for bit-exact resume; the stream-only loader derives what the exe derives. Invariants tested: resume == no save (full engine state) on all 46 maps and mid-fight at six ticks, re-save byte-identical, mission-start save restarts the mission, the oracle wins after a reload (six maps, also from a stream-only load).
- [x] L10f Compatibility pass: robustness (section 6), original-file tolerance + diagnostics (section 7), `famehall.dat` at exit (section 8), headless glue run (section 9); the real-file check is section 10.

## 6. Robustness (L10f; tests `tests/test_engine_save_robustness.py`)

* Contract: the readers raise only the `ValueError` family (`ArchiveError`, `MultiplayerSave`, "Invalid save file", "Outdated save file"); `saves.damaged` turns whatever a damaged *value* makes an engine-side reader raise (`KeyError`, `TypeError`, ...) into `ValueError`
  (`parse_save`, `savegame.from_save` / `kind`, `missionsave.world_from_save`); `ClientTail.state` too (a garbage `.reg` leaf). Count guards: object lists refuse a count above the bytes left (`serverstream.read_list`), the tail's mission / location counts and the reg entry
  count are checked against the file size, the engine blob inflates through `missionsave.inflate` (cap 512 MB, a zlib bomb = `ValueError`). Fuzz tests (random truncation, bit flips, 0 / 0xffffffff / 0x7fffffff / 0x80000000 words, zeroed runs) over synthetic town saves,
  real town saves and mission saves (also the stream-only form): no exception outside the family, no call over 2 s.
* **Shell** (`saveload.load_file`, DECISION): every failure of parse / build is a notice ("Invalid save file (detail)", the exe's own words first) and **nothing of the shell is replaced before the load succeeded** (campaign, town core, running mission). Main menu Load window and
  the town scene menu keep the window open with the notice (Cancel goes back); the **mission's ESC menu Load window loads while it is open** (`fileview.run_file_dialog` calls `load_file`, `ui.load_result`), so a refused file leaves the mission running under a notice instead of ending
  it. The exe differs: a failed load posts `0x421` (main menu, `FUN_0040d480`); the engine stays because it never destroys the game before the new one is built. Wrong magic / short file / outdated / multiplayer texts are the reader's (saves 7).

## 7. Original-file tolerance and diagnostics (L10f)

* A file the original wrote has no `Engine/*` blob and no RNG marker: `world_from_save` takes the stream-only path (`exact = False`), `from_save` (town) never looked at an engine key; both are tested with files stripped to that form.
* **Pass-through** (`engine/savemerge.py`): at load, `world.save_origin` / `game.save_origin` = `(the stream the engine builds from the fresh state, the file's own stream)`; at every save the freshly built stream is merged: a byte of a raw block, a scalar, a tuple element that the engine has not changed
  since the load (`new == base`) is taken from the file. So option words, `d20`, the 400-byte debug block, unnamed bytes of unit blocks (`blk_*`, unnamed mover / brain bytes), script blocks `b30` / `b400` / scalars survive a load -> save; changed values are the new ones; units match by (`id`, `d08`).
  Raw pointer keys (`ptr`, `link`, the mover / brain pointer fields, `d40` / `d5c` / `d64` / `d44`) are never taken over: they are renumbered by our writer (meaningless outside one file). Spell effects / carriers of a stream-only load are not restored (known, 7.1), so they are not
  written back. Unknown keys of the client `.reg` tree are kept (`ClientState.extra`, grafted back by `to_tree`; `world.client_extra`). Files that carry the blob are merged the same way (the origin is built at load too).
* **`python -m engine save-info FILE`** (`engine/saveinfo.py`): container fields (magic, version, lengths, round-trip check `pack() == file`), description, kind (town / mission), writer (engine extension present or original-style), map / scenario id, tick, difficulty, option words, debug block (RNG marker or zeros),
  players (name, human / AI, gold, kills, groups, units), the human-owned humanoids, **untyped unit bytes** (non-zero bytes of mover / brain that no named field covers, and of the raw `blk_*` blocks, with unit counts), the mission branch counts, script summary (non-zero values, fired flags, counters, unnamed blocks),
  the Scenario.dll block (variables, shop towns, locations, current index), mission list, hotkeys, client `.reg` keys, and a **"could not type"** list (stream that does not parse, mission branch kept raw, `.reg` keys the engine does not type). A refused file prints the reason.
* **`python -m engine save-diff A B [--limit N]`**: typed field-level diff of two files (`fields_of`: container, stream objects by field, raw blocks decoded by `serverblocks` layouts + the unnamed bytes, tail, `.reg` keys, variables, shop table, locations, hotkeys); pointer keys and the engine blob are ignored,
  units are keyed by scenario uid. Use it on an original save and our save of the same moment, or on one original save and the engine's re-save of it (must say "no typed field differs").

## 8. `famehall.dat` (L10f; `engine/famehall.py`)

* CONFIRMED (REA, listing of `allods2.exe`): the exe loads it at start (`FUN_004a91d5`, call `0x481755`) and writes it **at shutdown**: `FUN_004a90c9` is called from the client's destructor `0x482526` (`0x4825e2`, file `0x5f32c0` opened `0x1001` = create / truncate), so it is
  rewritten on every exit. Entries are added by `FUN_004a8d28` (called at `0x486ce2` in the mission-end handler when `FUN_00493da0` = campaign finished, Var 0x300 >= 0x78) through `FUN_004a8c5e`: insert before the first entry whose score is <= the new one (`new < entry` moves on, `0x4a8cbe`), else append, cut to the
  limit (`obj+0xc`). Score = `trunc(hero+0x110 / (times * 10.0) * obj[+8])`, or `/ 500000.0` when the time sum `obj[+4]` is 0 (doubles `0x5cecd0` = 10.0, `0x5cecd8` = 500000.0); name = the hero's `+0xec` string.
* Engine (DECISION): the file lives beside the settings file (`Settings` folder, `famehall.path`), never in the install; the first run reads the install's copy (`Shell.load_hall`); `Shell.shutdown()` (called by the backend after the loop) rewrites it atomically. **Entries:** the shell adds the main hero when the last mission ends (`Shell.record_ending`, `famehall.score`: the operands are the hero's XP sum, the campaign's time sum and the kill counter, saves 5; the kill counter is stood in for by the human's monster kills, INFERRED). There is still no Hall of Fame screen
  (menu button disabled) and no credits (the end-of-campaign flow ends in the menu, `game.py CAMPAIGN_ENDINGS`; the exe: credits `0x428` -> hall `0x429` -> menu).

## 9. Headless glue run (L10f; `tests/test_engine_save_glue.py`)

The real `python -m engine` shell loop (`backend_pygame/shell.py`, `PlaySession`, `window.run`, `fileview.py`) runs with `SDL_VIDEODRIVER=dummy` and scripted pygame events: main menu LOAD (damaged file = notice, the dialog stays), an original-style mission save loads into the real game loop (stream-only), ESC menu Save (typed
description) writes a file, ESC menu Load with a damaged file = notice and the same world keeps running, Load of the saved file replaces the world, End Quest -> main menu, LOAD of a town save -> town scene, scene menu Save, window close -> `famehall.dat` in the settings folder. Found and fixed by it: nothing broke in the
glue; the damaged-file case in the mission menu used to end the mission (now a notice, section 6).

## 10. VERIFY IN GAME (one list; the user's real-game check)

Tools: `python -m engine save-info FILE` (what the file is, what could not be typed), `python -m engine save-diff A B` (typed diff). Slot folder: `~/.config/allods2-engine/saves` (`Settings.save_dir`; `ALLODS2_SETTINGS` moves the settings file and with it the folder). The original keeps its saves in its install folder
(`game*.sav`). Always copy, never move. Report: the file name, what `save-info` printed (paste it), what happened (crash / notice / wrong state) and a screenshot when something looks different.

**A. Original -> here** (make each file in the original, copy it to our folder, run `save-info`, then start our shell and Load it from the main menu):

1. **Town save** (any town scene: ESC -> Save Game; ideally after one or two missions with items and spells). Expect: listed with the same text and date format, loads into the same town scene; party, gold, items, spell books, shop stock regenerated, campaign variables (the map's open locations). Report: `save-info` "could not type" lines and any
   non-zero option words, the town shown, party / gold differences. Then `save-diff original.sav our-resave.sav` (Save it again here under the same text) should say "no typed field differs" (or only fields we derive: the location rectangles, fog); report any other line.
2. **Mission-start save** (`game9999.sav` = "Restart last mission", made by entering a mission; also usable from the original's folder as is). Expect: loads, the party stands at the drop cell with the saved items, the script runs (messages / triggers). Report the `save-info` "untyped unit bytes" line.
3. **Mid-mission save** (ESC -> Save Game during a fight with spells, summons, corpses, items on the ground, some fog explored). Expect: units / HP / mana / items / effects / corpses / fog come back; known gaps: walking steps, casts in progress, flying missiles, effects and carriers on the ground (the Wall of Fire etc.) are not restored from an original file (their classes `PointEffect` / `AreaEffect` / `SpellTransport` now parse, saves 6.12, but the exe stores neither the effect object nor the geometry); the script's pass counters and the RNG restart.
   Report: anything missing or wrong, and whether the fight continues normally for a minute.
4. **`game9998.sav`** ("Abort mission and return to town", made when leaving a town scene): loads back into that town.
5. **Refusals**: copy a truncated copy of any save, a renamed other file, and (if you have one) a multiplayer save: each must show a notice and leave the shell as it was (no crash).

**B. Here -> original** (save in our shell, copy the file into the original's folder; the original must list and load it):

6. **Town save** (scene menu -> Save Game): the original lists it with our text, loads, shows the town, party, items, gold, variables. Report any "Invalid save file" / "Outdated save file", a crash, or wrong values.
7. **Mission-start save** (`game9999.sav` written at a mission start): the original loads it (map, party, script).
8. **Mid-mission save** (ESC -> Save Game in a fight): the original loads it. This is the riskiest item, but this round settled most of its causes: the Building / Sack / SpellEffect scalars, the runner's stopwatch block, the armour block and the mission list are now the exe's own values (saves 6.12), and the exe ignores the `Engine/*` keys and the RNG bytes (saves 6.3 / 6.11). What remains is whatever the code reading could not show (the unit `+0x44` wrapper word, the group `+0x1c` tags, carriers written as inert `SpellEffect`s). Report a crash on load (note which map and what was on screen: summons, walls, items on the ground, structures) and any
   unit / structure that is off.
9. If the original refuses or crashes: run `save-diff ORIGINAL_OWN_SAVE OUR_SAVE` on two saves of the **same moment** (same mission start) and paste the output.

**C. Windows and flow** (save-ui 5.1-5.13 stay valid): window looks and positions, date format, empty first row, overwrite behaviour, delete question text, list order, LOAD enable with only invalid files, auto-saves `game9999` / `game9998` listed first and hidden from the Save window, ESC-menu Save / Load enabled in a mission, a refused file in the mission's Load window shows a notice (here the game
   keeps running; the original goes to the main menu and shows **no** text, save-ui 6).

**D. famehall.dat**: after quitting our shell a `famehall.dat` exists beside the settings file (same bytes as the install's on a first run); the install's copy is untouched. The original adds your hero when the campaign is completed (built here since the REA round, section 8: score = XP sum / (time sum * 10) * kills, the kill counter stood in for by the monster kills): if you play to the end, compare the score and the position with the original's `famehall.dat` (the hall and credits screens are not built here).

## Open questions

* L10e-B DECISIONs to confirm with a real save (VERIFY IN GAME, saves.md 7.1): the group `+0x1c` tags and the unit `+0x44` wrapper word; which of the exe's unsaved runner counters (stage / stage2 / passes) matter.

* Field meanings still open (saves.md 6.12 list: the item armour block of the accumulators);  whether REA can drive `allods2.exe` to produce a real save (would turn INFERRED into CONFIRMED).
