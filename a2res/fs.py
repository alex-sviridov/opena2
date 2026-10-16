"""Read-only game file systems: one interface over the GOG `.res` archives,
loose folders, and chains of both.

Paths are game paths relative to the data root, first component = archive
(`graphics/units/units.reg`); '\\' and '/' both separate, and components
match case-insensitively as on Windows.  `read` returns a memoryview (zero
copy for archives); `read_bytes` copies; `open` gives a seekable binary
file over the same memory (for PIL and friends).
"""

import fnmatch
import io
import os

from .archive import ResArchive, _parts

# Mount order of FUN_00481186 (GOG allods2.exe 1.01).
ARCHIVES = ("graphics", "main", "patch", "world", "music", "video",
            "sfx", "movies", "scenario", "speech")


def norm(path):
    """'a\\B//c' -> 'a/B/c' (case kept)."""
    return "/".join(_parts(path))


def game_lower(path):
    """FUN_004e26c9: the resource manager lower-cases every path before the
    lookup, A-Z only (CRT tolower, C locale)."""
    return path.translate(_LOWER)


_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def join(*parts):
    return norm("/".join(p for p in parts if p))


def basename(path):
    return norm(path).rpartition("/")[2]


def dirname(path):
    return norm(path).rpartition("/")[0]


def splitext(path):
    return os.path.splitext(norm(path))


