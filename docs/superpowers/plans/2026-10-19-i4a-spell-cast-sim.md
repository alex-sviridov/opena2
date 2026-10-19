# I4a: Fire Arrow cast simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The player's hero casts Fire Arrow at a unit in the headless simulation, with the exe's order, mana, windup, flight, hit, damage, XP and recovery, verified by tests.

**Architecture:** Research tasks (REA on `allods2.exe`) first, writing tagged facts into `docs/data/spells.md §9c` and `docs/engine/combat.md §13`; then pure math in `engine/sim/spells.py`, new world state (`Unit.spell_cast`, `World.carriers`), the `CastSpell` command, a cast phase machine next to `combat.swing_tick`, and a `carrier_system`. The exe has no flying body on the server: a carrier counts `trunc(dist*256)/speed` ticks, then applies the damage ([spells §9](../../data/spells.md)).

**Tech Stack:** Python 3.13, numpy, pytest, REA MCP tools (`mcp__rea__*`) on `samples/allods2_en_gog/allods2.exe`.

**Spec:** [`docs/superpowers/specs/2026-10-19-spell-cast-design.md`](../specs/2026-10-19-spell-cast-design.md) (section 2 = this plan; sections 3-4 are I4b / I4c, out of scope here).

## Global Constraints

- **1:1 recreation of the exe.** Every number and rule comes from REA of the GOG `allods2.exe` or from an already CONFIRMED doc; where REA cannot answer, write INFERRED in the doc and add a VERIFY IN GAME line, never a silent guess. The user's standing rule: use REA to reconstruct the original math.
- GOG single player only; no 1.30 / a2mgr references; multiplayer out of scope.
- Addresses are VAs of the GOG exe. Tags `CONFIRMED` / `INFERRED` on every fact (CLAUDE.md).
- Dependencies: stdlib + numpy; no new pip packages. The sim has no floats in the dump; floats only where the exe uses x87 (`ftol` = truncation toward zero).
- Existing goldens must not change: new dump keys appear only when non-empty (pattern of `World._death_state`, `world.py:1036`).
- The AI does not cast (phase K): mages under `ai=True` keep the melee fallback; a test pins it.
- Tests run headless on synthetic worlds (helpers as in `tests/test_engine_combat.py`: `world()`, `fighter()`, `run()`); no install needed except tests marked `needs_data`.
- Run one subagent at a time (CLAUDE.md). Commit only when the tests pass; the user confirmed commits for this plan's tasks.
- Commit message ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

- Casting with exactly `mana == cost` succeeds and leaves 0; with `cost - 1` is refused with no spend and no state change.
- Target dies (or is removed, stage 5) between the order and the release, and between release and delivery: no crash, no damage to a freed id, mana policy as REA says.
- Two casts in one tick / a cast ordered during recovery: the second is refused or queued exactly as the exe does, never two carriers for one windup.
- Caster killed during windup or flight: the already-released carrier still delivers (or not) as REA says; a dead caster's id must not be dereferenced.
- Target out of range at the order, target moves out of range after release: no range test at delivery (the exe has none) and no divide by zero for distance 0 (`dist = 0` gives 0 flight ticks).

---

## File Structure

- `docs/data/spells.md` §9c (new): server cast chain facts, tagged. `docs/engine/combat.md` §13 (new): the engine mapping and VERIFY IN GAME items.
- `engine/world.py`: `SpellCast`, `Carrier` dataclasses, `Unit.spell_cast`, `World.carriers`, `World.next_carrier_id`, `World.spell_table`, dump keys, events `CastStarted`, `CastRefused`.
- `engine/sim/spells.py` (new): pure math (`flight_ticks`, `cast_level`, `fire_damage`, `recovery_ticks`) + `start_cast` + `cast_tick` + `carrier_system`.
- `engine/sim/commands.py`: `CastSpell`. `engine/sim/orders.py`: intake. `engine/sim/movement.py`: state hook. `engine/sim/simulation.py`: system list.
- Tests: `tests/test_engine_spells_math.py`, `tests/test_engine_spells_cast.py`, `tests/test_engine_spells_carrier.py`.

---

### Task 1: REA research, client side (command, checks, responses)

**Files:**
- Modify: `docs/data/spells.md` (new §9c.1), `docs/open-questions.md`

**Interfaces:**
- Produces: a fact list that Tasks 4 and 5 consume: (a) exe command id and operands for a unit-target cast, (b) the checks and their order, (c) the refusal texts / sounds, (d) whether the hero walks into range first, (e) pending-mode 5 click rules.

- [ ] **Step 1: Open the binary**

`mcp__rea__open_binary` on `/work/allods2/samples/allods2_en_gog/allods2.exe` (or `list_documents` if a session is already open; see memory note rea-ghidra-analysis for key routines and search tips).

- [ ] **Step 2: Decompile and read the client cast path**

