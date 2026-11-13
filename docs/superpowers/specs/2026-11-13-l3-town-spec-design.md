# L3 - Town mode spec: design

Date: 2026-11-13. Task source: [docs/prototype.md](../../prototype.md) "L3 - Town mode spec (research, headless)".

## Intent

Decide, from REA of the GOG `allods2.exe`, everything needed to build the town screens (`town`), before any drawing. Output is documentation only; no engine code. GOG single player only, no multiplayer. Every fact is marked CONFIRMED (REA address) or INFERRED; decisions are backed by REA, and what the exe cannot settle goes to the open questions.

## Deliverables (`docs/engine/`)

- `town.md`: index and shared core. Mode bits `client+0x404 & 0x226`, entry / exit paths, the state machine (enter town, talk, shop, inn, hero screen, world map, leave) built from the windows' real message flow, the link to `CampaignGame` (L1 `visit_towns`, `TalkTo`, `EnterInn`, `leave_mission`) and to the L2 stand-in `engine/shell/locations.py`, shared plumbing (hero arrows `0x414` / `0x415`, window frame, speech and tips triggers, the `window+0x160` word), what the headless side can test, what only the user's eyes can judge, the refined effort of `town` and its build steps (L4...).
- `town-worldmap.md`: `FUN_0048b419`, mission markers and positions, the Cross animation.
- `town-hero.md`: `FUN_0049a428`, `FUN_0049bd95`, `FUN_0049e187`.
- `town-shop.md`: the shop windows (`TalkTo` sites `0x4b9117`, `0x4bec83`, `0x4c0995`), item data from docs/data/items.md §4, §12, §13.
- `town-inn.md`: the inn and mercenary windows (`0x49b812` area), dialogue words.

Per-window docs use fixed sections: layout per resolution (rect tables), widgets and resources, messages in / out, data read / written, sounds and tips, open questions.

## Method

Order: world map, hero, shop, inn, then the state machine. One doc per window, committed when finished (the user authorised commits without asking until L3 is done). Start from the known addresses, follow callers / callees with REA. Update docs/prototype.md, docs/open-questions.md and CLAUDE.md status when L3 closes.

## Out of scope

Drawing code, layout goldens (build steps), save / load, cutscenes, multiplayer.
