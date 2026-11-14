# Town mode: the world map screen (L3, window id `0x41a`)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)) and of `Scenario.dll`. Marks: **CONFIRMED** (routine address given) / **INFERRED**.
Part of the L3 town spec ([design](../superpowers/specs/2026-11-13-l3-town-spec-design.md)); the shared core (`client+0x404` bits, state machine) is `town.md`.
Single player only. Names of fields are ours; offsets and routines are the exe's.

The "world map" of the player is one window class (size `0x1b4`, vtable `0x5cd760`, ctor `0x46e66b`, created once at start-up by `FUN_00483129` as `client+0xf0`, id `0x41a`,
sprites and bitmaps loaded only while it is open). `FUN_0048b419` is **not** the draw: it is the *open* routine (CONFIRMED); the draw is vtable slot `+0x2c` = `FUN_0046fdd5`.

## 1. Purpose and entry / exit

The map lets the party walk from the location it stands on to another available location of the campaign and then enters that location (mission start or town). It reads no
`Var`; the campaign state it shows is Scenario.dll's available list.

**Entry (CONFIRMED).** `FUN_0048b419` has two callers, both in the client message handler `FUN_004852d8` (table `0x488731`, byte table `0x488821`, index `msg - 0x416`):

| message | handler | what runs before the map |
|---|---|---|
| `0x41d` (mission over, victory dialog or quit) | `0x486a68` | single-player campaign path ([shell 3.3 / triggers 11.5](triggers.md)): mission torn down, roster carry-over, then **`SetPartyPoint(point of GetCurrentLocation)`** (`0x493b90`: window `+0x104/+0x108`), `ScenarioLeaveLocation(&code)`, recruit `Var(0x305)`, cutscene `code >= 0` (`0x48f919`). Next: chapter `Var(0x300) >= 0x78` -> ending `0x428`; `ScenarioIsTownAvailable(0) == 0` -> **no-town start** `0x486d4f` (`GetAvailableLocations` head -> `EnterLocation` -> post `0x468`; the map is never shown); else `window+0x1b0 := 0` and `0x486da1` calls `0x48b419` |
| `0x42d` (leave a town) | `0x487d34` | `window+0x1b0 := 0`; if `GetCurrentLocation` is a town (type 2): `SetPartyPoint(town point)`, `ScenarioLeaveLocation(&code)`, cutscene `code >= 0` (`0x487daf`), and **if the town id is 1 `window+0x1b0 := 1`** (the intro walk, 3.4); then `0x487de0` calls `0x48b419` |