`mcp__rea__procedure_pseudo_code` and `procedure_assembly` for `FUN_005702be`, `FUN_0056c72b`, `FUN_00418a02` (pending mode 5), and the network command applier cases for the cast commands (`FUN_005503af` area; spells.md line 75 names it). Use `procedure_callers`/`procedure_callees` to follow into `FUN_0056dca2` (states `0xd`/`0xe`).

- [ ] **Step 3: Answer, with addresses, each of these**

1. Command id and operands (caster ids, spell index, target object id or cell) for message `0x1e`/`0x1f` and `0x25`/`0x26`; which one a unit-target Fire Arrow uses.
2. Every check before the order is accepted: caster alive, spell known (`unit+0x140` bit), mana vs `param[1]`, target kind (`param[4]`), range (spells.md says "no range test found at cast": confirm or find it), fog, owner relation.
3. For each failed check: what the client does (message-line text index in `main.txt`, sound id, cursor), and whether the server is told.
4. Whether the caster walks into range first (`brain+0x14` set from `FUN_005195b1` range, `pathfinding.default_range`), and the exact order id set.
5. Who is the caster when several units are selected (first id only, like `intake`?).

- [ ] **Step 4: Write §9c.1 in `docs/data/spells.md`**

One table: fact | routine and address | tag. Add every unresolved item to `docs/open-questions.md` (Spells section) and a `VERIFY IN GAME` line. Remove the answered line "Client cast command path" from `open-questions.md` (CLAUDE.md rule: answered questions are deleted from both places).

- [ ] **Step 5: Commit**

```bash
git add docs/data/spells.md docs/open-questions.md
git commit -m "Docs: client cast path of unit-target spells (REA) for I4a

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: REA research, server side (timeline, carrier, staff, cancel)

**Files:**
- Modify: `docs/data/spells.md` (§9c.2), `docs/engine/combat.md` (§13 skeleton), `docs/open-questions.md`

**Interfaces:**
- Produces, for Tasks 3-7: numbers and rules for (a) states `0xd`/`0xe` and their phase counters, (b) mana spend point and the `mage flag` check, (c) windup / recovery byte formulas and `step_end` write, (d) carrier delivery order inside the server tick, (e) behaviour on dead target / dead caster / cancel, (f) the staff (`weapon+0x84`) path and its level, (g) client visual facts for I4b (spawn height, trail rate, blend mode, sound timing) recorded but not built.

- [ ] **Step 1: Read the chain**

`mcp__rea__procedure_pseudo_code` + assembly for `FUN_0056dca2` (order switch, cast request), `FUN_0056e906`, `FUN_0056e986`, `FUN_00519998`, `FUN_00519d7f`, `FUN_00519db8`, `FUN_00518d1e`, `FUN_00518efd`, `FUN_00542e60`, `FUN_0051e65b`, `FUN_00516aae`, `FUN_0050f12c` (state switch, cases for `0xd`/`0xe`/3), `FUN_00504ab8`. Follow `procedure_callees` for anything unnamed.

- [ ] **Step 2: Answer, with addresses**

1. States `0xd` and `0xe`: what each does per tick; the phase variable (`+0x58`), the byte timer (`+0x6c`), the windup byte `+0x134` and recovery byte `+0x135` sources for a caster (spell windup = ? ticks; is it `ShootDelay`/`AttackDelay` of the unit type or a constant?), "effect at phase 5 -> 0".
2. Exactly when mana is spent (`0x51922e` / `0x519998`) and what the mage-flag check is (`unit+0x4c & 4`? the item cast skips it?). Whether mana is returned on cancel.
3. Recovery: `+0x135 + rand(0..3) + hero_delay + complication` : confirm each term, which RNG call and in what order relative to other draws (the world RNG stream order matters for determinism and for matching the original).
4. `step_end` (`+0x138`) write for a cast (death spec §2.1 reserved it).
5. Carrier list tick: where in the server tick `FUN_00518efd` runs relative to creature ticks; what happens when the target id no longer resolves; whether the carrier knows the caster after the caster died (attacker credit `param[0x10]`).
6. Position used for `dist` (centre of footprint, `pathfinding.centre_x/centre_y`?) and the unit of `FUN_00516aae`.
7. Staff path: `castSpell=Fire_Arrow:1` -> `weapon+0x84`, state 3 and combat §5 item 4: does a staff hit cast on top of the melee blow, or is a staff a ranged weapon whose attack IS the cast? Level = item count; mana free?
8. Cancel: Stop or new order during windup / recovery.
9. Client visual facts for I4b (spawn height, trail rate, blend id, sound 510 frame).

- [ ] **Step 3: Write §9c.2 and combat §13**

Tagged table in spells.md §9c.2; combat.md §13 = "Spell casts (I4)": the engine mapping skeleton (filled in by Tasks 3-7) and a VERIFY IN GAME list. Update `open-questions.md` (add leftovers, delete answered).

- [ ] **Step 4: Decide the staff wiring and record it**

Write one paragraph at the top of §9c.2: "Staff cast is (a) a `CastSpell` order or (b) a weapon branch of the attack" with the evidence. Tasks 6 and 7 follow it.

- [ ] **Step 5: Commit**

```bash
git add docs/data/spells.md docs/engine/combat.md docs/open-questions.md
git commit -m "Docs: server cast chain, carrier delivery, staff cast (REA) for I4a

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Math module

