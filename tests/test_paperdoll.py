"""Paper-doll layer order (docs/formats/paperdoll.md)."""

from allods2 import graphics as gfx


def test_doll_order_mage():
    order = gfx.doll_layer_order(mage=True, two_handed=False)
    assert order[:3] == [("P", 7), ("B",), ("P", 11)] and order[-1] == ("S", 7)
    assert ("P", 8) not in order and ("P", 2) not in order
    mask = gfx.doll_mask_order(mage=True, two_handed=False)
    assert (("P", 8), 9) in mask and (("B",), 0) in mask
    assert [m[0] for m in mask].index(("P", 8)) == [m[0] for m in mask].index(("P", 0)) - 1


def test_doll_order_fighter_two_handed():
    one = gfx.doll_layer_order(mage=False, two_handed=False)
    two = gfx.doll_layer_order(mage=False, two_handed=True)
    assert one[0] == ("B",) and one[8] == ("P", 0) and one[-1] == ("P", 1)
    assert two[-1] == ("P", 0) and ("P", 1) not in two and two.count(("P", 0)) == 1
    mask = gfx.doll_mask_order(mage=False, two_handed=True)
    assert ("B",) not in [m[0] for m in mask] and mask[-1] == (("P", 0), 1)
