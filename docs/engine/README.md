# Allods 2 engine

The recreated game, built on the core library (`allods2/`, `a2res/`).

| Document | Contents | Status |
|---|---|---|
| [architecture.md](architecture.md) | layers, import rules, coordinate systems, tick, main loop, terrain drawing, CLI | G1 skeleton done |
| [rendering.md](rendering.md) | draw list and backend: pass order, placement, shadows, light rows, smoothing, culling, debug overlays, timings, interface / cursor / picking / marker (§14) | G2b, G3b done |
| [cutscenes.md](cutscenes.md) | m1: the Smacker 2 decoder, fades, the cutscene screen, start-up chain, chapter triggers, the Cut Scenes window; [cutscenes-rea.md](cutscenes-rea.md) = what the exe does | m1 done, VERIFY IN GAME |
| [save.md](save.md) | L10 plan: the original `game%d.sav` for town and mission saves, steps L10a-f, decisions | L10a-d done (town) |
| [save-ui.md](save-ui.md) | Save / Load / Delete windows, the slot folder (naming, order, dates), what a load does, VERIFY IN GAME | L10d |
| [vision.md](vision.md) | fog of war: sight mask, tile bits, refresh, what is hidden per state, minimap fog, cheats, saves; VERIFY IN GAME | J2 |
| [ui-layout.md](ui-layout.md) | screen layout per mode, cursors, picking, selection, marker, info panel (REA facts) | G3b done |
| [simulation.md](simulation.md) | tick, update order inside a server tick, unit state machine, movement formulas (step length, turning, cell occupancy), pathfinding (§7), orders (§8), handoff (§9), RNG (§10), exe addresses, VERIFY IN GAME | H1, H2, H3 sim side, I1 RNG done |
| [click-to-move-research.md](click-to-move-research.md) | REA research for phase H3: mouse input to order message, server intake, groups, formation, group pass, stop commands, "No way", VERIFY IN GAME | CONFIRMED / INFERRED per fact |
| [combat.md](combat.md) | phase I1: the attack order (cmd `0x19`), approach (follow driver), swing timeline, hit resolution `FUN_00516f6f` as math with worked examples, stat building (monster = template + weapon, human recompute), client damage numbers, VERIFY IN GAME | I1 done, CONFIRMED / INFERRED per fact |
| [ai.md](ai.md) | phase I3: monster AI = squad group order `0x12` handler `FUN_005728fa` every 16 ticks, sight flood, pool, target score, hit reaction, flee post step, engine mapping, VERIFY IN GAME; §12 casters and special attacks (K1) | I3, K1 (AI casting) done, CONFIRMED / INFERRED per fact |
| [combat.md §14](combat.md#14-spell-casts-i4a) | phase I4a: the player's spell cast (command, order `0xd`, Brain mode 8, cast phases, carriers, damage), staff casts; REA facts in [spells §9c](../data/spells.md) | I4a done (sim); view/UI = I4b |
| [triggers.md](triggers.md) | map scripts (section 7): compilation `FUN_00562745`, the check / trigger / instant tables, pass timing (group pass, every 16 ticks), victory and defeat `FUN_004f856a`, engine `sim/triggers.py` | decoded, engine built (subset), CONFIRMED / INFERRED per fact |
| [effects.md](effects.md) | phase K2: spell effect objects (list `unit+0x20`, mask `+0x144`), apply / merge / tick / undo, the stat switch, point / area / field carriers, cell effect slots | CONFIRMED / INFERRED per fact |
| [items.md](items.md) | phase K5: picking up an item by click (cursor, command `0x21`, approach, the whole-pile take), what scripts see (checks 12 / 16 / 17, instants 11-13, 20, 28, 38), the seven quest-item maps | CONFIRMED / INFERRED |
| [unit-struct.md](unit-struct.md) | runtime unit struct of the exe: classes, sizes, allocation sites, field table, per-tick behaviour, client mirror | CONFIRMED / INFERRED / UNKNOWN per field |

| [campaign.md](campaign.md) | L1: the headless campaign (roster carry-over, recruits, town stand-in, mission chain, `python -m engine campaign`), DECISIONs, the chain result | L1 done, CONFIRMED / INFERRED per fact |
| [shell.md](shell.md) | L0: startup (logos, videos), the main menu (mask, buttons, states), the screen graph, PreCreate (new game), the options windows and the settings file, video format, the shell state machine | L0 done, CONFIRMED / INFERRED per fact |
| [chargen.md](chargen.md) | L2 step 1: the character generator panel after PreCreate: layout / rects, attribute rules and costs, Reset, class pick, hint, sounds, the creation message `0x48` | decoded, CONFIRMED / INFERRED per fact |
| [town-shop.md](town-shop.md) | L3: the three shop windows (id `0x3e8`, mode bit 2): panels and rects, table / shelf regions, buy / sell / cancel rules, messages `0x32`-`0x36` / `0x22` / `0x3f`, stock regeneration, sounds, `#tips3`; answers `window+0x160` and `Var(0x302)` | CONFIRMED / INFERRED |
| [town-inn.md](town-inn.md) | L3: the Inn dialogue handlers behind Hire / Dismiss / Talk / About: text keys (accept / reject use the chapter `Var(0x300)`), bit-31 toggle and `TalkTo` order, sounds of the three classes, Exit and hero arrows | CONFIRMED / INFERRED |
| [town-scenes.md](town-scenes.md) | L6 research: the three town scenes (human / druid / Kaarg): hit-mask bytes -> regions, left-press click table (inn `0x42b`, shop `0x42a`, leave `0x442` + `0x42d`, NPC speech lines), hover highlights, every animation (assets, frames, timers, sounds, positions), draw order, per-visit state, data recipe | CONFIRMED / INFERRED |
| [town.md](town.md) | L3 hub: shared core (mode mask, window table, messages), the state machine of a visit, link to `CampaignGame` / the L2 stand-in, testable vs eyes, build steps L4-L9 | CONFIRMED / INFERRED |
| [town-worldmap.md](town-worldmap.md) | L3: the world map window `0x41a` (`FUN_0048b419` open, `FUN_0046fdd5` draw): layout, path graph, hover / walk / enter, the 49 location points, texts, sounds, messages `0x41d` / `0x42d` / `0x468` | CONFIRMED / INFERRED |

Audio (K11): [audio.md](audio.md).

Design specs: [../superpowers/specs/](../superpowers/specs/). Format and
mechanics specs the engine follows: [../formats/](../formats/README.md),
[../mechanics/](../mechanics/README.md). Open questions:
[../open-questions.md](../open-questions.md).