**Files:**
- Create: `engine/sim/spells.py`, `tests/test_engine_spells_math.py`

**Interfaces:**
- Consumes: `allods2.formats.spelldefs` (`SpellDef.scaled(level)`, `level_of(skill, mind)`, `damage_taken(rolled, protection)`, `ftol`), `engine.sim.combat.hero_delay`.
- Produces:
  - `flight_ticks(spell, dx, dy) -> int` (dx, dy in 1/256 cell)
  - `cast_level(unit, spell, item_count=None) -> int`
  - `roll_damage(spell, level, rng) -> int` (before protection)
  - `damage_after_protection(rolled, protection) -> int`
  - `recovery_ticks(base, hero_delay, complication, rng) -> int`

- [ ] **Step 1: Write the failing tests**

```python
"""Spell math (I4a): flight time, level, damage roll, recovery.  Spec: docs/data/spells.md section 9 / 9c."""

import pytest

from allods2.formats import spelldefs
from engine.rng import Rng
from engine.sim import spells as sp


class FakeSpell:
    def __init__(self, number=1, delivery=2, speed=200):
        self.number, self.delivery, self.speed = number, delivery, speed


def test_flight_ticks_is_truncated_distance_over_speed():
    s = FakeSpell()
    assert sp.flight_ticks(s, 7 * 256, 0) == 8             # 1792 // 200
    assert sp.flight_ticks(s, 3 * 256, 4 * 256) == 6       # sqrt(768^2+1024^2)=1280 // 200
    assert sp.flight_ticks(s, 0, 0) == 0


def test_lightning_is_fixed_at_five():
    assert sp.flight_ticks(FakeSpell(number=10, speed=60), 9 * 256, 0) == 5


def test_direct_delivery_has_no_flight():
    assert sp.flight_ticks(FakeSpell(delivery=1), 5 * 256, 0) == 0


def test_cast_level_item_count_wins():
    class U:
        skills = (0, 40, 0, 0, 0, 0)
    assert sp.cast_level(U(), FakeSpell(), item_count=1) == 1


def test_damage_after_protection_matches_spelldefs():
    assert sp.damage_after_protection(10, 50) == spelldefs.damage_taken(10, 50) == 5
    assert sp.damage_after_protection(7, 0) == 7


def test_fire_arrow_damage_range_level_1_and_99():
    table = spelldefs.load()
    fa = table.get(1)
    for level, (lo, hi) in ((1, (5, 10)), (99, (21, 43))):
        seen = {sp.roll_damage(fa, level, Rng(seed)) for seed in range(300)}
        assert min(seen) == lo and max(seen) <= hi
```

The 99 row follows spells.md ("`21 + rand(0..22)`"): bounds `min' + rand(0..spread')` with `min' = ftol(5 * (99/30 + 1))`. If `scaled(99)` disagrees, fix the **test** to the value `SpellDef.scaled` returns and say so in the commit message (the formula there is already CONFIRMED).

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_engine_spells_math.py -q`
Expected: FAIL (`engine.sim.spells` missing).

- [ ] **Step 3: Implement**

```python
"""Spell casting (phase I4): math, cast start, cast phases, carriers.  Facts: docs/data/spells.md section 9 and 9c, docs/engine/combat.md 13."""

import math

from allods2.formats import progression as prog, spelldefs      # as engine/sim/xp.py imports `prog`

LIGHTNING = 10


def flight_ticks(spell, dx, dy):
    """Missile flight time (`FUN_00519998`, `FUN_00516aae`): `trunc(sqrt(dx^2 + dy^2)) / speed` for missile delivery (positions in 1/256 cell),
    5 for Lightning, 0 otherwise (CONFIRMED, animation.md 3.4)."""
    if spell.delivery != 2:
        return 0
    if spell.number == LIGHTNING:
        return 5
    return int(math.sqrt(dx * dx + dy * dy)) // spell.speed


def cast_level(unit, spell, item_count=None):
    """An item cast uses the item's count; a unit's own cast `skill[sphere] - 30 + Mind`, clamped (`spelldefs.level_of`)."""
    if item_count is not None:
        return item_count
    mind = prog.attributes(unit.stats)[2]
    return spelldefs.level_of(unit.skills[spell.sphere], mind)


def roll_damage(spell, level, rng):
    """`min' + rand(0..spread')` of the scaled spell, before protection (spells.md section 5)."""
    sc = spell.scaled(level)
    return sc.damage_min + (rng.rand(sc.damage_spread + 1) if sc.damage_spread > 0 else 0)


