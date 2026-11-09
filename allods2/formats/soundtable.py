"""Sound id table and the purpose of every audio file (docs/formats/sound.md).

`sfx/sfx.reg` section `Sfx`: keys `Sfx<n>` -> path under `sfx/` without the
extension (the loader fills a 661-slot array; absent keys stay empty).  Files
the table does not name are loaded by code with names built at run time;
`purpose()` classifies them by folder.
"""

import dataclasses

from .. import reg


@dataclasses.dataclass
class SoundTable:
    count: int                       # Global/SfxCount (highest id)
    ids: dict                        # id -> game path "sfx/<name>.wav" (lower case)
    missing: dict                    # id -> path of an entry whose file does not exist

    def path(self, sid):
        return self.ids.get(sid)

    def to_dict(self):
        return {"count": self.count,
                "sounds": {str(k): v for k, v in sorted(self.ids.items())},
                "missing_files": {str(k): v for k, v in sorted(self.missing.items())}}


def load(fs):
    d = reg.load_reg("sfx/sfx.reg", fs).to_dict()
    count = d["Global"]["SfxCount"]
    ids, missing = {}, {}
    for key, name in d["Sfx"].items():
        if not key.startswith("Sfx"):
            continue
        sid = int(key[3:])
        path = "sfx/" + name.replace("\\", "/").lower() + ".wav"
        (ids if fs.exists(path) else missing)[sid] = path
    return SoundTable(count, ids, missing)


# (prefix, purpose), first match wins; INFERRED from names until REA settles each.
PURPOSE = (
    ("music/", "music"),
    ("speech/talk/", "speech: dialogue"),
    ("speech/accept/", "speech: quest accepted"),
    ("speech/reject/", "speech: quest refused"),
    ("speech/about/", "speech: about"),
    ("speech/town/", "speech: town"),
    ("speech/shop", "speech: shop"),
    ("sfx/characters/", "hero / class voice"),
    ("sfx/monsters/", "monster"),
    ("sfx/units/", "unit combat / movement"),
    ("sfx/magic/", "spell"),
    ("sfx/ambient/", "ambience"),
    ("sfx/chrgen/", "character creation UI"),
    ("sfx/town", "town (inn / shop)"),
)


def purpose(path):
    p = path.lower()
    for prefix, what in PURPOSE:
        if p.startswith(prefix):
            return what
    return "UI / misc"


# Hero / class voice banks, in the exe's bank order (constructor 0x4c5038, REA).
BANKS = ("aldor", "sagita", "hildarius", "galinel", "igles", "dina",
         "xbow", "knight", "druid", "troll", "orc", "mage")
VOICE_DIRS = ("select", "attack", "move", "swarm")        # numbered 1..4, probed
VOICE_SINGLE = ("retreat", "pickup", "defend")            # <dir>/1.wav
VOICE_FILES = ("easy", "hard", "dead")                    # <bank>/<name>.wav
SLOTS = ("attack", "hit_material", "easy", "hard", "dead")   # units.reg Sound list
PLAYLIST_MISSION = tuple("music/b%02d.wav" % i for i in range(17))
MUSIC_SCREENS = {"menu": "music/menu.wav", "map": "music/map.wav",
                 "chrgen": "music/chrgen.wav", "credit": "music/credit.wav",
                 "town": ("music/b14.wav", "music/b16.wav", "music/b15.wav")}


def hero_banks(fs):
    """bank -> {category: [paths]}; numbered files counted the way the exe does
    (1, 2, ... until the first missing number, at most 4)."""
    out = {}
    for b in BANKS:
        base = "sfx/characters/%s/" % b
        cats = {}
        for d in VOICE_DIRS:
            files = []
            for n in range(1, 5):
                f = "%s%s/%d.wav" % (base, d, n)
                if not fs.exists(f):
                    break
                files.append(f)
            cats[d] = files
        for d in VOICE_SINGLE:
            f = "%s%s/1.wav" % (base, d)
            cats[d] = [f] if fs.exists(f) else []
        for d in VOICE_FILES:
            f = "%s%s.wav" % (base, d)
            cats[d] = [f] if fs.exists(f) else []
        out[b] = cats
    return out


def unit_sound_sets(fs):
    """units.reg UnitN -> the five sfx.reg ids of its `Sound` key."""
    d = reg.load_reg("graphics/units/units.reg", fs).to_dict()
    out = {}
    for k, v in d.items():
        if k.startswith("Unit") and isinstance(v, dict) and "Sound" in v:
            out[k] = dict(zip(SLOTS, v["Sound"]))
    return out


def to_json(fs):
    t = load(fs)
    speech = {}
    for p in fs.files("speech"):
        speech.setdefault(p.split("/")[1], []).append(p)
    return {
        "table": t.to_dict(),
        "unit_sound_sets": unit_sound_sets(fs),
        "hero_banks": hero_banks(fs),
        "music": {"mission_playlist": list(PLAYLIST_MISSION), "screens": MUSIC_SCREENS},
        "speech_folders": {k: len(v) for k, v in sorted(speech.items())},
    }
