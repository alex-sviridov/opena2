"""The world map (L5, docs/engine/town-worldmap.md): the path graph, the route, the hover rule, the walk schedule and the `globalmap.txt` texts, as pure code.
No pygame, no drawing; `engine/shell/locations.py` is the screen over it.

Everything the map reads from the install is read here at run time (`load_locations` from `Scenario.dll`, `PathGraph.load` from the two path bitmaps,
`load_texts` from `globalmap.txt`); nothing derived from the game files is stored in the repository.

Marks as in the spec: the graph tracer's bookkeeping, the walk's end test (one draw either way) and which of two parallel edges the matrix keeps are INFERRED
(town-worldmap 3.3, 8.5); the rest is CONFIRMED there."""

import re
from pathlib import Path

import numpy as np

from allods2.text import decode_text

MISSION, TOWN = 1, 2                    # location types (`engine.sim.campaign`)
W, H = 640, 480
STEP, DRAW_MS = 8, 100                  # route points per draw, ms per draw (tick `0x4715a5`)
CROSS_FRAMES, MIN_DRAWS = 13, 15        # the Cross frames, `+0x134 > 14`
DESC_RECT = (70, 48, 390, 200)          # the description's wrap rect (open question 2)
TEXT_X, TITLE_Y, DESC_Y, DESC_LINE = 230, 27, 48, 10
TITLE_GRADIENT = (65, 47, 20)           # the brown code gradient `0x620100` -> `DAT_00620e80`, row 0 (palettes 6), font4's glyph index -> colour

BACKGROUND = {False: "main/graphics/global.map/gmap.bmp", True: "main/graphics/global.map/umoir.bmp"}
PATHMAP = {False: "graphics/global.map/pathmap.bmp", True: "graphics/global.map/umoirpath.bmp"}
SPRITES = {k: "graphics/global.map/%s/sprites.16a" % k for k in ("flag1", "flag", "cross", "missionflag", "flagonmap", "yourflag")}
BALL = "graphics/global.map/ballmap.bmp"
TEXTS = "main/text/globalmap.txt"
POINT_SOUNDS = ("sfx/Point1.wav", "sfx/Point2.wav")
FLAG_FRAMES = 9


# -- the location points (Scenario.dll) ---------------------------------------------------------------------------------------------------

_IMM = rb"(?:\x6a(.)|\x68(.{4}))"
_CTOR = re.compile(rb"\x6a\x00\x6a\x00" + _IMM * 4 + rb"\xb9(.{4})", re.S)         # push 0, push 0, push y, push x, push id, push type, mov ecx, object


def parse_locations(dll):
    """`{(type, id): (x, y)}` from the bytes of `Scenario.dll` (town-worldmap 5.3: the static constructor calls `0x100038e0(type, id, x, y, 0, 0)`; the first
    object of a key wins, the three later ones with the same ids are in no list)."""
    def imm(m, i):
        a, b = m.group(i), m.group(i + 1)
        return a[0] if a is not None else int.from_bytes(b, "little")
    out = {}
    for m in _CTOR.finditer(bytes(dll)):
        y, x, ident, kind = imm(m, 1), imm(m, 3), imm(m, 5), imm(m, 7)
        if kind in (MISSION, TOWN):
            out.setdefault((kind, ident), (x, y))
    return out


def find_dll(install=None):
    from allods2.common import INSTALL
    root = Path(install or INSTALL)
    for p in root.iterdir() if root.is_dir() else ():
        if p.name.lower() == "scenario.dll":
            return p
    return None


def load_locations(install=None):
    """The 49 location points of the install, `{}` when `Scenario.dll` is not there."""
    p = find_dll(install)
    return parse_locations(p.read_bytes()) if p else {}


# -- the path graph (FUN_00471a75) ----------------------------------------------------------------------------------------------------------

NEIGHBOURS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]      # cx outer, cy inner


