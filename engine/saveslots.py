"""Saved-game slots (docs/engine/save-ui.md; the original's list code `FUN_0043dc54`, slot naming `FUN_0043ece0`).  Pure: files and numbers, no window.

`SaveSlots(directory)` = the folder of `game*.sav` files.  The folder is the player's own (the settings file names it, `engine.audio.settings.saves_path`); the
install is never touched.  What it does, rule by rule as the exe:

* `scan()`: every regular file matching `game*.sav` whose first u32 is `0x26677342` (`FUN_0043dc54` + the entry loop of `FUN_0043ece0`); the description is the
  `0x100` bytes at the offset the u32 at +4 names (the start of the client tail); a file that is not a save is left out of the list.  The Save dialog hides
  `game9999.sav` and `game9998.sav` (`hidden=True` here; `scan(include_hidden=False)`), the Load dialog lists them.  Order = **newest first** (`CompareFileTime`
  of the last write times, `0x43dc0f`); ties by name (the exe's quick sort has no rule).
* `any_saves()`: `FindFirstFile("\\game*.sav")` finds anything (`FUN_0043ff4a`): the main menu's LOAD button and the menu entry are enabled by it; an invalid file counts.
* `new_name(slots)`: `game%04d.sav` with the smallest unused index from 0 over the **listed** names (the exe parses the four characters at 4..7 as digits and sorts).
* `autosave_name(slot)`: `game%d.sav` of `9999 - slot` (`0x48850d`).
* `write(name, data)`: atomic (temp file + rename in the same folder); `delete(name)`; `read(name)`.

`choose_target(text, selected, slots)` is the Save dialog's OK rule (`0x43f8da`): the typed text is the description; when it equals a listed description (rows 1..) that row becomes
the selection; the file is the selected row's (row 0 = the new name).  Quirk kept: a row selected and then retyped overwrites **that** row's file."""

import os
import re
import struct
import tempfile
from dataclasses import dataclass

MAGIC = 0x26677342
DESC_SIZE = 0x100
AUTOSAVE_MISSION, AUTOSAVE_TOWN = 9999, 9998            # `game9999.sav` ("Restart last mission"), `game9998.sav` ("Abort mission and return to town")
PATTERN = re.compile(r"game.*\.sav\Z", re.IGNORECASE | re.DOTALL)       # `\game*.sav` (the Windows find is case-insensitive)
ENCODING = "cp1251"


@dataclass(frozen=True)
class Slot:
    name: str                       # file name, `game0003.sav`
    description: str
    mtime: float                    # last write time, seconds since the epoch
    hidden: bool = False            # game9999 / game9998: not in the Save dialog

    @property
    def number(self):
        """The slot number of the exe's naming code: the four characters at 4..7 read as digits (`c - '0'` weighted 1000 / 100 / 10 / 1, any character)."""
        n = self.name
        return sum((ord(n[4 + i]) - 0x30) * w for i, w in enumerate((1000, 100, 10, 1))) if len(n) >= 8 else 0


def slot_number(n):
    return Slot(n, "", 0.0).number


def is_hidden(name):
    return name.lower() in ("game9999.sav", "game9998.sav")


def autosave_name(slot):
    """`game%d.sav` of `9999 - slot` (the message `0x442` handler `0x4884b9`: slot 0 = the mission start, 1 = leaving a town)."""
    return "game%d.sav" % (9999 - slot)


def new_name(slots):
    """`game%04d.sav` with the smallest unused index (CONFIRMED `FUN_0043ece0`): the sorted numbers of the listed files, the first position `i` where the number is not `i`, else
    last + 1; no file = 0.  Four digits are not enforced (index >= 10000 prints wider, `game%ld.sav`)."""
    nums = sorted(s.number for s in slots)
    if not nums:
        idx = 0
    else:
        idx = nums[-1] + 1
        for i, v in enumerate(nums):
            if v != i:
                idx = i
                break
    return "game%04d.sav" % idx if idx < 10000 else "game%d.sav" % idx


def date_text(mtime):
    """The list's right part: `%02d.%02d.%d  %02d:%02d:%02d` = day.month.year  hour:minute:second of the file's local write time (CONFIRMED `0x5f06f0`, the CTime getters `0x44dfe0`..`0x44e080`)."""
    import time
    t = time.localtime(mtime)
    return "%02d.%02d.%d  %02d:%02d:%02d" % (t.tm_mday, t.tm_mon, t.tm_year, t.tm_hour, t.tm_min, t.tm_sec)


def entry_text(slot):
    """One list row: `"%s  %02d.%02d.%d  %02d:%02d:%02d"` (description, date)."""
    return "%s  %s" % (slot.description, date_text(slot.mtime))


def choose_target(text, selected, slots):
    """The Save dialog's OK (`0x43f8da`).  `slots` = the listed slots (row k >= 1 is `slots[k - 1]`; row 0 = the new file), `selected` = the selected row.  Returns `(row, file name,
    description)`; `text` is the edit field (the description).  An empty text does nothing in the exe (the OK button is disabled): returns None."""
    if not text:
        return None
    row = selected
    for k, s in enumerate(slots, 1):
        if s.description == text:
            row = k
            break
    name = new_name(slots) if row < 1 or row > len(slots) else slots[row - 1].name
    return row, name, text


class SaveSlots:
    def __init__(self, directory):
        self.directory = os.fspath(directory)

    def path(self, name):
        if os.sep in name or (os.altsep and os.altsep in name) or name in ("", ".", ".."):
            raise ValueError("not a slot file name: %r" % (name,))
        return os.path.join(self.directory, name)

    # -- reading ----------------------------------------------------------------------------------------------------------------
    def _files(self):
        try:
            names = os.listdir(self.directory)
        except OSError:
            return []
        return sorted(n for n in names if PATTERN.match(n) and os.path.isfile(os.path.join(self.directory, n)))

    def any_saves(self):
        """The enable test of the main menu's LOAD and the in-game menu's Load entry (`FUN_0043ff4a`): any file `game*.sav`, valid or not."""
        return bool(self._files())

    def describe(self, name):
        """`Slot` of a file, or None when it is not a saved game (the first u32 is not the magic, or the description cannot be read)."""
        p = self.path(name)
        try:
            with open(p, "rb") as f:
                head = f.read(8)
                if len(head) < 8 or struct.unpack_from("<I", head, 0)[0] != MAGIC:
                    return None
                f.seek(struct.unpack_from("<I", head, 4)[0])
                raw = f.read(DESC_SIZE)
            if len(raw) < DESC_SIZE:
                return None
            mtime = os.path.getmtime(p)
        except OSError:
            return None
        return Slot(name, raw.split(b"\0", 1)[0].decode(ENCODING, errors="replace"), mtime, is_hidden(name))

    def scan(self, include_hidden=False):
        """The listed saves, newest first."""
        out = [s for s in map(self.describe, self._files()) if s is not None and (include_hidden or not s.hidden)]
        out.sort(key=lambda s: (-s.mtime, s.name))
        return out

    def read(self, name):
        with open(self.path(name), "rb") as f:
            return f.read()

    # -- writing ----------------------------------------------------------------------------------------------------------------
    def write(self, name, data):
        """Atomic: the bytes go to a temporary file in the folder, then replace `name`.  Raises `OSError` when the folder is not writable."""
        p = self.path(name)
        os.makedirs(self.directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".save-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return p

    def delete(self, name):
        """`DeleteFileA`; False when the file is gone already."""
        try:
            os.unlink(self.path(name))
            return True
        except FileNotFoundError:
            return False
