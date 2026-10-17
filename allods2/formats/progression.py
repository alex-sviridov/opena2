"""Character progression: the XP curve, skill/school names and the hero start templates.

Spec: docs/data/progression.md.  Nothing is copied out of the game: the curve is computed from the
formula the exe computes at start-up, and the hero templates are read from the install's data.bin
(through `unitstats` and `spelldefs`).
"""

from dataclasses import dataclass

from . import spelldefs, unitstats

# docs/data/progression.md section 1.  Index 0 is the "general" skill, 1-5 the five schools.
SKILL_NAMES = ("general", "blade", "axe", "bludgeon", "pike", "shooting")
SCHOOLS = {1: "Blade/Fire", 2: "Axe/Water", 3: "Bludgeon/Air", 4: "Pike/Earth", 5: "Shooting/Astral"}

THRESHOLDS = 150            # entries of the curve table (0x6a8998)
SKILL_CAP = 100             # an award is ignored once the skill is 100
KILL_FACTOR = 0.5           # kill credit = victim.xp * 0.5
OFF_SCHOOL_SHIFT = 3        # xp = (xp + 7) >> 3 outside the best school (shooting excepted)
REPEAT_WINDOW = 5           # distinct victim types remembered for the repeat-kill discount
MIND_XP_DIV = 30.0          # award = trunc(xp * (Mind / 30 + 0.25))
MIND_XP_BASE = 0.25

# Template names that make a human a hero (`FUN_00514cf2` substring test, case sensitive).
HERO_MARKS = ("_Hero", "Start_")

_ATTRS = ("body", "reaction", "mind", "spirit")
_SKILL_FIELDS = ("skill_general", "skill_blade", "skill_axe", "skill_bludgen", "skill_pike", "skill_shooting")


def _build_thresholds():
    # thr[n] = trunc(1.1 ** n); FUN_00512824 computes it with pow() in double precision
    return tuple(int(1.1 ** n) for n in range(THRESHOLDS))


class Progression:
    """The XP curve and the hero templates.

    thresholds    150 ints, `thr[n]` = XP accumulated in one skill that corresponds to skill level n
    hero_templates  list of dicts (see `hero_template`)
    """

    def __init__(self, hero_templates=()):
        self.thresholds = _build_thresholds()
        self.hero_templates = list(hero_templates)

    def threshold(self, n):
        """`thr[min(n, 149)]` (`FUN_005128ac`)."""
        return self.thresholds[min(n, THRESHOLDS - 1)]

    def level_of(self, xp):
        """Largest n with `thr[n] <= xp` (`FUN_00512870`, the client's inverse of the curve).  The exe
        returns the table value `thr[149]` instead of 149 once `xp >= thr[149]`; kept."""
        for i in range(THRESHOLDS - 1):
            if self.thresholds[i + 1] > xp:
                return i
        return self.thresholds[THRESHOLDS - 1]      # the exe also reads one dword past the table at i = 149

    def hero(self, server_id):
        for h in self.hero_templates:
            if h["server_id"] == server_id:
                return h
        return None

    def to_dict(self):
        return {"thresholds": list(self.thresholds),
                "skill_names": list(SKILL_NAMES),
                "schools": {str(k): v for k, v in SCHOOLS.items()},
                "constants": {"skill_cap": SKILL_CAP, "kill_factor": KILL_FACTOR,
                              "off_school_shift": OFF_SCHOOL_SHIFT, "repeat_window": REPEAT_WINDOW,
                              "mind_xp_div": MIND_XP_DIV, "mind_xp_base": MIND_XP_BASE},
                "hero_templates": [dict(h) for h in self.hero_templates]}


def is_hero_name(name):
    return any(m in name for m in HERO_MARKS)


def best_school(skills):
    """Index (1..5) of the highest school skill, the first on ties; 0 when all are <= 0
    (`FUN_00514cf2`: strict `>` against a start value of 0)."""
    best, at = 0, 0
    for k in range(1, 6):
        if skills[k] > best:
            best, at = skills[k], k
    return at


def skills_of(t):
    """The six skills (general, five schools) of a human `UnitType`; -1 (keep the constructor
    default) is 0."""
    return tuple(max(0, t.get(f, -1)) for f in _SKILL_FIELDS)


def spells_of(mask, spells):
    """Spell names of a `known_spells` bit mask: bit n = spell n, n = 1..29 (`FUN_005145d1`).
    -1 (no mask) is none."""
    if mask is None or mask < 0:
        return []
    out = []
    for n in range(1, 30):
        if mask >> n & 1:
            d = spells.get(n) if spells is not None else None
            out.append(d.name if d is not None else "spell %d" % n)
    return out


def start_pools(skills, thresholds=None):
    """XP pools k = 1..5 and their sum of a freshly built human: `pool[k] = thr[skill_k]`
    (`FUN_00513497`)."""
    thr = thresholds or _build_thresholds()
    pools = tuple(thr[min(skills[k], THRESHOLDS - 1)] for k in range(1, 6))
    return pools, sum(pools)


def hero_template(t, spells=None):
    """The start state of one hero template (`unitstats.UnitType` of kind human)."""
    skills = skills_of(t)
    pools, total = start_pools(skills)
    attrs = {a: t.get(a) for a in _ATTRS}
    return {"name": t.name, "server_id": t.server_id, "unit_type": t.unit_type,
            "attributes": attrs, "hp_max": t.get("hp_max"), "mana_max": t.get("mana_max"),
            "skills": list(skills), "best_school": best_school(skills),
            "known_spells": spells_of(t.get("known_spells", -1), spells),
            "equipment": list(t.equipment),
            "start_pools": list(pools), "start_total": total}


def build(units, spells=None):
    """Progression of a `unitstats.UnitTable` (and a `spelldefs.SpellTable` for the spell names)."""
    heroes = [hero_template(t, spells) for t in units.of_kind(unitstats.HUMAN) if is_hero_name(t.name)]
    return Progression(heroes)


def load(fs=None):
    """The progression data of an install (`fs`: game file system)."""
    from ..databin import databin
    db = databin(fs)
    return build(unitstats.build(db), spelldefs.build(db, spelldefs.load_texts(fs)))