def damage_after_protection(rolled, protection):
    return spelldefs.damage_taken(rolled, protection)


def recovery_ticks(base, hero_delay, complication, rng):
    """`+0x135 + rand(0..3) + hero_delay + complication` (spells.md section 9, order of the RNG draw per Task 2 finding)."""
    return base + rng.rand(3) + hero_delay + complication
```

Before writing, read how `combat.swing_tick` calls `world.rng.rand(3)` (inclusive upper bound? `rand(3)` there gives `0..3`, spells.md says `rand(0..3)`) and mirror its convention; `roll_damage` must use the same inclusive/exclusive convention as the exe's `rand(n)` in `engine/rng.py`.
- [ ] **Step 4: Run, expect pass**

Run: `python -m pytest tests/test_engine_spells_math.py -q`
Expected: PASS. Fix by reading `engine/rng.py` if the 99-level bounds fail, not by loosening.

- [ ] **Step 5: Commit**

```bash
git add engine/sim/spells.py tests/test_engine_spells_math.py
git commit -m "Spells (I4a): flight time, level, damage roll, recovery math

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: World state, events, `CastSpell` command, refusals and mana

**Files:**
- Modify: `engine/world.py` (near `Damage` at ~164 and `Unit` at ~315; `World.__init__` ~435; `dump` ~948; loader ~773), `engine/sim/commands.py`, `engine/sim/orders.py:261`, `engine/sim/__init__.py` (export)
- Modify: `engine/sim/spells.py`
- Test: `tests/test_engine_spells_cast.py`

**Interfaces:**
- Consumes: Task 1 findings (command shape, checks, refusal reasons), Task 3 math.
- Produces:
  - `commands.CastSpell(player_id, unit_ids, spell_id, target, ai=False)`; `target = ("unit", id) | ("cell", (x, y))`
  - `world.SpellCast(spell, target_id, level, source, phase, timer, done)` and `Unit.spell_cast`
  - `world.Carrier(uid, caster, target, spell, level, ticks_left, born)`, `World.carriers`
  - events `CastStarted(tick, caster, target, spell)`, `CastRefused(tick, caster, reason)`
  - `spells.start_cast(world, unit, spell_id, target_id, source="known", item_count=None) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
"""CastSpell: intake, refusals, mana (I4a).  Synthetic worlds."""

import numpy as np
import pytest

from allods2.formats import spelldefs
from engine.sim import CastSpell, Simulation
from engine.world import CastRefused, CastStarted, Player, Unit, UNIT_ID_BASE, World
from test_engine_combat import fighter, world, ids


def caster(w, uid, x, y, mana=10, owner=1):
    u = fighter(w, uid, x, y, owner=owner, hp=100)
    u.mana = u.mana_max = mana
    u.skills = (0, 0, 0, 0, 0, 0)
    u.known_spells = 1 << 1                      # bit n = spell n known (unit+0x140), Task 1 confirms the field name
    return u


def sim_with_spells():
    w = world()
    w.spell_table = spelldefs.load()
    return w, Simulation(w)


def test_cast_with_exact_mana_spends_all():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5, mana=3), fighter(w, 2, 9, 5, owner=2)
    sim.step([CastSpell(1, (c.id,), 1, ("unit", t.id))])
    assert any(isinstance(e, CastStarted) for e in w.fight_log) and c.mana == 0


def test_cast_one_short_is_refused_and_changes_nothing():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5, mana=2), fighter(w, 2, 9, 5, owner=2)
    before = w.dump_hash()
    sim.step([CastSpell(1, (c.id,), 1, ("unit", t.id))])
    refused = [e for e in w.fight_log if isinstance(e, CastRefused)]
    assert refused and refused[0].reason == "no_mana" and c.mana == 2 and c.spell_cast is None
    assert not w.carriers


def test_unknown_spell_and_missing_target_are_refused():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5), fighter(w, 2, 9, 5, owner=2)
    c.known_spells = 0
    sim.step([CastSpell(1, (c.id,), 1, ("unit", t.id))])
    sim.step([CastSpell(1, (c.id,), 1, ("unit", 0xdead))])
    assert [e.reason for e in w.fight_log if isinstance(e, CastRefused)] == ["not_known", "no_target"]


def test_command_of_another_player_is_ignored():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5), fighter(w, 2, 9, 5, owner=2)
    sim.step([CastSpell(2, (c.id,), 1, ("unit", t.id))])
    assert c.spell_cast is None and not w.fight_log


def test_empty_world_dump_is_unchanged_without_casts():
    w, _ = sim_with_spells()
    assert "carriers" not in w.dump()
```

