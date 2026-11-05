"""The order in which the exe walks the view's object map (`view+0x9d0`, `FUN_00420140` / `FUN_00420160`).

The map is an MFC `CMap` keyed by the 16-bit object id with the default 17 buckets: the hash is `id >> 4` modulo 17 (`0x422420`, `0x4223b0`), an
entry is linked at the head of its bucket (`FUN_004222c0`), the walk visits the buckets in ascending order and each chain head first.  So inside a
bucket the most recently registered object comes first.  CONFIRMED.  Everything that loops over "all view objects" (minimap dots `FUN_004ac414`,
the per-cell layer registration `FUN_0040403b`) sees this order, not the creation order.
"""

HASH_SIZE = 17


def bucket(oid):
    return (oid >> 4) % HASH_SIZE


def walk_order(entries):
    """`entries`: [(object id, payload)] in registration order -> the same pairs in the exe's walk order."""
    ranked = sorted(enumerate(entries), key=lambda t: (bucket(t[1][0]), -t[0]))
    return [e for _, e in ranked]
