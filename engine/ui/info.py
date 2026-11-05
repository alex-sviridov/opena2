"""Unit info panel (window 7), pure part: which unit is shown, the portrait recipe and the text rows
(docs/engine/ui-layout.md 11.1).  No pygame: `engine.backend_pygame.interface` draws what this module lists.

Text rows carry panel-relative coordinates and the exe's flags (`FUN_0045d536`): 0 left, 1 right (`x -= measure`), 2 centre
(`x -= measure // 2`), and a colour table name (gold labels, sage values, orange headers)."""

from dataclasses import dataclass

from allods2.graphics.paperdoll import TWO_HANDED_CLASSES, doll_layer_order, doll_mask_order

from engine.sim import combat as combat_mod
from engine.sim import combatstats
from engine.sim import gear as gear_mod
from engine.sim import xp as xp_mod

from .knowledge import knowledge_id
from .widgets import GOLD, ORANGE, SAGE

LEFT, RIGHT, CENTRE = 0, 1, 2
DETAIL_ALL = 7
MODE_PICTURE, MODE_TEXT = "picture", "text"
MALE_BACK, FEMALE_BACK = "graphics/interface/heroback/backm.256", "graphics/interface/heroback/backf.256"
BODIES = {0: "mfighter", 2: "mmage", 4: "ffighter", 6: "fmage"}      # `+0x1b8 & 6`
HORSE_TYPES = range(17, 22)
MERCENARY, ENEMY = 0x54, 0x53           # main.txt tags
LABEL_BODY = 0x0F                       # Body, Agility, Mind, Spirit = 0xf..0x12
SKILL_FIGHTER, SKILL_MAGE, RESIST = 0x1E, 0x24, 0x29
HEALTH = 0x13                           # main.txt "Health"
NO_UNITS, UNITS = 0x2F, 0x31            # "No units" "selected" / "Units" "selected:"


@dataclass(frozen=True)
class Row:
    text: str
    x: int
    y: int
    flags: int = LEFT
    table: str = GOLD


# --- who is shown ---------------------------------------------------------------------------------------------------------------

def is_hostile(world, viewer, u):
    """The unit's owner has relation bit 0 (war) toward the viewer (`FUN_0041e830`, INFERRED meaning)."""
    p = world.players.get(u.owner)
    return bool(u.owner != viewer and p and len(p.relations) >= viewer and p.relations[viewer - 1] & 1)


def is_allied(world, viewer, u):
    """`FUN_0041e860(owner)`: bit 8 of the viewer's client relation word for the owner (CONFIRMED; bit 8 = shares vision, the viewer's own
    slot has it, sprites.md).  Mapping to the engine's words is INFERRED (DECISION): own, the viewer's vision bit `0x10` toward the owner,
    or the owner's alliance bit 2 toward the viewer (the earlier J1 rule, kept)."""
    if u.owner == viewer:
        return True
    me = world.players.get(viewer)
    if me is not None and 0 < u.owner <= len(me.relations) and me.relations[u.owner - 1] & 0x10:
        return True
    p = world.players.get(u.owner)
    return bool(p and len(p.relations) >= viewer and p.relations[viewer - 1] & 2)


def shown_unit(world, viewer, hover=None, modal=False):
    """The unit the panel shows: the hovered unit (game mode 1, no modal), else the only selected one, else None."""
    if hover is not None and not modal and hover in world.units:
        return world.units[hover]
    sel = world.players[viewer].selection
    if len(sel) == 1 and sel[0] in world.units:
        return world.units[sel[0]]
    return None


def shown_structure(world, hover=None, modal=False):
    """The structure the panel shows: the hovered one (`FUN_004af3bf`: `view+0x9a8` looked up by `FUN_0041ff90`, a `CStructure` goes to the structure
    branch; same conditions as units), else None.  A click never selects a structure, so there is no selected-structure case in the engine."""
    if hover is None or modal:
        return None
    ob = world.objects.get(hover)
    return ob if ob is not None and ob.kind in ("structure", "bridge") else None