The exact refusal reasons and which of them the exe reports to the player (versus silently dropping the order) come from Task 1; if the exe drops silently, replace `CastRefused` with no event and assert no state change only. The `known_spells` field name: use whatever `Unit` actually carries for the spellbook bit mask (`unit+0x140`); if none exists add `known_spells: int = 0` to `Unit`, filled by `from_map` from the template `known_spells` (p56) and the hero's starting book (units.md).

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_engine_spells_cast.py -q`
Expected: FAIL (names missing).

- [ ] **Step 3: Implement world state**

In `engine/world.py` add next to `Damage`:

```python
@dataclass
class CastStarted:
    """Fight log: a cast was accepted (mana spent for a learned spell)."""
    tick: int
    caster: int
    target: int
    spell: int


@dataclass
class CastRefused:
    """Fight log: a cast order was refused (`reason`: Task 1 names)."""
    tick: int
    caster: int
    reason: str


@dataclass
class SpellCast:
    """The cast in progress (state 0xd/0xe, Task 2 names): the phase and timer mirror the swing's `phase` / `timer`."""
    spell: int
    target_id: int
    level: int
    source: str                     # "known" or "item"
    phase: int = 0
    timer: int = 0
    done: bool = False


@dataclass
class Carrier:
    """Missile carrier (`FUN_00518d1e`): delivers the spell to `target` when `ticks_left` runs out (docs/data/spells.md section 9)."""
    uid: int
    caster: int
    target: int
    spell: int
    level: int
    ticks_left: int
    born: int
```

`Unit` gets `spell_cast: object = None` and (if absent) `known_spells: int = 0`. `World.__init__` gets `self.carriers = []`, `self.next_carrier_id = 1`, `self.spell_table = None`; the asset loader at ~773 sets `w.spell_table = assets.spells()`. In `dump()` add `"carriers": [[c.uid, c.caster, c.target, c.spell, c.level, c.ticks_left, c.born] ...]` **only if** `self.carriers`, and per-unit `"cast"` through a `_cast_state(u)` static method returning `None` for `spell_cast is None and known_spells == initial`, following `_death_state`'s pattern (return None when at start value so old goldens stay valid). `known_spells` is not dumped unless it differs from the template-derived start value.

- [ ] **Step 4: Implement the command and `start_cast`**

`commands.py`:

```python
@dataclass(frozen=True)
class CastSpell(Command):
    """Cast command (Task 1: exe ids): the first unit of `unit_ids` casts spell `spell_id` at `target` = ("unit", id) or ("cell", (x, y))."""
    player_id: int
    unit_ids: tuple
    spell_id: int
    target: tuple
    ai: bool = False                # K: the AI cast path

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
```

`orders.py` `orders_system`: add before the generic fallthrough

```python
        elif isinstance(cmd, CastSpell):
            spells.cast_command(world, cmd)
```

`spells.py`:

```python
from .. import world as w   # events


def cast_command(world, cmd):
    """Intake like `orders.intake` for the first id only (Task 1 item 5); dispatches to `start_cast`."""
    if cmd.player_id not in world.players or not cmd.unit_ids:
        return
    u = world.units.get(cmd.unit_ids[0])
    if u is None or u.owner != cmd.player_id or u.hp <= 0:
        return
    kind, arg = cmd.target
    start_cast(world, u, cmd.spell_id, arg if kind == "unit" else None)


def refuse(world, u, reason):
    from .combat import log
    log(world, w.CastRefused(world.tick, u.id, reason))
    return False


def start_cast(world, u, spell_id, target_id, source="known", item_count=None):
    """The checks of the client path (Task 1) then `FUN_00519998`: spend the mana of a learned spell, set the cast state.  Returns True when the
    cast started.  A refusal changes nothing (tested)."""
    from .combat import log
    spell = world.spell_table.get(spell_id)
    t = world.find_unit(target_id)
    if source == "known" and not (u.known_spells >> spell_id) & 1:
        return refuse(world, u, "not_known")
    if t is None:
        return refuse(world, u, "no_target")
    if source == "known" and u.mana < spell.mana_cost:
        return refuse(world, u, "no_mana")
    if source == "known":
        u.mana -= spell.mana_cost
    level = cast_level(u, spell, item_count)
    u.spell_cast = w.SpellCast(spell_id, t.id, level, source)
    log(world, w.CastStarted(world.tick, u.id, t.id, spell_id))
    return True
```

Apply Task 1/2 corrections as you implement: the check order, the mage-flag condition (replace `source == "known"` guard where REA says the mana check keys off `+0x4c & 4`), whether mana is spent here or at release, and whether the cast goes through an order (approach) first. The tests change in the same commit if REA says so. Export `CastSpell` from `engine/sim/__init__.py`.

- [ ] **Step 5: Run, expect pass; run the whole engine suite for goldens**

Run: `python -m pytest tests/test_engine_spells_cast.py tests/test_engine_orders_golden.py tests/test_engine_combat.py -q`
Expected: PASS, goldens untouched.

- [ ] **Step 6: Commit**

```bash
git add engine tests/test_engine_spells_cast.py
git commit -m "Spells (I4a): CastSpell command, refusals, mana spend, cast state

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Cast phases, release, carrier delivery, damage and XP

