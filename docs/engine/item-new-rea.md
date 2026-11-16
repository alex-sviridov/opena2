# Item "new" mark vs. the twinkle (REA, GOG allods2.exe)

Question: which backpack items show the magenta sparkle in the original? Tags: CONFIRMED = read in the exe, INFERRED = deduced.

## 1. Client flag byte `item+8` (client item ctor `FUN_004387b2`, called from `0x40d9b2` and `0x4699d2`)

* CONFIRMED: `+8` starts as the wire flag byte `f`, then is masked by the wire form:
  * `f & 0x80` (plain stack): `+8 &= 0x40` (only the "new" bit survives; count = `f & 0x3f`).
  * `f & 0x20` (modifier item): `+8 &= 0x60` (bits `0x20` and `0x40` survive), count := 1, `+0x1c` price read, effect list decoded from the payload.
  * neither (u16 count stack): `+8` unchanged (`0x40` or 0).
  * Then `+8 |= descriptor byte +4` (the `itemname.pkt` / `FUN_005244d6` descriptor of the code: `suitable_for << 1`, 1 / 5 / 7 / 0x17 for specials, **plus `0x20` and `0x10` when the descriptor was built from an item with modifiers**, `FUN_0052457c`; `0x20` is cleared again for item types 3 / 4, `FUN_005244d6`).
* So client `+8 & 0x20` = **"the item has modifiers (is magic)"** (CONFIRMED: `FUN_0052457c` and `FUN_005241bf` set `0x20` exactly when the item carries an effect list; a stack or plain item never has it). It is NOT the "new" mark.
* Client `+8 & 0x40` = the server's "new" mark (wire bit `0x40`). CONFIRMED that it is carried through every ctor branch; the twinkle code does not test it. CONFIRMED consumer: the item-list handler (case `0x76` of the pump `FUN_0040d9b2`, `0x411758`): `if (item+8 & 0x40) { item+8 &= 0xbf; print "Picked up ..." }` (main `0x55`, `(0x56 N 0x57)` for a stack above 1, log colour, 3000 ms, `0x411848`); nothing else reads it, the twinkle does not.

## 2. Server item `+8` (the "new" mark)

* Writer, CONFIRMED: `FUN_005108fa` (the pickup of a sack, callers `0x4f3d68`, `0x50f12c`): every item of the carried list `param_1[0x10]` gets `+8 = 1`, then `FUN_00529e5b` files them in the pack (`FUN_00529ac2`). No other writer was searched exhaustively (the engine's `gear.pick_up` mirrors this one).
* Clearer, CONFIRMED: `FUN_005241bf` (wire serialiser of one item, callers `0x40d9b2`, `0x4699d2`, `0x4e9e97`, `0x502d67`, `0x503236`, `0x50338e`, `0x503493`): `if (item+8 != 0) { flags |= 0x40; item+8 = 0; }`. The mark is therefore sent **once** (the first time the item is serialised to the client after pickup) and cleared on the server immediately. It is also what the save writer emits (`0x40`, saves.md 3.x), so a save made before the first serialisation keeps it.
* Other writers, CONFIRMED by a scan of every `mov [reg+8], imm` / `mov [reg+8], reg` in the item and server code (`0x4f0000`-`0x570000`): the only immediate `+8 := 1` in item code is `FUN_005108fa` (`0x510957`); the ctor `0x5241b2` and the serialiser clear it; the stack merge `FUN_00529ae2` ORs it (`0x529bac`: `target.+8 |= source.+8`, so a picked-up stack merging into an old one marks the whole entry new, which the engine's `pack_insert` does). Trades (shop buy / sell), hero-death drops, script items (instants 11 / 12 / 20 / 28 / 38) and equip moves write none: their items arrive unmarked (the other `+8 := 1` stores at `0x515da4`, `0x51bd06`, `0x5219d5`, `0x52fef4` belong to other classes: creature, carrier, quest records).
* Hover, pack open, timer, equip: no clear exists on the server beyond the serialisation above (CONFIRMED for `+8`; nothing else found writing it). On the client nothing clears `+8` (the twinkle test only reads it).

## 3. What sparkles in the original

* CONFIRMED (`FUN_004a26c1`): per server step, for every cell whose item has `(+8 & 0x20) != 0` and is not the carried object with count 1, the cell counter increments; `FUN_004a285a` draws the sparkle from that counter. There is no clear, no timer: **a magic item (one with modifiers, i.e. wire `0x20` / descriptor `0x20`) sparkles for as long as it is shown in the pack strip**; non-magic items (stacks, plain class items, potions without effect list, scrolls) never sparkle. Whether the item was just picked up is irrelevant (the new bit `0x40` is not read by the twinkle).
* INFERRED reading: the sparkle is the "this is a magic item" decoration; the doc name "new twinkle" in ui-layout 11.13 is a mislabel.

## 4. What our engine does wrong / should do

* Wrong: `engine/ui/pack.py` `CellView.new` is documented as "item flag `0x20`" but filled from `Item.new` (`bool(it.new)`, pack.py ~304) which `gear.pick_up` sets True on every pickup and nothing clears: every picked-up item sparkles forever (user's observation).
* Should: draw the twinkle iff `bool(item.mods)` (any effect record; saves.py encodes this as wire `0x20`; kind 1 skipped records do not count: use the same test as `encode_item`, i.e. at least one non-`K_SKIPPED` mod) and the item is not the carried object with count 1. Do not read `Item.new` for it.
* `Item.new` stays the server `+8` mark: keep setting it on pickup (it feeds `PickupWatch`, which needs it as a one-shot) but it should be cleared when first serialised: in the engine, when `PickupWatch.poll` has reported it (or when the save is written, mimicking `FUN_005241bf` clearing on serialisation). Fixed: `PickupWatch.poll` clears the flag of the player's pack items right after it made the lines (`_clear_marks`), like the exe's serialise-and-clear plus the client's own clear; a second pickup of the same key reports again. A save made before the first poll keeps the bit (as in the exe).
* Twinkle counter: per cell and only for magic items in the exe; the engine uses the world tick (documented INFERRED equal phase), fine.

## Open questions

* None.
