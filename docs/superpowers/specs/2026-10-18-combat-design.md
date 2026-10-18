# I1: melee attack (design)

Goal: a unit ordered to attack an enemy walks into range, swings with the original timing and deals damage with the original
formulas. Rule from the user: **reproduce the exe 1:1, keep asking REA when needed.** Single player only. Facts, formulas and routine
addresses: [combat](../../engine/combat.md) (REA, GOG exe; "C§" below = its sections), RNG in
[simulation §10](../../engine/simulation.md#10-rng). Approved in conversation (classification: architectural; ranged and spell
attacks deferred except where the exe shares the code).

## 1. Where the research changed the brief

| Brief | Exe (CONFIRMED, C§) | Spec decision |
|---|---|---|
| "match the original's exact RNG sequence is optional" | the CRT LCG, seeded from the clock, shared with the client thread (sim §10) | same generator, explicit per-game seed; algorithm matches, a recorded original session cannot be replayed |
| click -> "attack order" | the command only sets order 3 + mode 0; **the unit starts at the next `tick & 15 == 6`** (C§2.1, 2.3) | group pass runs the executor; 0-15 ticks of latency are part of the behaviour |
| "give up conditions" | none by time; target removed (state 0x10) stops at the executor; planner failure -> mode 0 + auto scan (C§2.5) | stop on removed target; failure -> mode 0 (no scan); I1: also stop when target HP <= 0 (death is I2) |
| "in range" | facing must equal the octant **and** gap <= range; gap is Chebyshev with size terms (C§3.1) | exact |
| "attack speed" | `windup + recovery(+ hero delay + rand 0..3) + 2` ticks per cycle, byte timers (C§4) | exact, hit tick = swing start + windup |
| "hit chance: level difference?" | no levels: `T + rand(0..200) - 100 > D` or roll >= 90; sure-hit flag (C§5.2) | exact |
| "resistances by damage type" | weapon type -> percent `res_*`; elements -> protection; absorption flat; `trunc(x*(100-p)/100 + 0.75)` (C§5.2) | exact |
| "critical hits" | none (Bless / Curse force max / min damage; no effect system yet) | inputs exist, never set |
| "monster damage" | template + equipped weapon, merged as bytes (C§6) | exact (VERIFY IN GAME item 1) |
| "damage numbers behind a debug toggle" | the original shows them by default (option "Flying damage", Ctrl+L) (C§8) | on by default, Ctrl+L, same motion; debug log behind `--debug combat` |

## 2. Units

1. **`engine/sim/rng.py`** `Rng(seed)`: `srand`, `rand15`, `rand(n)` (`0` for `n == 0` without a draw), `state`; `World.rng`; `World(..., seed=1)`,
   `from_map(..., seed=)`; `dump()` gets `"rng"` only when the state differs from the initial seed state. `Simulation` exposes `seed`
   (kept in the log header). `engine run` seeds from the clock (`--seed N`). Test: every module under `engine/sim/` is parsed and may not import `random`
   or call `numpy.random`; the CRT sequence for seed 1 is pinned (41, 18467, 6334, 26500, 19169).
2. **`engine/sim/combatstats.py`** (pure, no world state): `AttackRecord`, `ArmourBlock`, `CombatStats(record, block, flags, range, windup, recovery,
   weapon_weight, mage)`; `monster_stats(template, items)`, `human_stats(template, skills, xp_total, items)`: base block, equipment strings (weapon, shield,
   armour by slot, `parse_equipment`), modifier effects of the kinds in C§6, merge with byte arithmetic, clamps; no side effects. `World._load_units`
   stores the result in `Unit.combat` (built once at load; recomputed by the progression hook later).
3. **`engine/sim/combat.py`** (pure functions first): `attack_gap`, `reach_gap` (`FUN_00556dcd`), `octant`, `in_range`, `take_hit(record, block, attacker_flags,
   rng, bless=0, curse=0, mage=False, human=False)` returning the damage, `swing_timers`, `hero_delay`, `can_attack` (matrix), `extra_ticks`. Then the
   system parts: `set_attack(world, unit, target)` (order 3, range, mode 0), `refresh_attack` (executor), `attack_mode` (Brain mode 5), `swing_tick`
   (state 3), `resolve_attack` (gate, `take_hit`, HP, event). HP stored as exe s16, clamped to 0 in `Unit.hp` with the `died` event once (C§9.1).
4. **`engine/world.py`:** `Unit` gets `combat`, `target` (brain+0xc id or None), `mode_attack` (Brain mode 5), `range` (brain+0x14), `brain_order`
   (0 / 1 swing / 3 step), `swing_count` (+0x15), `phase` (+0x58 0/5/7), `timer` (+0x6c byte), `done` (+0x136), `swing_target` (+0x5c), `last_attacker`.
   `dump()` appends a `"fight"` dict only for a unit with any of them (old goldens stay valid). Events: `Damage(tick, attacker, target, amount, hp)`,
   `Died(tick, unit)`; not dumped.
