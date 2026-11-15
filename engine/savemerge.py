"""Pass-through of what the engine does not model (L10f; docs/engine/save.md "Original-file tolerance").

A save the original wrote is loaded into engine state, which keeps only what the engine models; saving it again would write our defaults over the bytes we do not understand
(option words, the unnamed bytes of a unit's blocks, script blocks ...).  `merge(new, base, orig)` repairs that: `orig` is the stream as parsed from the file, `base` the stream the
engine built from its freshly loaded state (same builder as `new`), `new` the stream built now.  A field (a byte of a raw block, a scalar) the engine has not changed since the load
(`new == base`) takes the original's value; a changed one keeps the new value.  So **load -> save with no play in between is byte for byte the original's stream**, and after play only what
play changed differs.  Raw pointer keys (`ptr`, `link`, the pointer fields of the mover / brain blocks) are never taken from the original: the keys are only meaningful inside one writer's file.
Lists of units are matched by identity (`base.id`, `base.d08`), other lists by position when the three lengths agree, else the new list stays."""

import dataclasses

from allods2.formats import serverblocks as B
from allods2.formats import serverstream as SS

SKIP_FIELDS = {"ptr", "link", "d40", "d5c", "d64", "d44", "pad", "tick", "block"}      # pointer keys and values the loader reads back as engine state


def _pointer_bytes(owner, name, size):
    """Byte offsets of a raw block that hold pointer keys."""
    lay = {"mover": B.MOVER, "brain": B.BRAIN}.get(name) if owner == "Unit" else None
    out = set()
    if lay is not None:
        for fname, f in lay.fields.items():
            if any(k in fname for k in ("ptr", "last_caster", "slot")):
                out.update(range(f.off, f.off + f.size))
    return out


def _bytes(new, base, orig, keep):
    if not (len(new) == len(base) == len(orig)):
        return new
    return bytes(n if (n != b or i in keep) else o for i, (n, b, o) in enumerate(zip(new, base, orig)))


def _key(u):
    return (u.base.id, u.base.d08)


def _merge_list(new, base, orig, seen):
    if new and all(isinstance(x, SS.Unit) for x in new) and all(isinstance(x, SS.Unit) for x in base) and all(isinstance(x, SS.Unit) for x in orig):
        bm, om = {_key(u): u for u in base}, {_key(u): u for u in orig}
        for u in new:
            k = _key(u)
            if k in bm and k in om:
                merge(u, bm[k], om[k], seen)
        return new
    if len(new) == len(base) == len(orig):
        out = []
        for n, b, o in zip(new, base, orig):
            if dataclasses.is_dataclass(n) and not isinstance(n, type):
                out.append(merge(n, b, o, seen))                    # in place: shared objects stay shared
            else:
                out.append(o if n == b else n)                      # an int, a None slot ...
        return out
    return new


def merge(new, base, orig, seen=None):
    """Fold `orig`'s unmodelled values into `new` in place (see the module docstring); returns `new`."""
    seen = set() if seen is None else seen
    if id(new) in seen or not (type(new) is type(base) is type(orig)) or not dataclasses.is_dataclass(new):
        return new
    seen.add(id(new))
    cname = type(new).__name__
    for f in dataclasses.fields(new):
        if f.name in SKIP_FIELDS:
            continue
        nv, bv, ov = getattr(new, f.name), getattr(base, f.name), getattr(orig, f.name)
        if isinstance(nv, (bytes, bytearray)) and isinstance(bv, (bytes, bytearray)) and isinstance(ov, (bytes, bytearray)):
            setattr(new, f.name, _bytes(bytes(nv), bytes(bv), bytes(ov), _pointer_bytes(cname, f.name, len(nv))))
        elif dataclasses.is_dataclass(nv) and not isinstance(nv, type):
            merge(nv, bv, ov, seen)
        elif isinstance(nv, list) and isinstance(bv, list) and isinstance(ov, list):
            setattr(new, f.name, _merge_list(nv, bv, ov, seen))
        elif isinstance(nv, tuple) and type(bv) is type(ov) is tuple and len(nv) == len(bv) == len(ov):
            setattr(new, f.name, tuple(o if n == b else n for n, b, o in zip(nv, bv, ov)))
        elif isinstance(nv, (int, str)) and type(nv) is type(bv) is type(ov):
            if nv == bv:
                setattr(new, f.name, ov)
    return new


def merge_stream(new, origin):
    """`new` = the stream just built; `origin` = `(base, orig)` kept at load time, or None.  A failing merge (a layout the walker does not understand) leaves `new` as built."""
    if origin is None:
        return new
    import copy
    try:
        return merge(copy.deepcopy(new), origin[0], origin[1])
    except Exception:           # noqa: BLE001  never lose a save to the pass-through
        return new
