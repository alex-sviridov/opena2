# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Units and registries

- `.reg` writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`); whether
  `.res` uses the same container. [reg](formats/reg.md#open-questions)
- `.reg` header `+0x14` and entry `+0`. [reg](formats/reg.md#open-questions)

## data.bin

- Human and structure parameter maps (`FUN_004ade80`, `FUN_004adea0`
  users), item-class i16s, factor doubles, `castSpell`/`damage*` modifier
  values (`FUN_00528e94`, `FUN_00528d43`). [databin](formats/databin.md#open-questions)

## Not started (from the reversing plan)

- `.alm` sections 0 and 4–12 (general info, structures, units, triggers,
  …); the server reader `FUN_0053ea3a` parses all of them (switch on the
  section id). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
