"""Save-file diagnostics (L10f): `python -m engine save-info FILE` and `python -m engine save-diff A B`.

Pure (no pygame).  `info(data)` / `flatten(save)` read a `game%d.sav` through the typed parsers (`allods2.formats.saves`, `serverstream`) and report
what the parser typed and what it could only keep raw: the user runs it on a file the original wrote and on one of ours and reports the differences
(docs/engine/save.md "VERIFY IN GAME").  A file that does not parse is described as far as it goes (container fields, then the error)."""

import struct
import zlib

from allods2.formats import saves as S
from allods2.formats import serverblocks as B
from allods2.formats import serverstream as SS
from allods2.formats.mfc import ArchiveError

POINTER_FIELDS = {"ptr", "link"}                  # raw pointer keys: arbitrary per writer, never compared
POINTER_NAMES = ("ptr", "follow_ptr", "slot", "last_caster", "patrol_list_ptr", "struct_ptr", "spell_ptr")
RNG_MAGIC = 0x32474E52


def _hex(b, limit=24):
    b = bytes(b)
    return b[:limit].hex() + ("..(%d)" % len(b) if len(b) > limit else "")


def _layout_of(owner, name):
    if owner == "Unit" and name == "mover":
        return B.MOVER
    if owner == "Unit" and name == "brain":
        return B.BRAIN
    return None


def _is_pointer(layout, fname):
    return any(k in fname for k in POINTER_NAMES)


def unnamed_nonzero(raw, layout):
    """Offsets of non-zero bytes of `raw` that no named field of `layout` covers (None layout: every non-zero byte)."""
    covered = set()
    if layout is not None:
        for f in layout.fields.values():
            covered.update(range(f.off, f.off + f.size))
    return [i for i, v in enumerate(bytes(raw)) if v and i not in covered]


# --- flatten: a typed field view ------------------------------------------------------------------------------------------------------------

def flatten(obj, prefix="", out=None, seen=None, owner=""):
    """`{path: value}` of a typed object: dataclasses by field, lists by index (units / players by identity key), raw blocks of `Layout`ed units by field name
    plus the hex of their unnamed bytes, bytes as hex.  Pointer keys are skipped.  `seen` guards shared objects (a hero is in a group and in the container)."""
    import dataclasses
    out = {} if out is None else out
    seen = set() if seen is None else seen
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        if id(obj) in seen:
            out[prefix + "@"] = "(shared)"
            return out
        seen.add(id(obj))
        cname = type(obj).__name__
        for f in dataclasses.fields(obj):
            if f.name in POINTER_FIELDS:
                continue
            v = getattr(obj, f.name)
            layout = _layout_of(cname, f.name)
            if layout is not None and isinstance(v, (bytes, bytearray)) and len(v) == layout.size:
                for n, val in layout.decode(v).items():
                    if not _is_pointer(layout, n):
                        out["%s.%s.%s" % (prefix, f.name, n)] = val
                un = unnamed_nonzero(v, layout)
                if un:
                    out["%s.%s.unnamed" % (prefix, f.name)] = ",".join("%x=%02x" % (i, v[i]) for i in un)
                continue
            flatten(v, prefix + "." + f.name if prefix else f.name, out, seen, cname)
        return out
    if isinstance(obj, (bytes, bytearray, memoryview)):
        out[prefix] = _hex(obj, 1 << 20)         # the whole block: a diff must see every byte (display shortens)
    elif isinstance(obj, (list, tuple)):
        if obj and all(isinstance(x, int) for x in obj) and len(obj) > 16:
            out[prefix] = "[%d ints] %s" % (len(obj), _hex(struct.pack("<%dq" % len(obj), *obj), 32) if len(obj) < 4096 else "")
            out[prefix + ".#"] = len(obj)
            out[prefix] = tuple(obj)
            return out
        out[prefix + ".#"] = len(obj)
        for i, x in enumerate(obj):
            key = i
            if isinstance(x, SS.Unit):
                key = "u%d" % x.base.d08
            flatten(x, "%s[%s]" % (prefix, key), out, seen, owner)
    elif isinstance(obj, dict):
        for k, x in obj.items():
            flatten(x, "%s[%s]" % (prefix, k), out, seen, owner)
    else:
        out[prefix] = obj
    return out


