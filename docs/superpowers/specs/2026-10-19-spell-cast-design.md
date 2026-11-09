# I4: the hero casts Fire Arrow (design)

Goal: the player's hero casts the prototype spell **Fire Arrow** (#1, [spells §9](../../data/spells.md#9-prototype-spell-phase-i-step-32)) at a
unit: order, mana, cast animation, missile, hit, damage, recovery, matching the exe 1:1. Then phase I is closed out. Rule from the user:
**reproduce the exe 1:1; once this spec is committed, implement without further questions** (CLAUDE.md workflow). Single player, GOG only.
Classification: architectural (new sim system, new world table, new command, UI). Delivered as three parts, each with its own plan and commit:
**I4a** research + simulation, **I4b** view + UI, **I4c** close-out. Facts carry CONFIRMED / INFERRED tags, unknowns go to VERIFY IN GAME.

## 1. Where the research changed the brief

| Brief | What the docs already say | Spec decision |
|---|---|---|
| "a projectiles table: position with sub-cell precision, velocity or target; path, collisions, max range" | The server has **no flying body**. The missile carrier `FUN_00518d1e` counts `trunc(dist*256) / speed` ticks (`FUN_00516aae`), then `FUN_00542e60` delivers to the carrier and `FUN_0051e65b` applies the damage to the target unit. No collision, no path, no homing in the sim. The client projectile (id `2*spell+8`, Fire Arrow = 10) is a *visual* spawned by message `0x86`/`0x8b` with the flight ticks ([animation §3.4](../../formats/animation.md)) | A **carrier table** (`caster`, `target`, `spell`, `level`, `ticks_left`, `born`), not bodies. The visual position is derived in the view: interpolate caster -> target over the flight ticks (INFERRED, confirmed by REA in I4a if the client flies it differently) |
| "short-lived effects (an animation at a position)" | Fire Arrow has **no impact sprite** (id 11 has none); the visuals are the missile (`firebolt`, `A16=1`, phase `(age/2) mod Phases`) and the `smoke0` trail already in the anim API (`anim.load_projectile_set(10)`) | `world.effects` is built generic (position, set, start tick, lifetime) but I4 puts only the trail and the missile through it; impact sprites arrive with the spells that have them (K). Blend modes (D5) are read from the anim set, not invented |
| "mana cost; when mana is spent" | Spend is at **cast start** (`FUN_00519998`, mage flag check + spend, `0x51922e`). But both start heroes cast Fire Arrow from `Wood Staff {castSpell=Fire_Arrow:1}`: **item cast, level 1, no mana** | Two sources, both built: **staff/item cast** (level = item count N, free) and **learned spell** (`known_spells` bit, cost `param[1]`, level `skill[sphere] - 30 + Mind`). The default hero test uses the staff (what the campaign does); mana is exercised by the learned path (`Mage_Hero`) |
| "targeting rules: range, line of sight" | `max_range` is "no range test found at cast" ([spells §2](../../data/spells.md)); it is the AI approach distance. No LOS table is decoded ([open-questions](../../open-questions.md), Not started) | I4a answers with REA what the **client** does in `FUN_005702be` (range walk, "out of range", "no mana" response). LOS is **not modelled** unless that path uses it (then it joins the open question, not this spec) |
| "cooldown" | There is none; the cost is **recovery ticks**: `+0x135 + rand(0..3) + hero_delay + complication(3)` ([spells §9](../../data/spells.md)), spell `step_end` write (the I2 rest clock) | Implemented as that recovery; `Unit.step_end` gets the cast write that [death spec §2.1](2026-10-18-death-design.md) reserved |
| "resistances, area radius" | Fire Arrow is `distribution 1`: single target, no area. Damage `min' + rand(0..spread')` then `ftol(d*(100-prot_fire)/100 + 0.75)`, 0 if `+0x4c & 8` | Single target only. Area carriers are phase K |
| "win and lose conditions from E6 triggers" | `.alm` triggers (sections 7, 10-12) are **not started**; the condition dispatch `FUN_00574ba1` is unresolved ([open-questions](../../open-questions.md)) | I4c does **not** invent them. Its handoff section lists what is known (hero death: `HeroDied`, `Player.defeat_dialog`) and states the trigger work as the prerequisite for J |
| "fog/vision rules found in I3" | Answered in [ai §4](../../engine/ai.md): the sight flood is the **only** AI vision rule; no cone, no fog, no per-owner knowledge. Fog is a render-only layer ([rendering](../../engine/rendering.md), `0xc000` cell bits) | The handoff cites both; nothing to build |
| "AI doesn't cast yet" | Agreed: `FUN_0056a981`, `FUN_0056b059`, `FUN_0056bc7b`, the caster lists and the cast branches stay in the phase K list ([ai §12](../../engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127)) | Unchanged. The spell pass must not break the `ai=True` paths: mages keep falling back to melee |
| "Status: I done, Next: J1" | CLAUDE.md "Next: I4" also names special attacks and structures as targets | CLAUDE.md after I4c: "I done except special attacks (`FUN_0056a981`) and structure targets, moved to the phase K list"; Next: J1. Both are copied into `ai.md §12` |

