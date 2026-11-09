# I2: death, corpses, XP, loot, regeneration (design)

Goal: a unit at HP <= 0 dies with the exe's sequence, leaves a corpse that decays as the exe's does, drops loot and pays XP to its killer; HP and
mana regenerate on the exe's schedule. Rule from the user: **reproduce the exe 1:1; once this spec is committed, implement without further
questions** (CLAUDE.md workflow). Single player only. Facts, routines and VERIFY IN GAME: [combat §12](../../engine/combat.md#12-death-corpses-loot-xp-and-regeneration-i2-research);
XP formulas: [progression §3-§4](../../data/progression.md). Classification: architectural (new sim system, new world table, UI feedback).

## 1. Where the research changed the brief

| Brief | Exe (CONFIRMED, C§12) | Spec decision |
|---|---|---|
| "HP <= 0 check, unit stops blocking" | HP <= 0 (0 counts) starts the dying countdown at its own creature tick `T0`; **nothing is released until the removal tick** (state `0x10`) | footprint / occupant / spatial index released at removal only |
| "die animation plays once and holds" | client: action 6 for `2 * DyingPhases` ticks, then the corpse frame (already `dying` -> `corpse` in `allods2/anim`) | `action = "dying"` at `T0`; the draw picks dying/corpse/bones by HP (death stage) |
| "how long does the corpse last" | server removal `T0 + D` (D = `dying_time`), **ground unit only when HP <= -10**: a body at HP -9..0 waits for the 64-tick HP drain or more hits (HP 0 forever). Then the corpse decays 1 HP / 32 ticks: bones at -11 / -21 / -41, not drawn at -601 (~20 min). Flyers / ghosts: HP := -1000 at `T0 + D`, gone | exact; no fade, the graphic changes with HP |
| "attackers targeting it stop" | they **keep swinging** (no HP / state test in mode 5 or the hit gate) until the next `tick & 15 == 6` executor pass **after** state `0x10`, then stop (order `0xc`) | I1's early stop is removed |
| "its selection" | **CONFIRMED** (combat C§12.2): kept at death stage 1 (HP -10..0), dropped when the client reaches stage >= 2 (HP <= -11; the HP message of `T0` for an overkill, else the decay message after the removal); the engine also drops it at removal (a removed body is no longer in `world.units`; DECISION, <= 32 ticks early) | `death._deselect_if_bones` every dying tick; `remove_unit` at removal |
| "sack of items or gold" | monsters (`unit_type >= 0x40`) roll gold and one item; carried items drop for everything not summoned / `NPC`; a pile on the unit's cell, merged with an existing one | `Item` piles in `world.items` |
| "who gets XP" | per hit (hero attacker, victim alive before, HP > -10 after) **and** `0.5 * victim.xp` at the **removal tick** for `victim+0x40` (last hitter) only | exact; no group share |
| "regeneration in/out of combat" | no combat test; `k = 3` when `tick - step_end > 80` (signed; a step, turn, swing or cast resets it, being hit does not; CONFIRMED combat.md 12.5). HP: once per 64 ticks per unit (`block & 3 == id & 3`); mana: every 16 ticks; both at `tick & 15 == 12` | exact |

## 2. Units

1. **`engine/world.py`:** `Unit` gets `death_seen` (+0x13c), `step_end` (+0x138, the rest clock, combat.md 12.5: `_start_step` writes
   `tick + step_ticks`, `_tick_unit` a turn message `tick + dir16`, `combat.swing_tick` a swing start `tick + windup + recovery`; spell casts write `tick` when the spell system exists), `hp_acc` / `mana_acc` (+0xa2 / +0xa3), `carried` (item codes of its section 8 group), `kill_list` (+0x1a8, up to 5 `[server_id, count]`).
   `state` gets the value `DEAD = 0x10`. New `World.corpses` (id -> Unit, state `0x10`), `World.find_unit(id)` (units, then corpses),
   `World.bury(uid)` (the release: spatial index, group, selections; ground units move to `corpses`, flyers / ghosts are dropped), `death_stage(hp)`,
   `World.next_pile_id()`. `HP` is the s16 of the exe: **the I1 clamp at 0 goes**. `dump()` adds a `"death"` dict per unit and a `"corpses"` list only when non-empty (old goldens unchanged).
   Events (fight log, never dumped): `Damage` only for the blows message `0x73` carries (HP before > 0 or HP now > -10), `Died(tick, unit, killer)` at HP crossing <= 0,
   `Removed(tick, unit)`, `LevelUp(tick, unit, school, skill)`, `Loot(tick, unit, x, y, gold, codes)`.
2. **`engine/sim/death.py`** (system part of layer 4): `dying_tick(world, u)` (the HP <= 0 branch of `FUN_0050f12c`: `T0` block, countdown, removal test), `remove_dead(world, u)`
   (`FUN_00510a70` + the loop tail: bury, loot, hero rules, kill credit), `drop_loot` (rolls in the exe's order), `death_stage`, `decay_corpses`.
3. **`engine/sim/vitals.py`:** `vitals_system(world, commands)` = the 16-tick job at `tick & 15 == 12` (runs **first** in the step, before commands and creatures): HP regen
   (`block & 3 == id & 3`), the HP < 0 drain (`block & 3 == 0`), mana regen, corpse decay. Block = `tick >> 4`.
4. **`engine/sim/xp.py`:** `award(world, hero, xp_in, school, victim)` (`FUN_005128cb` chain: Mind scaling, repeat-kill discount, off-school, span cap, pool, skill-up),
   `damage_credit` (`FUN_00513128`), `kill_credit` (`FUN_00512fcb`), `level_up` (recompute max HP / mana through `progression.derived_vitals(t, skills, total=)`, clears `Unit.combat`).
   `progression.attributes(t)` returns the capped (Body, Reaction, Mind, Spirit); `derived_vitals` gets an optional `total`.
5. **`engine/sim/combat.py`:** `resolve_attack` stores HP unclamped, logs by the 0x73 rule, calls `xp.damage_credit` and logs `Died`; `refresh_attack` / `attack_mode` look the target up with `find_unit`
   and stop only when it is missing or its state is `0x10` (executor pass; mode 5 keeps swinging at a corpse). **`movement.py`:** `_tick_unit` calls `death.dying_tick` for HP <= 0 and
   removes the unit when the state became `0x10`; `_start_step` / the turn rule write `step_end`. **`simulation.py`:** `vitals_system` first.
6. **View:** `unit_frame` picks the action by death stage (1: `dying` from `action_start_tick`, holds on `corpse`; 2-4: `bones1..3`; 5 / missing frames: not drawn); `build_draw_list` draws `world.corpses`
   with the units (corpses under living units of the same cell: drawn first, INFERRED from the corpse list of the exe drawn before units); piles are drawn as today; picks skip units of death stage >= 2 (HP <= -11; a stage-1 body is hoverable and attackable by click, CONFIRMED); minimap dots skip stage >= 2 (corpses of stage 1 keep theirs).
   HP bar (existing) for the hovered unit too (`hover=` argument), plus the mana bar for units with mana (`ui-layout §9`); info panel gets mana, skills (best school / levels) and XP via the G3c fonts.
7. **Docs:** combat.md (§12 done in research; sections 9, 10 updated, engine mapping), progression.md ("no award logic yet" removed), simulation.md (Death), unit-struct, open-questions, CLAUDE.md ("Next: I3").

## 3. Assumptions recorded (INFERRED, flagged in combat.md)

- Hero test = a human whose template name is a hero (`progression.is_hero_name`) instead of the unit-type word `0x21..0x3f` (same units).
- Attribute / equipment bonuses of the recompute and regeneration (`+0xde`, `+0xe2`) are 0 (no effect system yet, I1 §10); Mind is the capped template value.
- Loot items: the bag = `carried` codes + the template equipment (`combatstats.equipment_codes`, CONFIRMED combat.md 12.4: shield, weapon iff the weapon class parameter 15 `suitable_for` != 0, a human's armour slots) unless the unit is summoned or its template name contains `NPC`; item effect texts are not kept. Generated items enter the pile as `GenItem.code`.
- The pile is placed on the unit's own cell only (CONFIRMED, no free-cell search, combat.md 12.4): an existing pile there is merged (even on a blocked cell); otherwise `World.place_pile` refuses a cell with bit 0 of the block layer set (`World.pile_blocked`) and the loot is deleted (no `Loot` event, rolls spent).
- A level-up keeps the current HP / mana (clamped to the new maximum). The client shows only a message-line text (`main.txt[0x81 + school]`, mage `0x86 + school`, + hero name, 3000 ms; CONFIRMED combat.md 12.7), drawn by `engine/ui/orders.level_up_messages` from the `LevelUp` log entry (view layer, no sim change); the skill-up sound and the unit hit / death sounds are emitted as `SoundEvent`s ([audio.md](../../engine/audio.md)); not played yet. No floating text, effect sprite or kill notification exists.
- Kill counters, bestiary byte and message `0x94` are not modelled; the hero-death message `0xb4` is a `HeroDied` fight-log event plus `Player.hero_deaths / death_code / defeat_dialog` (CONFIRMED, combat.md 12.3a); the main hero (`Player.main_hero`, INFERRED: first hero of the human at load, the exe's `owner+0x38` writer is not traced) gets HP -50. The load / quit dialog and the sim freeze are UI work (not built); the sim keeps running in the engine.
- A hero's kill list, not the victim's, is the repeat-kill list; entries key on the victim's `server_id`.
- The summon-cap job (`+0x148` = master id, combat.md 12.6; chance `(n-1)/100` per master, one minion removed per job) is not modelled: CONFIRMED unreachable from campaign data (only the Summon spell writes it), and the engine has no Summon spell yet. Implement together with it (draw order = CMap iteration order, combat.md 12.11 question 2).

## 4. Tests (headless, always run)

- Timeline: scripted kill of an Orc_Sword-like unit (D = 14): `T0` order / state cleared, `action == "dying"`, defence halved, timer D-1, still in `world.units` and blocking
  (`live_cells`), removed exactly at `T0 + 14`, cell free in the same tick, in `corpses`; ground unit at HP -5 is **not** removed until the drain reaches -10 (64-tick steps); HP 0 never; flyer removed at `T0 + D`.
- Draw: dying frames play once (`2 * DyingPhases` ticks) and hold on the corpse frame; bones at HP -11 / -21 / -41; stage 5 not drawn; decay rate 1 HP / 32 ticks on even blocks; hero stops at -61.
- Attackers: keep hitting a dying target and a corpse (no XP, no Damage entry at HP <= -10), stop at the first executor pass after removal (order `0xc`, mode off), no auto scan; an `AttackUnit` on a corpse is accepted and stops at the next pass.
- Selection: kept at stage 1, dropped at HP <= -11 (also at an overkill `T0`); unit counts.
- XP: per-hit credit only for a hero attacker, victim alive before and > -10 after, victim owned by a non-human player; kill credit at the removal tick to the last hitter only; repeat-kill discount (`10/(n+10)`), off-school `(x+7)>>3`, span cap, skill-up
  threshold, `derived_vitals` change of max HP; summoned victim pays nothing; dead killer pays nothing.
- Loot (fixed seed, scripted rng for the rolls): chance `p/101`, gold `base + rnd(spread)`, draw order, no loot for summoned / `NPC` / heroes' rolls, pile merge on an existing pile, blocked cell (loot deleted, no neighbour search, trees allowed, neighbours irrelevant), carried items.
- Regeneration: HP per application `maxHP*2*(100+bonus)*k/regen` hundredths with the accumulator, the per-id phase, `k = 3` when `tick - step_end > 80` (signed: a `step_end` in the future gives `k = 1`), clamp at max, mana every block, HP < 0 drain every 64 ticks, nothing for HP == 0; N-tick totals against the formula.
- Determinism: a scripted fight with deaths, loot and level-up replays to the same `dump_hash` in one batch and at 30 / 60 fps.
- UI: bars (hover, mana), info panel texts, pick skips stage >= 2; screenshot of a corpse.
- Game-file test (skipped without the install): every monster template's `dying_time`, loot params and regen resolve; the worked numbers of C§12.5.

## 5. Close-out

Goldens only if a dump changes (none expected), bench re-run, `CLAUDE.md` "Known so far" + "Next: I3" (retaliation / AI scans, spells), open questions updated, one commit per stage (research+spec, death, vitals, xp, loot, UI, close-out).
