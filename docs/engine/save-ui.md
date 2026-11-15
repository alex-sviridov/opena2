# Save / Load / Delete windows and the save slots (L10d)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)). Marks: **CONFIRMED** (routine given) / **INFERRED** / **DECISION** (engine choice). Single player only.
Code: `engine/saveslots.py` (pure model), `engine/shell/saveload.py` (windows + the main menu's `load` screen), `engine/shell/town.py` (the scene menu), `engine/savegame.py`
(`kind`, `MissionSaveCodec`), `engine/shell/machine.py` (`Shell.slots`, `save_game`, `resume`). Tests: `tests/test_engine_saveslots.py`, `tests/test_engine_shell_saveload.py`,
goldens `save_dialog`, `save_dialog_typed`, `load_dialog`, `delete_confirm` (`golden.json["shell"]`). Container, stream and client tail: [saves 6](../formats/saves.md#6-the-saved-game-gamedsav); status of the whole step: [save](save.md).

## 1. The slot folder (CONFIRMED `FUN_0043dc54`, `FUN_0043ff4a`, `FUN_0043ece0`)

* The exe scans `<game dir>\game*.sav` (`0x5f0698` `\game*.sav`, `FindFirstFileA` / `FindNextFileA`, directories skipped). **Engine DECISION:** the folder is the player's own: `Settings.save_dir`
  (settings file, `engine/audio/settings.py`), default `saves/` beside the settings file (`~/.config/allods2-engine/saves`); the install is never written.
* **List filter.** Save window: every file except `game9999.sav` and `game9998.sav` (`strcmp`, case-sensitive in the exe; the engine matches case-insensitively); Load window: all. After the scan a file
  counts only if its first u32 is `0x26677342`; the description is the `0x100` bytes at the file offset given by the u32 at +4 (the start of the client tail, [saves 6.3](../formats/saves.md#63-the-client-tail-confirmed-fun_0048dc9f-writes-fun_0048c2e9-reads-from-offset-4--0x100)); a file that fails
  is dropped from the list (`FUN_0044fd70`: its `cFileName` was cleared). INFERRED: a multiplayer save is listed as well (the same header).
* **Order: newest first** (CONFIRMED comparator `0x43dc0f` = `CompareFileTime(b.ftLastWriteTime, a.ftLastWriteTime)`, qsort `FUN_00583a80` over the 0x140-byte find records). Ties: unspecified in the exe; the engine sorts by name.
* **Row text** (CONFIRMED format `0x5f06f0`, the CTime getters `0x44dfe0` year `tm+0x14 + 0x76c`, `0x44e000` month `tm+0x10 + 1`, `0x44e020` day `tm+0xc`, `0x44e040` / `0x44e060` / `0x44e080` h / m / s, `FUN_0059e723(0)` =
  local time of `ftLastWriteTime`): `"%s  %02d.%02d.%d  %02d:%02d:%02d"` = description, two spaces, **day.month.year**, two spaces, hour:minute:second. `saveslots.entry_text`.
* **New file name** (CONFIRMED `FUN_0043ece0`): the numbers are the four characters at 4..7 of each **listed** file name read as digits (`c - '0'` x 1000 / 100 / 10 / 1, no digit check), sorted ascending; no listed file = 0, else the
  first position `i` where `sorted[i] != i`, else `last + 1`; printed `game%04ld.sav` (`game000%ld`, `game00%ld`, `game0%ld` by size, `game%ld.sav` from 1000 on, the same text as `%04d`; the four literals `0x5f0714`, `0x5f0724`, `0x5f0734`, `0x5f0744`). An unlisted file with that name
  (invalid, or the hidden ones) is overwritten. `saveslots.new_name`.
* **Auto-save names** (CONFIRMED `0x48850d`): `game%d.sav` of `9999 - slot`: slot 0 `game9999.sav` ("Restart last mission", patch 0x37), slot 1 `game9998.sav` ("Abort mission and return to town", patch 0x5f). The engine does not write them
  yet ([save](save.md): `Services.autosave` stays a hook; mission-kind = L10e / L10f).
* **LOAD enable** (CONFIRMED `FUN_0043ff4a`): `FindFirstFile("\game*.sav")` finds *any* file (valid or not): the main menu's LOAD GAME button ([shell 3.1](shell.md)) and the menu entry "Load Game" are enabled by it.
  `SaveSlots.any_saves()`. With no `Shell.slots` the button stays disabled (tests, no folder).
* **Writing**: DECISION atomic (temp file in the folder + `os.replace`); the exe's `FUN_0048dc9f` opens the target directly.

## 2. The windows (CONFIRMED build slots; sizes by the common snap, [ui-layout 11.4](ui-layout.md#114-in-game-menu-pause-freeze))

Both are dialogs derived from the common base (`FUN_004dc48e`): constructor rect `(100, 0x1e, 600, 0x1c2)` = 500x420 -> **488x360** (`FUN_004dc4fc`), centred on the real screen. Child rects below are relative to
the window (`W` = 488; INFERRED that `FUN_0041e250` returns the parent's width: it fits the 0x28 margins and the scroll bar at `W - 0x28`), `(l, t, r, b)` as the build calls give them. Texts: `dialogs.txt` lines through `FUN_00474733` (`this+0xc` + id; the delete question comes from `patch.txt`).

| Window | Child | id | Rect (x, y, w, h) | Text | Notes |
|---|---|---|---|---|---|
| **Save** (`FUN_0043ebf6`, class `0x5cbe50`, build `0x43ece0`) | caption label | 2 | (0x28, 0x20, W-0x50, 0x18) | d `0x1d` "Save Game" | flag 2 = centred |
| | edit field | 1 | (0x28, 0x44, W-0x50, 0x18) | tooltip d `0x1e` "Enter a name for the saved game" | class `FUN_004d601b` |
| | label | 0 | (0x28, 0x68, W-0x50, 0x18) | d `0x90` "Saved Games" | left |
| | list box | 3 | (0x28, 0x80, W-0x68, 0x90) | tooltip d `0x1f` "Saved Games" | class `FUN_0043ddb9` over `FUN_004d82f8`; the scroll bar (id 10, `FUN_004da54d`) is the 24 px right of it (x 424..448) |
| | buttons | 4 / 6 / 5 | y `0x128..0x140` (list bottom `0x110` + 0x18 .. + 0x30); x `3W/20..7W/20`, `8W/20..12W/20`, `13W/20..17W/20` | Ok (d 0), Delete (d `0x9d`), Cancel (d 1); tooltips d `0x20` "Confirm selection", `0x9e` "Delete selected#saved game", `0x21` "Cancle" | messages `0x479` / `0x475` / `0x47a` |
| **Load** (`FUN_0043deaf`, class `0x5cbdc8`, build `0x43df48`) | caption label | 1 | (0x28, 0x20, W-0x50, 0x18) | d `0x97` "Load Saved Game" | centred |
| | label | 2 | (0x28, 0x44, W-0x50, 0x18) | d `0x18` "Load Game" | left (a second heading under the caption) |
| | list box | 3 | (0x28, 0x5c, W-0x68, 0xc0) | tooltip d `0x19` "Select Game to load" | + scroll bar id 10 |
| | buttons | 4 / 6 / 5 | y `0x134..0x14c`, same x | Ok (tooltip d `0x1a` "Confirm selection"), Delete, Cancel (tooltip d `0x1b`) | same messages |

The button rects use integer division. Hot keys: none besides the common ones (Tab focus, ESC = message `0x446`, [ui-layout 11.4](ui-layout.md#114-in-game-menu-pause-freeze)). Sounds: the dialog text button's
press sound (`UI_SOUND` = sfx id 2, as the options windows); no other sound is made by these windows. INFERRED (not read): the row pitch (font1 17 px), the list / edit / scroll-bar look (flat boxes in the engine, needs eyes), the
edit field's character limit (the engine limits the description to the 255 bytes of the buffer `local_130[256]`, `0x43f8da`), Up / Down in the list.

### 2.1 Save window rules (CONFIRMED handler `0x43f8da`, slot 18 of the vtable)

* The list's row **0** is the "new file" row: an empty entry (`Add(&DAT_0061b1fc)` / `Add(&DAT_0061b200)` before the scan; the name array's element 0 is the new name `game%04ld.sav`, the scan's entries start at 1). The selection starts at 0 (`this+0x94 = 0`).
* **List selection** (message `0x46e`, sub 3): the selected row's description goes into the edit field (row 0: the empty string `0x61b204`); `FUN_0043fe78` then enables **Ok iff the field is non-empty**. A change of the field text (sub 1) re-runs it.
* **Ok / Enter** (`0x479` / `0x444`; only while Ok is enabled): description := field text; if it equals (`strcmp`) the description of a listed row 1.., that row becomes the selection; file name := the selected row's file (row 0 =
  the new name); the window closes with `0x445`. **Quirk kept:** a row picked and then retyped overwrites *that* row's file with the new text. `saveslots.choose_target`.
* **No overwrite question** exists: the closing handler `FUN_004891d8` (case `this+0x140`) runs `FUN_0048dc9f` at once on `0x445`; then, if the mask is 1 (a mission) and not paused, the tick clock is re-based; the window is freed.
* **Delete** (`0x475`): `sel = FUN_0044f0f0()`; `sel != 0` (row 0 cannot be deleted) opens the confirmation: text window `FUN_00444243(1, 0x40, 100, 0x17c, 0x252, text, 0, 4)` (case 4 = **Yes** main `0x4b` / **No** main `0x4c`, results `0x447` /
  `0x448`; constructor size 316x494 -> text-window rules of [ui-layout 11.4](ui-layout.md#114-in-game-menu-pause-freeze), `widgets.text_window`), text = `patch.txt 0x32` "Are you sure you want to delete game '" + the row's string +
  `patch.txt 0x33` "' ?". Yes: `DeleteFileA(file)`, the row is removed from the three arrays, the selection moves to `FUN_0044f0f0()` and the `0x46e` message is re-sent (the new row's text fills the field). INFERRED: the row string
  quoted is the description only (`FUN_0044f2d0` reads the list model; the exe adds the description there, the formatted "description + date" is a second array); the engine quotes the description.
* **Cancel** (`0x47a`) and ESC: close with `0x446`, nothing written.
* The Save window is reachable only from the in-game menus: message `0x41a` (mode 0 or 1), which first clears the description (`this+0x148`) and the file name (`this+0x248`).

### 2.2 Load window rules (CONFIRMED handler `0x43e7f0`, slot 18 of the vtable `0x5cbdc8`)

* The selection starts at row 0 (`in_ECX[0x25] = 0` in the constructor `0x43deaf`): the newest file. **Ok and Delete are disabled when the list is empty** (`0x43df48`: `FUN_00401760() == 0` -> `+0x1c(1, 0)`).
* **Ok / `0x444` (Enter or the list's activation)**: selection < 0 closes as a cancel (`0x446`); else the file name and the description of the selected row are copied into the game's buffers (`this+0x248` name, `this+0x148` description) and the window
  closes with `0x445`. The closing handler (`FUN_004891d8`, case `this+0x13c`) posts **`0x419`** (the load). Cancel / ESC (`0x446`): when no game runs (`DAT_006044c4 == 0`, i.e. the main menu) post `0x421` (back to the main menu); else when `game+0x43c == 0xff` post `0x41e`
  (the failed-mission window's Load Game: exit to the main menu); the in-game cases resume the game and re-base the tick clock.
* **Delete** (`0x475`): the same confirmation and removal as the Save window (`sel >= 0` here, there is no new row); with no row left Ok and Delete are disabled (`FUN_004d4013(4 / 6)`).
* Entry points: main menu LOAD GAME (message `0x418`, [shell 3.1](shell.md)), the in-game menu `0x416` and the scene menu `0x41f` "Load Game" (`0x418`), the failed window's "Load Game" button. All enabled by `FUN_0043ff4a`.

## 3. What a load does (CONFIRMED `FUN_0048db37`; saves, town-worldmap 8)

`0x419` -> `FUN_0048db37`: wait cursor, `+0x5d8 := 2` (single player), the file named in `this+0x248` is read by the server (`FUN_004e9b95`, [saves 6](../formats/saves.md#6-the-saved-game-gamedsav)); `FUN_0040d480` failing (bad / refused file) posts **`0x421`** (the
main menu); then `FUN_0048c214` reads the save's `CurrentState/InBattle`: non-zero -> the mission is resumed (`FUN_0048c8a3(1)`, no new auto-save); **zero -> a town save: the server is rebuilt (`0x41ab50`, `0x4f84f8`, the message pump), the client tail is read (`0x48c2e9`),
`FUN_0041aaa5(0, 0)` builds the town scene of the saved location and `0x42e` is posted**. The map is never shown after a load. The error texts ("Invalid save file", "Outdated save file", the multiplayer refusal) belong to the reader ([saves 6.1](../formats/saves.md#61-container-confirmed-fun_004e9816-writer-fun_004e9b95-reader));
where the exe shows them is not traced (INFERRED a message box).

Where a save can be made: a town scene (scene menu `0x41f` -> `0x41a`) and a mission (`0x416` menu -> `0x41a`). **The world map has no menu and no key** ([town-worldmap](town-worldmap.md)), the inn and the shop windows have no menu entry (ESC closes them): a town
save is therefore always written from a scene, and a load of it stands in that scene's town (the position written is the current location's index in the available list).

## 4. The engine

* `SaveSlots(directory)`: `scan(include_hidden)`, `describe`, `any_saves`, `read`, `write` (atomic), `delete`, `path` (a name never leaves the folder); `choose_target`, `new_name`, `autosave_name`, `entry_text`.
* **Windows** (`engine/shell/saveload.py`): `SaveDialog`, `LoadDialog` (shared `SlotDialog`: list, three buttons, nested `TextBox` = the Yes / No and the notice windows), `load_file(shell, name)`. Buttons act on the release over the pressed one;
  Enter = Ok (`0x444`), ESC = Cancel, Up / Down move the selection, the wheel scrolls the list, typing goes to the edit field (Save).
* **Screens:** the **scene menu** (ESC or the scene's `0x10` region) has Save (enabled when a slot folder exists) and Load (enabled by `any_saves`); either closes the menu and opens its window over the scene. Save Ok -> `Shell.save_game(file,
  description)` = `CampaignGame.to_save(description).pack()` written to the slot; a write error shows a notice. Load Ok -> `load_file` -> `Shell.resume(game)` -> the new `TownCore` enters the saved town (`MSG_ENTER`) -> screen `town`
  (`town -> town` in `GRAPH`). The **main menu** LOAD GAME enables from the folder (`MainMenu.enter`) and goes to the `load` screen (the menu picture under the Load window); Cancel -> `menu`, Ok -> `town` (or `locations` for a save without a town location).
  `GRAPH`: `town -> town`, `load -> town, locations`.
* **Restoring the location:** `savegame.from_save(.., resume_location=True)` sets `camp.location` to the saved position in the available list (CONFIRMED `ScenarioLoad`: the entry at that position becomes current); the L10c default (location None, rests on the map) stays for headless use.
* **Mission saves (L10e-B, built):** see "L10e-B" below. (Earlier text, superseded:)
* **Not supported yet (the L10e / L10f hook):** a mission-kind file (`InBattle` = 1, `savegame.kind`) shows the notice "Loading a saved mission is not supported yet." (DECISION text); in a mission the in-game menu's Save and Load stay disabled; the auto-saves
  `game9999` / `game9998` are not written (`Services.autosave` is called with the slot and ignored). The single extension point is `savegame.MissionSaveCodec` (`save(session, description)`, `load(save, campaign)`) assigned to `Shell.mission_codec`.
* **Errors (L10f: [save 6](save.md#6-robustness-l10f-tests-testsenginesaverobustnesspy)):** any failure of the readers (also a damaged value deep in the stream) = a notice, nothing of the shell replaced; in the mission's ESC menu the Load window loads while it is open, so a refused file never ends the running mission. Earlier text: an unreadable / refused file -> a notice with the reader's message ("Invalid save file", "Outdated save file", the multiplayer message; a truncated file adds the detail), the Load window stays open; a failed write -> a notice, the Save window stays open (the old file is untouched: atomic write);
  a failed delete -> a notice.
* Decisions: no overwrite confirmation (as the exe); the delete question quotes the description; the menu closes when a window opens and does not reopen (INFERRED from `FUN_004891d8`, which only clears bit 8); the Save window keeps the typed text across a Delete.

## 4.1 L10e-B: mission saves in the shell (built)

* `Shell.mission_codec` = `savegame.MissionSaveCodec` (default; None restores the "not supported" notice). `saveload.load_file` of a mission-kind file: `codec.load` -> `Shell.resume_mission(params)` -> `("game", params)` (edges `town -> game`, `game -> town`, `load -> game`); `GameScreen` plays `params["loaded"].world` (no `start_mission`, no new auto-save, saved camera / selection / fog). An unreadable mission stream is a notice "Invalid save file (...)" (a refused load from inside a mission goes to the main menu, `0x421`).
* **Mission ESC menu:** Save and Load are enabled when the shell has a slot folder (`GameUi.files`, `modal.menu_dialog(files=)`; Load only with any `game*.sav`, `FUN_0043ff4a`); the entry closes the menu (`GameUi.file_request`) and `window.run` opens the shell's `SaveDialog` / `LoadDialog` over the frozen frame (`backend_pygame/fileview.py`); Save Ok -> `Shell.save_mission` (the world as a mission save; the dialog keeps its notice on an error), Load Ok -> the loop ends with `ui.quit == "load"` and `ui.load_file`, `GameScreen.run` loads it. The menu has **no** "Restart last mission" / "Abort mission and return to town" entry (CONFIRMED menu list, ui-layout 11.4): those are the descriptions (patch `0x37` / `0x5f`) of `game9999.sav` / `game9998.sav` in the Load window, so restarting = loading `game9999`.
* **Auto-saves:** `Shell.mission_start_save(session)` after the campaign mission's session is built (`game9999.sav`, `FUN_0048c8a3(0)` -> `0x442`); `Shell.autosave(9998)` from the town core's leave event (`game9998.sav`, a town save: the party is still in the town). `Services.autosave(slot)` stays the observer hook.

## 5. VERIFY IN GAME (user's real-game check)

The consolidated list (original <-> here, town / mission-start / mid-mission, with `save-info` / `save-diff`) is [save 10](save.md#10-verify-in-game-one-list-the-users-real-game-check); the items below are the window-level details it refers to.

1. **Save from a town scene** (ESC or the star region -> Save Game): the window's look against the original (caption, edit field, "Saved Games" label, list, Ok / Delete / Cancel positions, scroll bar); the date format `DD.MM.YYYY  HH:MM:SS` and the two spaces; the empty first row.
2. **Overwrite**: save twice with the same text (the second goes to the same file, no question); pick a row, retype, Ok (overwrites that row's file).
3. **Original <-> engine files**: copy an original `game*.sav` made in a town into the engine's slot folder: it must list, load and stand in the town scene (party, gold, inventory, spell books, variables); copy an engine save into the original's folder: it must list with the same text and load
   (the L10c INFERRED parts of the stream: [saves 7](../formats/saves.md#7-code)). Check which town the original shows (the saved location) and that the shop stock after the load is regenerated.
4. **Delete**: the confirmation text (`Are you sure you want to delete game '...' ?`: what is quoted, the description or the whole row), Yes / No, the selection after the delete, Ok / Delete disabled on an empty list.
5. **Main menu**: LOAD GAME enabled exactly when a `game*.sav` exists (also an invalid one); Cancel returns to the menu; the Load window over the menu picture.
6. **Mission-kind files** (`game9999.sav` made by the original at a mission start): listed first in the Load window; since L10e-B it loads through the stream-only path (see 8-13).
7. The list order (newest first), the row pitch, the selected-row colour, the edit field's character limit and caret, Enter / double-click behaviour, the click sounds, the window position at 800x600 / 1024x768 (centred on the real screen).
8. **Mission start auto-save:** start a mission here, quit to the menu, Load Game: `game9999` ("Restart last mission") is listed (first, hidden from the Save window) and restarts the mission; the same file copied into the original's folder loads there (map, party at the drop cell, script state).
9. **Mid-mission save here -> load in the original:** ESC -> Save Game in a fight (spells, summons, corpses, items on the ground): the original must list it, load it, and show the units / HP / items / fog; look for a crash on the INFERRED Building / SpellEffect / VirtualCaster / Sack scalars (saves 7.1) and that the unknown `Engine/*` reg key and the RNG bytes at the end of the debug block do not disturb it.
10. **Original mission save -> load here:** a save made by the original in a fight loads (derived path): party, HP / mana, items, effects, corpses, script values, fog bits; the script's stage counters and the RNG restart (exe quirk: they are not in the file).
11. **Resume feel:** after a load the fight continues without a visible jump (positions, walking units, cast in progress, flying missiles are not restored from the original's saves).
12. **ESC menu:** Save / Load entries enabled in a mission (Load only when a `game*.sav` exists), the windows open over the frozen map, Cancel returns to the game; Load from a mission replaces the game; a town save loaded from a mission stands in its town.
13. **`game9998`:** after leaving a town scene (leave click) the Load window lists "Abort mission and return to town"; loading it returns to that town.

## Open questions

* The list / edit / scroll-bar classes (`FUN_004d82f8`, `FUN_004d601b`, `FUN_004da54d`): row pitch, colours, selection look, the edit field's character limit, keyboard handling, double-click: starting routines `FUN_004d82f8` (list), `FUN_004d601b` (edit). The engine draws flat boxes.
* Which string the delete question quotes (description or the displayed row): `FUN_0044f2d0`, `FUN_0044f210` in `0x43ece0`; and where the exe shows the reader's error messages for a refused file (`FUN_004e9b95` callers).
* Whether the menu closes or stays under the Save / Load window in the original (`FUN_004852d8` cases `0x41a` / `0x418`).
* Tie order of two files with equal write times (qsort `FUN_00583a80`).
