# L10: save / load with the original `game%d.sav` format

Status: **plan** (nothing built). Goal: the engine reads every save the original GOG game writes and writes saves the original
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

**L10b - Container + client tail codec (headless).** Extend `allods2/formats/saves.py`: full typed `ClientTail` (the `.reg` tree
keys of §6.3, mission list, Scenario.dll block, hotkeys), byte-exact round trip, error messages as the exe ("Invalid save file",
"Outdated save file"). Tests: synthetic, one per rule.

**L10c - Town save <-> `CampaignGame` (headless).** Typed server stream for loaded-flag-0 saves: players, party units
(`engine/party.py` record path, items through the `.a2c` item codec), gold, statistics, spell books; Scenario block <-> `Campaign`
(variables, `Campaign.shop`, location list). `CampaignGame.to_save()/from_save()`; invariant test: save -> load -> `visit_towns`
oracle continues identically, world-dump hashes unchanged.

**L10d - Dialogs and slots (shell, play-test).** REA: Save / Load / Delete windows (`FUN_0043ebf6`, `FUN_0043deaf`, list
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

- [ ] L10e-0 MFC archive codec: tags exactly as saves 6.10 (verify the counter start against a real save), class table (`Player`, `Unit`, `Humanoid`, `Building`, `SpellEffect`, `VirtualCaster`, `Sack`, `Item`, `Effect`, `Spell`), MFC counts, counted lists, old-pointer map; synthetic tests.
- [ ] L10e-1 Players + groups (6.6, 6.7): decoded; needs `group+0x20` object, the 11 option words. Town saves (L10c) depend only on this plus Items.
- [ ] L10e-2 Items, Effects, Sacks (6.9 table): fully decoded; map to `.a2c` item codec / `engine` items (L10c shares it).
- [ ] L10e-3 Units (6.8, 6.9): decode `Humanoid::Serialize` first, then `unit+0x1c8/0x1e4` objects and the raw blocks; map to `engine/` unit fields (HP, mana, position, orders, effects, brain `+0x1c0/+0x1c4`, hero fields).
- [ ] L10e-4 Buildings / structures (`Building` 6.9, decoded) and ground items (Sack list `FUN_0052d5b2`).
- [ ] L10e-5 Spell effects and virtual casters (6.9, decoded).
- [ ] L10e-6 Map dynamic layer (6.9, decoded: sparse list); `map+0x54084` decoded (CMap u16 -> 60 bytes, saves 6.11); needs the meaning of the 60-byte value.
- [ ] L10e-7 Script state (6.9, decoded byte layout) <-> `engine` script runner; the object at `[server+0x7c]+0xc` is the unit container (count + Unit refs, 6.11).
- [ ] L10e-8 Tick counters, `0xbadface1` pair, the 400-byte tail (`[server+0x170]` = debug block: write 400 zeros; the 11 option words: write 0 (6.11)).
- [ ] L10e-9 Integration: `World` <-> stream, unknown fields kept raw, invariants of step L10e (reload determinism).

## Open questions

* Everything left of L10a (saves 6.9, listed per family above); whether REA can drive `allods2.exe` to produce a real save (would turn INFERRED into CONFIRMED).