**Files:**
- Modify: `engine/sim/spells.py`, `engine/sim/movement.py:603` (state switch in `_tick_unit`), `engine/sim/simulation.py:15`
- Test: `tests/test_engine_spells_carrier.py`

**Interfaces:**
- Consumes: Task 2 findings (state numbers, windup, delivery slot), Task 4 `SpellCast`, `Carrier`.
- Produces: `spells.cast_tick(world, u)` (called from the creature tick for the cast state), `spells.carrier_system(world, commands)`, `spells.deliver(world, c)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Cast timeline, carrier flight and delivery (I4a)."""

import pytest

from allods2.formats import spelldefs
from engine.sim import CastSpell, Simulation
from engine.world import Damage, Died
from test_engine_combat import fighter, world
from test_engine_spells_cast import caster, sim_with_spells


def cast_at(w, sim, c, t):
    sim.step([CastSpell(1, (c.id,), 1, ("unit", t.id))])


def test_timeline_release_flight_delivery():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5, mana=10), fighter(w, 2, 12, 5, owner=2, hp=100)
    start = w.tick
    cast_at(w, sim, c, t)
    seen = []
    for _ in range(80):
        sim.step()
        seen.append((w.tick, len(w.carriers), t.hp))
    release = next(tk for tk, n, _ in seen if n)
    delivered = next(tk for tk, n, hp in seen if hp < 100)
    assert release > start                               # windup first
    assert delivered - release == 8 or delivered - release == 9    # 7 cells * 256 // 200 = 8 (Task 2 fixes the off-by-one)
    assert not w.carriers                                # removed after delivery
    assert 5 <= 100 - t.hp <= 10                         # level 1, prot 0


def test_damage_uses_protection():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5), fighter(w, 2, 9, 5, owner=2, hp=1000)
    t.stats = None
    t.prot_fire = 50                                     # Task 2 names the real field (unit protection by element)
    cast_at(w, sim, c, t)
    for _ in range(60):
        sim.step()
    assert 1000 - t.hp in range(2, 6)


def test_target_dies_before_delivery_no_crash():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5), fighter(w, 2, 12, 5, owner=2, hp=100)
    cast_at(w, sim, c, t)
    for _ in range(12):
        sim.step()
    t.hp = -50
    for _ in range(40):
        sim.step()
    assert not w.carriers


def test_caster_dies_after_release_still_no_crash():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5), fighter(w, 2, 12, 5, owner=2, hp=100)
    cast_at(w, sim, c, t)
    while not w.carriers:
        sim.step()
    c.hp = -50
    for _ in range(40):
        sim.step()
    assert not w.carriers


def test_recovery_blocks_second_cast_and_sets_step_end():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5, mana=9), fighter(w, 2, 9, 5, owner=2, hp=1000)
    cast_at(w, sim, c, t)
    cast_at(w, sim, c, t)                                # same tick + 1: still casting
    assert c.mana == 6 and c.step_end > 0


def test_replay_gives_the_same_hash():
    def run():
        w, sim = sim_with_spells()
        c, t = caster(w, 1, 5, 5), fighter(w, 2, 12, 5, owner=2, hp=100)
        cast_at(w, sim, c, t)
        for _ in range(80):
            sim.step()
        return w.dump_hash()
    assert run() == run()
```

