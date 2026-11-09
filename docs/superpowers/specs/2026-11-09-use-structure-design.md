# K6: using a structure (design)

Research: [engine/structures.md](../../engine/structures.md) (REA-confirmed unless marked). Goal: the hero uses switches / levers
(and altars, the same toggle), unblocking maps 96 and 103 (`use.scripted`, `use.switch`, `use.altar`). Wells, graves, signposts: K8 (documented only).

## Understanding
- Outcome: `UseStructure` walks the unit to the structure and toggles its HP 0 <-> 1 once; check 21 (already built) reads it; the draw shows the
  destroyed art for HP < 1. No passability change, no link between structures, no "used" event.
- Constraints: match the exe, including the **position lookup quirk** (the structure toggled is the first one within Chebyshev 2 of
  `(x-1, y-1)` of the unit's cell, not the clicked one); a debug option uses the clicked structure instead. Single player.
- Success: scenario tests (toggle, graphics flag, trigger fires, determinism replay); debug runs of maps 96 and 103 reach their win conditions
  with scripted uses; coverage report flips `use.scripted`, `use.switch`, `use.altar`.

## Design
- `commands.UseStructure(player_id, unit_id, object_id)`: the exe's client sends the unit ids selected; the engine keeps one unit (the last, as the
  server does) per command. Intake as for `PickUp` (group, cancel), then `structures.command_use`.
- `engine/sim/structures.py` (layer 4, mirrors the pickup order in `gear.py`): `set_use` (order `0xf`, `FUN_0056d22b`: destination = structure
  cell + (0,0)/(1,1)/(2,2), range 1/2/3 by footprint width 1-2 / 3-4 / 5+), `refresh_use` (group-pass executor of order `0xf`: Brain mode 15),
  `use_mode` (`FUN_0056ecbc`: in range and facing the destination -> state `0xf`; state already `0xf` -> `stop_unit`; else walk with `go_tick`, turn when
  in range), `use_tick` (state `0xf`, the effect once: lookup A, switch / altar toggle; lookup B for wells is the K8 hook, not built).
- Unit fields `mode_use`, `use_obj`, `use_dest`, `use_dist` (not in the world dump).
- Toggle: `hp = 0 if hp else 1` (types 28, 29, 76, 77), `FLAG_DESTROYED` follows `hp < 1`; instant 26 stays silent (as now). Passability untouched.
- UI: cursor `town` already exists over a Usable structure with one hero selected; `OrderInput.release` sends `UseStructure` for it.
- Triggers: check 21 / instant 26 exist; nothing new is needed on the script side (checked against the 96 / 103 trigger records).

## Assumptions (DECISIONs)
- Moving towards the destination uses the plain move driver towards the destination cell (the exe's stop-distance driver `FUN_00555411` is
  modelled by testing the range at every cell centre); an unreachable destination ends the order like any move.
- The structure list order = map file order (uid order), INFERRED in structures.md.
