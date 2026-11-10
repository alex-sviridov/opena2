"""Regenerate tests/golden.json: SHA-256 of the `world-dump` JSON of a few maps, and
of the RGB bytes of fixed engine screenshots (key "screenshots").

    python tools/update_golden.py [INSTALL_DIR]
    python tools/update_golden.py --only interface,ui [INSTALL_DIR]    # refresh only these keys

The hashes are derived values (no game data), so the file is committed.  Run it
only when a change of the world state or of the drawing is intended.  Specs:
docs/superpowers/specs/2026-10-16-world-state-design.md and
2026-10-16-object-drawing-design.md "Tests".
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from engine.world import World  # noqa: E402

MAPS = ("10", "20", "52")
GOLDEN = os.path.join(ROOT, "tests", "golden.json")

# Parity positions (map, viewport x, y in world px, kinds that must be in view): trees,
# a structure, a bridge and water meet.  The engine screenshot at shadows=False, lit=False
# equals the E4 reference (`map render --relief`) pixel for pixel.
PARITY = {
    "10-forest": ("10", 256, 256, ("object",)),
    "10-shore-rock": ("10", 1056, 740, ("object", "structure")),
    "10-camp": ("10", 1184, 804, ("object", "structure")),
    "52-bridge": ("52", 2656, 2884, ("object", "bridge")),
    "52-bridge-2": ("52", 3136, 2692, ("bridge",)),
    "52-village": ("52", 2752, 292, ("object", "structure")),
}
# E5 parity positions (map, x, y, what must be in view): units, flyers, a large unit, a pile.  The
# engine at shadows=False, lit=False with units and piles equals `map render --relief --layers all`.
UNIT_PARITY = {
    "10-units": ("10", 400, 1792, ("unit",)),
    "10-ogre": ("10", 816, 1870, ("unit",)),
    "52-bats": ("52", 1000, 300, ("unit", "flyer")),
    "63-piles": ("63", 2900, 3600, ("backpack", "unit")),
}
# name -> (map, x, y, tick, plain): "plain" = shadows=False, lit=False (the parity
# render); the others use the game's default options (regression, not parity).
SHOTS = {"parity-" + k: (v[0], v[1], v[2], 0, True) for k, v in PARITY.items()}
SHOTS.update({"parity-" + k: (v[0], v[1], v[2], 0, True) for k, v in UNIT_PARITY.items()})
SHOTS["full-10-shore-rock"] = ("10", 1056, 740, 0, False)
SHOTS["full-52-village"] = ("52", 2752, 292, 0, False)
SHOTS["full-10-units"] = ("10", 400, 1792, 8, False)
SHOTS["full-52-bats"] = ("52", 1000, 300, 5, False)


# Real-map routes for the pathfinding goldens: (map, start, target); human static plan, unit type walker.
ROUTES = (("10", (33, 67), (69, 40)), ("10", (33, 69), (64, 20)), ("20", (20, 66), (32, 11)),
          ("20", (54, 26), (15, 8)), ("52", (25, 101), (92, 41)), ("52", (84, 40), (18, 104)))


def path_hashes(install=None):
    """{"map:sx,sy>tx,ty": {"len", "sha256" of the route}} of ROUTES (docs/engine/simulation.md 7)."""
    from engine.sim.movement import path_grid
    from engine.sim.pathfinding import plan_static
    assets, worlds, out = AssetCache(install), {}, {}
    for spec, a, b in ROUTES:
        if spec not in worlds:
            worlds[spec] = World.from_map(open_map(spec, install), assets)
        r = plan_static(path_grid(worlds[spec], 1), a, b, human=True)
        key = "%s:%d,%d>%d,%d" % ((spec,) + a + b)
        out[key] = {"found": r.found, "len": len(r.cells),
                    "sha256": hashlib.sha256(json.dumps(r.cells).encode("ascii")).hexdigest()}
    return out


def golden_hash(spec, install=None):
    return World.from_map(open_map(spec, install), AssetCache(install)).dump_hash()


def units_hash(install=None):
    """SHA-256 of the units.json that `data export units` writes."""
    import hashlib
    from allods2.common import as_fs
    from allods2.formats import unitstats
    blob = json.dumps(unitstats.load(as_fs(install)).to_dict(), indent=1, sort_keys=True)
    return {"sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}


def items_hash(install=None):
    """SHA-256 of the items.json that `data export items` writes."""
    from allods2.common import as_fs
    from allods2.formats import itemdefs
    blob = json.dumps(itemdefs.load(as_fs(install)).to_dict(), indent=1, sort_keys=True)
    return {"sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}


def spells_hash(install=None):
    """SHA-256 of the spells.json that `data export spells` writes."""
    from allods2.common import as_fs
    from allods2.formats import spelldefs
    blob = json.dumps(spelldefs.load(as_fs(install)).to_dict(), indent=1, sort_keys=True)
    return {"sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}


def progression_hash(install=None):
    """SHA-256 of the progression.json that `data export progression` writes."""
    from allods2.common import as_fs
    from allods2.formats import progression
    blob = json.dumps(progression.load(as_fs(install)).to_dict(), indent=1, sort_keys=True)
    return {"sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}


def rgb_hash(rgb):
    return hashlib.sha256(rgb.tobytes()).hexdigest()


def shot_hashes(install=None):
    """{name: sha256 of the 1024 x 768 RGB bytes} of SHOTS (needs pygame-ce)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame import render
    from engine.backend_pygame.sprites import SpriteCache
    from engine.backend_pygame.surfaces import SurfaceCache
    from engine.view import Camera, DrawOptions, TerrainView
    assets = AssetCache(install)
    envs, out = {}, {}
    for name, (spec, x, y, tick, plain) in SHOTS.items():
        facing = 0x80 if name[7:] in UNIT_PARITY and name.startswith("parity-") else None   # E5: direction 8
        if (spec, facing) not in envs:
            w = World.from_map(open_map(spec, install), assets, facing=facing)
            tv = TerrainView(w, assets.tileset())
            envs[spec, facing] = (w, tv, SurfaceCache(tv), SpriteCache(assets))
        w, tv, tc, sc = envs[spec, facing]
        cam = Camera(1024, 768, w.width, w.height, x, y)
        opts = DrawOptions(shadows=False, lit=False, units=name.startswith("parity-") and name[7:] in UNIT_PARITY) \
            if plain else DrawOptions()
        out[name] = rgb_hash(render.screenshot(tv, cam, tick, None, tc, assets, opts, None, sc))
    return out


