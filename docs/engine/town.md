# Town mode: index, state machine, build plan (L3)

REA of the GOG `allods2.exe` (sha256 in [formats/README.md](../formats/README.md)). Marks: **CONFIRMED** / **INFERRED**. Design: [L3 spec](../superpowers/specs/2026-11-13-l3-town-spec-design.md).
This is the hub of the town spec. The per-window facts are in the five window docs and are not repeated here; this doc owns the **shared core** (mode mask, window objects, message flow), the **state machine** of a visit, the **link to the engine** (`CampaignGame`, the L2 stand-in), what is testable without eyes, and the **build steps**. Single player only (`client+0x5d8 == 2`).

| doc | window | mode bit | opener / closer |
|---|---|---|---|
| [town-worldmap.md](town-worldmap.md) | world map `client+0xf0` (`0x46e66b`) | `0x10` | `0x48b419` / `0x445 -> 0x44c` then `0x468` |
| *(no doc: scene art in [animation 4.11](../formats/animation.md))* | town scene `+0x110` / `+0x114` / `+0x118` | none (mask 0) | `0x48bbc0` |
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
| **L4 town core** | the mask + the transition table of section 2 as pure code, the town ids / window table, `0x42e` / `0x42d` rules, autosave-slot events, `Var(0x301)` gate; wire into `shell/machine.py` with placeholder screens | L2 | the table over fake windows, edge coverage | none |
| **L5 world map** | graph + route + walk + text + flags (needs the Cross set, [animation](../formats/animation.md#open-questions)); replaces `locations.py`'s mission list; intro walk | L4 | graph / route / schedule / intro | flag anchor, route dots, music |
| **L6 town scenes** | the three scenes: art, animations ([animation 4.11](../formats/animation.md)), hover regions (open), click -> inn / shop / leave, music | L4 | region table, transitions | everything visual |
| **L7 inn** | the window: panels, person strip, Hire / Dismiss / Talk / About, hero arrows, dialogue window + speech; the `visit_towns`-equivalence test | L4, L6 | handlers, keys, equivalence with `visit_towns` | layout, captions (open), sounds |
| **L8 shop** | shop windows, the DLL shop table + stock, trade state machine, gold | L4, L6 | trade rules, stock, messages | layout, animations, sounds |
| **L9 close-out** | remove the stand-in, play-test list, coverage / CLAUDE.md status | all | the campaign test through the real screens (scripted clicks) | the whole town loop |

Order: L4, then L5 and L6 (independent), then L7 and L8 (independent), L9. Open research items that block a step are listed per window doc; the ones that block **drawing** (captions, rects, hit regions) are all "layout numbers": they are read from the exe at the start of the step that draws them (L5 / L6 / L7 / L8), not before.

## 6. Open questions

All window-level questions are in the five docs and in [open-questions.md](../open-questions.md). Spec-level:
1. The town **scene** classes (`0x4ca23c`, `0x4ce2b9`, `0x4d09ee`) have no doc: their hit-region numbers and the druid `man` / `woman` choice are listed in [animation open questions](../formats/animation.md#open-questions); to be researched at the start of L6.
2. Whether a saved game restores the party point and which town screen it re-enters ([town-worldmap 8](town-worldmap.md#8-open-questions) 4): needed by `save`.
3. Where the Hire cost / party limit lives, if anywhere (the inn handlers read neither: [town-inn 1](town-inn.md)); start `TalkTo` in Scenario.dll and the server's recruit path.
