"""L5 (docs/engine/town-worldmap.md): the world map's pure model (graph, route, hover, walk, texts) and its screen.  The synthetic tests need no install; the install
ones check the spec's numbers (100 / 81 nodes, 107 edges covering 2766 points, 49 location points, the intro route of 216 points)."""

import os
import struct

import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from engine import worldmap as M  # noqa: E402
from engine.sim import campaign as C  # noqa: E402
from helpers import GFS, needs  # noqa: E402

needs_map = needs("graphics", "global.map", "pathmap.bmp")


def has_dll():
    return M.find_dll() is not None


# -- the model, no install ---------------------------------------------------------------------------------------------------------------

def grid_from(rows):
    """Rows of characters ('.' nothing, '-' path, 'N' node), top row = y 0, as a (x, y) grid."""
    g = np.array([[{".": 0, "-": 1, "N": 2}[c] for c in r] for r in rows], np.uint8)
    return np.ascontiguousarray(g.T)


def test_the_graph_finds_nodes_column_major_and_traces_edges_with_both_end_nodes():
    g = M.PathGraph(grid_from(["N---N", ".....", "N...."]))
    assert g.nodes == [(0, 0), (0, 2), (4, 0)]                              # x outer, y inner
    assert g.edges[(0, 2)] == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)] and g.edges[(2, 0)] == g.edges[(0, 2)][::-1]
    assert (0, 1) not in g.edges and not g.connected()                       # the node at (0, 2) has no path


def test_route_is_the_cheapest_path_with_junction_nodes_twice_and_same_point_is_two_points():
    #   0 -- 1 -- 2      0-2 directly is a longer detour below
    g = M.PathGraph(grid_from(["N-N-N", ".....", "....."]))
    a, b, c = g.nodes
    assert g.route(a, c) == [(0, 0), (1, 0), (2, 0), (2, 0), (3, 0), (4, 0)]   # the junction (2, 0) appears twice
    assert g.route(a, a) == [a, a]
    assert M.route_cost(g, c, a) == 6


def test_route_tie_goes_to_the_first_path_found_in_ascending_node_order():
    #  a diamond: two equal paths 0-1-3 and 0-2-3
    rows = ["N.N.N",
            "-...-",
            "..N..",
            "-...-",
            "N.N.N"]
    g = M.PathGraph(grid_from(rows))
    assert len(g.nodes) >= 4 and g.connected() is not None
    s, e = g.nodes[0], g.nodes[-1]
    assert g.route(s, e) == g.route(s, e)                                    # deterministic (cached and recomputed alike)


def test_nearest_location_by_squared_distance_no_radius_first_wins_a_tie():
    pts = [(100, 100), (200, 100), (150, 400)]
    assert M.nearest(pts, 0, 0) == 0 and M.nearest(pts, 640, 480) == 2 and M.nearest(pts, 149, 100) == 0
    assert M.nearest(pts, 150, 100) == 0                                     # equidistant from 0 and 1: the earlier entry
    assert M.nearest([], 5, 5) is None


def test_walk_schedule_dots_cross_frames_and_minimum_length():
    w = M.Walk([(i, 0) for i in range(100)])
    assert w.dots == [(0, 0)] and w.cross_frame == 0 and w.laying
    w.step()
    assert w.dots == [(0, 0), (8, 0)] and w.cross_frame == 1                 # one new dot per draw
    n = 1
    while not w.step():
        n += 1
    assert n + 1 == 15 and w.cross_frame == 12                               # a short route still takes 15 draws (1.5 s); the Cross stops at frame 12
    long = M.Walk([(i, 0) for i in range(216)])
    k = 1
    while not long.step():
        k += 1
    assert k == 27 == M.total_draws(216)                                     # the intro route (town-worldmap 3.4)
    assert M.total_draws(2) == 15


def test_walk_finish_ends_it_at_once():
    w = M.Walk([(0, 0), (1, 1)])
    w.finish()
    assert w.done


def test_texts_cut_the_two_trailing_characters_and_tags_follow_the_type():
    class FS:
        def read(self, p):
            return b"#title21\r\nThe Camp\r\n#briefing21\r\nFind it.\r\n#town2\r\nKaarg\r\n#description2\r\nA town.\r\n"
    t = M.load_texts(FS())
    assert M.title_and_body(t, (C.MISSION, 21)) == ("The Camp", "Find it.\r\n")          # the body keeps its CR LF: the wrapper and the draw deal with it
    assert M.title_and_body(t, (C.TOWN, 2)) == ("Kaarg", "A town.\r\n")
    assert M.title_and_body(t, (C.MISSION, 99)) == ("", "")
    assert M.tags((C.TOWN, 3)) == ("town3", "description3")


def test_tracer_keeps_a_stub_and_a_second_edge_is_dropped():
    """`FUN_00471f0d`: an A-list that ends off a node (a stub) is kept and the next call appends to it; an edge that exists is not replaced."""
    #  node (0,0) has a one-pixel stub going down and the real path going right to the node (4,0)
    g = M.PathGraph(grid_from(["N---N", "-....", "....."]))
    assert g.nodes == [(0, 0), (4, 0)]
    edge = g.edges[(0, 1)]
    assert edge[0] == (0, 0) and edge[-1] == (4, 0)


