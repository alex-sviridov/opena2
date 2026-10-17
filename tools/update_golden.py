"""Regenerate tests/golden.json: SHA-256 of the `world-dump` JSON of a few maps, and
of the RGB bytes of fixed engine screenshots (key "screenshots").

    python tools/update_golden.py [INSTALL_DIR]

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


def golden_hash(spec, install=None):
    return World.from_map(open_map(spec, install), AssetCache(install)).dump_hash()


def units_hash(install=None):
    """SHA-256 of the units.json that `data export units` writes."""
    import hashlib
    from allods2.common import as_fs
    from allods2.formats import unitstats
    blob = json.dumps(unitstats.load(as_fs(install)).to_dict(), indent=1, sort_keys=True)
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
    map 10, camera centred on the human unit (data.bin humans), that unit selected.  The text uses
    pygame's bundled font, so the hash is tied to the pinned pygame-ce version."""
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


def minimap_hashes(install=None):
    """{map: sha256 of the minimap RGB bytes} for MAPS (no pygame)."""
    from allods2.common import as_fs
    from allods2.minimap import load_color_table, minimap_rgb
    table = load_color_table(as_fs(install))
    return {m: rgb_hash(minimap_rgb(open_map(m, install).runtime_terrain(), table)) for m in MAPS}


def main(argv):
    install = argv[1] if len(argv) > 1 else None
    out = {m: golden_hash(m, install) for m in MAPS}
    out["screenshots"] = shot_hashes(install)
    out["minimaps"] = minimap_hashes(install)
    out["interface"] = interface_hash(install)
    out["units"] = units_hash(install)
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