## 2. I4a: research and simulation

### 2.1 REA questions (only what is not yet in the docs)

Record each as CONFIRMED / INFERRED with addresses in [spells §9c](../../data/spells.md) (new) and [combat §13](../../engine/combat.md) (new).

1. **Client cast path** `FUN_005702be` (and `FUN_0056c72b`): the message it sends (`0x1e`/`0x1f`, `0x25`/`0x26`), the checks before it (spell known, mana,
   range, target kind, fogged target -> move per the cursor table), the wording and trigger of the **no mana** and **out of range** responses (message line text index, sound).
2. **Approach**: does the hero walk into range first (order, `brain+0x14` = spell range via `pathfinding.default_range`) or cast at once?
3. **Cast timeline**: windup `unit+0x134`, release at phase 5 -> 0 (`FUN_00519d7f`/`db8`), action 8 (cast) frame at which the client spawns the projectile (`FUN_0046707e`), the release frame
   vs the server effect tick (animation §2.4), and what `step_end` gets.
4. **Item cast**: `weapon+0x84` / state 3 path of the staff (level N, no mana, charges?) vs the learned-spell path; who owns the "castSpell" weapon branch in `FUN_00516f6f` (combat §5 item 4).
5. **Cancel semantics**: a Stop or a new order during the windup (is mana already spent? does the missile fly?), a dead or moved target during the flight (the carrier delivers to a corpse? `FUN_0051e65b` target checks).
6. **Visual**: spawn position and height of the missile, trail spawn rate, blend mode of `firebolt` and `smoke0` (palette ids, D5), sound 510 timing.

Anything the exe does not reveal becomes a VERIFY IN GAME item (never a guess in code).

### 2.2 World and systems

- `engine/world.py`: `Unit` gets `spell_cast` (None or the cast in progress: spell, target, level, source "item"/"known", windup/recovery counters); `World.carriers` (list in creation order:
  `uid`, `caster`, `target`, `spell`, `level`, `ticks_left`, `born`), `World.next_carrier_id`; `dump()` adds `"carriers"` and the per-unit `"cast"` **only when non-empty** (existing goldens stay unchanged).
  Events (fight log, never dumped): `CastStarted(tick, caster, target, spell)`, `CastRefused(tick, caster, reason)` (`no_mana`, `out_of_range`, `no_target`, per research 2.1.1), `Hit` reuses `Damage`.
- `engine/sim/spells.py` (new; layer 4): `start_cast` (`FUN_00519998`: checks, spend, flight ticks `trunc(dist*256)/speed`, recovery), `cast_tick` (windup -> release),
  `carrier_system` (tick down, deliver: `FUN_0051e65b` -> the existing `combat` damage path with the spell damage `SpellDef.scaled(level)` and `prot_fire`, XP credit through `xp.damage_credit` for the hero, `Died` as usual),
  `damage_taken`/`level_of` are the existing `spelldefs` functions (no duplicate formula).
- `engine/sim/commands.py`: `CastSpell(player_id, unit_ids, spell_id, target)` with `target` = `("unit", id)` or `("cell", (x, y))` (the cell form is accepted by the type but Fire Arrow only uses units; Control Spirit etc. are K).
  Exe mapping is fixed by research 2.1.1. `ai: bool = False` stays for K.
- `engine/sim/simulation.py`: `carrier_system` after `movement_system` (the exe delivers inside the server tick; the exact slot is research 2.1.3). The default system list gains it; `ai=True` runs unchanged.
- `engine/sim/orders.py`: intake for `CastSpell` (selected units of the player, one caster per command as the exe), refusing as the exe does.
- Mages under AI still call melee: the combat code path that chose melee for spell users is kept, and a test pins it (so K changes it knowingly).

### 2.3 Tests (headless, no game files where possible)

- Formula table: Fire Arrow damage for L = 1, 30, 99 against prot 0 / 50 / flag `+0x4c & 8`; flight ticks for distances 1, 3, 7 cells (speed 200); recovery range `3 + {0..3} + hero_delay`.
- Timeline: a scripted cast: order tick, windup, release tick, carrier `ticks_left`, delivery tick, HP delta, `step_end`, mana before/after (learned) and unchanged (staff).
- Refusals: not enough mana (no spend, event), out of range as research 2.1.1 says, dead target, target not a unit.
- Cancel/death cases per research 2.1.5.
- Determinism: replay of the command log gives the same `dump_hash`; carrier order is creation order.
- No regression: all existing goldens unchanged (the new dump keys are omitted when empty).