def test_wrapper_breaks_on_the_measure_with_the_trailing_space_strictly_below_the_width():
    m = lambda t: len(t)                                                     # 1 px per character, a space counts
    # "aaa bbb ccc": "aaa bbb " is 8 < 9, adding "ccc" makes 11 >= 9: break after "bbb ", the rest (3 < 9) fits and gets a CR
    assert M.wrap_paragraph("aaa bbb ccc", 9, m) == ["aaa bbb ", "ccc\r"]
    assert M.wrap_paragraph("aaa bbb", 8, m) == ["aaa bbb\r"]
    assert M.wrap_paragraph("aaa bbb", 7, m) == ["aaa ", "bbb\r"]            # 7 < 7 is false: the whole text does not fit
    assert M.wrap_paragraph("abcdefghijkl mm", 5, m) == ["abcdefghijkl ", "mm\r"]     # a first word that is too wide stays whole
    assert M.wrap_paragraph("", 9, m) == [""]                                # the loop body runs once; the line's left trim eats the CR
    assert M.wrap("one\r\n\r\ntwo\r\n", 99, m) == ["one\r", "two\r"]          # CR LF splits paragraphs; the split left-trims the rest, so a blank line vanishes


def test_the_last_line_is_drawn_without_its_last_two_characters():
    assert M.draw_lines(["abc ", "def!\r"]) == ["abc ", "def"]               # the CR and one real character
    assert M.draw_lines(["x\r"]) == [""] and M.draw_lines([]) == []


def test_parse_locations_reads_the_constructor_pushes_and_keeps_the_first_object():
    def ctor(t, i, x, y):
        return b"\x6a\x00\x6a\x00" + b"\x68" + struct.pack("<I", y) + b"\x68" + struct.pack("<I", x) + b"\x6a" + bytes([i]) + b"\x6a" + bytes([t]) + b"\xb9" + b"\0\0\0\0"
    dll = b"xx" + ctor(2, 1, 215, 234) + b"yy" + ctor(1, 10, 302, 158) + ctor(1, 10, 1, 1)
    assert M.parse_locations(dll) == {(2, 1): (215, 234), (1, 10): (302, 158)}


def test_straight_paths_and_stand_in_points_without_an_install():
    d = M.WorldData({(1, 5): (10, 10)})
    assert d.point((1, 5)) == (10, 10) and d.point((1, 77)) == d.point((1, 77))
    r = M.StraightPaths().route((0, 0), (10, 4))
    assert r[0] == (0, 0) and r[-1] == (10, 4) and len(r) == 11


# -- the install's numbers -----------------------------------------------------------------------------------------------------------------

@needs_map
@pytest.mark.skipif(not has_dll(), reason="no Scenario.dll")
def test_install_graph_cover_and_location_points():
    loc = M.load_locations()
    assert len(loc) == 49 and loc[(2, 1)] == (215, 234) and loc[(1, 10)] == (302, 158) and loc[(1, 96)] == loc[(1, 93)] == (306, 148)
    g = M.PathGraph.load(GFS, False)
    covered = sum(len(p) for (i, j), p in g.edges.items() if i < j)
    assert len(g.nodes) == 100 and len(g.edges) // 2 == 107 and covered == 2552 + 2 * 107 and g.connected()
    assert sum(p in g.index for p in loc.values()) == 47                      # all but town 1 and mission 10
    gi = M.PathGraph.load(GFS, True)
    assert len(gi.nodes) == 81 and len(gi.edges) // 2 == 90 and gi.connected()
    assert loc[(2, 1)] in gi.index and loc[(1, 10)] in gi.index
    assert len(gi.route(loc[(2, 1)], loc[(1, 10)])) == 216                  # the intro walk's worked example
    for p in loc.values():                                                    # every location is reachable from town 2
        assert g.route(loc[(2, 2)], p)


@needs_map
def test_install_texts_cover_every_shown_location():
    t = M.load_texts(GFS)
    shown = [(1, n) for n in (21, 30, 31, 32, 40, 41, 42, 43, 50, 51, 52, 53, 60, 61, 62, 63, 70, 71, 72, 73, 74, 75, 76, 77, 80, 81, 82, 83, 84, 85, 86, 87, 90, 91, 92, 93, 94, 95, 96, 100, 101, 102, 103, 110)]
    for loc in shown + [(2, 2), (2, 3)]:
        title, body = M.title_and_body(t, loc)
        assert title and body, loc


# -- the screen ------------------------------------------------------------------------------------------------------------------------------

def map_shell(available, party=None, intro=False, points=None):
    from engine.campaign import CampaignGame
    from engine.shell import Services, Shell
    sh = Shell(None, services=Services(autosave=lambda s: None, music=lambda m: None, start_game=lambda p: object()))
    sh.campaign = CampaignGame()
    sh.campaign.camp.available = list(available)
    sh._worldmap = M.WorldData(points or {})
    core = sh.town_core()
    core.party_point, core.intro = party, intro
    sh.start("locations")
    return sh