5. **`engine/sim/commands.py`:** `AttackUnit(player_id, unit_ids, target_id)` = cmd `0x19`. **`orders.py`:** intake as for `MoveUnits` plus the target lookup (a unit
   in `world.units`; a structure target is dropped, C§10), `attack_group` (C§2.1: cancel all, then per member the matrix, self test, `set_attack`), the group pass
   runs the executor for groups with order 0 (C§2.3), `Stop` unchanged.
6. **`engine/sim/movement.py`:** the per-unit tick becomes: step in progress (brain order 3) / swing (brain order 1) / mode dispatch (go, wait, **attack**), then the
   state-3 phases of the same unit (C§4) before the next unit (creature order, so damage is visible to units processed later in the same tick). New `_follow_drive`
   = the follow driver of simulation §7.4 (re-plan rules, hop plan with the follow fallback, turn when `reach_gap <= range`), reusing the move driver's step code.
7. **UI:** `choose_cursor` already returns the attack cursor over hostile units; `OrderInput.release` turns "attack over a unit" into `AttackUnit` (hotkey `A` +
   click and the default left click on an enemy). Floating damage numbers in the view (`engine/view/damage.py`, drawn by the backend with the owner colour
   ramp), Ctrl+L toggles, default on; `--debug combat` adds a log line per hit (`tick attacker -> target roll/dmg hp`).
8. **Docs:** combat.md, simulation §10 (done in the research commit), unit-struct (mode 5, `+0x5c`, corrections), spells §5 / overview §3 (roll rule), animation §5.3
   (pointer), open-questions, CLAUDE.md ("Next: I2").

## 3. Tests (headless, always run unless marked game-file)

- RNG: sequence pin, `rand(0)` draws nothing, range of `rand(n)` over many draws, determinism of two worlds with the same seed, import scan.
- Formulas: every branch of `take_hit` with a scripted RNG (fixed draws): hit by roll, 90 rule, sure hit, miss, absorption to 0, resistance rounding table
  (x = 0..7 at 30 % -> 0, 1, 2, 2, 3, 4, 4, 5), second part, elemental part gating, Bless / Curse, scaled damage bytes, zero armour, huge armour, immune flag; the
  two worked examples of C§5.3 as exact expectations (hit counts 83/201 and 16/201, damage sets).
- Distribution: N = 20 000 hits with a fixed seed against the exact probabilities (hit rate within 3 sigma, damage histogram support and mean).
- Gap / octant: table tests against the formulas (sizes 1-3, diagonals, 16-bit wrap), `follow_distance` equality.
- Scenario (synthetic world, scripted units): attacker 8 cells from the target is ordered at tick t; first swing starts at the next `tick & 15 == 6` after arrival
  and facing; the first damage lands exactly `windup` ticks after the swing start; the next swing starts `windup + recovery + 2 (+ draw)` after it; HP falls by
  the recorded damages; the event log matches.
- Target moves: it walks away mid-approach (attacker re-plans and follows, arrives, swings); it steps out of reach during the wind-up (hit lost, no damage,
  recovery still runs); a new move order during a swing finishes the swing first.
- Refusals: ground attacker vs flyer (no order, stands), self target, dead target, unknown id, foreign unit ids in the command.
- Determinism: a scripted session (move, attack, re-order) replays to the same `dump_hash` in one batch and at 30 / 60 fps; the seed is in the log.
- Game-file test (skipped without the install): `monster_stats` / `human_stats` for every template resolve, no negative damage, A and B examples reproduce from
  data.bin and the item table; hero numbers pinned in a golden (`tests/golden.json["combat"]`).

## 4. Close-out

Goldens regenerated for any dump change (none expected: new keys are optional), `tools/bench_orders.py` re-run (no regression), a scripted fight screenshot, the
VERIFY IN GAME list (C§11) copied into simulation §9, `CLAUDE.md` "Known so far" + "Next: I2" (death, corpses, XP kill credit, retaliation), open questions
updated, one commit per stage (RNG, stats, formulas, order + approach + swing, UI, close-out).

## 5. Assumptions recorded

Normal difficulty (no monster tweak); monster weapons add to the template (CONFIRMED order, VERIFY); ranged units use the melee code path with the arrow delay and
no projectile in the sim; mages fall back to melee because spells are phase K; units processed in creature (id) order; wall-clock lifetime of damage numbers is
frame-time in the view (not sim).
