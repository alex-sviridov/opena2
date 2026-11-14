# Town mode: index, state machine, build plan (L3)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)). Marks: **CONFIRMED** / **INFERRED**. Design: [L3 spec](../superpowers/specs/2026-11-13-l3-town-spec-design.md).
This is the hub of the town spec. The per-window facts are in the five window docs and are not repeated here; this doc owns the **shared core** (mode mask, window objects, message flow), the **state machine** of a visit, the **link to the engine** (`CampaignGame`, the L2 stand-in), what is testable without eyes, and the **build steps**. Single player only (`client+0x5d8 == 2`).

| doc | window | mode bit | opener / closer |
|---|---|---|---|
| [town-worldmap.md](town-worldmap.md) | world map `client+0xf0` (`0x46e66b`) | `0x10` | `0x48b419` / `0x445 -> 0x44c` then `0x468` |
| [town-scenes.md](town-scenes.md) | town scene `+0x110` / `+0x114` / `+0x118` | none (mask 0) | `0x48bbc0` |
| [town-hero.md](town-hero.md) + [town-inn.md](town-inn.md) | inn `+0x104` human / `+0x10c` Kaarg / `+0x108` druid | `4` | `0x48b885` (msg `0x42b`) / `0x49b69b` |
| [town-shop.md](town-shop.md) | shop `+0xf8` human / `+0x100` Kaarg / `+0xfc` druid | `2` | `0x48aea8` (msg `0x42a`) / `0x4b956e` |

## 1. Shared core (CONFIRMED, details in the linked docs)