class PathGraph:
    """`nodes` = the pixels of value 2 (x outer, y inner scan), `edges[(i, j)]` = the polyline from node i to node j, both end nodes included (`[j][i]` is its
    reverse).  `grid[x][y]` is the picture value (0 nothing, 1 path, 2 node) with y top-down (the file's rows are bottom-up)."""

    def __init__(self, grid):
        self.grid = grid
        xs, ys = np.nonzero(grid == 2)                                  # np.nonzero is row-major in (x, y): x outer, y inner
        self.nodes = [(int(x), int(y)) for x, y in zip(xs, ys)]
        self.index = {p: i for i, p in enumerate(self.nodes)}
        self.edges = {}
        self._trace_all()
        self.adj = {i: [] for i in range(len(self.nodes))}
        for (i, j), pts in sorted(self.edges.items()):
            self.adj[i].append((j, len(pts)))
        self._routes = {}

    @classmethod
    def load(cls, fs, intro=False):
        from allods2.graphics.bmp import load_bmp
        bm = load_bmp(PATHMAP[bool(intro)], fs)
        return cls(np.ascontiguousarray(bm.index.T))                    # (x, y); `load_bmp` already put the top row first = y 0

    def _v(self, x, y):
        return int(self.grid[x, y]) if 0 <= x < self.grid.shape[0] and 0 <= y < self.grid.shape[1] else 0

    def _trace_all(self):
        """`FUN_00471f0d` (CONFIRMED `0x471f0d`-`0x4721fe`): per node, the tracer is called again and again on one list `A` (seeded with the node) until it adds nothing;
        after each call, an `A` that ends on a node pixel becomes the edge `[i][j]` (and `[j][i]` reversed) unless `[i][j]` exists, and is then reset to the node; an `A` that
        ends elsewhere (a stub) or on an existing edge is **kept** and the next call appends to it (the exe's quirk: UmoirPath has two such stubs)."""
        self.visited = {}
        for i, start in enumerate(self.nodes):
            a = [start]
            self.visited[start] = 1
            for _ in range(10000):                                      # the exe has no guard; the install never needs one
                self._trace(start[0], start[1], 2, a, start)
                if len(a) == 1:
                    break
                j = self.index.get(a[-1])
                if j is not None and (i, j) not in self.edges:
                    self.edges[(i, j)] = list(a)
                    self.edges[(j, i)] = list(a)[::-1]
                    a = [start]

    def _trace(self, x, y, depth, a, start):
        """`FUN_004721ff`: scan the 8 neighbours (cx outer, cy inner) and act on the first that qualifies: an unvisited path pixel is marked (`depth`), appended and
        followed (the call chain unwinds when it returns: the exe's function always returns 0); a node pixel other than `start` is appended and ends the trace."""
        for cx in range(x - 1, x + 2):
            if not 0 <= cx < self.grid.shape[0]:
                continue
            for cy in range(y - 1, y + 2):
                if not 0 <= cy < self.grid.shape[1] or (cx, cy) == (x, y):
                    continue
                v = int(self.grid[cx, cy])
                if v == 1 and (cx, cy) not in self.visited:
                    self.visited[(cx, cy)] = depth
                    a.append((cx, cy))
                    cur = (cx, cy)
                    while True:                                         # the recursion, unrolled
                        nxt = self._first(cur, a, start)
                        if nxt is None:
                            return
                        cur = nxt
                    return
                if v == 2 and (cx, cy) != start:
                    a.append((cx, cy))
                    return

    def _first(self, cur, a, start):
        x, y = cur
        for cx in range(x - 1, x + 2):
            if not 0 <= cx < self.grid.shape[0]:
                continue
            for cy in range(y - 1, y + 2):
                if not 0 <= cy < self.grid.shape[1] or (cx, cy) == cur:
                    continue
                v = int(self.grid[cx, cy])
                if v == 1 and (cx, cy) not in self.visited:
                    self.visited[(cx, cy)] = 1
                    a.append((cx, cy))
                    return (cx, cy)
                if v == 2 and (cx, cy) != start:
                    a.append((cx, cy))
                    return None
        return None

    # -- statistics for the tests / the spec's cover check -------------------------------------------------------------------------
    def connected(self):
        todo, seen = [0], {0}
        while todo:
            for j, _ in self.adj[todo.pop()]:
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
        return len(seen) == len(self.nodes)

    # -- the route (FUN_0047110e / FUN_004713c2) -----------------------------------------------------------------------------------
    def node_of(self, point):
        """The node of a location point: the node pixel itself, else the nearest node (a location off the nodes is not in the install)."""
        if point in self.index:
            return self.index[point]
        return min(range(len(self.nodes)), key=lambda i: (self.nodes[i][0] - point[0]) ** 2 + (self.nodes[i][1] - point[1]) ** 2)

    def route(self, a, b):
        """The route between two location points: the concatenation of the edge polylines of the cheapest path (cost = the sum of the edge point counts,
        nodes tried in ascending order, no node twice, a path replaces the best only when strictly cheaper); `[a, b]` when they are the same point."""
        if a == b:
            return [a, b]
        key = (a, b)
        if key not in self._routes:
            i, j = self.node_of(a), self.node_of(b)
            best = [None, None]

            def dfs(n, path, cost):
                if best[0] is not None and cost >= best[0]:
                    return
                if n == j:
                    best[0], best[1] = cost, list(path)
                    return
                for m, c in self.adj[n]:
                    if m not in path:
                        path.append(m)
                        dfs(m, path, cost + c)
                        path.pop()
            dfs(i, [i], 0)
            pts = []
            if best[1]:
                for u, v in zip(best[1], best[1][1:]):
                    pts += self.edges[(u, v)]
            self._routes[key] = pts or [a, b]
        return self._routes[key]


