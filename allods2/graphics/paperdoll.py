"""Paper doll (inventory figure): the exe's layer draw order and hit-mask
order (FUN_004688f7).  Spec: docs/formats/paperdoll.md.
"""

TWO_HANDED_CLASSES = ("bowman", "archer", "xbowman", "axeman2h", "swordsman2h", "mage_st")


def doll_layer_order(mage, two_handed):
    """Draw order after the horse / hero-back layers: ("B",) body, ("P", n)
    primary and ("S", n) secondary layer of slot n.  two_handed = slot 0's
    item class is in TWO_HANDED_CLASSES (fighters only)."""
    if mage:
        return [("P", 7), ("B",), ("P", 11), ("P", 9), ("S", 9), ("P", 3), ("S", 3),
                ("P", 6), ("P", 4), ("P", 0), ("P", 5), ("S", 7)]
    out = [("B",), ("P", 11), ("P", 10), ("P", 6), ("P", 3), ("P", 4), ("P", 8), ("P", 9)]
    if not two_handed:
        out.append(("P", 0))
    out += [("P", 7), ("S", 3), ("P", 5), ("S", 8), ("S", 9)]
    out.append(("P", 0) if two_handed else ("P", 1))
    return out


def doll_mask_order(mage, two_handed):
    """Hit-mask order: (layer, id) with id = slot + 1, body 0.  Mages add
    slot 8 (never drawn); fighters leave out the body."""
    order = doll_layer_order(mage, two_handed)
    if mage:
        order.insert(order.index(("P", 0)), ("P", 8))
    else:
        order.remove(("B",))
    return [(layer, 0 if layer == ("B",) else layer[1] + 1) for layer in order]


def hit_mask(layers, fs=None, size=(160, 240)):
    """The doll's hit mask (paperdoll.md 4; the exe passes a byte surface to `FUN_004688f7`): `layers` = [(file path, id)] in `doll_mask_order`; every layer
    writes its id (slot + 1, the body 0) over the pixels it covers, later layers over earlier ones.  A layer without a file covers nothing.  Returns
    a (height, width) uint8 array."""
    import numpy as np

    from .canvas import Canvas
    from .sprites import SpriteFile
    mask = np.zeros((size[1], size[0]), np.uint8)
    for path, ident in layers:
        try:
            f = SpriteFile.load(path, fs)
        except (KeyError, OSError, ValueError):
            continue
        canvas = Canvas(*size)
        canvas.draw_256(f.sprites[0], 0, 0, f.palette)
        mask[canvas.pix.any(axis=2)] = ident
    return mask
