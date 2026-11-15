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
* **Not supported yet (the L10e / L10f hook):** a mission-kind file (`InBattle` = 1, `savegame.kind`) shows the notice "Loading a saved mission is not supported yet." (DECISION text); in a mission the in-game menu's Save and Load stay disabled; the auto-saves
  `game9999` / `game9998` are not written (`Services.autosave` is called with the slot and ignored). The single extension point is `savegame.MissionSaveCodec` (`save(session, description)`, `load(save, campaign)`) assigned to `Shell.mission_codec`.
* **Errors:** an unreadable / refused file -> a notice with the reader's message ("Invalid save file", "Outdated save file", the multiplayer message; a truncated file adds the detail), the Load window stays open; a failed write -> a notice, the Save window stays open (the old file is untouched: atomic write);
  a failed delete -> a notice.
* Decisions: no overwrite confirmation (as the exe); the delete question quotes the description; the menu closes when a window opens and does not reopen (INFERRED from `FUN_004891d8`, which only clears bit 8); the Save window keeps the typed text across a Delete.

## 5. VERIFY IN GAME (user's real-game check)

1. **Save from a town scene** (ESC or the star region -> Save Game): the window's look against the original (caption, edit field, "Saved Games" label, list, Ok / Delete / Cancel positions, scroll bar); the date format `DD.MM.YYYY  HH:MM:SS` and the two spaces; the empty first row.
2. **Overwrite**: save twice with the same text (the second goes to the same file, no question); pick a row, retype, Ok (overwrites that row's file).
3. **Original <-> engine files**: copy an original `game*.sav` made in a town into the engine's slot folder: it must list, load and stand in the town scene (party, gold, inventory, spell books, variables); copy an engine save into the original's folder: it must list with the same text and load
   (the L10c INFERRED parts of the stream: [saves 7](../formats/saves.md#7-code)). Check which town the original shows (the saved location) and that the shop stock after the load is regenerated.
4. **Delete**: the confirmation text (`Are you sure you want to delete game '...' ?`: what is quoted, the description or the whole row), Yes / No, the selection after the delete, Ok / Delete disabled on an empty list.
5. **Main menu**: LOAD GAME enabled exactly when a `game*.sav` exists (also an invalid one); Cancel returns to the menu; the Load window over the menu picture.
6. **Mission-kind files** (`game9999.sav` made by the original at a mission start): listed first in the Load window; loading shows our "not supported yet" notice (L10e / L10f); the original shows no such thing.
7. The list order (newest first), the row pitch, the selected-row colour, the edit field's character limit and caret, Enter / double-click behaviour, the click sounds, the window position at 800x600 / 1024x768 (centred on the real screen).

## Open questions

* The list / edit / scroll-bar classes (`FUN_004d82f8`, `FUN_004d601b`, `FUN_004da54d`): row pitch, colours, selection look, the edit field's character limit, keyboard handling, double-click: starting routines `FUN_004d82f8` (list), `FUN_004d601b` (edit). The engine draws flat boxes.
* Which string the delete question quotes (description or the displayed row): `FUN_0044f2d0`, `FUN_0044f210` in `0x43ece0`; and where the exe shows the reader's error messages for a refused file (`FUN_004e9b95` callers).
* Whether the menu closes or stays under the Save / Load window in the original (`FUN_004852d8` cases `0x41a` / `0x418`).
* Tie order of two files with equal write times (qsort `FUN_00583a80`).
