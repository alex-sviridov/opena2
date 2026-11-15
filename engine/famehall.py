"""The hall of fame file (`famehall.dat`, docs/formats/saves.md 5; L10f).

The exe loads it at start (`FUN_004a91d5`, `0x481755`) and writes it back **at shutdown** (`FUN_004a90c9` from the client's destructor `0x482526`, file opened `0x1001` = create / truncate, so
it is always rewritten, CONFIRMED).  Entries are added by `FUN_004a8d28` (called at `0x486ce2` when `FUN_00493da0` says the campaign is finished) through `FUN_004a8c5e`: insert before the first entry
whose score `a` is <= the new one (`new.a < entry.a` moves on, CONFIRMED `0x4a8cbe`), append when none, then truncate to the limit `+0xc` (10 in the install's file).  The score formula
(`FUN_004a8d28`: `round(hero+0x110 / (sum_of_mission_times * 10.0) * obj[+8])`, or `/ 500000.0` when the sum is 0) has an operand `obj[+8]` the saves never set (saves.md 6.5), so the engine
**does not add entries** (DECISION; open question): it keeps the hall it loaded and writes it at exit.

Engine DECISION: the file lives beside the settings file (`Settings` folder), never in the install; the first run starts from the install's own `famehall.dat` (read through the game file system)."""

import os
import tempfile

from allods2.formats import saves as S

NAME = "famehall.dat"
LIMIT = 10                       # the install's file holds 10 entries; the object's `+0xc` (INFERRED: constant)


def path(settings_path):
    """`famehall.dat` beside the settings file."""
    return os.path.join(os.path.dirname(settings_path) or ".", NAME)


class Hall:
    def __init__(self, entries=(), limit=LIMIT):
        self.entries = list(entries)
        self.limit = limit

    def add(self, name, score, b=0, c=0):
        """`FUN_004a8c5e`: before the first entry with `score >= entry.a`, else at the end; the list is cut to `limit`."""
        e = S.HallEntry(name, score, b, c)
        at = next((i for i, x in enumerate(self.entries) if score >= x.a), len(self.entries))
        self.entries.insert(at, e)
        del self.entries[self.limit:]
        return at

    def pack(self):
        return S.build_famehall(self.entries)


def load(directory_file, fs=None):
    """The hall: the file at `directory_file` (settings side), else the install's `famehall.dat` through `fs`, else empty (the exe's default hall is `FUN_004a9730`, not decoded).  A damaged file = the next source."""
    for read in (lambda: open(directory_file, "rb").read() if directory_file else None, lambda: bytes(fs.read_bytes(NAME)) if fs is not None else None):
        try:
            data = read()
            if data:
                return Hall(S.parse_famehall(data))
        except Exception:      # noqa: BLE001  a missing / damaged file: the next source
            continue
    return Hall()


def write(hall, file):
    """Atomic write (temp file + replace); returns the path or None when the folder cannot be written (never raises: a failed shutdown write must not hide the exit)."""
    try:
        folder = os.path.dirname(file) or "."
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".hall-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(hall.pack())
            os.replace(tmp, file)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return file
    except OSError:
        return None