def interface_hash(install=None):
    """sha256 of the full 640x480 interface window (spec 2026-10-17-interface-selection-design.md test 7):
    map 10, camera centred on the human unit (data.bin humans), that unit selected.  The text is drawn
    with the game's fonts (G3c), so the hash no longer depends on pygame's bundled font."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame.interface import screenshot_window
    from engine.ui import Layout
    from engine.view import Camera, DrawOptions, TerrainView
    assets = AssetCache(install)
    w = World.from_map(open_map("10", install), assets)
    u = next(u for u in w.units.values() if u.human)
    lay = Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, u.x * 32 - v.w // 2, u.y * 32 - v.h // 2, border=8 * 32)
    return rgb_hash(screenshot_window(TerrainView(w, assets.tileset()), cam, lay, 0, None, assets,
                                      DrawOptions(), None, (u.id,)))


def fog_hashes(install=None):
    """{"window": sha256 of the 640x480 window, "minimap": of the fogged minimap image} of map 10 with the fog of war as after the first vision pass
    (docs/engine/vision.md): the human unit's owner is the viewer, nothing else seen; the explored ring is a second pass after moving the unit 6 cells."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame.interface import screenshot_window
    from engine.sim import vision
    from engine.ui import Layout
    from engine.view import Camera, DrawOptions, Minimap, TerrainView
    from allods2.common import as_fs
    from allods2.minimap import load_color_table
    assets = AssetCache(install)
    w = World.from_map(open_map("10", install), assets)
    u = next(u for u in w.units.values() if u.human)
    vision.enable(w, u.owner)
    vision.vision_system(w, [])
    u.x += 6
    vision.vision_system(w, [])
    lay = Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, u.x * 32 - v.w // 2, u.y * 32 - v.h // 2, border=8 * 32)
    win = screenshot_window(TerrainView(w, assets.tileset()), cam, lay, 0, None, assets, DrawOptions(), None, (u.id,), player_id=u.owner)
    mm = Minimap(w, load_color_table(as_fs(install)))
    return {"window": rgb_hash(win), "minimap": rgb_hash(mm.image(cam))}


