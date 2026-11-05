"""The story window's text script (docs/engine/ui-layout.md 11.5): the `#event<n>` section of `main\\text\\mission<id>.txt`, cut into pages.

Pure core, no pygame.  A section is a list of tag lines `<NPC=21, IAMMALE, IAMFIGHTER, PART=1>` each followed by the page text.  The window
shows page 1, 2, 3 ... one per press of Ok; page `n` is the text after the FIRST tag (in file order) that contains `part=n` and whose conditions
hold for the main hero; the window closes when no tag qualifies (`FUN_004dd226`, called by `FUN_004dc84c`).  Tag matching is a plain
substring search on the lower-cased tag, as in the exe (so `part=1` also matches `part=10`).
"""

import re
from dataclasses import dataclass

NOTHING_TO_SAY = "Nothing to say"           # the text widget's initial string (exe literal `0x5eead8` / `0x5eeac8`)

# picture crop offsets of unit types 0x40..0x66 (the exe's table at 0x5f2d98, (x, y) pairs; (-1, -1) = default crop)
_CROP = (30, 72, 26, 23, 10, 44, -1, -1, 15, 21, 32, 21, -1, -1, 7, 49, -1, -1, -1, -1, 8, 72, -1, -1, -1, -1, -1, -1, -1, -1, 30, 72, 23, 31,
         43, 7, 37, 28, 37, 28, 37, 28, 37, 28, 37, 28, 37, 28, 37, 28, 37, 24, 37, 24, 37, 24, 37, 24, 37, 15, 37, 15, 37, 15, 37, 15, 35, 15,
         35, 15, 35, 14, 35, 21, 32, 18, 15, 21)
DEFAULT_CROP = (0x24, 8, 0x48, 92)          # source (x, y, w, h) in the 160x240 picture, placed at (8, 7) of an 88x108 surface (rows top-down: INFERRED, the exe's rect is
                                            # (0x24, 0x8c, 0x6c, 0xe8) = bottom-up rows 140..232); the table entries give (x, y, 0x48, 0x60)
PICTURE_SIZE = (0x58, 0x6C)


@dataclass(frozen=True)
class Page:
    text: str                       # the page text between the tag line and the next `<` (minus the CR before it)
    npc: int                        # `npc=` id of the speaker (0 = none)
    has_npc: bool                   # the tag contains `npc=` (the speaker picture is shown)
    sound: str = ""                 # `sound:` name (INFERRED: played by the caller; unused by the install's texts)
    tune: int = -1                  # `tune:` number
    tips: int = 0                   # `tips:` number (message `0x45b` when the dialogue ends)


def section(text, key):
    """`FUN_004dd05b`: the part of `text` after the line `#<key>` up to the next `#` ('' when the key is absent).  The exe cuts from the first `#<key>`
    (substring search: `#event1` also finds `#event10`; case-insensitivity INFERRED), skips the key line (`#key` + 2 bytes = CR LF)."""
    p = text.lower().find("#" + key.lower())
    if p < 0:
        return ""
    body = text[p + len(key) + 3:]
    q = body.find("#")
    return body if q < 0 else body[:q]


FAILURE_DEFAULT = 0x118          # main.txt line `0x118 + n` is the default reason of `#failure<n>` for n = 2, 3, 4 (CONFIRMED `0x48d96b`)


def failure_texts(text, main):
    """The mission-failed reason list `0x6227b0` (CONFIRMED, built at mission start `0x48d913`-`0x48d9c2`): for n = 2, 3, ... the section `#failure<n>` of the mission text
    (`FUN_004ddb87`: the same cut as `section`, '' when absent); an empty one is replaced by `main` line `0x118 + n` while n < 5, otherwise the list ends.  Entry `k` serves the
    failure cause `k + 2`.  Newlines are normalised and the ends trimmed (DECISION: the exe keeps the raw bytes, e.g. a leading LF after a `#failure2 ` line)."""
    out, n = [], 2
    while True:
        sec = section(text, "failure%d" % n) if text else ""
        sec = sec.replace("\r\n", "\n").strip("\n ")
        if not sec:
            if n >= 5:
                return out
            sec = main(FAILURE_DEFAULT + n)
        out.append(sec)
        n += 1


def failure_text(text, main, cause):
    """The failed window's body (`0x486fd5`: `0x6227b0[cause - 2]`); '' outside the list (the exe reads past the list, J1 shows nothing)."""
    lst = failure_texts(text, main)
    return lst[cause - 2] if 0 <= cause - 2 < len(lst) else ""