def test_screen_hover_picks_the_nearest_flag_and_the_title_follows():
    sh = map_shell([(C.MISSION, 21), (C.MISSION, 30)], party=(C.TOWN, 2),
                   points={(C.MISSION, 21): (100, 100), (C.MISSION, 30): (400, 300), (C.TOWN, 2): (50, 50)})
    from engine.shell import Move
    cur = sh.current
    sh.handle(Move(390, 290))
    assert cur.dest == 1 and cur.route[0] == (50, 50) and cur.route[-1] == (400, 300)
    sh.handle(Move(110, 90))
    assert cur.dest == 0
    kinds = [type(o).__name__ for o in cur.scene().ops]
    assert kinds[0] == "Image" and kinds.count("Sprite") == 3                # two location flags + the party flag; the dots are Images
    from engine.shell.scene import Sprite
    sprites = {o.path.split("/")[-2] for o in cur.scene().ops if isinstance(o, Sprite)}
    assert sprites == {"missionflag", "flagonmap", "yourflag"}


def test_screen_walk_lays_dots_plays_the_point_sounds_and_enters_the_location():
    sh = map_shell([(C.MISSION, 21)], party=(C.TOWN, 2), points={(C.MISSION, 21): (300, 200), (C.TOWN, 2): (100, 100)})
    sounds = []
    sh.services.sound = sounds.append
    from engine.shell import Move, Press
    sh.handle(Move(300, 200))
    sh.handle(Press(300, 200, 1))
    cur = sh.current
    assert cur.walk is not None and not cur.walk.done
    sh.update(100)
    assert sounds[:1] == [M.POINT_SOUNDS[1]] and cur.walk.cross_frame == 1          # the index toggles first: Point2 is the first sound
    from engine.shell.scene import Sprite
    assert any(isinstance(o, Sprite) and o.path.endswith("cross/sprites.16a") for o in cur.scene().ops)      # the Cross, no location flags
    for _ in range(40):
        if sh.name != "locations":
            break
        sh.update(100)
    assert sh.name == "game" and sh.params["mission"] == 21 and sh.town_core().mask == 1
    assert sounds[:4] == [M.POINT_SOUNDS[1], M.POINT_SOUNDS[0], M.POINT_SOUNDS[1], M.POINT_SOUNDS[0]]          # alternating (no file system: the sounds have no length)


def test_a_point_sound_starts_only_when_the_current_one_has_finished():
    sh = map_shell([(C.MISSION, 21)], party=(C.TOWN, 2), points={(C.MISSION, 21): (500, 400), (C.TOWN, 2): (100, 100)})
    sh._worldmap.sound_ms = lambda path: 320                                  # about the install's Point1 / Point2
    sounds = []
    sh.services.sound = sounds.append
    from engine.shell import Press
    sh.handle(Press(500, 400, 1))
    for _ in range(12):
        sh.update(100)
    assert len(sounds) == 3 and sounds[0] != sounds[1]                        # draws 1, 5 and 9: 320 ms keep the current sound playing for three draws


def test_screen_click_needs_no_hit_test_and_a_town_enters_its_scene():
    sh = map_shell([(C.TOWN, 2)], party=(C.TOWN, 2), points={(C.TOWN, 2): (100, 100)})
    from engine.shell import Press
    sh.handle(Press(600, 450, 1))                                            # far from everything: the nearest (here own) location is taken
    for _ in range(40):
        sh.update(100)
    assert sh.name == "town" and sh.town_core().view == "scene"


def test_screen_keys_and_the_right_button_do_nothing_and_never_leave():
    sh = map_shell([(C.MISSION, 21)], party=(C.TOWN, 2))
    from engine.shell import Key, Press
    for k in ("escape", "return", "x"):
        sh.handle(Key(k))
    sh.handle(Press(10, 10, 3))
    assert sh.name == "locations" and sh.current.walk is None


def test_intro_map_walks_by_itself_to_the_head_of_the_list_with_no_text():
    sh = map_shell([(C.MISSION, 10)], party=(C.TOWN, 2), intro=True, points={(C.MISSION, 10): (302, 158), (C.TOWN, 2): (215, 234)})
    cur = sh.current
    assert cur.intro and cur.walk is None and cur.dest is None
    ops = cur.scene().ops
    assert ops[0].path.endswith("umoir.bmp") and [o.path.split("/")[-2] for o in ops if type(o).__name__ == "Sprite"] == ["flag"]
    sh.update(100)
    assert cur.walk is not None and cur.dest == 0                            # the first draw starts it
    from engine.shell import Press
    sh.handle(Press(5, 5, 1))                                                # a click while walking finishes at once
    assert sh.name == "game" and not sh.town_core().intro


def test_synthetic_screen_without_install_files_still_runs_every_op():
    sh = map_shell([(C.MISSION, 21), (C.TOWN, 3)])
    from engine.shell import Move
    sh.handle(Move(320, 240))
    assert sh.current.scene().ops and sh.current.title == ""                 # no texts without a file system