def minimap_hashes(install=None):
    """{map: sha256 of the minimap RGB bytes} for MAPS (no pygame)."""
    from allods2.common import as_fs
    from allods2.minimap import load_color_table, minimap_light, minimap_rgb
    table = load_color_table(as_fs(install))
    out = {}
    for m in MAPS:
        mp = open_map(m, install)
        out[m] = rgb_hash(minimap_rgb(mp.runtime_terrain(), table, minimap_light(mp.heights)))
    return out


def orders_summaries():
    """{scenario: {hash, ended, cells, no_way, ...}} of tests/orders_scenarios.py (synthetic worlds; no install needed)."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import orders_scenarios
    return orders_scenarios.all_summaries()


def casts_summaries():
    """{scenario: {hash, ended, hp, mana, ...}} of tests/spell_scenarios.py (synthetic worlds; no install needed)."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import spell_scenarios
    return spell_scenarios.all_summaries()


def audio_hashes():
    """{scenario: {count, sha256 of the SoundEvent list}} of tests/audio_scenarios.py (synthetic worlds; no install needed; docs/engine/audio.md 8)."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import audio_scenarios
    return audio_scenarios.all_hashes()


def arrows_hashes(install=None):
    """{volley, volley+3: sha256 of the 640x480 frame, shots, world: dump hash} of tests/arrow_scenarios.py (map 73, shooters with arrows in flight, K9)."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import arrow_scenarios
    return arrow_scenarios.hashes(AssetCache(install), install)


