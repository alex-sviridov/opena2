# Text files `main/text/*.txt` and `patch/patch.txt`

Plain cp1251 text, CR LF line ends, no BOM, no escapes. Every file is loaded **whole** by one of two loaders (addresses in the GOG
allods2.exe, see [README](README.md)); the format of the content is one of two kinds. Facts below were measured on every file of the install.

## 1. Loaders (CONFIRMED)

| Loader | Used for | Behaviour |
|---|---|---|
| `FUN_00474585` (this = line list: `+4` buffer, `+8` count, `+0xc` base index; callers `0x43c055` credits, `0x480c8d` the game object) | **line lists** | reads the file into a `size + 1` heap block, then walks it: a line ends at the first `\r`, which is overwritten with `\0`; the next line starts 2 bytes later (the LF is skipped without being tested); each line is `CharToOemA`'d (cp1251 -> OEM, the font code page, [fonts](fonts.md)) and its pointer added to the list; the count is the number of terminated lines. A last line without CR LF (e.g. `credits.txt`, `town.txt`) is added to the list but not counted in `+8`. Lookup `FUN_00474733(i)` = global string `base + i` (`FUN_0041f350`). Lines are indexed from 0; an empty line is an empty string, never skipped |
| `FUN_004741ad` | **section files** | reads the whole file, appends `\0`, `CharToOemA` over the buffer, keeps it as one block (`globalmap.txt` into `DAT_006227c4`, `quest.txt`, `town.txt`, `mission<id>.txt`) |

Section lookup (`FUN_004dd05b`, `FUN_004ddb87`, `FUN_004ddc9c`) is a substring search for `#key`, the cut ends at the next `#`: see
`engine/ui/story.py` `section` (an unterminated or absent key gives an empty text; `#event1` also matches `#event10`).
A `#` anywhere in a body therefore ends the section, so the files use a lone `#` line as an explicit terminator (below).

## 2. Files (INFERRED roles unless a spec says CONFIRMED; measured structure exact)

| File | Kind | Content |
|---|---|---|
| `main.txt` (370 lines), `dialogs.txt` (177), `patch/patch.txt`, `spells.txt` (25), `spell.txt` (30), `stats.txt` (51), `unitname.txt` (109), `building.txt` (180), `itemname.txt` (492), `heropicture.txt` (27), `npcnames.txt` (2371), `itemserv.txt` (492), `sites.txt`, `tunes.txt`, `cutscene.txt`, `cutpaths.txt` | line lists | line `i` = string `i`; the index is the code of the caller (item code, unit type, text id, cut-scene code); `main.txt` strings carry `<A>` style hotkey letters ([ui-layout](../engine/ui-layout.md)); `heropicture.txt` = sprite folder names ([animation](animation.md)); `cutpaths.txt` / `cutscene.txt` = video folders / list titles ([cutscenes](../engine/cutscenes.md)) |
| `credits.txt` | line list | a line starting with `"` is a picture name ([credits](../engine/credits.md)) |
| `help.txt` | line list | chat command help; some lines start with `#` (`#kick`, `#locate`): they are text, not keys |
| `globalmap.txt` | sections | `#title<n>` / `#briefing<n>` for each world-map site `n` ([town-worldmap](../engine/town-worldmap.md)) |
| `town.txt` (242 `#` lines, 71 `===` comments) | sections | `#tips<n>` and the town scenes' story sections, `===` lines are author comments inside a body (shown only if the section is cut across them: the exe has no comment rule) |
| `quest.txt` | sections | `#quest<n>` (multiplayer quest system, unused in single player) |
| `mission<id>.txt` (id = 10, 20, .., 110: 46 files) | sections | `#briefing`, `#subobjective<n>`, `#failure<n>` (n = 2, 3, ...: the failure causes, `engine/ui/story.py` `failure_texts`), `#event<n>` (the story window script of tags `<NPC=21, IAMMALE, IAMFIGHTER, PART=1>`, `story.py`), a lone `#` line closes each; `===` comments between sections |

Not a text file: `itemname.pat` (patch data), `namemake.exe` (the original's name tool), `docs/1.txt` (readme).

## Open questions

- The role of `sites.txt`, `tunes.txt`, `stats.txt`, `npcnames.txt`, `itemserv.txt` (which callers read which line) is per-consumer and recorded in
  the spec of each consumer where built; no format question is open.
