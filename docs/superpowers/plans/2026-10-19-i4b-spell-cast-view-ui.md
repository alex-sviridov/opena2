# I4b: Fire Arrow cast view and UI Implementation Plan

> **For agentic workers:** executed inline by the same session that ran I4a (ledger = git history + this file's checkboxes). Steps use checkbox syntax.

**Goal:** The cast of I4a is visible and playable: the missile with its smoke trail in the draw list (alpha `.16a`, depth-sorted with units), the cast animation, and a `C` hotkey that arms the pending cast mode, shows the cast cursor and sends `CastSpell` on a click at a unit.

**Architecture:** sim facts come from `World.carriers` (I4a) plus two new carrier fields (`start`, `flight`) that make the missile position a pure function of the tick; the draw list turns a carrier into `DrawItem`s of a new `("projectile", id, source)` sprite kind; `SpriteCache` learns the `.16a` alpha blend (`src*(a+1)/16 + dst*(15-a)/16`, animation.md 4.4); `OrderInput` gets the cast key and the CAST release branch; the window passes a `spell_fn`.

**Tech Stack:** Python 3.13, numpy, pygame (headless dummy driver in tests), pytest.

**Spec:** [`docs/superpowers/specs/2026-10-19-spell-cast-design.md`](../specs/2026-10-19-spell-cast-design.md) section 3. Facts: [animation §4.4](../../formats/animation.md), [click-to-move-research §1.2-1.4](../../engine/click-to-move-research.md), [spells §9c](../../data/spells.md), [combat §14](../../engine/combat.md).

## Global Constraints

- 1:1 with the exe; INFERRED facts are tagged and listed under VERIFY IN GAME in combat §14. View-only code never mutates the world (the 30/60 fps hash test of I4c depends on it).
- The animation clock is the simulation's tick (`tick - action_start_tick`), never the render clock.
- Existing goldens must not change; new dump keys only when non-empty.
- Tests: synthetic where possible; pieces that need the install carry `needs_data` (tests/helpers.py).

## Review Focus

- A carrier with `flight == 0` or a target that vanished mid-flight must not crash the draw list (no division by zero, no missing unit).
- A projectile partly or fully outside the camera window is culled, not drawn off-surface.
- `C` with an empty or foreign selection, with no castable spell, or with the mode already armed does nothing harmful; a right click cancels the mode and keeps the selection.
- A click on ground in cast mode issues no order (cell casts are phase K) and still resets the pending mode.

---

### Task 1: Carrier geometry and the cast animation (sim side)

**Files:** `engine/world.py` (`Carrier.start`, `Carrier.flight`), `engine/sim/spells.py` (`cast_release`, `cast_start`), `tests/test_engine_spells_cast.py`

- [ ] Carrier gets `start: tuple = (0, 0)` (caster position in 1/256 cell at release) and `flight: int = 0` (ticks the missile was created with); `dump()` appends them to the carrier row. Point carriers copy both.
- [ ] `cast_start` sets `u.action, u.action_start_tick = mv.ATTACK, world.tick` (the client action 8 shares the attack animation block, animation.md 2.4; message 0x86 at the same tick).
- [ ] Tests: `test_carrier_records_start_and_flight`, `test_cast_start_plays_the_attack_animation`.

### Task 2: `.16a` alpha blend and the projectile asset kind

**Files:** `allods2/assets.py` (`AssetCache.projectile_set`), `engine/backend_pygame/sprites.py` (kind `"projectile"`, blend `"alpha"`, `blend_alpha`), `engine/backend_pygame/render.py`, `tests/test_engine_alpha.py`

- [ ] `AssetCache.projectile_set(pid)` -> `ProjectileSet` or None, cached.
- [ ] `SpriteCache.file/palette` resolve `("projectile", pid, source)`: `.16a` and `.256` via `aset.sprites(source)`, palette = the file's own (A16 / Palette != 0) else `aset.shade_palette` (projectiles.pal); the `trail` source is the smoke `.16a`.
- [ ] `SpriteCache._build` for blend `"alpha"`: `(mask_t, src_t, alpha_t)` from `decode.alpha`; `blend_alpha(surface, x, y, entry)` computes `(src * (a + 1) + dst * (15 - a)) >> 4` per channel (`a` 0..15).
- [ ] Tests: the pure mix formula (a = 0, 7, 15), `blend_alpha` on a tiny surface with a synthetic entry, and (needs_data) the firebolt frame builds an alpha entry with a non-empty mask.

### Task 3: Missile and trail in the draw list

**Files:** `engine/view/drawlist.py` (`PASS_PROJECTILE`, `_carriers`, `missile_position`), `tests/test_engine_spell_draw.py`

- [ ] `missile_position(c, caster_pos, target_pos, tick)`: age `a = tick - c.born`, fraction `min(a, flight) / max(flight, 1)`, linear from `c.start` to the target's CURRENT position (the projectile moves toward the target each tick, animation 4.4 default rule), z = `MISSILE_Z`.
- [ ] `_carriers`: for each missile carrier: facing 16 from the direction caster -> target, `ProjectileSet.frame_at("flight", facing, a, age0=-1)`, a `DrawItem(kind="sprite", sprite=("projectile", pid, "main"), blend="alpha")` centred on the position with the record `Width x Height` box, plus the trail: the 6 previous positions (`a-1 ... a-6`, oldest first) as `("projectile", pid, "trail")` items (ids 10 and 12, `TRAIL_SOURCES`).
- [ ] Depth `(PASS_PROJECTILE = 6, row, -col, SLOT_PROJECTILE, uid, part, sub)`, after units of the same cell. Culled when outside the window; a vanished target or caster leaves the missile on its last straight line (it is derived from the carrier only).
- [ ] Tests with fake assets (pattern of `test_engine_unit_draw.py`): item count (1 missile + trail), alpha blend, position at ages 0 / mid / end, depth after a unit in the same cell, culling, flight 0, vanished target.

### Task 4: The cast key, spell slot and click dispatch

**Files:** `engine/ui/orders.py` (`OrderInput.spell_fn`, `key("c")`, `release` CAST branch), `engine/backend_pygame/window.py` (`ORDER_KEYS`, `spell_fn`), `tests/test_engine_spell_ui.py`

- [ ] `OrderInput(..., spell_fn=None)`: `spell_fn()` -> the spell number the selection can cast now, or 0. `key("c")`: own non-empty selection and `spell_fn()` -> `pending = CAST`, `self.spell = n`, no command; otherwise nothing (the mask rule: the cast button is enabled only when the selection has a castable spell; INFERRED that "castable" includes enough mana).
- [ ] `release(S.CAST, cell, hover_unit)`: a unit id -> `CastSpell(player, sel, self.spell, hover_unit)`; ground -> no command (cell casts are phase K); the pending mode resets either way (R 1.2).
- [ ] `window.py`: `pygame.K_c` -> "c"; `spell_fn` = `engine.ui.orders.castable_spell(world, player)`: the lowest spell number known by a selected unit that has the mana for it (`spells.known_mask`, `spell_table`).
- [ ] Tests: key arms the mode; empty / foreign / no-spell selections do nothing; release at a unit sends `CastSpell` with the armed spell; release at ground sends nothing and resets; right release cancels and keeps the selection (existing behaviour, pinned).

### Task 5: Screenshot, docs, status

**Files:** `tests/test_engine_screenshot.py` (needs_data), `docs/engine/combat.md` §14, `docs/engine/ui-layout.md`, `CLAUDE.md`

- [ ] A screenshot test with a missile in flight on a real map renders without error and differs from the same frame without the carrier.
- [ ] Docs: combat §14 view/UI mapping and VERIFY IN GAME (missile spawn height, trail draw order, `C` instead of the spellbook), ui-layout (no command bar yet: the panel button belongs to the command bar of J1), CLAUDE.md "I4b done".
- [ ] Full suite, commit.