def route_cost(graph, a, b):
    return len(graph.route(a, b))


# -- hover (0x4716aa) -------------------------------------------------------------------------------------------------------------------

def nearest(points, mx, my):
    """The index of the point nearest to `(mx, my)` by squared distance, no radius; the earlier entry wins a tie.  None for an empty list."""
    best, at = None, None
    for i, (x, y) in enumerate(points):
        d = (x - mx) ** 2 + (y - my) ** 2
        if best is None or d < best:
            best, at = d, i
    return at


# -- the walk schedule (draw 0x470153-0x4707ba) ----------------------------------------------------------------------------------------

class Walk:
    """One walk along `route`: one `step()` per draw (every 100 ms).  Before draw k (1-based) `progress` = 8k; the dots shown are the route points `i < min(progress,
    count - 1)` with `i % 8 == 0`; the Cross frame is `min(k - 1, 12)`; after the draw the counters grow by 1 / 8.  Done at the first draw whose grown counters
    satisfy `progress > count` and `k > 14` (CONFIRMED `0x4703b8`-`0x4703e3`: `+0x12c > size`, `+0x134 > frames + 1`; at least 1.5 s)."""

    def __init__(self, route):
        self.route = route
        self.count = len(route)
        self.draws = 0
        self.progress = STEP
        self.done = False

    @property
    def dots(self):
        return [self.route[i] for i in range(0, min(self.progress, self.count - 1), STEP)]

    @property
    def cross_frame(self):
        return min(self.draws, CROSS_FRAMES - 1)

    @property
    def laying(self):
        """The Point sounds play while the grown progress is `< count - 1` (CONFIRMED `0x470353`; the "not playing" test is not modelled)."""
        return self.progress < self.count - 1

    def step(self):
        """One draw; True when the walk is over (the caller then runs the end sequence)."""
        self.draws += 1
        self.progress += STEP
        self.done = self.progress > self.count and self.draws >= MIN_DRAWS
        return self.done

    def finish(self):
        self.done = True


def total_draws(count):
    """How many draws a route of `count` points takes (the schedule's closed form)."""
    k = 0
    w = Walk([(0, 0)] * count)
    while not w.step():
        k += 1
    return k + 1


# -- the text (globalmap.txt) --------------------------------------------------------------------------------------------------------------

def load_texts(fs):
    """`{tag: text}` of `main\\text\\globalmap.txt` (`#tag` sections, cp1251); the text keeps its trailing CR LF like the exe's section buffer."""
    try:
        raw = decode_text(bytes(fs.read(TEXTS)))
    except (KeyError, OSError):
        return {}
    out, tag, buf = {}, None, []
    for line in raw.splitlines(keepends=True):
        if line.startswith("#"):
            if tag is not None:
                out[tag] = "".join(buf)
            tag, buf = line.strip()[1:], []
        elif tag is not None:
            buf.append(line)
    if tag is not None:
        out[tag] = "".join(buf)
    return out


def tags(loc):
    """`(title tag, body tag)` of a location (town-worldmap 5.4)."""
    kind, n = loc
    return ("title%d" % n, "briefing%d" % n) if kind == MISSION else ("town%d" % n, "description%d" % n)


def title_and_body(texts, loc):
    """The title (the section minus its last 2 characters, the CR LF) and the body (the whole section, CR LF included: the wrapper and the draw handle the end,
    `wrap` / `last_line`); empty strings when missing."""
    t, b = tags(loc)
    return texts.get(t, "")[:-2] if t in texts else "", texts.get(b, "")


# -- the description's wrapper (FUN_0045d479 -> FUN_0045d2b5 -> FUN_0045ccbb) ----------------------------------------------------------------------

