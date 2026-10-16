"""One `.res` archive: memory-mapped, directory parsed once, files returned
as zero-copy memoryview slices of the map.

Format and lookup rules: docs/formats/res.md.
"""

import mmap
import os
import struct
from collections import Counter

SIGNATURE = 0x31415926
HEADER = 0x18
ENTRY = 32
NAME_MAX = 15               # names compare on at most 15 characters
T_SECTION = 1               # type & 0xF: 0 file, 1 section
SORTED = 0x10               # section children sorted: bsearch + strcmp
DELETED = 0x40000000        # lookups skip it (meaning INFERRED)
DIR_INLINE = 0x80000000     # root-type flag: directory not at the header's offset

_ENTRY = struct.Struct("<4I16s")


class Entry:
    """A directory entry.  File: a = absolute offset, b = byte length.
    Section: a = first child index, b = child count."""
    __slots__ = ("name", "type", "a", "b")

    def __init__(self, name, type_, a, b):
        self.name, self.type, self.a, self.b = name, type_, a, b

    @property
    def is_dir(self):
        return self.type & 0xF == T_SECTION

    def __repr__(self):
        return "Entry(%r, type=0x%x, %d, %d)" % (self.name, self.type, self.a, self.b)


class ResArchive:
    """Read-only .res archive.  `name` is the stem the game mounts it under
    (graphics.res -> "graphics").  read() returns memoryviews into the map;
    they stay valid while the archive is open."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self._f = open(path, "rb")
        try:
            self.size = os.fstat(self._f.fileno()).st_size
            if self.size < HEADER:
                raise ValueError("%s: file too short" % path)
            self._map = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
            self._view = memoryview(self._map)
            sig, first, count, rtype, self.dir_offset, n = struct.unpack_from("<6I", self._map, 0)
            if sig != SIGNATURE:
                raise ValueError("%s: bad signature 0x%08x" % (path, sig))
            if rtype & DIR_INLINE:
                raise ValueError("%s: inline directory (root flag 0x80000000) not supported" % path)
            if self.dir_offset + ENTRY * n > self.size:
                raise ValueError("%s: directory past end of file" % path)
        except BaseException:
            self.close()
            raise
        self.root = Entry("", rtype, first, count)
        self.entries = [Entry(nm.split(b"\0", 1)[0].decode("cp1251"), t, a, b)
                        for _, a, b, t, nm in _ENTRY.iter_unpack(
                            self._map[self.dir_offset:self.dir_offset + ENTRY * n])]
        self._index = {}            # id(section) -> {key: entry}, built on first use

    # -- lifetime ---------------------------------------------------------
    def close(self):
        view, self._view = getattr(self, "_view", None), None
        if view is not None:
            view.release()
        m = getattr(self, "_map", None)
        if m is not None:
            try:
                m.close()
            except BufferError:     # caller still holds slices; the GC closes it
                pass
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- directory --------------------------------------------------------
    def children(self, section=None):
        s = section or self.root
        return self.entries[s.a:s.a + s.b]

    def _child(self, section, key):
        """FUN_004e918e: sorted section -> bsearch/strcmp on the key cut to
        15 chars; otherwise _strnicmp(key, name, 15), first match wins.
        Each section's table is built once, on first use."""
        table = self._index.get(id(section))
        if table is None:
            table = {}
            sort = section.type & SORTED
            for c in self.children(section):
                k = c.name[:NAME_MAX] if sort else c.name[:NAME_MAX].lower()
                table.setdefault(k, c)
            self._index[id(section)] = table
        key = key[:NAME_MAX]
        return table.get(key if section.type & SORTED else key.lower())

    def lookup(self, path, dirs=False):
        """Entry for an archive-relative path ('\\' or '/'); None when
        absent.  FUN_004e9046: every step must be a live section; the result
        must not be deleted or a sorted section (dirs=True accepts any
        section, for directory listing)."""
        node = self.root
        for part in _parts(path):
            if node.type & (DELETED | 0xF) != T_SECTION:
                return None
            node = self._child(node, part)
            if node is None:
                return None
        if node.type & DELETED:
            return None
        if not dirs and (node is self.root or node.type & SORTED):
            return None
        return node

    def walk(self, section=None, prefix=""):
        """Yield (path, entry) for every file, depth first, '/'-separated,
        in directory order."""
        for c in self.children(section):
            if c.is_dir:
                yield from self.walk(c, prefix + c.name + "/")
            else:
                yield prefix + c.name, c

    # -- data -------------------------------------------------------------
    def read_entry(self, e):
        """memoryview of a file entry's bytes (no copy)."""
        if e.a + e.b > self.size:
            raise ValueError("%s: %s past end of file" % (self.path, e.name))
        return self._view[e.a:e.a + e.b]

    def read(self, path):
        e = self.lookup(path)
        if e is None or e.is_dir:
            raise FileNotFoundError("%s:%s" % (self.name, path))
        return self.read_entry(e)

    def __contains__(self, path):
        e = self.lookup(path)
        return e is not None and not e.is_dir

    # -- validation -------------------------------------------------------
    def check(self):
        """(problems, unreachable paths, Counter of entry types, file count,
        file bytes): the directory ends the file, every entry is reached
        exactly once from the root, file ranges tile 0x18..directory, and
        every walked path resolves back to its own entry."""
        bad = []
        if self.dir_offset + ENTRY * len(self.entries) != self.size:
            bad.append("directory does not end the file")
        seen, spans, stack = Counter(), [], [self.root]
        while stack:
            sec = stack.pop()
            if sec.a + sec.b > len(self.entries):
                bad.append("section %r children past directory" % sec.name)
                continue
            for i in range(sec.a, sec.a + sec.b):
                seen[i] += 1
                e = self.entries[i]
                if e.is_dir:
                    stack.append(e)
                else:
                    spans.append((e.a, e.b, e.name))
        if len(seen) != len(self.entries) or any(v != 1 for v in seen.values()):
            bad.append("%d entries, %d reached, %d reached twice" % (
                len(self.entries), len(seen), sum(v > 1 for v in seen.values())))
        pos = HEADER
        for a, b, name in sorted(spans):
            if a != pos:
                bad.append("%s at 0x%x: %s 0x%x" % (name, a, "gap from" if a > pos else "overlaps", pos))
            pos = max(pos, a + b)
        if pos != self.dir_offset:
            bad.append("file data ends at 0x%x, directory at 0x%x" % (pos, self.dir_offset))
        odd = [p for p, e in self.walk() if self.lookup(p) is not e]
        types = Counter(e.type for e in [self.root] + self.entries)
        return bad, odd, types, len(spans), sum(b for _, b, _ in spans)

    def __repr__(self):
        return "ResArchive(%r, %d entries)" % (self.path, len(self.entries))


def _parts(path):
    return [p for p in path.replace("\\", "/").split("/") if p]