Numbers marked "Task 2 fixes" are the only ones allowed to move, and only to the value REA gives, with the address in a comment next to the assertion.

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_engine_spells_carrier.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`spells.py` additions (state/phase names are Task 2's; the skeleton mirrors `combat.swing_tick`):

```python
CAST_STATE = 0xd                 # Task 2: states 0xd / 0xe (FUN_0056e906 / FUN_0056e986)
PHASE_START, PHASE_WINDUP, PHASE_RECOVERY = 0, 5, 7


def cast_tick(world, u):
    """State machine of the cast, same shape as `combat.swing_tick` (spells.md section 9: windup `+0x134`, effect at phase 5 -> 0,
    recovery `+0x135 + rand(0..3) + hero_delay + complication`)."""
    sc = u.spell_cast
    if sc is None:
        return
    spell = world.spell_table.get(sc.spell)
    st = combat_stats(world, u)
    t = world.find_unit(sc.target_id)
    if sc.phase == PHASE_START:
        sc.done = False
        sc.phase = PHASE_WINDUP
        sc.timer = st.windup & 0xFF
        u.step_end = world.tick + st.windup + st.recovery          # Task 2 item 4 fixes the exact write
    elif sc.phase == PHASE_WINDUP:
        sc.timer = (sc.timer - 1) & 0xFF
        if sc.timer == 0:
            if t is not None:
                release(world, u, sc, spell, t)
            sc.phase = PHASE_RECOVERY
            delay = hero_delay(st.weapon_weight, st.reaction) if st.human and st.has_weapon else 0
            sc.timer = recovery_ticks(st.recovery, delay, spell.complication_level, world.rng) & 0xFF
    elif sc.phase == PHASE_RECOVERY:
        sc.timer = (sc.timer - 1) & 0xFF
        if sc.timer == 0:
            u.spell_cast = None
            u.state = mv.IDLE_STATE


def release(world, u, sc, spell, t):
    """`FUN_00519db8` damage branch: build the missile carrier with the flight time (`FUN_00519998`)."""
    dx = centre_x(t) - centre_x(u)
    dy = centre_y(t) - centre_y(u)
    n = flight_ticks(spell, dx, dy)
    world.carriers.append(Carrier(world.next_carrier_id, u.id, t.id, sc.spell, sc.level, n, world.tick))
    world.next_carrier_id += 1


def carrier_system(world, commands):
    """`FUN_00518efd` for every active carrier in creation order: count down, deliver at 0 (slot in the tick per Task 2 item 5)."""
    for c in list(world.carriers):
        if c.ticks_left > 0:
            c.ticks_left -= 1
        if c.ticks_left <= 0:
            world.carriers.remove(c)
            deliver(world, c)


def deliver(world, c):
    """`FUN_00542e60` -> `FUN_0051e65b` -> `FUN_00516f6f`: roll the spell damage, protection, HP, XP credit, `Died`."""
    spell = world.spell_table.get(c.spell)
    t = world.find_unit(c.target)
    if t is None:
        return                                                      # the id was freed (Task 2 item 5 confirms)
    caster = world.find_unit(c.caster)
    rolled = roll_damage(spell, c.level, world.rng)
    prot = protection_of(world, t, spell.sphere)                    # Task 2: unit protection by element, data.bin / item bonuses
    dmg = 0 if protected_flag(t) else damage_after_protection(rolled, prot)
    before = t.hp
    t.hp = before - dmg
    if caster is not None:
        t.last_attacker = caster.id
        if world.ai_on:
            ai.on_hit(world, caster, t)
        xp.damage_credit(world, caster, t, dmg, before)
    if before > 0 or t.hp > -10:
        log(world, Damage(world.tick, c.caster, t.id, dmg, t.hp, rolled, True))
    if before > 0 and t.hp <= 0:
        log(world, Died(world.tick, t.id, c.caster))
```

Required corrections from reading the code, not guesses: `centre_x/centre_y` come from `engine/sim/pathfinding.py:349`; `combat_stats`, `log`, `hero_delay` from `engine/sim/combat.py`; `protection_of` and `protected_flag` are two small helpers you add to `combatstats.py`/`spells.py` reading the unit's `protectionFire`-style stat (data.bin template protection percent by sphere plus item bonuses, spells.md §5 and §9 "Resistance") and the `+0x4c & 8` flag, both CONFIRMED in spells.md; schools without a stored stat raise `NotImplementedError` (only sphere 1 is needed now). Whether the XP school passed to `award` is the spell's sphere (spells.md §6 cast XP) rather than 0: use §6, and add the cast XP at cast start if §6/Task 2 says so.

Wire the state: in `movement._tick_unit` after `if u.state == ATTACK_STATE:` add `elif u.spell_cast is not None: spells.cast_tick(world, u)`; give the unit `state = CAST_STATE` at `start_cast`; make `_tick_inner` skip the Brain modes while `spell_cast` is set (as `brain_swing` does for the swing), cancel semantics per Task 2 item 8. In `simulation.py` insert `spells.carrier_system` after `movement_system` in the default list.

- [ ] **Step 4: Run, expect pass**

Run: `python -m pytest tests/test_engine_spells_carrier.py tests/test_engine_spells_cast.py tests/test_engine_spells_math.py -q`
Expected: PASS.

- [ ] **Step 5: Full regression**

Run: `python -m pytest tests -q -x`
Expected: PASS, no golden changes (`tests/golden.json` untouched).

- [ ] **Step 6: Commit**

```bash
git add engine tests
git commit -m "Spells (I4a): cast phases, missile carriers, delivery damage and XP

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Staff (item) cast

**Files:**
- Modify: `engine/sim/spells.py`, possibly `engine/sim/combat.py` (per Task 2's staff decision)
- Test: `tests/test_engine_spells_cast.py`

**Interfaces:**
- Consumes: `combatstats.equipment_codes`, the item table (`castSpell=<name>:<n>` modifier text, `docs/data/items.md`), Task 2 staff decision.
- Produces: `spells.staff_spell(world, u) -> (spell_id, count) | None`; the staff cast wired as Task 2 decided.

- [ ] **Step 1: Write the failing tests**

```python
def test_staff_cast_is_free_and_level_is_the_item_count():
    w, sim = sim_with_spells()
    c, t = caster(w, 1, 5, 5, mana=0), fighter(w, 2, 12, 5, owner=2, hp=1000)
    c.known_spells = 0
    give_staff(w, c, "Wood Staff {castSpell=Fire_Arrow:1}")
    sim.step([CastSpell(1, (c.id,), 1, ("unit", t.id))])
    for _ in range(80):
        sim.step()
    assert c.mana == 0 and 5 <= 1000 - t.hp <= 10


def test_staff_spell_parser():
    from engine.sim.spells import parse_cast_spell
    assert parse_cast_spell("Wood Staff {castSpell=Fire_Arrow:1}") == ("Fire_Arrow", 1)
    assert parse_cast_spell("Plain Sword") is None
```

`give_staff` is a test helper you add: sets the unit's equipped item list the way `combatstats.equipment_codes` reads it (read that function first and build the item code through `w.item_table`; if the table is not loadable without the install, mark these two tests `needs_data` as `tests/helpers.py` does).

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_engine_spells_cast.py -k staff -q`
Expected: FAIL.

- [ ] **Step 3: Implement as Task 2 decided**

(a) If the staff cast is a `CastSpell` order: `cast_command` calls `staff_spell(world, u)` when the spell is not in the unit's book and passes `source="item", item_count=count`. (b) If it is a weapon branch of the attack (combat §5 item 4): `combat.resolve_attack` calls `spells.start_cast(..., source="item")` after a landed hit with `dmg > 0` and target HP > 0, exactly as the exe gates it, and the test above is rewritten to drive an `AttackUnit`. Either way, `parse_cast_spell(text)` is:

```python
import re

_CAST = re.compile(r"\{castSpell=([A-Za-z_]+):(\d+)\}")


def parse_cast_spell(item_text):
    m = _CAST.search(item_text)
    return (m.group(1), int(m.group(2))) if m else None
```

The spell id comes from `world.spell_table.lookup(name.replace("_", " "))`.

- [ ] **Step 4: Run, expect pass; regression**

Run: `python -m pytest tests/test_engine_spells_cast.py tests/test_engine_combat.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine tests
git commit -m "Spells (I4a): staff castSpell items cast for free at the item count

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: AI pin, docs, status

**Files:**
- Test: `tests/test_engine_spells_cast.py`
- Modify: `docs/engine/combat.md` (§13 filled), `docs/data/spells.md`, `docs/engine/ai.md` (§12 moved items), `docs/open-questions.md`, `docs/engine/README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the AI pin test**

```python
def test_mage_under_ai_still_fights_in_melee_not_casting():
    w, sim = sim_with_spells()
    sim = Simulation(w, ai=True)
    m = caster(w, 1, 5, 5, owner=2)
    h = fighter(w, 2, 6, 5, owner=1, hp=100)
    for _ in range(200):
        sim.step()
    assert not w.carriers and m.spell_cast is None             # phase K builds the AI cast; this pins the I4a boundary
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_engine_spells_cast.py -k mage_under_ai -q`
Expected: PASS (if it fails the cast hook leaked into the AI path: fix the hook, not the test).

- [ ] **Step 3: Docs**

`combat.md §13`: engine mapping (functions and files above), the VERIFY IN GAME list gathered from Tasks 1-2. `spells.md`: replace "(spell use is phase K)" statements that I4a changed. `ai.md §12`: add "special attacks `FUN_0056a981` and structures as targets: moved here from I4". `open-questions.md`: delete answered lines, add new ones. `docs/engine/README.md`: add the I4a row. `CLAUDE.md`: Status line "…I3, I4a done. Next: I4b (view and UI, spec 2026-10-19-spell-cast-design.md §3)" and a short Spells paragraph (files, command, tests) in the style of the neighbouring entries.

- [ ] **Step 4: Full run**

Run: `python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A docs CLAUDE.md tests
git commit -m "I4a done: Fire Arrow cast simulation, docs and status

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage (spec §2):** REA questions 2.1.1-2.1.6 -> Tasks 1-2; world state and systems 2.2 -> Tasks 4-5; staff vs learned (§1 row, §5) -> Tasks 2 and 6; tests list 2.3 (formulas, timeline, refusals, cancel, determinism, no regression) -> Tasks 3-5, 7; AI boundary -> Task 7; deliverables (docs, CLAUDE.md) -> Task 7. Carrier events `CastRefused` are covered in Task 4. I4b/I4c are out of scope by design.
- **Placeholders:** no TBD; the places where code depends on a research outcome name the finding that fixes it and the test changes in the same commit.
- **Type consistency:** `SpellCast`, `Carrier`, `start_cast`, `cast_tick`, `carrier_system`, `deliver`, `flight_ticks`, `cast_level`, `roll_damage`, `damage_after_protection`, `recovery_ticks`, `parse_cast_spell` are used with the same names and signatures across Tasks 3-7. `known_spells` is the single name for the spellbook bits.
- **Known risk:** Task 3's `cast_level` helper uses the Mind accessor `progression.attributes(u.stats)[2]` (as in `xp.award`); Task 5's protection helpers are new and small, their field names come from reading `unitstats`/`combatstats`.