- **Town ids**: 1 human, 2 Kaarg, 3 druid, from `GetCurrentLocation` (`FUN_00473a30`); the id picks the scene, the inn and the shop class ([town-hero 1](town-hero.md#1-purpose-and-entry-exit)). All window objects are built once at start-up and live for the session; every opening re-runs the window's *load*, every close its *unload*.
- **The mode mask** `client+0x404`: bits `1` mission, `2` shop, `4` inn, `8` modal, `0x10` world map, others in [town-hero 1](town-hero.md#1-purpose-and-entry-exit). **A town scene is mask 0.** `0x226` = the screens that show the hero arrows. Entry guard of inn and shop: `mask == 0`. The return message `0x42e` (scene again) is posted only when the mask is **exactly** the window's own bit (`4` / `2`) at the click.
- **Messages** (shared table: [town-worldmap 4](town-worldmap.md#4-messages-in-out)): `0x42b` open inn, `0x42a` open shop, `0x42e` back to the scene, `0x42d` leave the town (to the map), `0x442` autosave, `0x445` window-self "OK" -> base unload -> `0x44c` "child closed" (the client clears the bit, shop sends server `0x36`), `0x468` "enter the location" after a walk, `0x414` / `0x415` hero arrows.
- **Hero list and arrows**: one list rebuilt at each load (creation order of the player's units, wrapping index), used by inn and shop ([town-hero 3 / 5](town-hero.md#3-widgets-and-resources)).
- **No window has a cancel key but ESC** (inn: ESC = Exit; shop: ESC = Exit; map: no key leaves it).
- **Gold** is the party's, kept by the server; only the shop screen touches it; the inn never reads it ([town-inn 1](town-inn.md)).

## 2. State machine of a visit (CONFIRMED edges; each edge names its routine)

```
                         new game / chargen Accept
                                   |
   mission won (0x41d) ------------+--- no town available ----> start head mission directly (0x486d4f)
   (carry-over, SetPartyPoint,     |
    LeaveLocation, recruit)        +--- Var(0x300) >= 0x78 ---> ending (0x428)
                                   v
                              WORLD MAP  (mask 0x10)  <------------------------------+
                  walk to a location, then 0x445 -> 0x44c -> 0x468 (EnterLocation)    |
                       |                                  |                           |
              type 1 (mission)                       type 2 (town)                    |
                       v                                  v                           |
              0x48c8a3: autosave game9999        TOWN SCENE (mask 0, music b14/b16/b15)
              mission starts (mask 1)                |       |        |              |
              ... victory -> 0x41d                   |0x42b  |0x42a   |leave click   |
                                                     v       v        v              |
                                              INN (4)   SHOP (2)   0x442 (autosave   |
                                               ESC/Exit  ESC/Exit   game9998), 0x42d |
                                                  \       /          Var(0x301) gate |
                                                  0x445->0x44c->0x42e (back to scene)|
                                                                     0x42d: SetPartyPoint,
                                                                     LeaveLocation, cutscene,
                                                                     town 1 -> intro walk ---+
```

Rules (all from the window docs):
1. **Mission over -> map or town.** `0x41d` runs the L1 end-of-mission flow ([campaign](campaign.md)), then: ending if `Var(0x300) >= 0x78`; no town available -> the head of the available list is entered at once (the map is never shown); else the map ([town-worldmap 1](town-worldmap.md#1-purpose-and-entry-exit)).
2. **Map -> location.** The walk ends with `EnterLocation(id)` and `0x468`: a mission (type 1) is started through `0x48c8a3` (with the `game9999.sav` autosave, `0x442`); a town (type 2) builds the **scene** (`0x41aaa5(0, 0)`, `0x48bbc0`).
3. **Scene -> inn / shop / leave.** Click regions: human scene 1 shop, 2 inn, 8 leave; the other scenes use the flags 1 / 2 / 8 ([town-hero 1](town-hero.md#1-purpose-and-entry-exit)). The inn opener runs `EnterInn` + `FUN_004f312a` (units for the words) **at every opening**; the shop opener sends `0x32` EnterShop and the load regenerates / reads the stock ([town-shop 1](town-shop.md#1-purpose-and-entry--exit)).
4. **Leave.** `0x442` (autosave `game9998.sav`, "Abort mission and return to town"), then `0x42d`: `SetPartyPoint`, `ScenarioLeaveLocation`, cutscene if its code is `>= 0`, town 1 -> the **intro walk** flag, back to the map. The human scene leaves only when `Var(0x301) != 0` (else the speech `plagatguard`); the druid / Kaarg readers of `Var(0x301)` are open ([triggers open questions](triggers.md#open-questions)).
5. **The mask is the only state.** There is no state object: the screens are windows on the root, `client+0x404` records which are open, and each closes by `0x44c`. A second click on the scene while a bit is set does nothing (guard).

## 3. Link to the engine (hand-over, no code in L3)

| exe | engine today | what the town needs |
|---|---|---|
| `0x41d` flow, carry-over, recruit | `CampaignGame.leave_mission` ([campaign](campaign.md)) | split the stand-in: keep the carry-over / `LeaveLocation` / recruit, stop calling `visit_towns` from it when the town screens exist |
| `EnterInn(words)` at every inn opening, `TalkTo` per click | `sim/campaign.enter_inn_words`, `talk_to`; `CampaignGame.visit_towns()` = the policy "talk to everyone, hire nobody" | the inn screen calls the same two functions per click; **`visit_towns` stays as the headless oracle** and must give the same `TalkTo` set as a scripted full click sequence ([town-inn 4](town-inn.md#4-what-the-headless-side-can-test-what-needs-eyes)) |
| available list, party point | `Scenario.available`; no party point | the map window's state (`+0x104/+0x108`, not saved: [town-worldmap 5.2](town-worldmap.md#52-available-list-and-the-campaign)) |
| shop table, gold | gold on `CampaignGame`, **no shop table** ([triggers 11 "Not modelled"](triggers.md)) | the DLL shop blocks + `itemgen` stock, [town-shop 5](town-shop.md#5-data-read--written) |
| scene, map, windows | `engine/shell/locations.py` (L2 text stand-in: party, gold, missions, Main Menu) | replaced screen by screen; the stand-in stays until the map exists |
| mask, window table | `engine/shell/machine.py` (`GRAPH`) | a mask-like state for the town screens: scene / inn / shop as `Screen`s of the shell graph, the map as one, `0x42e` and `0x42d` as transitions |

## 4. What the headless side can test, what needs eyes

Headless (pure; each is stated in the window docs): the map graph, route, hover and walk schedule ([town-worldmap 7](town-worldmap.md#7-what-the-headless-side-can-test-what-needs-eyes)); the window-by-town table, the mask arithmetic, the entry guard, the exit sequence `0x445 -> 0x44c -> 0x42e` ([town-hero 7](town-hero.md#7-what-the-headless-side-can-test-what-needs-eyes)); the inn handlers' state changes and keys ([town-inn 1](town-inn.md)); the trade state machine and the money rules ([town-shop 7](town-shop.md#7-what-the-headless-side-can-test-what-needs-eyes)); the state machine of section 2 as a transition table over fake windows (every edge above, including the guards and the `Var(0x301)` gate); the autosave slots written on each edge (`9998` on leaving a town, `9999` on starting a mission).
Needs your eyes / ears: everything in the "needs eyes" lists of the window docs; plus the scene (hover regions, animations: [animation open questions](../formats/animation.md#open-questions)), the transitions' feel (wait cursor, the black fill around the 640x480 area at larger resolutions: [town-worldmap 8](town-worldmap.md#8-open-questions) 3), the music changes (`map.wav`, `b14` / `b15` / `b16`).

## 5. Build steps (refined effort; every step ends with the golden / unit tests it can have, then a play-test)

The old plan counted `town` as one block. The research splits it into six steps; sizes are guesses from the amount of confirmed data (S = a day of work, M = several).

| step | content | depends on | headless tests | needs eyes |
|---|---|---|---|---|
| **L4 town core** *(done 2026-11-14)* | the mask + the transition table of section 2 as pure code, the town ids / window table, `0x42e` / `0x42d` rules, autosave-slot events, `Var(0x301)` gate; wire into `shell/machine.py` with placeholder screens | L2 | the table over fake windows, edge coverage | none |
| **L5 world map** *(done 2026-11-14)* | graph + route + walk + text + flags (needs the Cross set, [animation](../formats/animation.md#open-questions)); replaces `locations.py`'s mission list; intro walk | L4 | graph / route / schedule / intro | flag anchor, route dots, music |
| **L6 town scenes** (done) | the three scenes: art, animations, hover regions, click -> inn / shop / leave, NPC speech clicks, music ([town-scenes](town-scenes.md): the data recipe is its section 7) | L4 | region table, transitions | everything visual |
| **L7 inn** | the window: panels, person strip, Hire / Dismiss / Talk / About, hero arrows, dialogue window + speech; the `visit_towns`-equivalence test | L4, L6 | handlers, keys, equivalence with `visit_towns` | layout, captions (open), sounds |
| **L8 shop** | shop windows, the DLL shop table + stock, trade state machine, gold | L4, L6 | trade rules, stock, messages | layout, animations, sounds |
| **L9 close-out** | remove the stand-in, play-test list, coverage / CLAUDE.md status | all | the campaign test through the real screens (scripted clicks) | the whole town loop |

Order: L4, then L5 and L6 (independent), then L7 and L8 (independent), L9. Open research items that block a step are listed per window doc; the ones that block **drawing** (captions, rects, hit regions) are all "layout numbers": they are read from the exe at the start of the step that draws them (L5 / L6 / L7 / L8), not before.

### L4 as built

`engine/town.py` (pure): `TownCore` = the mask (`client+0x404`) + the message flow (`post` / `pump`: `0x445 -> 0x44c -> 0x42e` is a chain of posts), `view` (map / scene / inn / shop / mission / ending), `events` (autosave 9998 / 9999, music, speech `plagatguard`, cutscene, mission start), the window table `TOWNS`, `EDGES`. Rules as section 2: entry guard `mask == 0`, `0x42e` only when the mask is exactly the window's own bit, human leave gated by `Var(0x301)`, town 1 leave sets the intro flag, `0x41d` = `mission_over(Outcome)` (ending / head mission at once / map). `engine/shell/town.py`: placeholder `town` / `inn` / `shop` screens (Exit / ESC); `locations` (the L2 stand-in for the map) now walks through the core and lists the available towns after the missions; `Shell.town_core()` / `drain_town()` turn events into services (`Services.autosave`, playlist, sound). Tests `tests/test_engine_town.py` (22 core + shell tests, no install).
REA round after L4 (CONFIRMED): (a) the druid scene's click handler `0x4d06cc` (region 8) and the Kaarg one (`0x4d3058`) post `0x442` + `0x42d` with **no `Var` test** (their only `GetVar` reads are `Var(0x300)` texts, `0x4d07ec` ... `0x4d3188`); `Var(0x301)` is read by the human scene's leave (`0x4cad41`) and the gate animations (`0x4cd100`, `0x4cdd0f`) only; (b) `0x41d` (`0x486a68`) tests `mask & 1`, `0x48da92` clears bit 1 (`and al, 0xfe`, `0x48db28`); (c) order: mission time, teardown, carry-over `0x4ebd5f`, `SetPartyPoint` (`0x493b90`) **before** `ScenarioLeaveLocation` (`0x627160`), recruit `0x4f312a`, cutscene `0x48f919` if code >= 0, ending test `0x493da0`, then no town (`0x62758c`) -> enter the head + `0x468`, else `window+0x1b0 := 0` and the map; (d) a refused human leave posts nothing but the speech (`0x4cad85`). DECISIONs: (1) *(was open, now CONFIRMED above)* druid / Kaarg leave without the gate; (2) until L5 the stand-in map is shown after a mission even when no town is available (the exe starts the head mission at once; the core already does, the shell turns that outcome into `world_map`); (3) the autosave events reach `Services.autosave`, which does nothing: saving waits for the user's format decision; (4) the town scene playlists are `town1` / `town2` / `town3` (b14 / b16 / b15) in `MUSIC_SCREENS`; (5) `visit_towns` still runs inside `leave_mission` (the inn screen replaces it in L7).

### L5 as built

`engine/worldmap.py` (pure): `load_locations` (the 49 points read from `Scenario.dll` by the constructor-push pattern at run time, nothing stored), `PathGraph` (nodes, edge tracer, cheapest-path `route`), `nearest` (hover), `Walk` (the draw schedule), `load_texts` / `title_and_body` (`globalmap.txt`), `WorldData` (the install side; straight-line paths and stand-in points when the files are missing). `engine/shell/locations.py` is now **the map screen** (name `locations`, no buttons): the 640x480 picture (`gmap.bmp`, intro `umoir.bmp`), the pointer picks the nearest available flag, dots show the route, a press starts the walk (a dot and a Point sound per 100 ms, the Cross at the destination, at least 15 draws), a press or key during the walk finishes it, the end is `TownCore.walk_to` (mission start / town scene); the intro map walks to the head of the list by itself (`TownCore.intro`, set by `chargen` Accept until the town scene exists); every key is consumed (no menu, no way back: the exe's). Verified headless against the spec's numbers (`tests/test_engine_worldmap.py`: 100 / 81 nodes, 107 edges covering 2766 points, 47 of 49 points on nodes, intro route 216 points = 27 draws, texts for every shown location) and by a rendered picture (flags, dots, Cross, title and description on the parchment).
REA round (CONFIRMED): the walk's end test `0x4703b8`-`0x4703e3` is `+0x12c > size` and `+0x134 > frames + 1` after both counters grew (the schedule in `Walk`); the Point-sound rule (round 2 in town-worldmap: the current sound must have finished, the first one is Point2); the Cross frame is `min(+0x134, frames - 1)` (`0x470287`). DECISIONs: the pointer before the first move is the shell's last known one (`Shell.mouse`); the description uses the exe's own wrapper and its last-line quirk, the title the brown gradient, the path tracer is a port (all CONFIRMED in town-worldmap "L5 research round 2" and 8.5). Needs eyes: the picture on the 800x600 / 1024x768 black border, the description colour table `0x61faa0` over the parchment, the Point sounds and `map.wav`, the flag / Cross animation speed.

L5 educated guesses for what only eyes and ears can settle (INFERRED, kept open; the play-test confirms or corrects them):
1. **Borders at 800x600 / 1024x768:** black, like every other 640x480 screen (no town code draws outside the centred rect).
2. **Description colour:** the exe's table `0x61faa0` is a light-to-dark ramp used with font2's shade rows, so it should read as dark text with a light outline on the parchment, as in our render; a different look means the ramp direction is inverted.
3. **Point sounds / `map.wav`:** a soft tick every ~0.4 s while the dots are laid (Point2 first), over a looping map track; no click or hover sound.
4. **Flag / Cross animation:** flags cycle at 10 fps (one frame per 100 ms draw), the Cross runs its 13 frames once during the walk and holds frame 12.
5. **Dropped characters:** the original really shows the last line without its final "!" / "." (the code is unambiguous; nobody fixed it because the loss is hardly noticeable).

### L6 as built

`engine/townscene.py` (pure): `REGION_OF_BYTE`, `Mask` (`townmask.bmp` bytes, origin subtracted, -1 outside 640x480, the dither noise kept), `StandInMask` (three rectangles without an install), `SceneSpec` (per-town data, frame counts measured from the install when loaded, the spec's numbers as defaults), `SceneState` (`Human` / `Druid` / `Kaarg`: `advance(dt_ms)` = one draw, step 67 / 100 ms with `>` as the exe, `hover`, `press` -> ("inn",) / ("shop",) / ("leave",) / ("speech", name) / ("menu",) / None, `draw_ops()` in the exe's draw order, `take_sounds()`), `Globals` (the process-global counters, owned by the `Shell`, with the shell's `rng`). `engine/shell/town.py` `TownScene` is the real scene screen: a left **press** acts, moves hover, `update` advances, sounds through `shell.play`, the **entry loop** through the new `Services.loop(path | None)` (one looping UI sound: `NullAudio.loop`, stopped when the scene is left), speech by the `speech:` convention; the human leave gate stays in `TownCore.leave_town`; Inn / Shop remain the L4 panels (L7 / L8). Without the install the scene is three Fill rectangles and the existing tests click them (`tests/shell_scenarios.click_region`). Tests `tests/test_engine_townscene.py` (50: mask reader and the three real masks' dense boxes, click table, the Var(0x301) gate through the shell, stars every 10th, gate counter, guard rule, druid variant rule, Kaarg timers, visit kinds, birds, a render of each scene to `out/town_scene_<race>_<640|800>.png`). REA round and INFERRED decisions: [town-scenes 9](town-scenes.md#9-l6-round-rea--the-build-2026-11-14).
DECISIONs: the `("menu",)` outcome (region `0x10`) does nothing yet; the human scene's `Var` reads for the gate animations use the campaign's variables live; a new `SceneState` (new random visit kinds, timers re-armed) at every opening of the scene, also when it comes back from the inn / shop (CONFIRMED loader behaviour).
Needs eyes: the druid man / woman patches look like darker boxes over the base picture at idle (the 24-bit patches carry their own, darker background: the spec says opaque; if the original blends or keys them, change `Druid.draw_ops`); the sprite alpha of the `.16a` layers on the base; whether the baba idles invisibly; the horse sound repeat; footstep and guard sound timing; animation speeds; the click on the `0x10` region (stars on the human scene, the whole left strip on the Kaarg one).

## 6. Open questions

All window-level questions are in the five docs and in [open-questions.md](../open-questions.md). Spec-level:
1. *(answered, L6 research 2026-11-14)* The three town **scene** classes (`0x4ca23c`, `0x4ce2b9`, `0x4d09ee`): mask byte -> region table, click handlers (left press), hover / highlight, every animation with frames / timers / sounds, the druid man / woman rule and the per-visit state are in [town-scenes.md](town-scenes.md); what is left (woman body by symmetry, `Town_add.bmp` role, speech-file mapping) is its section 8.
2. *(answered)* A load resumes the mission, or builds the town scene of the saved location (`InBattle` key, [town-worldmap 8](town-worldmap.md#8-open-questions) 4); only the writer of that key in the save routine is untraced (`save`).
3. Where the Hire cost / party limit lives, if anywhere (the inn handlers read neither: [town-inn 1](town-inn.md)); start `TalkTo` in Scenario.dll and the server's recruit path.

### Status of the window-level questions (L3 close-out, 2026-11-14, second round)

Answered by REA (details in the window docs): inn button rects and captions; the inn / shop animation scheduler; missing sound files are silent; client unit flag bits; the lifetime of the inn's person units; `0x405`; the tips window rect and `#tips4`; shop buy / pack-full / leave rules; the container message `0x76` and its keys; the shop gold / totals fields; the shop window's black strip and spell-book view; the cell background slots; the shop hero-arrow mirror; `Var(0x301)` / `Var(0x307)`; load-game behaviour; the map description rect, flag anchor (top-left) and the border (black); **the inn person strip (a click on a figure selects and acts), and that the left sheet's quest captions and the centre arrow overlays are multiplayer-only**.

**Still open, with the reason** (none changes a rule; each is read at the build step that draws it):
- needs a run of the exe (no Wine / display here): the info panel's position at 800x600 / 1024x768, client price vs server price of stock;
- pure pixel / art reading: the pixel positions of the three shop numbers, the "HIRED" anchor and the sprite placement inside a figure cell, which `backinv*` colour means what, the stock grid draw (`0x4b392a`), the shop panel tooltips, the druid / Kaarg shelf rects and animation tables, the last frame numbers of the druid / Kaarg ambient events;
- bookkeeping with a headless stand-in already specified: the world map's path-edge tracer (`FUN_00471f0d`, `FUN_004721ff`).

## 7. Working guesses for the still-open items (**GUESS**, not facts)

Each stays in [open-questions.md](../open-questions.md) (marked "guess in town.md 7"). The build steps use these values and flip them to CONFIRMED / corrected when the exe or the art says otherwise. Basis in brackets.

| open item | guess used until checked | basis |
|---|---|---|
| info panel position at 800x600 / 1024x768 | always **O + (480, 238)**, 160 x 242, same as at 640x480 | all other town widgets are O-relative; the move is symmetric (+480 / -480) |
| client price vs server price of stock | **one price source**: the generated item's price (`+0x1c`) shown and charged; no buy fails after the client accepted | the client price is a serialised attribute of the same item |
| the three shop numbers' positions | gold, buy total, sell total drawn **centred horizontally in the button's rect, in its lower half**, caption in the upper half, font `0xa`; Exit none | caption + number share the button (draw order: caption, then number) |
| "HIRED" anchor / sprite in a figure cell | figure sprite centred horizontally, **feet 2 px above the cell bottom**; "HIRED" centred horizontally, **12 px above the cell bottom**, font table `0x620ea0` | 48 x 64 cell, row grid anchored at the bottom |
| `backinv*` meaning | `backinvg` = normal cell, `backinvs` = item unsuitable for the shown hero (red), `backinvb` = selected / carried highlight | the unsuitable test feeds `+0xd0`; `b` used by the pack / table classes |
| stock grid draw | 2 x 3 cells of 80 x 80, item icon centred, stack count bottom-right, price bar as in [items](../data/items.md) | grid size from the panel rect |
| shop tooltips | the item tooltip builder of the pack strip (`FUN_0043901f` text); panel hints = `#tips3` / `#tips4`, no other tooltips | no other text source found |
| druid / Kaarg shelf rects and animations | **the human 2 x 2 shelf rects** (A..D), shelf order armor / magic / potion / weapon (Kaarg 4th = weapons, druid 4th = elven, gated by `Var(0x302)`); idle animation = the human scheme (100 ms steps) | one shared base class `0x4b9cf5` |
| druid / Kaarg ambient events | same cadence as the human one: `D = rand / 16 + 3000` ms between events, a sound fires at **frame 30** of its animation, water / dish sounds one random of four per 100 ms step when the frame is 0 | the slot table and the human scheduler |
| world-map path-edge tracer | use the specified headless emulation (DFS cheapest route, cover check `2766 = 2552 + 2 x 107`) | [town-worldmap 3.3](town-worldmap.md#33-the-path-graph-fun_00471a75-confirmed-structure-bookkeeping-inferred) |