def selection_summary(world, viewer, hover=None, modal=False):
    """('unit', u) | ('structure', obj) | ('none', None) | ('many', n): what the panel draws (no unit and a count for none / several selected)."""
    st = shown_structure(world, hover, modal)
    if st is not None:                                  # the hovered object wins over the selection, whatever its kind
        return "structure", st
    u = shown_unit(world, viewer, hover, modal)
    if u is not None:
        return "unit", u
    n = len(world.players[viewer].selection)
    return ("none", None) if n == 0 else ("many", n)


def is_hero(u):
    """`obj+0x1b8 & 1`: the hero types (`_Hero` templates: the units that earn XP, `xp.is_hero`; INFERRED mapping)."""
    return xp_mod.is_hero(u)


def is_human(u):
    """`obj+0x1b8 & 0x11`: every human-class unit (data.bin humans): drawn as a paper doll, tagged Mercenary / Enemy."""
    return bool(u.human)


def is_female(u):
    return u.stats is not None and u.stats.get("gender", 0) == 1


def is_mage(u):
    return gear_mod.is_mage(u)


def combat_of(world, u):
    """The unit's `CombatStats` without caching it in the unit (the UI never changes world state)."""
    had = u.combat
    st = combat_mod.combat_stats(world, u)
    if had is None:
        u.combat = None
    return st


def detail(world, viewer, u, know_all=False, knowledge=None):
    """Detail level `d` 0..7 (`FUN_0046aa1d` `0x46aa30`-`0x46aab5`, CONFIRMED): `knowledge[id] >> 1` for the unit's `+0x1dc` (0 when the id is 0 or
    >= 0xa00), then 7 when the owner's player id is 0, or `FUN_0041e860(owner)` holds (own / vision-sharing), or the cheat flag `0x62280c`
    (`know_all`).  `knowledge` is the viewer's `ui.knowledge.Knowledge` (None = nothing known)."""
    if know_all or u.owner == 0 or is_allied(world, viewer, u):
        return DETAIL_ALL
    return knowledge.level(knowledge_id(u)) if knowledge is not None else 0


# --- portrait -------------------------------------------------------------------------------------------------------------------

def item_picture_name(code):
    """`FUN_00438ba1`: material, class, quality, index of a 16-bit item code; scrolls (class 14) `"%02d%02d%03d"` of (material, 14, code & 0xff)."""
    material, cls = code >> 12, (code >> 8) & 15
    if cls == 14:
        return "%02d%02d%03d" % (material, cls, code & 0xFF)
    return "%02d%02d%1d%02d" % (material, cls, (code >> 5) & 7, code & 31)


def equipped_items(world, u):
    """`{creature slot: resolved item}` of a human: its own loadout, else the template's equipment strings (read only)."""
    if u.equipment:
        return gear_mod.gear_of(world, u)
    if u.stats is None or world.item_table is None:
        return {}
    return combatstats.template_gear(u.stats, world.item_table, is_mage(u))[0]


def doll_layers(world, u):
    """The paper-doll files in draw order (`FUN_004688f7`, paperdoll.md): `[path]` of `.256` layers (and a leading `.bmp` for horse types).
    Layer slot n = creature slot n + 1; a layer without an item or without a file is skipped by the backend."""
    mage, female = is_mage(u), is_female(u)
    gear = equipped_items(world, u)
    weapon = gear.get(1)
    two = (not mage) and weapon is not None and weapon.defn.name.lower() in TWO_HANDED_CLASSES
    body = BODIES[(2 if mage else 0) | (4 if female else 0)]
    out = []
    if u.type_id in HORSE_TYPES:
        out.append("graphics/infowindow/horse.bmp")
    if not mage:
        out.append(FEMALE_BACK if female else MALE_BACK)
    base = "graphics/equipment/" + body + "/"
    for layer in doll_layer_order(mage, two):
        if layer[0] == "B":
            out.append("%s%d.256" % (base, u.face))
            continue
        kind, n = layer
        item = gear.get(n + 1)
        if item is None:
            continue
        out.append("%s%s/%s.256" % (base, "primary" if kind == "P" else "secondary", item_picture_name(gear_mod_code(item))))
    return out