def split_paragraphs(text):
    """`FUN_0045d2b5` (CONFIRMED): cut at every CR LF (the LF dropped, the CR kept, both sides left-trimmed); a non-empty rest is the last paragraph."""
    out = []
    while True:
        i = text.find("\r")
        if i < 0 or text[i + 1:i + 2] != "\n":                          # the exe loops forever on a lone CR; the install has none
            break
        out.append(text[:i + 1].lstrip())
        text = text[i + 2:].lstrip()
    if text:
        out.append(text)
    return out


def wrap_paragraph(text, width, measure):
    """`FUN_0045ccbb` (CONFIRMED `0x45ccbb`-`0x45cf8d`).  The text is trimmed; a body that fits (`measure < width`, strictly) gets a CR appended and is the last line; else
    words are added (a word = up to and including its space) while `measure(line) < width` holds, the line being measured **with its trailing space**; the break
    is the last position that fitted (a first word that is too wide stays whole).  Lines keep their trailing space (only the leading side is trimmed);
    the loop body runs once even for an empty paragraph (one line, a lone CR)."""
    s = text.strip()
    lines = []
    while True:
        pos = brk = 0
        line = ""
        if measure(s) < width:
            s += "\r"
            brk = len(s)
        else:
            while True:
                brk = pos
                i = s[pos:].find(" ")
                pos = pos + i + 1 if i >= 0 else len(s)
                line, rest = s[:pos], s[pos:]
                if rest == "" and measure(line) < width:
                    brk = pos
                    break
                if measure(line) >= width:
                    break
        if brk == 0:                                                    # a first word at least as wide as the line stays whole (the exe loops forever when it is exactly as wide)
            brk = pos
        lines.append(s[:brk].lstrip())
        s = s[brk:].lstrip()
        if not s:
            return lines


def wrap(text, width, measure):
    """`FUN_0045d479`: the description's lines (the last line of a paragraph ends in a CR)."""
    return [ln for p in split_paragraphs(text) for ln in wrap_paragraph(p, width, measure)]


def draw_lines(lines):
    """What the draw (`0x4705e4`-`0x470698`) paints: every line but the last as it is, the last without its **last two characters** (the exe assumes the CR LF of a
    section there; the wrapper has already replaced it by one CR, so a real character is lost too: CONFIRMED by the code, VERIFY IN GAME); CRs are not drawn."""
    out = [ln.replace("\r", "") for ln in lines[:-1]]
    if lines:
        out.append(lines[-1][:-2].replace("\r", ""))
    return out


# -- the data the screen reads (one object per shell) ---------------------------------------------------------------------------------------

class StraightPaths:
    """Stand-in graph without the path bitmaps (synthetic tests, an install without them): the route is the straight line, one point per pixel."""

    def route(self, a, b):
        n = max(2, int(max(abs(a[0] - b[0]), abs(a[1] - b[1]))) + 1)
        return [(round(a[0] + (b[0] - a[0]) * i / (n - 1)), round(a[1] + (b[1] - a[1]) * i / (n - 1))) for i in range(n)] if a != b else [a, b]


class WorldData:
    """The install's side of the map: location points, the two path graphs (built on first use), the texts.  Locations that are not in `Scenario.dll` (synthetic
    campaigns) get a fixed pseudo-random point so the screen still has something to show."""

    def __init__(self, locations=None, fs=None, texts=None):
        self.locations = dict(locations or {})
        self.fs = fs
        self._texts = texts
        self._graphs = {}

    @classmethod
    def load(cls, fs, install=None):
        return cls(load_locations(install), fs)

    def point(self, loc):
        p = self.locations.get(loc)
        if p is None:
            kind, n = loc
            p = self.locations[loc] = (40 + (kind * 7 + n * 37) % 560, 60 + (n * 53 + kind * 11) % 380)
        return p

    def graph(self, intro=False):
        key = bool(intro)
        if key not in self._graphs:
            try:
                self._graphs[key] = PathGraph.load(self.fs, key)
            except Exception:                                   # noqa: BLE001  no install / no bitmap: straight lines
                self._graphs[key] = StraightPaths()
        return self._graphs[key]

    def route(self, a, b, intro=False):
        return self.graph(intro).route(a, b)

    def sound_ms(self, path):
        """The length of a sound file in ms (0 without a file system: the sound then counts as finished at once)."""
        if self.fs is None:
            return 0
        try:
            from allods2.formats import sound
            return int(sound.load(path, self.fs).duration * 1000)
        except Exception:                                       # noqa: BLE001
            return 0

    @property
    def texts(self):
        if self._texts is None:
            self._texts = load_texts(self.fs) if self.fs is not None else {}
        return self._texts
