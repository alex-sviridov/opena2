"""Map-unit `behaviour` bits 1, 2, 4 (quest-target flags of FUN_005303ed, docs/formats/map.md part 5): the 46 campaign maps set only bit 8."""

from allods2.cli import campaign_maps, open_map

from helpers import GFS, needs_data

pytestmark = needs_data


def test_no_campaign_unit_sets_the_quest_target_bits():
    seen = set()
    for m in campaign_maps(GFS):
        seen |= {u.behaviour for u in open_map(m, GFS).units}
    assert seen == {0, 8}
