# Progression, heroes and data-layer close-out (F3 + E/F verification)

Goal: document character progression, export it, give hero units their skills, then verify the
whole game-data layer (units, items, spells, maps, progression) before movement and combat (phase H)
depend on it. Single player, GOG exe only (sha256 `0eaa9673…`). Marks per CLAUDE.md: CONFIRMED = read
in the exe via REA; INFERRED otherwise. Formulas below are math, not decompiler output.

## 1. Progression: findings already confirmed

**There is no single character level.** A human has six skill words `+0xa8..+0xb2` (index 0 general, 1-5
the five schools: Blade/Fire, Axe/Water, Bludgeon/Air, Pike/Earth, Shooting/Astral; see
[unit-struct](../../engine/unit-struct.md)). Skills 1-5 level individually; each has its own XP pool at
`+0x23c+4k` (k = 1..5); `+0x130` is the sum of the pools. `+0x23c` itself (k = 0) is the best-school index
for `Hero`/`Start` templates (`FUN_00514cf2`). Skill 0 never levels here.

**Curve (CONFIRMED, `FUN_00512824` at start-up, called from `0x480c8d`).**

```
thr[n] = trunc(1.1 ** n)           n = 0..149      (table 0x6a8998, 150 dwords)
threshold(n) = thr[min(n, 149)]    FUN_005128ac
```

`thr` is XP *accumulated in that skill* needed to reach level n (1.1^n: 1 at n<=7, 13 780 at n=100).
A skill level is capped at 100 (award is ignored when the skill is >= 100).

**Pool initialisation (CONFIRMED, `FUN_00513497`).** `pool[k] = thr[skill_k]` for k = 1..5, `total = sum(pool)`;
the "base" copy `+0x116+2k` = `skill_k`. So a freshly built hero with skill 20 starts with `thr[20]` XP.