def has_speaker_layout(sec):
    """`+0x7c` after `FUN_004dd05b`: the section contains `npc` anywhere -> the window is built with the picture widget and the narrow text rect."""
    return "npc" in sec.lower()


def hero_flags(female, mage):
    """The exe's hero `+0x1b8` bits used by the tags: bit 4 = female, bit 2 = mage (CONFIRMED `FUN_004dd226` / the voice letter of `FUN_004dc84c`)."""
    return (4 if female else 0) | (2 if mage else 0)


def _int(s):
    m = re.match(r"\s*[+-]?\d+", s)
    return int(m.group()) if m else 0


def _ids(tag, key):
    out, p = [], 0
    while True:
        i = tag.find(key, p)
        if i < 0:
            return out
        out.append(_int(tag[i + len(key): i + len(key) + 5]))
        p = i + len(key)


def page(sec, n, flags, alive=lambda npc: True):
    """Page `n` (1, 2, ...) of the section for a hero with `flags` (`hero_flags`); `alive(npc)` = a living unit with that id exists.  None = no more pages."""
    pos, want = 0, "part=%d" % n
    while True:
        i = sec.find("<", pos)
        if i < 0:
            return None
        j = sec.find(">", i)
        if j < 0:
            return None
        tag = sec[i + 1:j].lower()
        pos = j + 1
        if want not in tag:
            continue
        female, mage = bool(flags & 4), bool(flags & 2)
        if "iamfemale" in tag and not female:
            continue
        if "iammale" in tag and female:
            continue
        if "iammage" in tag and not mage:
            continue
        if "iamfighter" in tag and mage:
            continue
        if any(not alive(k) for k in _ids(tag, "npcalive:")):
            continue
        if any(alive(k) for k in _ids(tag, "npcdead:")):
            continue
        npc, has_npc = 0, "npc=" in tag
        if has_npc:
            npc = _int(tag[tag.find("npc=") + 4:][:5])
        sound = ""
        k = tag.find("sound:")
        if k >= 0:
            rest = tag[k + 6:]
            sound = rest[1:].split('"')[0] if rest.startswith('"') else rest.split(";")[0]
        tune = _int(tag[tag.find("tune:") + 5:][:5]) if "tune:" in tag else -1
        tips = _int(tag[tag.find("tips:") + 5:][:5]) if "tips:" in tag else 0
        nl = sec.find("\n", j)
        if nl < 0:
            return None                                     # no line end after the tag: the exe returns 0 here
        start = nl + 1
        lt = sec.find("<", start)
        if lt < 0:
            end = len(sec)
        else:
            end = sec.rfind("\r", start, lt)               # back to the CR of the line before the next tag
            if end < 0:
                end = lt                                    # an LF-only file (the exe's backward scan has no stop there; the install is CRLF)
        return Page(sec[start:end], npc, has_npc, sound, tune, tips)


def pages(sec, flags, alive=lambda npc: True, limit=1000):
    """Every page in order (the window's sequence until it closes)."""
    out = []
    for n in range(1, limit):
        p = page(sec, n, flags, alive)
        if p is None:
            return out
        out.append(p)
    return out


def dummy_doll_path(npc):
    """The paper doll of the dummy speaker `FUN_0041d8bb(npc)` builds when no living unit has the id (CONFIRMED `0x41d8bb`, `FUN_004688f7`): flags `0x56` = female (`& 4`)
    mage (`& 2`), no equipment, face `+0x28 = npc - 0x50`, so the picture is the body layer alone, `graphics\\equipment\\fmage\\<npc - 0x50>.256` (a mage has no back
    picture).  The install has fmage faces 1..20 (speaker ids 0x51..0x64); any other id makes the exe stop with "FATAL ERROR: can't load" (`FUN_00424559`)."""
    return "graphics/equipment/fmage/%d.256" % (npc - 0x50)


def crop_of(type_id):
    """(x, y, w, h) of the crop of the 160x240 portrait (`FUN_0041d48d`: the default, or the table of types 0x40..0x66 with `y != -1`)."""
    if 0x40 <= type_id <= 0x66:
        k = (type_id - 0x40) * 2
        x, y = _CROP[k], _CROP[k + 1]
        if y != -1:
            return x, y, 0x48, 0x60
    return DEFAULT_CROP