class MemoryFile(io.RawIOBase):
    """Seekable read-only binary file over a memoryview (no copy)."""

    def __init__(self, view, name=""):
        self._v = memoryview(view)
        self._pos = 0
        self.name = name

    def readable(self):
        return True

    def seekable(self):
        return True

    def readinto(self, b):
        n = min(len(b), len(self._v) - self._pos)
        if n <= 0:
            return 0
        b[:n] = self._v[self._pos:self._pos + n]
        self._pos += n
        return n

    def read(self, size=-1):
        end = len(self._v) if size is None or size < 0 else min(len(self._v), self._pos + size)
        out = self._v[self._pos:end].tobytes()
        self._pos = max(self._pos, end)
        return out

    def readall(self):
        return self.read()

    def seek(self, offset, whence=0):
        base = (0, self._pos, len(self._v))[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def tell(self):
        return self._pos


class FS:
    """Interface.  Subclasses implement _file(path) -> memoryview | None,
    _dir(path) -> list of child names | None, and _isdir(path)."""

    name = ""

    def read(self, path):
        """memoryview of a file's bytes; FileNotFoundError when absent."""
        v = self._file(norm(path))
        if v is None:
            raise FileNotFoundError("%s: %s" % (self.name or type(self).__name__, path))
        return v

    def read_bytes(self, path):
        return self.read(path).tobytes()

    def open(self, path):
        return io.BufferedReader(MemoryFile(self.read(path), norm(path)))

    def isfile(self, path):
        return self._file(norm(path)) is not None

    exists_file = isfile

    def isdir(self, path):
        return self._isdir(norm(path))

    def exists(self, path):
        return self.isfile(path) or self.isdir(path)

    def listdir(self, path=""):
        names = self._dir(norm(path))
        if names is None:
            raise FileNotFoundError("%s: no folder %s" % (self.name or type(self).__name__, path))
        return names

    def walk(self, path=""):
        """os.walk-like (dirpath, dirnames, filenames), names as stored,
        directory order; dirpath is a game path."""
        path = norm(path)
        dirs, files = [], []
        for n in self.listdir(path):
            (dirs if self._isdir(join(path, n)) else files).append(n)
        yield path, dirs, files
        for d in dirs:
            yield from self.walk(join(path, d))

    def files(self, path=""):
        """Every file path under `path`, sorted case-insensitively."""
        out = [join(d, f) for d, _, fs in self.walk(path) for f in fs]
        return sorted(out, key=str.lower)

    def glob(self, pattern, path=""):
        """Files under `path` whose path (lower case) matches `pattern`
        (fnmatch, lower case, '/'-separated)."""
        pat = pattern.lower()
        return [p for p in self.files(path) if fnmatch.fnmatchcase(p.lower(), pat)]


class ResFS(FS):
    """The game's mounted archives: <install>/<stem>.res for each ARCHIVES
    member present.  Paths are lower-cased (A-Z) first, as the game's
    manager does (`game_lower`); the first component then selects the
    archive and the rest follows ResArchive.lookup (res.md § Lookup)."""

    def __init__(self, install, archives=ARCHIVES):
        self.name = self.install = install
        names = {n.lower(): n for n in os.listdir(install)}
        self.archives = {}
        for stem in archives:
            if stem + ".res" in names:
                self.archives[stem] = ResArchive(os.path.join(install, names[stem + ".res"]))
        if not self.archives:
            raise FileNotFoundError("no .res archives in %s" % install)

    def close(self):
        for a in self.archives.values():
            a.close()

    def _split(self, path):
        head, _, rest = game_lower(path).partition("/")
        return self.archives.get(head), rest

    def _file(self, path):
        arc, rest = self._split(path)
        if arc is None or not rest:
            return None
        e = arc.lookup(rest)
        return None if e is None or e.is_dir else arc.read_entry(e)

    def _isdir(self, path):
        if not path:
            return True
        arc, rest = self._split(path)
        if arc is None:
            return False
        e = arc.lookup(rest, dirs=True)
        return e is not None and e.is_dir

    def _dir(self, path):
        if not path:
            return list(self.archives)
        arc, rest = self._split(path)
        if arc is None:
            return None
        e = arc.lookup(rest, dirs=True)
        if e is None or not e.is_dir:
            return None
        return [c.name for c in arc.children(e)]

    def entry(self, path):
        """(archive, Entry) of a file, for offset/size queries."""
        arc, rest = self._split(norm(path))
        e = arc.lookup(rest) if arc else None
        return (arc, e) if e is not None and not e.is_dir else (None, None)

    def __repr__(self):
        return "ResFS(%r: %s)" % (self.install, ", ".join(self.archives))


class DirFS(FS):
    """A loose folder; components match case-insensitively.  Folder
    listings are cached (the tree is assumed not to change)."""

    def __init__(self, root):
        self.name = self.root = root
        self._listing = {}

    def _names(self, real):
        d = self._listing.get(real)
        if d is None:
            try:
                d = {n.lower(): n for n in sorted(os.listdir(real))}
            except OSError:
                d = {}
            self._listing[real] = d
        return d

    def real(self, path):
        """OS path of a game path, or None."""
        cur = self.root
        for part in _parts(path):
            n = self._names(cur).get(part.lower())
            if n is None:
                return None
            cur = os.path.join(cur, n)
        return cur

    def _file(self, path):
        p = self.real(path)
        if p is None or not os.path.isfile(p):
            return None
        with open(p, "rb") as f:
            return memoryview(f.read())

    def _isdir(self, path):
        p = self.real(path)
        return p is not None and os.path.isdir(p)

    def _dir(self, path):
        p = self.real(path)
        if p is None or not os.path.isdir(p):
            return None
        return list(self._names(p).values())

    def __repr__(self):
        return "DirFS(%r)" % self.root


class ChainFS(FS):
    """Layers searched in order: the first that has a file wins; folder
    listings are merged (case-insensitive, first spelling kept)."""

    def __init__(self, *layers):
        self.layers = list(layers)
        self.name = " + ".join(getattr(l, "name", "") or type(l).__name__ for l in layers)

    def _file(self, path):
        for l in self.layers:
            v = l._file(path)
            if v is not None:
                return v
        return None

    def _isdir(self, path):
        return any(l._isdir(path) for l in self.layers)

    def _dir(self, path):
        out, seen, found = [], set(), False
        for l in self.layers:
            names = l._dir(path)
            if names is None:
                continue
            found = True
            for n in names:
                if n.lower() not in seen:
                    seen.add(n.lower())
                    out.append(n)
        return out if found else None

    def __repr__(self):
        return "ChainFS(%s)" % ", ".join(map(repr, self.layers))


class OSFS(FS):
    """Plain OS paths (absolute or relative to the working directory), for
    loading a single loose file: SpriteFile.load("x/sprites.256")."""

    name = "os"

    def read(self, path):
        with open(path, "rb") as f:
            return memoryview(f.read())

    def _file(self, path):
        return self.read(path) if os.path.isfile(path) else None

    def isfile(self, path):
        return os.path.isfile(path)

    def _isdir(self, path):
        return os.path.isdir(path)

    def _dir(self, path):
        return sorted(os.listdir(path)) if os.path.isdir(path) else None

    def open(self, path):
        return open(path, "rb")


OS = OSFS()


def open_fs(source):
    """An FS for `source`: an FS is returned as is; a folder holding .res
    archives -> ResFS; any other folder -> DirFS; None -> OS paths."""
    if source is None:
        return OS
    if isinstance(source, FS):
        return source
    source = os.fspath(source)
    if os.path.isdir(source) and any(n.lower().endswith(".res") for n in os.listdir(source)):
        return ResFS(source)
    if os.path.isdir(source):
        return DirFS(source)
    raise FileNotFoundError("not a folder: %s" % source)