def ui_hashes(install=None):
    """{scenario: sha256 of the RGB bytes} of the J1 interface (docs/engine/ui-layout.md 11): map 10 with the placed party, the hero selected, the
    panel in both modes, a message line, the level-up line (XP set through the engine's xp path), the menu / End Quest / pause / story / mission complete / failed windows, and
    the text panel at 800x600.  Text is drawn with the game's fonts (no pygame font), so the hashes do not depend on the pygame-ce font."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame.interface import make_game_ui, screenshot_window
    from engine.sim import triggers, xp
    from engine.ui import Layout, level_up_messages, modal, widgets
    from engine.view import Camera, DrawOptions, TerrainView
    assets = AssetCache(install)
    m = open_map("10", install)
    w = World.from_map(m, assets)
    triggers.enable(w, m, assets=assets, party=0)
    hero = next(u for u in w.units.values() if u.human and u.owner == 1)
    tv = TerrainView(w, assets.tileset())
    out = {}

    def shot(name, ui, size=(640, 480), now_ms=0, tooltip=None, hover=None, at=None, select=None, book=None, pack=None, mouse=None):
        lay = ui.layout
        v = lay.viewport
        at = at or hero
        if select == ():
            w.players[1].selection = ()
        cam = Camera(v.w, v.h, w.width, w.height, at.x * 32 - v.w // 2, at.y * 32 - v.h // 2, border=8 * 32)
        out[name] = rgb_hash(screenshot_window(tv, cam, lay, 0, None, assets, DrawOptions(), None, (hero.id,) if select is None else select, ui=ui, now_ms=now_ms, tooltip=tooltip,
                                               hover=hover, book=book, pack=pack, mouse=mouse))

    def fresh(size=(640, 480)):
        return make_game_ui(assets, Layout.for_size(*size), w, 1, "10")

    ui = fresh()
    shot("hero_picture", ui)
    ui.toggle_mode()
    shot("hero_text", ui)
    ui.toggle_mode()
    ogre = w.objects[0x6006]                                  # hovered structure (Ogre House, 500/500): picture mode, then text mode (ui-layout 10)
    shot("structure_picture", ui, hover=ogre.id, at=ogre)
    ui.toggle_mode()
    shot("structure_text", ui, hover=ogre.id, at=ogre)
    ui.toggle_mode()
    from engine.backend_pygame.text import measure
    from engine.ui.tooltip import bar_text, place
    cell = widgets.cell_rect(ui.layout, 6)                    # Stand Ground: the widest text, pushed back from the right edge
    pos = (cell.x + 20, cell.y + 20)
    shot("bar_tooltip", ui, tooltip=place(bar_text(ui.layout, pos, "own", False, ui.main), pos, lambda t: measure(t, 2), ui.layout.size))
    ui.messages.show("%s 25 %s" % (ui.main.line(0x58), ui.main.line(0x59)), 0, 3000, "normal")
    ui.messages.show(ui.main.line(0x66 + 1), 0, 2000)
    shot("messages", ui)
    ui = fresh()
    ui.open_menu()
    shot("menu", ui)
    ui.apply(("open", "endquest"))
    shot("endquest", ui)
    ui = fresh()
    ui.toggle_pause()
    shot("pause", ui)
    ui = fresh()
    ui._story(1)
    shot("story", ui)
    ui = fresh()
    w.mission_complete = True
    ui.poll(0)
    w.mission_complete = False
    shot("complete", ui)
    ui = fresh()
    ui.modals.push(modal.failed_dialog(ui.layout, ui.main_text, ui.dialog_text, wrap=ui.wrap))
    shot("failed", ui)
    ui = fresh((800, 600))
    ui.toggle_mode()
    shot("hero_text_800", ui)
    ui = fresh()
    shot("heads_party", ui, select=())                        # nothing selected: HeadsL / HeadsR (a bare picture), the party stands on the map (ui-layout 11.8)
    ui = fresh((1024, 768))
    shot("hero_extra_1024", ui)                               # window 8 holds the hero's text, the info panel stays in the picture mode
    shot("structure_extra_1024", ui, hover=ogre.id, at=ogre)
    ui = fresh()
    xp.award(w, hero, 10 ** 6, 1)
    level_up_messages(w, 1, ui.messages, 0, ui.main, lambda h: h.name or ui.hero_name)
    shot("levelup", ui)
    ui.toggle_mode()
    shot("levelup_text", ui)
    # the spell book open (ui-layout 11.12): the hero gets a mage's book, F4 / F6 bound, Haste on auto-cast, the Fire Ball slot selected, at 640x480 and 800x600
    from engine.ui import OrderInput, book as bk, spellbook as sb
    hero.spellbook = sum(1 << n for n in (1, 2, 3, 4, 24, 20, 21, 13, 11, 10, 5, 6, 16, 25))
    hero.auto_spell = 24
    for name, size in (("book_open", (640, 480)), ("book_open_800", (800, 600))):
        ui = fresh(size)
        o = OrderInput(1, size[0], lambda: w.players[1].selection, lambda: "own", mask_fn=lambda: sb.selection_slot_mask(w, (hero.id,)), item_mask_fn=lambda: 0)
        o.hotkeys[0], o.hotkeys[2] = sb.slot_of_spell(1), sb.slot_of_spell(24)
        o.select_slot(sb.slot_of_spell(2))
        ui.book.open_book()
        shot(name, ui, size, book=bk.draw_views(ui.book, o, w, (hero.id,), True))
    hero.spellbook, hero.auto_spell = None, 0
    # the backpack open (ui-layout 11.13): the hero (with its template equipment made explicit) carries eight items, the first is scrolled off, the potion has an F4 label
    # and the right arrow is lit under the pointer; at 640x480 and 1024x768 (caps)
    from allods2.formats import saves
    from engine.sim import gear
    gear.ensure_loadout(w, hero)
    hero.pack = (saves.Item(0x102, 1), saves.Item(0x109, 1), saves.Item(0xE41, 5), saves.Item(0xE42, 3), saves.Item(0xE06, 1, 0, ((41, 1, 3),)),
                 saves.Item(0x104, 1), saves.Item(0x103, 1), saves.Item(0x10A, 1))
    for name, size in (("pack_open", (640, 480)), ("pack_open_1024", (1024, 768))):
        ui = fresh(size)
        ui.pack.open_pack()
        ui.book.inventory_open = True
        ui.sync_pack()
        ui.pack.offsets[hero.id] = 1
        ui.pack.item_keys[0] = (0xE41, ())
        mouse = (ui.pack.right_arrow_rect().x + 8, size[1] - 40)
        shot(name, ui, size, pack=ui.pack.views(w, mouse), mouse=mouse)
    hero.pack = ()
    return out


SOUNDS = ("music/menu.wav", "sfx/click00.wav", "sfx/units/sword.wav", "sfx/characters/dina/attack/1.wav",
          "sfx/characters/galinel/select/2.wav", "sfx/town/shop/nofit.wav", "speech/about/0001t000p01.wav",
          "speech/talk/0021f040p09.wav", "speech/talk/0021s031p03.wav", "speech/shop_druid/books/10.wav")


def sound_hashes(install):
    """SHA-256 of the decoded 16-bit PCM of ten sounds (every format kind and the noisy / partial-block cases)."""
    from allods2.common import as_fs
    from allods2.formats import sound
    fs = as_fs(install)
    return {p: hashlib.sha256(sound.load(p, fs).pcm_bytes()).hexdigest() for p in SOUNDS}


def shell_hashes(install=None):
    """{screen: sha256 of the RGB bytes} of the shell screens: startup, menu (idle, hover, held, disabled hover), new game (idle, hero hover, hero chosen), the options pages."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from shell_scenarios import shell_golden
    return shell_golden(install)