def doll_mask_layers(world, u):
    """`[(path, id)]` of the hit mask (`doll_mask_order`, same files as `doll_layers`): id = slot + 1, the body 0 (it clears what lies under it, mages).  The mage's
    P8 is in the order but never drawn, so it covers nothing."""
    mage, female = is_mage(u), is_female(u)
    gear = equipped_items(world, u)
    weapon = gear.get(1)
    two = (not mage) and weapon is not None and weapon.defn.name.lower() in TWO_HANDED_CLASSES
    base = "graphics/equipment/" + BODIES[(2 if mage else 0) | (4 if female else 0)] + "/"
    out = []
    for layer, ident in doll_mask_order(mage, two):
        if layer[0] == "B":
            out.append(("%s%d.256" % (base, u.face), 0))
            continue
        kind, n = layer
        item = gear.get(n + 1)
        if item is None or (mage and kind == "P" and n == 8):
            continue
        out.append(("%s%s/%s.256" % (base, "primary" if kind == "P" else "secondary", item_picture_name(gear_mod_code(item))), ident))
    return out


def gear_mod_code(item):
    return combatstats.item_code(item)


def portrait(world, u, info_picture=None):
    """('doll', [paths]) for a human, ('bmp', path) for anything else (`graphics/infowindow/<InfoPicture>[face].bmp`), None without a picture.
    `info_picture(unit) -> name or None` is the units.reg `InfoPicture` lookup."""
    if is_human(u):
        return "doll", doll_layers(world, u)
    name = info_picture(u) if info_picture else None
    if not name:
        return None
    return "bmp", "graphics/infowindow/%s%s.bmp" % (name, u.face if u.face > 1 else "")


def structure_picture(s, records):
    """`graphics/infowindow/<Picture>.bmp` of structure `s` (`FUN_004af3bf` `0x4af884`-`0x4af8f9`: structures.reg `Picture`, template `+0x54`, no count
    suffix); None when the record has none.  `records`: `assets.structures_reg()`.  The exe aborts with "FATAL ERROR: can't load" on a missing file; the
    13 structures whose file is missing (ruins, sphinx, magic symbol) are never hovered (Indestructible, not Usable, or Flat)."""
    rec = records.get(s.type_id)
    name = rec.get("Picture") if rec else None
    return "graphics/infowindow/%s.bmp" % name if name else None


def structure_rows(s, texts, building_names):
    """Text-mode rows of a structure (`FUN_004af3bf` `0x4af7be`-`0x4af86f`, ui-layout 10): all centred at x 0x48 - the `building.txt` line `type - 1`
    (`FUN_00474733(obj+0x24 - 1)`) in gold at y 0x1c, "Health" (`main.txt` 0x13) at 0x2c, `"%d/%d"` of the signed s16 `+0x104` / `+0x108` in sage at 0x36.
    No owner, state or level row."""
    i = s.type_id - 1
    name = building_names[i] if 0 <= i < len(building_names) else ""
    hp, hp_max = [((v + 0x8000) & 0xFFFF) - 0x8000 for v in (s.hp, s.hp_max)]
    return [Row(name, 0x48, 0x1C, CENTRE, GOLD), Row(texts.line(HEALTH), 0x48, 0x2C, CENTRE, GOLD),
            Row("%d/%d" % (hp, hp_max), 0x48, 0x36, CENTRE, SAGE)]


# --- text mode ------------------------------------------------------------------------------------------------------------------

def _monster_damage(lo, sp, human):
    if lo & 0x80 and not human:
        return (lo & 0x7F) * 15, sp * 15
    return lo, sp