def fields_of(data):
    """The flat typed view of a whole file (bytes): container, stream, client tail.  Returns `(fields, notes)`; `notes` = what could not be typed."""
    notes = []
    save = S.parse_save(data)
    f = {"container.version": save.version, "container.stream_len": len(save.stream)}
    try:
        stream = SS.ServerStream.parse(save.stream)
    except (ArchiveError, ValueError, struct.error) as e:
        notes.append("server stream does not parse: %s" % e)
        stream = None
    if stream is not None:
        for k, v in flatten(stream, "stream").items():
            f[k] = v
        if stream.loaded and stream.mission is None:
            notes.append("mission branch kept raw (%d bytes): not the layout of saves.md 6.12" % len(stream.mission_raw))
        if stream.debug[-8:-4] == struct.pack("<I", RNG_MAGIC):
            f["stream.debug.rng_state"] = struct.unpack_from("<I", stream.debug, 396)[0]
            f["stream.debug.head"] = _hex(stream.debug[:392], 32) if any(stream.debug[:392]) else "zeros"
        else:
            f["stream.debug"] = "zeros" if not any(stream.debug) else _hex(stream.debug, 32)
        f.pop("stream.debug", None) if "stream.debug.head" in f else None
    t = save.tail
    f["tail.description"] = t.description
    for k, v in flatten(t.state, "client").items():
        if k != "client.engine":
            f[k] = v
    f["client.engine_blob"] = len(t.state.engine)
    for k in flatten_reg(t.state.extra):
        notes.append("client .reg key not typed (kept, written back): %s" % k)
    f["tail.missions"] = tuple(t.missions)
    f["tail.mission_tail"] = tuple(t.mission_tail)
    sc = t.scenario
    for i, v in enumerate(sc.variables):
        if v:
            f["scenario.var[%d]" % i] = v
    for blk in range(16):
        raw = sc.shops[blk * 20:blk * 20 + 20]
        if any(raw):
            f["scenario.shop[%d/%d]" % (blk // 4, blk % 4)] = struct.unpack("<5I", raw)
    f["scenario.locations"] = tuple((l.index, l.type, bytes(l.name).hex()) for l in sc.locations)
    f["scenario.current"] = sc.current
    for i, h in enumerate(t.hotkeys):
        if h.a or h.b or h.data:
            f["hotkey[%d]" % i] = (h.a, h.b, _hex(h.data))
    return f, notes


def flatten_reg(tree, prefix=""):
    out = {}
    for k, v in tree.items():
        key = prefix + "/" + k if prefix else k
        if isinstance(v, dict):
            out.update(flatten_reg(v, key))
        else:
            out[key] = v
    return out


# --- save-info ------------------------------------------------------------------------------------------------------------------------------------

def info(data):
    """The text report of a file (bytes)."""
    lines = []
    add = lines.append
    add("file size            %d bytes" % len(data))
    if len(data) >= 16:
        magic, end, version, ln = struct.unpack_from("<IIII", data, 0)
        add("container            magic 0x%08x%s, server block ends at 0x%x, version 0x%08x, stream length %d" % (magic, " (ok)" if magic == S.SAVE_MAGIC else " (WRONG)", end, version, ln))
    try:
        save = S.parse_save(data)
    except S.MultiplayerSave as e:
        add("REFUSED (multiplayer): %s" % e)
        return "\n".join(lines)
    except ValueError as e:
        add("REFUSED: %s" % e)
        return "\n".join(lines)
    t = save.tail
    st = t.state
    add("description          %r" % t.description)
    add("kind                 %s (CurrentState/InBattle = %d)" % ("mission" if st.in_battle & 1 else "town", st.in_battle))
    origin = "engine extension present (written by this engine)" if st.engine else "no engine extension: original-style file (loads through the stream-only path)"
    add("writer               %s" % origin)
    add("character            %r, view (%d, %d), selection %s, formation %s" % (st.name, st.view_x, st.view_y, st.selection, st.options.get("Formation")))
    notes = []
    try:
        stream = SS.ServerStream.parse(save.stream)
    except (ArchiveError, ValueError, struct.error) as e:
        add("server stream        DOES NOT PARSE: %s" % e)
        stream = None
    if stream is not None:
        add("server stream        tick %d (block %d), map %r, scenario id %d, difficulty %d, loaded %d, d20 %d" % (stream.tick, stream.block, stream.map_name, stream.scenario, stream.difficulty, stream.loaded, stream.d20))
        if any(stream.words):
            add("option words         %s" % list(stream.words))
        rng = stream.debug[-8:-4] == struct.pack("<I", RNG_MAGIC)
        add("debug block          %s" % ("engine RNG marker, state %d" % struct.unpack_from("<I", stream.debug, 396)[0] if rng else
                                         "all zeros" if not any(stream.debug) else "non-zero (%d bytes): %s" % (sum(1 for b in stream.debug if b), _hex(stream.debug, 20))))
        for i, p in enumerate(stream.players):
            n = sum(len(g.units) for g in p.groups)
            add("player %d             %r %s gold %d kills %d/%d hero deaths %d, %d groups, %d units, main hero id %d" %
                (i, p.name, "human" if p.human else "AI", p.gold, p.kills_monsters, p.kills_players, p.hero_deaths, len(p.groups), n, p.main_hero))
        units = stream.units
        humans = [u for u in units if u.hum is not None]
        add("units                %d in groups (%d humanoid), container %d" % (len(units), len(humans), len(stream.container)))
        mine = [u for p in stream.players if p.human for g in p.groups for u in g.units if u.hum is not None]
        for u in mine[:16]:
            add("  hero               id %d template %d %r hp %d/%d mana %d/%d items %d spells %s" %
                (u.base.id, u.base.w0c, u.name, _s16(u.words[8]), _s16(u.words[9]), _s16(u.words[11]), _s16(u.words[12]),
                 sum(1 for s in u.hum.slots if s) + (len(u.pack.items) if u.pack else 0), bin(u.spells.mask) if u.spells else "-"))
        if len(mine) > 16:
            add("  ... %d more human-owned humanoids" % (len(mine) - 16))
        un = {}
        for u in units:
            for name, lay in (("mover", B.MOVER), ("brain", B.BRAIN)):
                for off in unnamed_nonzero(getattr(u, name), lay):
                    un.setdefault("%s+0x%x" % (name, off), 0)
                    un[("%s+0x%x" % (name, off))] += 1
            for name in ("blk_a6", "blk_be", "blk_114", "blk_d4"):
                nz = unnamed_nonzero(getattr(u, name), None)
                if nz:
                    un[name] = un.get(name, 0) + 1
        if un:
            add("untyped unit bytes   non-zero in %s (counts = units)" % ", ".join("%s: %d" % kv for kv in sorted(un.items())))
        if stream.mission is not None:
            m = stream.mission
            sc = m.script
            vals = sc.variables
            add("mission branch       %d buildings, %d spell effects, %d piles, %d virtual casters, map layer %d cells / %d records" %
                (len(m.buildings), len(m.effects), len(m.sacks), len(m.casters), len(m.map.cells), len(m.map.records)))
            add("script               %d non-zero values, %d fired flags, complete %d, fail %d, unnamed: b30 %s, b400 %s, a48/a49/a4c %d/%d/%d, be10 %d" %
                (sum(1 for v in vals if v), sum(1 for v in sc.fired if v), sc.complete, sc.fail, "set" if any(sc.b30) else "zero", "set" if any(sc.b400) else "zero",
                 sc.b_a48, sc.b_a49, sc.d_a4c, sc.d_be10))
        elif stream.loaded:
            notes.append("mission branch kept raw (%d bytes): not the layout of saves.md 6.12" % len(stream.mission_raw))
    sc = t.scenario
    nv = [(i, v) for i, v in enumerate(sc.variables) if v]
    add("scenario variables   %d non-zero: %s%s" % (len(nv), ", ".join("0x%x=%d" % kv for kv in nv[:16]), " ..." if len(nv) > 16 else ""))
    towns = sorted({b // 4 for b in range(16) if any(sc.shops[b * 20:b * 20 + 20])})
    add("shop table           towns with data: %s" % towns)
    add("available locations  %s, current index %d" % ([(l.type, l.index) for l in sc.locations], sc.current))
    add("mission list         %d entries, tail %s" % (len(t.missions), t.mission_tail))
    add("hotkeys              %d of 9 set" % sum(1 for h in t.hotkeys if h.a or h.b or h.data))
    f, more = fields_of(data)
    notes += [m for m in more if m not in notes]
    add("client .reg keys     %s" % ", ".join(sorted(k for k in flatten_reg(t.reg.to_dict()) if not k.startswith(("Fog/", "Prj", "Engine/")))[:40]))
    add("round trip           %s" % ("pack() == file bytes" if save.pack() == bytes(data) else "pack() DIFFERS from the file (not byte-exact)"))
    if notes:
        add("could not type:")
        lines += ["  - " + n for n in notes]
    else:
        add("could not type:      nothing beyond the raw blocks listed above")
    return "\n".join(lines)


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


# --- save-diff ------------------------------------------------------------------------------------------------------------------------------------

def diff(a, b, limit=400):
    """The text of a field-level diff of two files (bytes): only fields that differ, `A -> B`; pointer keys and the engine blob are left out."""
    lines = []
    try:
        fa, na = fields_of(a)
    except ValueError as e:
        return "A: %s" % e
    try:
        fb, nb = fields_of(b)
    except ValueError as e:
        return "B: %s" % e
    keys = sorted(set(fa) | set(fb), key=lambda k: (k.split(".")[0], k))
    n = 0
    for k in keys:
        if k in ("client.engine_blob",) or k.startswith("stream.debug"):
            if fa.get(k) != fb.get(k):
                lines.append("%-48s %s -> %s" % (k, _short(fa.get(k)), _short(fb.get(k))))
            continue
        va, vb = fa.get(k, "<absent>"), fb.get(k, "<absent>")
        if va != vb:
            n += 1
            if n <= limit:
                lines.append("%-48s %s -> %s" % (k, _short(va), _short(vb)))
    if n > limit:
        lines.append("... %d more differing fields" % (n - limit))
    for tag, notes in (("A", na), ("B", nb)):
        lines += ["%s: %s" % (tag, x) for x in notes]
    head = "%d differing typed fields" % n if n else "no typed field differs"
    return head + ("\n" + "\n".join(lines) if lines else "")


def _short(v, limit=70):
    s = repr(v)
    return s if len(s) <= limit else s[:limit] + "..."