Deliverables: `spells.py`, `commands.py`, `world.py`, `orders.py`, `simulation.py`, `tests/test_engine_spells*.py`, spells.md §9c, combat.md §13, open-questions, CLAUDE.md status line "I4a done".

## 3. I4b: view and UI

- **Draw list** (`engine/view/drawlist.py`): `World.carriers` and `World.effects` become `DrawItem`s depth-sorted with units; the missile uses the projectile anim set (`load_projectile_set(10)`, phase `(age/2) mod Phases`,
  16 directions from caster -> target), the trail follows the rule in animation §4.4, blend modes come from the anim set. Position is interpolated per tick (sub-cell) in the **view only**; the sim stores no floats.
- **Cast animation**: `unit_frame` shows the `cast` action (action 8) during the windup/recovery of `Unit.spell_cast`.
- **UI** (`engine/ui/orders.py`, `cursor.py`, `layout.py`): one spell slot: hotkey and a panel button (positions from the exe's command bar where known, otherwise a DECISION recorded in [ui-layout](../../engine/ui-layout.md));
  clicking it sets the **pending mode 5 (cast)** (cursor table in click-to-move-research §1.3-1.4), a left click on a hostile unit issues `CastSpell`, a click elsewhere cancels/moves as the exe does.
  The refusal responses use the exe's text and message line (research 2.1.1); sound is not played here ([audio.md](../../engine/audio.md)).
- **Info panel**: the mana row already exists (`interface.py`); I4b adds the spell slot state (greyed when mana < cost) and the hero's mana bar update.
- Tests: draw-list contents for a flying carrier (item present, depth order, interpolated position, trail), pending-mode transitions, hotkey and button -> command, refusal text. Screenshot test of a fixed tick with a missile in flight (existing screenshot harness).

Deliverables: `drawlist.py`, `ui/*`, `backend_pygame/*`, `tests/test_engine_spell_view.py`, `test_engine_spell_ui.py`, ui-layout.md, CLAUDE.md "I4b done".

## 4. I4c: close-out

- **Scenario**: the hero (staff, and a variant with a learned spell) fights a monster group on a real map, using melee and Fire Arrow through commands only; runs until the hero or all monsters are dead;
  deterministic. Map and group chosen from the existing real-map test fixtures (`tests/test_engine_orders_maps.py` style); skipped without the install like those.
- **Replay at 30 and 60 fps**: the sim is a fixed-tick loop, so the test drives the same command log through the frame-rate-dependent driver at 30 and 60 fps (including the draw-list build every frame) and compares `dump_hash`
  at every N ticks and at the end. This proves the view never mutates the world.
- **H integration test with combat on**: the existing movement integration test runs with `ai=True` and casting enabled: no stuck units, spatial index consistent (`World` index check).
- **Performance**: `tools/bench_fight.py` (new, like `bench_orders.py`): 15 units fighting with carriers in flight; the report is ms per tick and per frame; the acceptance threshold is the number measured on the
  current melee fight plus a stated margin, written into the doc (no invented absolute figure).
- **Golden hashes**: 3 combat scenarios in `tests/golden.json` (`tools/update_golden.py`, synthetic worlds that need no install): staff cast kill, learned-spell cast with mana spend and refusal, melee + cast mix. Update only by the tool, per the golden rule in CLAUDE.md.
- **Docs**: combat.md complete (sections 10 and 13 updated); new section "Handoff to prototype completion": the hero-death/defeat pieces that exist, the **missing win/lose triggers** (`.alm` sections 7, 10-12, `FUN_00574ba1`) as the J prerequisite,
  the fog/vision facts (AI: sight flood only; render: fog bits), the UI pieces still missing for J (new-game screen, load/quit dialog on hero death, spellbook, inventory screens, formation); `ai.md §12` gets the moved items.
- **Close**: update CLAUDE.md (Status "I done" with the deferred items named; Next "J1: minimal UI"), `docs/open-questions.md`, `docs/engine/README.md` row. Commit per part, each only after the tests pass and with the user's confirmation.

## 5. Assumptions and risks (flagged, not decided silently)

- **Missile visual path** (straight interpolation) is INFERRED until research 2.1.6; it is view-only, so a correction cannot change a hash.
- **Staff vs learned spell** both built; if research shows the staff path is not a `CastSpell` command but a weapon branch of the attack (combat §5 item 4), the staff cast is wired as that branch and `CastSpell` serves the learned path only. The plan will state which at I4a's end.
- **No LOS**, no area carriers, no impact sprites, no Lightning chain: out of scope, named in the handoff.
- **Scale**: I4a is the largest part (research dominates). If a research question in 2.1 turns out to need more than the single routine named, it is split off into its own docs commit before sim code starts (stop and say so, do not guess).