Senders of `0x42d`: the three town scenes' leave click, `0x4cad72` (human town; **only when `Var(0x301) != 0`**, else the speech `plagatguard` is played), `0x4d076d` (druid town, region flag 8) and `0x4d306d`
(third town scene, region flag 8). Each first posts **`0x442` with wParam 1** (`0x4cad5d`, `0x4d0758`, `0x4d3058`): the handler `0x4884b9` writes the autosave `game%d.sav` for `9999 - 1` = **`game9998.sav`**
(description patch `0x5f`, "Abort mission and return to town") through `FUN_0048dc9f` (only in the campaign, `+0x5d8 == 2`). So the map is always preceded by that save; the sender of slot 9998 was the open question of
[saves 6](../formats/saves.md#6-the-saved-game-gamedsav) (answered here).

**`FUN_0048b419` (CONFIRMED).** `FUN_0047b8f5` on `0x626d20` = the *wait* cursor; `client+0xcc` (root window) `AddChild(client+0xf0)` (`FUN_004d3a64`); the map window's **load** (vtable `+0x80` = `FUN_0046fa4b`, 3.1);
root slot `+0x34` (redraw); `client+0x44c := 0`; **`client+0x404 |= 0x10`**; and if `DAT_006226a8` (sound on): playlist `music\map.wav` ([6](#6-sounds-music-and-tips)).

**Exit (CONFIRMED).** The walk ends in the draw (`0x4703b8`-`0x4707ba`): `0x470fee` sends the window its own message **`0x445`** (the dialog OK): base `FUN_004dc2b0` calls the unload (vtable `+0x84` = `FUN_0046fc55`: `+0x194 := 0`, frees
bitmaps, sprites, route, graph) and posts **`0x44c`** (wParam = the window) to the client; the client handler (`0x48556d` -> `FUN_004891d8`, branch `0x489cba`) compares the window with `client+0xf0` and
clears **`client+0x404 &= ~0x10`**. Then the draw posts **`0x468`** and calls `ScenarioEnterLocation(location)` ([4](#4-messages-in-out)). The map has no other exit: no cancel, no back, no menu (2.5, 4).

## 2. Layout per resolution

The window rect is the screen-centred 640x480 area: `(fx, fy, W - fx, H - fy)` with `fx = (W - 640) / 2`, `fy = (H - 480) / 2` = `DAT_00621420 / 24 / 28 / 2c` (CONFIRMED, ctor call `0x4836ed`, values `0x482176`-`0x4821c3`).
Everything below is relative to its origin `O = (fx, fy)` and the pointer is taken as `mouse - O` (CONFIRMED `0x471017`, `0x4716aa`). All coordinates are screen pixels, no scaling.

| mode | window rect | O |
|---|---|---|
| 640x480 | (0, 0, 640, 480) | (0, 0) |
| 800x600 | (80, 60, 720, 540) | (80, 60) |
| 1024x768 | (192, 144, 832, 624) | (192, 144) |

Nothing is drawn outside the rect by this window; what is behind it at 800x600 / 1024x768 is not this window's business (INFERRED black like the shell screens, [open question 3](#8-open-questions)).

Drawn items (CONFIRMED `FUN_0046fdd5`; `x, y` = the location point plus `O`; frames: 3.2). Order = z order:

| # | item | position (relative to O) | when |
|---|---|---|---|
| 1 | background bitmap | (0, 0), 640x480 | always |
| 2 | route dots (BallMap 8x8) | centred on route point `i` (`x - 4, y - 4`) for `i % 8 == 0` | idle: every point of the route; walking: `i < min(progress, count - 1)` |
| 3a | **idle**, normal map: one flag per available location, location point `p`, `p != party`: **MissionFlag** at `(p.x - 5, p.y - 0x29)` when `p == destination`, else **FlagOnMap** at `(p.x - 5, p.y - 0x25)` | frame `+0x128` | `+0x1b0 == 0`, `+0x12c == 0` |
| 3b | **walking**: Cross at `(dest.x - 10, dest.y - 12)`, frame `min(+0x134, 12)` | no location flags while walking | `+0x12c != 0` |
| 4 | party flag: normal map **YourFlag** at `(party.x - 0x14, party.y - 0x2c)`; intro **Flag** at `(party.x - 10, party.y - 0x18)` | frame `+0x130` | always |
| 5 | title text, centred at x `230`, y `27` | font4 (16x16), gradient brown `DAT_00620e80` row 0 | `+0x1b0 == 0` and the title is non-empty |
| 6 | description lines, centred at x `230`, y `48 + 10 i` | font2 (8x10), colour table `0x61faa0`; the **last line loses its last 2 characters** (the CR LF of the section) | with 5 |

(INFERRED reading of the call arguments `(x, y, text, 2, colour)`: `2` = centre, [ui-layout 11](ui-layout.md); the wrap rect of the description is `(0x46, 0x30, 0x186, 200)` = x 70..390, centre 230, which agrees; `FUN_0045d479`.)
The intro branch `+0x1b0 != 0, +0x12c == 0` would draw **Flag1** at `(p.x - 4, p.y - 0x20)` per location, but is unreachable (3.4). No panel, button, scroll bar or frame is drawn: the picture is the whole screen.

**Hover regions: none. Tooltips: none** (INFERRED): the tooltip slot `+0x14` = `0x471017` walks the window's region list (`+0xb8` rects, `+0xa4` ids) which the class never fills (the only references are its ctor / dtor / unload `0x46e55d`-`0x46ebee`);
the right-click rect `+0x114` that would also disable it is a dead remnant (2.1 note). The hover cursor is `0x626ccc` *select* (`FUN_0047162b`, `FUN_004739b0`) after every draw and move.

2.1 Dead code of the class (INFERRED: no xref to the entry, no vtable slot): `0x470803`-`0x470f71` (a scroll tab UI over `Scroll01..03`, `ScrollP1..3` and the sounds ScrollUp / ScrollDn), `0x46eb4d` (collects `GetAllLocations` points
into `+0xcc`), the zero-size button built in the init `0x46ec0b` (`FUN_004d5470(4, rect (0x21c, 0x1c2, 0x21c, 0x1c2), " ", message 0x7fff)`, never visible), the right-click handler `0x471957` (rect around `+0xfc` of `Hero.bmp`'s size `+0xf4`, `+0x114` set; `0x471a55`
clears it). Nothing here has a visible effect.

## 3. Widgets and resources

### 3.1 Load (`FUN_0046fa4b`, CONFIRMED)

Order: `FUN_00437ee0`; **sprites and bitmaps `FUN_0046eeb0`**; **sounds `FUN_0046edf2`**; text `main\text\globalmap.txt` (whole file, `FUN_004741ad` into `DAT_006227c4`); the path graph (`FUN_00471a75`, 3.3); `+0x154` = the adjacency
matrix, `+0x158` = the node list (`FUN_0047242a`); `+0x130 := 0`, **`+0x134 := 0`** (`0x46fbae`), `+0x190 := 0`; `+0x194 := 1` (loaded); then the window opens (`FUN_004dc232`: `+0x5c := 1`, show, enable, take the focus `0x4d3e14`).
The window is unloaded after every walk, so every opening starts with `+0x134 = 0` and `+0x12c = 0`: one walk per opening.

### 3.2 Resources (`0x46eeb0`, `0x46edf2`; sizes read from the install)

| field | file (game path, lower case) | what | frames / size |
|---|---|---|---|
| `+0x68` | `main/graphics/global.map/gmap.bmp` (`+0x1b0 == 0`) or `umoir.bmp` (`+0x1b0 != 0`, loader `0x46eeb0`) | background | 24-bit 640x480 |
| `+0x6c` | `graphics/global.map/hero.bmp` | only its size is read (`+0xf4/+0xf8`), never drawn | 24x40 |
| `+0x70` | `graphics/global.map/ballmap.bmp` | route dot | 8x8 |
| `+0x74` | `graphics/global.map/flag1/sprites.16a` | intro flag (dead branch) | 9 |
| `+0x78` | `.../flag/sprites.16a` | intro party flag | 4 |
| `+0x7c` | `.../cross/sprites.16a` | destination Cross | 13 |
| `+0x80` | `.../missionflag/sprites.16a` | selected location | 9 |
| `+0x84` | `.../flagonmap/sprites.16a` | other available locations | 9 |
| `+0x88` | `.../yourflag/sprites.16a` | party flag | 4 |
| `+0x8c`..`+0xa0` | `scroll01..03.bmp`, `scrollp1..3.bmp` | loaded, no reader in a reachable routine (2.1) | 164x12/16, 120x12/16 |
| `+0x180`..`+0x18c` | `sfx\ScrollUp.wav`, `ScrollDn.wav`, `Point1.wav`, `Point2.wav` | only Point1 / Point2 are played | |

Frame counts and the clock are in [animation 4.11](../formats/animation.md#411-town-scenes-townbirds-town_druid) ("World-map flags"; the UI sequence keys `ui:map_*` exist for Flag1 / Flag / MissionFlag / FlagOnMap / YourFlag; the **Cross has no set yet**).
Sprite draw is vtable `+0x18(x, y, frame, 0, 0)`; whether `(x, y)` is the sprite's anchor or its top-left is [open question 1](#8-open-questions).

### 3.3 The path graph (`FUN_00471a75`, CONFIRMED structure; bookkeeping INFERRED)

A 640x480 `u16` visited grid (`+0x20`, index `x * 480 + y`) and the **path bitmap** `graphics/global.map/pathmap.bmp` (normal map; 8 bit, 4-entry palette, **rows bottom-up: `y = 479 - row`**) or `umoirpath.bmp` (intro,
`+0x1b0 != 0`, `0x471de8`): pixel `1` = path, pixel `2` = node, `0` = nothing.

- **Nodes** = every pixel with value 2, scanned `x` outer, `y` inner (column-major); PathMap has 100, UmoirPath 81 (count at `+4`, points in a list).
- **Edges** (`FUN_00471f0d`, tracer `FUN_004721ff`): from each node, depth-first along unvisited path pixels, scanning the 8 neighbours with `cx` = x-1..x+1 outer and `cy` = y-1..y+1 inner (the first hit is taken and recursed into; a
  neighbouring *other* node pixel ends the trace and is appended); the result is a polyline that **includes both end nodes**, stored in the matrix as `[i][j]` and reversed as `[j][i]` (`n x n` pointers, `+0x154`).
- Headless check of this reading (emulated from the two routines, not run in the exe): PathMap -> 107 edges, **every path pixel in exactly one edge** (`2552 + 2 * 107 = 2766` points), the graph is connected;
  UmoirPath -> 90 edges, connected, 35 path pixels left uncovered (stubs). The 47 of the 49 location points lie exactly on a PathMap node; the two that do not (town 1, mission 10) are exactly the UmoirPath nodes that matter (3.4).
- **Route** `FUN_0047110e(from, to)`: `from == to` -> the route is the two points `[from, to]`; else the node indices of both points, then `FUN_004713c2` = depth-first branch and bound over the adjacency (nodes in ascending index
  order, no node twice, **cost = sum of the edge point counts**, a path replaces the best only when strictly cheaper): the **cheapest path, ties to the first found**. The route list (`+0xe0`) is the concatenation of the edge polylines
  (a junction node appears twice). It is recomputed only when the destination changes.

### 3.4 Intro mode `window+0x1b0 != 0` (CONFIRMED)

Set only by `0x42d` after leaving **town 1** (the first walk of a new game). Background Umoir, path graph UmoirPath, no text. On the first draw (`+0x12c < 8`, `0x46fe5d`): destination = the **head** of the available list
(mission 10), route from the party point (town 1, set by `0x42d`), `+0x12c := 8`: the walk starts by itself, no input needed. Route cost 216 points (worked example, DFS rule above) -> about 27 draws; the end enters mission 10 (`0x47074e`: the head) and posts `0x468`.

## 4. Messages in / out

**Into the window** (base dispatch `FUN_004d4769`; mask `0x10` is neither 1 nor 0, so keys go to the window manager and from there to the focused child, [shell 3.5](shell.md#35-keys-in-the-shell-esc-confirmed)):

| message | slot | routine | effect |
|---|---|---|---|
| `0x402` (tick) | `+0x48` | `0x4715a5` | at most every **100 ms** (`timeGetTime`, first one at once) calls the draw through slot `+0x34` |
| `WM_MOUSEMOVE` | `+0x4c` | `0x471679` | idle (`+0x12c == 0`): hover update (below); always the cursor |
| `WM_LBUTTONDOWN` | `+0x54` | `0x471918` | idle: `+0x12c := 8` = **start walking to the hovered location**; walking: finish at once (`0x470f72`) |
| `WM_KEYDOWN` / `WM_CHAR` | `+0x6c` / `+0x74` | `0x470fd4` / `0x470fba` | while walking: finish at once; **all keys are consumed, ESC included** (no menu, no skip of the choice) |
| `WM_LBUTTONUP`, `WM_RBUTTONUP`, dbl clicks | | `0x4737f0` (returns 0), `0x471a55`, default | nothing |
| `WM_RBUTTONDOWN` | `+0x60` | `0x471957` | dead remnant (2.1) |
| `0x445` / `0x446` | base | `0x4dc2b0` | unload + post `0x44c` (only `0x445` is ever sent) |

**Hover (`0x4716aa`, run on every move and on every idle draw while the route is empty).** Among the available locations (list order) take the one whose point is **nearest to the pointer by squared distance, no radius limit, strict `<`
so a tie keeps the earlier list entry**; it becomes the destination (`+0x10c/+0x110`), and if the destination changed the route `party -> destination` is rebuilt (3.3) and title / description are set from `globalmap.txt` (5). The preview route shows as dots.
**Click** needs no hit test: the nearest location is always taken (any click starts the walk, also on its own party location: route `[p, p]`, the town is then re-entered).

**Walk (draw, `0x470153`-`0x4707ba`; one step per draw = per 100 ms).** Draw `k = 1, 2, ...`: `+0x12c` = `8k` before the draw; dots for `i < min(+0x12c, count - 1)`, `i % 8 == 0` (one new dot per draw); Cross frame `min(+0x134, 12)`; after it
`+0x134 += 1`, `+0x12c += 8`; while `+0x12c < count - 1` and the current Point sound is not playing, the other of **Point1 / Point2** is played (`0x438570`, alternating by `+0x190`). Done after the first draw with `+0x12c > count` **and**
`+0x134 > 14`, i.e. `max(15, ~count / 8)` draws: **at least 1.5 s**. Then: party point := destination, `+0x12c := 0`, route cleared, and the end sequence:

| step | call | |
|---|---|---|
| 1 | `0x470fee`: own message `0x445` | unload, `0x44c` posted, `client+0x404 &= ~0x10` (1) |
| 2 | post **`0x468`** to the client | queued |
| 3 | `ScenarioEnterLocation(loc)` | intro: the head; normal: the first available location whose point equals the destination (list order) |

**`0x468` (client handler `0x487dea`, CONFIRMED) then** reads `GetCurrentLocation`: type 1 (mission): collects the hired mercenaries (for `i = 0..19` with `Var(0x200 + i)` and `Var(0x214 + i)` non-zero, `i + 1`), `FUN_004f36c0(server, Var(0x300), list)`,
the mission start `FUN_0048c8a3(0)` (it posts the `0x442` auto-save `game9999.sav`, [saves 6](../formats/saves.md#6-the-saved-game-gamedsav)); type 2 (a town): `0x41aaa5(0, 0)` and `0x48bbc0` (the town screen; windows, messages and mode bits are `town.md`).
**The map sends nothing to the hero screen, shop or inn.** Messages named for the next researchers: `0x41d`, `0x42d` (in), `0x442` (autosave), `0x44c` (window closed), `0x445` (dialog OK), `0x468` (enter the current location), `0x42e` (town, music).

## 5. Data read / written

### 5.1 Scenario.dll calls (ordinal -> exe pointer, loader `0x4818e7`)

| call | pointer | used by the map |
|---|---|---|
| `GetAvailableLocations` (14) | `0x62715c` | hover, flags, head, entry (draw and `0x4716aa`) |
| `EnterLocation` (5) | `0x627294` | end of the walk |
| `GetCurrentLocation` (18) `0x62718c`, `LeaveLocation` (6) `0x627160`, `IsTownAvailable` (16) `0x62758c`, `GetVar` (1) `0x62729c` | | only the entry handlers `0x41d` / `0x42d` / `0x468` |
| `GetAllLocations` (19) `0x627588` | | dead helper `0x46eb4d` |

A location object is `{ +0: type (1 mission, 2 town), +4: id, +8: CPoint x, +0xc: y }`; the list is a singly linked list of object pointers (`FUN_00472dc0` head, `FUN_00472de0` next). The point is the DLL's (static constructor
`0x100038e0(type, id, x, y, 0, 0)`; `CRect(x, y, x + w, y + h)`); **map coordinates are 640x480 picture pixels**.

### 5.2 Available list and the campaign

The list is [campaign.md](campaign.md) `CampaignGame.camp.available` (`engine/sim/campaign.py` `Scenario.available`, appended at the tail by completion unlocks and `TalkTo`, [triggers 11.2](triggers.md)); the map shows **missions and towns together**
(a town stays in it, except town 1 which leaves when left); `0x486d4f` / the intro use the head. The party point is the point of the location the party **last left** (mission just finished, `0x41d`; town just left, `0x42d`); at a new game it is town 1. It lives only in the window
(`+0x104/+0x108`, **not saved**: INFERRED, `FUN_0048dc9f` writes no such field; a loaded game re-derives it from the entry path, [open question 4](#8-open-questions)).
`Var(0x300)` is read only by `0x41d` (`>= 0x78` = ending instead of the map). The map **writes nothing** to the DLL except `EnterLocation` (which zeroes `Var(0x2f0..0x2ff)` and stores the location).

### 5.3 Location points (read from `Scenario.dll` by extraction, 49 objects; the all-locations list order is town 1, 2, 3 then missions 10, 20, 21, 30, ...)

Recipe: every call `0x100038e0` is preceded by `push 0`, `push 0`, `push y`, `push x`, `push id`, `push type`, `mov ecx, object`; the objects in the list at `0x10037028` are the 49 below (three further objects at `0x10037580` / `0x10037598` / `0x100375b0`
(ids 10 / 20 / 30 with other points) are in no list: dead). Verified: all but town 1 and mission 10 sit on a PathMap node, town 1 and mission 10 on UmoirPath nodes (headless check, [7](#7-what-the-headless-side-can-test-what-needs-eyes)).

towns: 1 (215, 234); 2 (370, 305); 3 (194, 225).
missions: 10 (302, 158); 20 (380, 364); 21 (423, 367); 30 (331, 395); 31 (443, 225); 32 (457, 202); 40 (339, 226); 41 (403, 228); 42 (531, 207); 43 (454, 358); 50 (210, 260); 51 (450, 240); 52 (132, 303); 53 (292, 191); 60 (511, 301); 61 (475, 312);
62 (253, 169); 63 (385, 221); 70 (86, 193); 71 (337, 306); 72 (530, 255); 73 (343, 347); 74 (595, 313); 75 (356, 359); 76 (111, 227); 77 (406, 117); 80 (554, 299); 81 (510, 182); 82 (424, 186); 83 (521, 372); 84 (552, 377); 85 (393, 360);
86 (67, 213); 87 (509, 161); 90 (283, 244); 91 (477, 269); 92 (93, 269); **93, 94, 95, 96 all (306, 148)** (the four class slots; only one is ever available); 100 (388, 140); 101 (273, 300); 102 (351, 190); 103 (575, 362); 110 (448, 140).

### 5.4 Text (`main\text\globalmap.txt`, cp1251, `#tag` sections; `FUN_004ddec6` title, `FUN_004ddff8` body; CONFIRMED)

| location | title tag | body tag |
|---|---|---|
| mission `n` (type 1) | `#title<n>` | `#briefing<n>` |
| town `n` (type 2) | `#town<n>` | `#description<n>` |

The file has 44 mission pairs (every mission except 10 and 20, which are never shown on the map: after mission 10 the list is `[20]` and after 20 a town is available only from town 2 on) and `#town2` / `#description2`, `#town3` /
`#description3` (no town 1). The title string is the section text minus its last 2 characters; the body is word-wrapped into the rect `(70, 48, 390, 200)` with font2 (`FUN_0045d479`) into the line array `+0x19c`. **It is not `town.txt`**
(`town.txt` belongs to the town screens, `0x48bbc0`); the map uses no `main.txt` string.

## 6. Sounds, music and tips

- **Music** (CONFIRMED `0x48b419`; [audio 4.1](audio.md#4-music)): a one-track playlist `music\map.wav` replaces the current playlist, only when `DAT_006226a8` is set; it repeats; the mission music was stopped at `0x41d`. Nothing stops it when the map closes: the next
  screen (mission start `0x4924cd`, town `0x48bbc0`) sets its own playlist.
- **Sounds**: only the walk ticks `sfx\Point1.wav` / `Point2.wav` (play with priority `0x80`, [audio 3.1](audio.md#31-voices-and-priority-confirmed-0x45aa2f-0x45ab9c-0x45ade7)), alternating, one per draw while the route is being laid. No click, no hover, no enter / leave sound. The cursor is the wait cursor while loading, then *select*.
- **Tips / tooltips**: none; no `#tips` window opens on the map (the town / shop tips are the town screens').

## 7. What the headless side can test, what needs eyes

Headless (pure functions of the install, all deterministic): the **graph** (nodes, edges, cover check `2766 = 2552 + 2 * 107`, connectivity, the 47 + 2 location points on nodes), the **route** (cheapest path, tie rule, `[p, p]`), the **hover rule** (nearest by
squared distance, first on ties, no radius), the **walk schedule** (dots per draw, `max(15, count / 8)` draws, Point sound alternation, the end sequence `0x445 -> 0x44c -> 0x468 -> EnterLocation`), the **intro** (town 1 -> mission 10, cost 216, no input), the entry decisions
(`0x41d`: ending / no-town start / map; `0x42d`: town 1 -> intro), `globalmap.txt` tag coverage (every mission except 10 and 20, towns 2 / 3), the Scenario location table by extraction, and the `CampaignGame` link (`start_mission(n)` for the entered mission; `engine/shell/locations.py`
is replaced by this screen: its mission list is the available list, its "choose a mission" is the click).

Needs your eyes: the placement of the flags and the Cross on the art (anchor, [open question 1](#8-open-questions)), the look and speed of the 10 fps flag / Cross animation, the dotted route (preview and laying), the text block over the picture (centre x 230,
font and colours), the Point ticks and the map music by ear, the *select* cursor, the picture edges at 800x600 / 1024x768, that no key (ESC) leaves the screen.

## 8. Open questions

1. *(answered)* **The flag / Cross draw point is the frame's top-left.** A `.16a` file has no hot spot ([sprites: Placement](../formats/sprites.md#placement-no-hotspot-in-the-file); the draw takes the position as given), and the install's frame sizes agree with the offsets as top-left corners: **Cross 20 x 24 at (dest - (10, 12))** is centred on the destination point, **YourFlag 40 x 48 at (party - (20, 44))** is centred horizontally with its base 4 px below the point, FlagOnMap 40 x 40 at (p - (5, 37)), MissionFlag 44 x 44 at (p - (5, 41)), intro Flag 20 x 24 at (party - (10, 24)), Flag1 32 x 32 (dead branch). The Cross set (13 frames) decodes like the others.
2. *(answered)* **The description wrap rect.** The call (`0x4718c9`-`0x4718e7`) builds `RECT(l, t, r, b)` through `0x41e210` from the pushes `0x46, 0x30, 0x186, 0xc8` (last pushed = first argument): **(70, 48, 390, 200), width 320, height 152**, then `FUN_0045d479(rect, text)` with the font table `0x620500` (`FUN_0045d2b5` measures the wrapped line count first, `0x45d4e2` draws line by line). The INFERRED 320 is now CONFIRMED.
3. What the client paints around the 640x480 window at 800x600 / 1024x768 (black is INFERRED; `FUN_00452bde` / `FUN_00452c3a` bracket the draw).
4. *(answered)* **A loaded save and the party point.** The load routine `FUN_0048db37` (after `FUN_0040d480` read the stream) asks `FUN_0048c214`, which reads the save's own `.reg` tree key **`CurrentState` / `InBattle`** (default 1): non-zero -> the mission is resumed (`FUN_0048c8a3(1)`); **zero -> the party was in a town**: the server is rebuilt (`0x41ab50`, `0x4f84f8`, message pump), `0x48c2e9`, then **`FUN_0041aaa5(0, 0)` = the town scene of the saved location** and `0x42e` (CONFIRMED). The map is never shown after a load, and the party point is not stored: it is set again from `GetCurrentLocation` when the town is left (`0x42d`, [1](#1-purpose-and-entry-exit)). A save made in a mission (autosave `game9999`) resumes the mission; `game9998` (made when leaving a town) has `InBattle = 0` only if the writer stored it so (the key's writer is in the save routine `FUN_0048dc9f`, not traced: INFERRED 0 for a town / 1 for a mission).
5. Exact tracer bookkeeping of `FUN_00471f0d` (the 35 uncovered UmoirPath pixels, several branches out of one node): only the structure and the PathMap cover are confirmed; the headless emulation stands in until a run of the exe.