**Award (CONFIRMED, `FUN_005128cb`, vtable slot `0x60`; kill credit `FUN_00512fcb` is slot `0x64`).**
Humans only (unit_type 0x21..0x3f; summoned units, `+0x1a0 != 0`, are excluded). For an award `xp`
attributed to school `s` (the unit's active attack/cast school at `+0xb6`, or the explicit argument):

```
xp = kill: trunc(killed.+0x1c * 0.5)            # monster XP param (data.bin 37), 0 for other sources
xp = xp * 10 / (kills_of_that_type + 10)         # repeat-kill list at +0x1a8, 5 entries, kill counter in the high word
if s != best_school and s != 5: xp = (xp + 7) >> 3     # off-school
xp = min(xp, thr[skill_s + 1] - thr[skill_s])    # FUN_00512f44 (single player; multiplayer divides the span by 5)
pool[s] += xp ; total += xp
if pool[s] >= thr[skill_s + 1]: skill_s += 1 ; base[s] += 1 ; notify client (event 2) ; recompute (vtable +0x58)
```

The award is skipped when killer and victim are allied/same team (`+0x14` relation matrix). Mage spell-cast
and heal credits (`FUN_00513128`, `FUN_005131ef`) feed the same slot `0x64` with amounts scaled from the spell
table (`0x68f5cc`) cost/effect, so XP is earned **per kill and per spell use**, not per damage point.
Skill bonuses (`+0xe8`, equipment/effects) are re-added after every award.

## 2. Research to finish with REA during implementation

Each item ends in a CONFIRMED/INFERRED row in `docs/data/progression.md`; addresses only, formulas are phase I.

1. **What a skill-up changes beyond the skill.** Start at the recompute virtual (`+0x58` of the human vtable),
   `FUN_0051c3e4`, `FUN_00502019` (`0xffb` event). Answer: does max HP, max mana, to-hit, defence or spell power
   derive from skill/attributes, and where (cap values, per-level steps)?
2. **Skill roles and use sites.** For each skill 1-5 (and general 0): what it affects (melee/ranged to-hit,
   damage, spell level = skill - 30 + Mind per [spells](../../data/spells.md)), plus the addresses that read
   `+0xa8..+0xb2` / `+0xe8..`. Scan the full disassembly for those offsets.
3. **XP sources and callers.** Callers of vtable `0x64`/`0x60` (kill, spell cast, heal), the weapon-school mapping
   `+0xb6`, the `+0x1a8` list reset, and the scenario/quest XP rewards.
4. **Hero start.** Which data.bin record a single-player map hero resolves to (map section 6 `server_id`, `flags & 0x10`
   = human), how `known_spells` (bitmask, bit n = spell n, n = 1..29 loop in `FUN_005145d1`) and `equipment`
   strings become spells/inventory, mana (`mana_max` -> `+0x9a`), and whether campaign carry-over (saves,
   `.a2c`) exists in the maps' own data. Carry-over stays out of scope if it needs save files.

## 3. Hero data (from data.bin, no extra source found)

Hero templates are human records whose name contains `Hero` or `Start`: `Start_MF/FF/MM/FM` (server ids
10210-10213), `Fighter_Hero` 10220, `Mage_Hero` 10230. Their params give attributes (body, reaction, mind,
spirit), `hp_max`, `mana_max`, the five school skills, `known_spells` bitmask and 10 equipment strings
(already parsed by `itemdefs`). Map section 6 overrides only HP ([units §3](../../data/units.md)). Item 4 above
must confirm that a map unit of these types also gets its skills exactly from the record.

## 4. Deliverables

1. `allods2/formats/progression.py` (core, no pygame): `Progression` with `thresholds` (computed from the
   formula), `SKILL_NAMES`, `SCHOOLS`, award constants (kill factor 0.5, off-school shift 3, repeat window 5,
   skill cap 100) and `hero_templates` (name, server id, attributes, skills, spells by name, equipment, start
   pools). `load(fs)`, `to_dict()`.
2. `AssetCache.progression()`; `data export progression` -> `out/data/progression.json` (gitignored);
   `tools/update_golden.py` extended; `docs/data/progression.md` (findings, CONFIRMED/INFERRED, open questions).
3. World: a `Unit` with a human/hero template gets `skills` (6 values), `xp` (pools k=1..5) and
   `best_school`; no award logic yet (phase H/I). Test on a campaign map with a hero.
4. **Close-out.**
   - `tests/test_data_integration.py` (skipped without the install): every table loads (databin, units, items, spells,
     progression); cross references resolve: unit type -> units.reg sprite set, item -> sprite, spell -> effect
     record, map unit/item/spell ids -> tables for every map of the install. Failures list the offenders.
   - `tests/golden.json`: hashes of all exported JSON (units, items, spells, progression) regenerated and reviewed by
     diff (only `progression` new unless a bug is found).
   - `docs/data/overview.md`: per table: source, status, "how the engine uses it". Linked from docs/data/README.
   - Section "Handoff to movement and combat" in overview.md: movement speeds and their units (`speed` param ->
     step length `+0xa8` in 1/256 cell per tick, `FUN_00559195`), attack range, cooldown (`windup`/`recovery`) and
     damage fields (`damage_min`/`spread`, kinds 0-5), the hit-chance and damage formula locations still to reverse
     in phase I (`0x516f6f`, to-hit `+0xa6`), and the prototype spell's (Fire Arrow) dependencies.
5. CLAUDE.md: Status "E and F done", Next "H1: unit movement state and the tick". Commit (spec first, then work).

## 5. Assumptions and decisions

- DECISION: no combined "level" in the engine; `Unit.skills`/`xp` mirror the exe. A UI "level" would be a display
  choice of a later phase.
- DECISION: threshold table is computed from the formula (REA-confirmed) and a unit test pins the first values and
  `thr[100] = 13780`, `thr[149] = 1470652`; there is no data file to ship.
- Implementation order: REA research (item 1-4) -> `progression.py` + loader + export -> world hero state -> close-out
  tests and docs. One sonnet subagent at a time, each told to verify against the exe with REA.

## Open questions

- Carry-over of hero state between campaign maps (needs saves / `.a2c`); stays in docs/open-questions.md.