def text_rows(world, u, texts, unit_names, viewer, hero_name="Hero", know_all=True, knowledge=None):
    """The text-mode rows of `FUN_0046aa1d` for unit `u` (table in ui-layout 11.1), panel-relative.  `texts`: `MainText`,
    `unit_names`: the unitname.txt lines."""
    d = detail(world, viewer, u, know_all, knowledge)
    st = combat_of(world, u)
    hero = is_hero(u)
    mage = st.mage
    rows = []

    def add(text, x, y, flags=LEFT, table=GOLD):
        rows.append(Row(text, x, y, flags, table))

    name = (u.name or (hero_name if u.owner == viewer else "")) if hero else ""
    type_line = unit_names[u.type_id] if 0 <= u.type_id < len(unit_names) else ""
    if name:
        name, _, second = name.partition("|")        # the client splits the unit's `+0x80` string at `|` (`FUN_0040d9b2`, message mask 0x80000000)
        add(name, 0x48, 0x12, CENTRE)
        if second:
            add(second, 0x48, 0x1C, CENTRE)
    else:
        add(type_line, 0x48, 0x1C, CENTRE)
        if is_human(u):
            hostile = is_hostile(world, viewer, u)
            if not hostile:
                add(texts.line(MERCENARY), 0x48, 0x12, CENTRE)
            elif u.type_id < 0x40:
                add(texts.line(ENEMY), 0x48, 0x12, CENTRE)
    attrs = st.attrs or tuple(max(0, u.stats.get(n, 0) if u.stats else 0) for n in ("body", "reaction", "mind", "spirit"))
    if d > 4:
        for k, label in enumerate(range(LABEL_BODY, LABEL_BODY + 4)):
            y = 0x2C + 10 * k
            add(texts.line(label), 6, y)
            add("%d" % attrs[k], 0x50, y, RIGHT, SAGE)
    if d > 0:
        add(texts.line(0x13), 0x73, 0x2C, CENTRE)
        add("%d/%d" % (u.hp, u.hp_max), 0x73, 0x36, CENTRE, SAGE)
        add(texts.line(0x14), 0x73, 0x40, CENTRE)
        add("%d/%d" % (u.mana, u.mana_max), 0x73, 0x4A, CENTRE, SAGE)
    if d > 2 and not mage:
        lo, sp = _monster_damage(st.record.lo, st.record.sp, st.human)
        add(texts.line(0x17), 6, 0x58)
        add("%d-%d" % (lo, lo + sp), 0x46, 0x58, RIGHT, SAGE)
        add(texts.line(0x19), 6, 0x62)
        add("%d" % st.record.skill, 0x46, 0x62, RIGHT, SAGE)
    elif d > 2:
        dmg = staff_damage(world, u, st)
        if dmg is not None:                         # a mage never gets the Attack row; the Dmg row only exists with a staff spell that hurts
            add(texts.line(0x17), 6, 0x58)
            add("%d-%d" % dmg, 0x46, 0x58, RIGHT, SAGE)
    if d > 3:
        add(texts.line(0x18), 0x4A, 0x58)
        add("%d" % st.block.absorb, 0x8C, 0x58, RIGHT, SAGE)
        add(texts.line(0x1A), 0x4A, 0x62)
        add("%d" % st.block.defence, 0x8C, 0x62, RIGHT, SAGE)
    if d > 1:
        from engine.sim import movement
        word = sight_word(u, st)
        add(texts.line(0x15), 0x28, 200)
        add("%d.%d" % (word >> 8, ((word & 0xFF) * 10) >> 8), 0x6A, 200, RIGHT, SAGE)
        add(texts.line(0x16), 0x28, 0xD2)
        try:
            speed = movement.unit_speed(u)
        except AttributeError:                      # a template without a speed column (synthetic worlds)
            speed = 0
        add("%d" % speed, 0x6A, 0xD2, RIGHT, SAGE)
    if d > 6:
        add(texts.line(0x1B if is_human(u) else 0x1C), 6, 0x70, LEFT, ORANGE)       # `0x46ac0b`: `+0x1b8 & 0x11` clear -> the Resistance text
        base = SKILL_MAGE if (mage and hero) or u.type_id in (0x17, 0x18) else SKILL_FIGHTER
        for k in range(5):
            y = 0x7A + 10 * k
            add(texts.line(base + k), 6, y)
            add("%d" % (u.skills[1 + k] if len(u.skills) > 1 + k else 0), 0x46, y, RIGHT, SAGE)
    if d > 5:
        add(texts.line(0x1C), 0x4A, 0x70, LEFT, ORANGE)
        for k in range(5):
            y = 0x7A + 10 * k
            add(texts.line(RESIST + k), 0x4A, y)
            add("%d" % st.block.prot[1 + k], 0x8C, y, RIGHT, SAGE)
    if d == DETAIL_ALL and hero:
        add(texts.line(0x23), 0x10, 0xAE)
        add("%d.%d" % (st.load // 10, st.load % 10), 0x7F, 0xAE, RIGHT, SAGE)
        add(texts.line(0x2E), 0x10, 0xBA)
        add("%d" % xp_shown(u), 0x7F, 0xBA, RIGHT, SAGE)
    elif d == DETAIL_ALL:
        if st.mage:
            add(texts.line(0xBE), 0x4A, 0xAE, CENTRE)
        if st.sure_hit:
            add(texts.line(0xBF), 0x4A, 0xBA, CENTRE)
    return rows


def staff_damage(world, u, st):
    """The mage's Dmg row (`FUN_0046aa1d` `0x46afad`-`0x46b12b`, ui-layout 11.1): (min', min' + spread') of the spell on the **wielded weapon**
    (client item `+0x188` = equipment slot 1; its `castSpell` effect kind `0x29` = spell, kind `0x32` = the charges / `:N`), scaled by `FUN_005195b1`
    with that count as the level (no skill, no Mind: the same level the staff cast uses, spells.md 9c).  None = no row: not a human (the client
    fills `+0x188` only for humans), no weapon spell, an unknown spell or a spell without damage (sum of the two bytes 0)."""
    ws = st.weapon_spell
    if ws is None or not u.human or world.spell_table is None:
        return None
    spell = world.spell_table.get(ws[0])
    if spell is None:
        return None
    sc = spell.scaled(ws[1] & 0xFF)
    lo, sp = sc.damage_min & 0xFF, sc.damage_spread & 0xFF
    return (lo, lo + sp) if lo + sp else None


def sight_word(u, st):
    """The client's `+0x10a` word (server `+0xa4`, 8.8 fixed point, ui-layout 11.1): a human's recompute `FUN_0051366b` writes
    `ftol(((mind + reaction) / 25 + 4) * 256)` (truncating) and `FUN_005113e7` adds the bonus word `+0xe4` (equipment and spell scan changes, `<< 8`);
    a monster's word is its template scan byte `<< 8` plus the spell changes (`+0xa4 += a << 8`).  Wrapped to 16 bits."""
    if st.human:
        word = combatstats.human_sight_word(u, st)
    else:
        word = ((int((u.stats.get("scan_range", 0) or 0) if u.stats else 0) + u.fx.scan + u.fx.scan_direct) & 0xFF) << 8
    return word & 0xFFFF


def xp_shown(u):
    """Client `+0x110` = the sum of the five XP pools `+0x16c..+0x17c` (server `+0x240..+0x250`, one per school, ui-layout 11.1)."""
    return sum(u.xp) if u.xp else u.xp_total


def count_rows(kind, n, texts):
    """The rows of the empty / multi-selection panel: ("No units" / "selected") or ("Units" / "selected:" / count), centred at x 0x48."""
    if kind == "none":
        return [Row(texts.line(NO_UNITS), 0x48, 0x36, CENTRE), Row(texts.line(NO_UNITS + 1), 0x48, 0x42, CENTRE)]
    return [Row(texts.line(UNITS), 0x48, 0x36, CENTRE), Row(texts.line(UNITS + 1), 0x48, 0x42, CENTRE),
            Row("%d" % n, 0x48, 0x4E, CENTRE)]