def main(argv):
    only = None
    if len(argv) > 2 and argv[1] == "--only":                 # `--only interface,ui [INSTALL]`: refresh just these keys, keep the others
        only = argv[2].split(",")
        argv = argv[:1] + argv[3:]
    install = argv[1] if len(argv) > 1 else None
    if only is not None:
        with open(GOLDEN, encoding="ascii") as f:
            out = json.load(f)
        makers = {"interface": interface_hash, "ui": ui_hashes, "fog": fog_hashes, "minimaps": minimap_hashes, "arrows": arrows_hashes, "sound": sound_hashes, "shell": shell_hashes, "audio": lambda install: audio_hashes()}
        for k in only:
            out[k] = makers[k](install)
        _write(out)
        return
    out = {m: golden_hash(m, install) for m in MAPS}
    out["screenshots"] = shot_hashes(install)
    out["minimaps"] = minimap_hashes(install)
    out["interface"] = interface_hash(install)
    out["units"] = units_hash(install)
    out["items"] = items_hash(install)
    out["spells"] = spells_hash(install)
    out["progression"] = progression_hash(install)
    out["paths"] = path_hashes(install)
    out["orders_slots"] = orders_summaries()      # was "orders" before the cell-record slots (simulation 7.4); old key dropped on regeneration
    out["casts"] = casts_summaries()
    out["ui"] = ui_hashes(install)
    out["fog"] = fog_hashes(install)
    out["arrows"] = arrows_hashes(install)
    out["sound"] = sound_hashes(install)
    out["shell"] = shell_hashes(install)
    out["audio"] = audio_hashes()
    _write(out)


def _write(out):
    with open(GOLDEN, "w", encoding="ascii") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    for m, h in out.items():
        if isinstance(h, dict):
            for k, v in h.items():
                print("%s %s" % (k, v))
        else:
            print("%s %s" % (m, h))


if __name__ == "__main__":
    main(sys.argv)
