/* Optional C port of the static / hop path planner of engine/sim/pathfinding.py (`_plan`).
 *
 * Spec: docs/engine/simulation.md section 7 (7.5 for the accelerator).  The pure-Python planner is the
 * reference: this file must give bit-identical results (field, labelling order, levels, route, end cell).
 * Loaded with ctypes by engine/native/__init__.py; no Python headers, plain C99.
 *
 * Grids are flat 256 x 256 (index y * 256 + x).  Labels are 16-bit and every index / label sum is taken
 * modulo 0x10000 as in the exe (FUN_0054d76e and the expanders FUN_0055d010 / FUN_0055c6f0).
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define GRID 256
#define CELLS (GRID * GRID)
#define UNSEEN 0xFFFFu
#define MAX_STEPS 1000

#define A2_PLANNER_VERSION 1

/* status codes written to out[2] */
#define ST_FOUND 0
#define ST_FALLBACK 1
#define ST_UNREACHABLE 2
#define ST_TOO_LONG 3
#define ST_NEED_FOLLOW 4        /* the target stayed unlabelled; the caller runs the follow fallback */
#define ST_NOMEM 5

/* ORDER_SIZE1: diagonals first (FUN_0055d010); ORDER_SIZED / ORDER_WALK: dx outer, dy inner, self included. */
static const int ORD1[8][2] = {{-1, -1}, {1, -1}, {-1, 1}, {1, 1}, {0, -1}, {-1, 0}, {1, 0}, {0, 1}};
static const int ORDS[9][2] = {{-1, -1}, {-1, 0}, {-1, 1}, {0, -1}, {0, 0}, {0, 1}, {1, -1}, {1, 0}, {1, 1}};

int a2_planner_version(void) { return A2_PLANNER_VERSION; }

/* FUN_0055c440: the size x size footprint with top-left (x, y) lies in the grid and is free. */
static int footprint_free(const uint8_t *blocked, int x, int y, int size)
{
    if (x < 0 || y < 0 || x + size > GRID || y + size > GRID)
        return 0;
    for (int j = 0; j < size; j++) {
        const uint8_t *row = blocked + (y + j) * GRID + x;
        for (int i = 0; i < size; i++)
            if (row[i])
                return 0;
    }
    return 1;
}

typedef struct {
    int32_t *v;
    size_t n, cap;
} vec;

static int push(vec *a, int32_t x)
{
    if (a->n == a->cap) {
        size_t cap = a->cap ? a->cap * 2 : 4096;
        int32_t *p = (int32_t *)realloc(a->v, cap * sizeof(int32_t));
        if (!p)
            return 0;
        a->v = p;
        a->cap = cap;
    }
    a->v[a->n++] = x;
    return 1;
}

/* The wave fill (`_wave_ref` / `_wave`).  `fld` receives the label field (UNSEEN = unlabelled), `searched`
 * the cells in the order they were first labelled (at most CELLS).  Returns the levels run, or -1 when out
 * of memory. */
static int wave(const uint8_t *blocked, const uint8_t *cost, int size, int sidx, int tidx, int limit,
                uint16_t *fld, int32_t *searched, int32_t *nsearched)
{
    int sized = size > 1;
    const int (*ord)[2] = sized ? ORDS : ORD1;
    int nord = sized ? 9 : 8;
    int delta[9], straight[9];
    for (int k = 0; k < nord; k++) {
        delta[k] = ord[k][1] * GRID + ord[k][0];
        straight[k] = ord[k][0] == 0 || ord[k][1] == 0;
    }
    for (int i = 0; i < CELLS; i++)
        fld[i] = (uint16_t)UNSEEN;
    /* label a cell was last expanded with: expanding it again with the same label is a provable no-op */
    int32_t *last = (int32_t *)malloc(CELLS * sizeof(int32_t));
    if (!last)
        return -1;
    for (int i = 0; i < CELLS; i++)
        last[i] = -1;
    fld[sidx] = 0;
    int32_t ns = 0;
    searched[ns++] = sidx;
    vec fr = {0}, nx = {0};
    int ok = push(&fr, sidx);
    int it = 0;
    while (ok && fld[tidx] == UNSEEN && fr.n > 0 && it < limit) {
        for (int half = 0; half < 2 && ok; half++) {       /* half step A -> B, then B -> A */
            nx.n = 0;
            for (size_t f = 0; f < fr.n && ok; f++) {
                int c = fr.v[f];
                unsigned cur = fld[c];
                if (last[c] == (int32_t)cur)
                    continue;
                last[c] = (int32_t)cur;
                int cx = c & 255, cy = c >> 8;
                for (int k = 0; k < nord; k++) {
                    int n = (c + delta[k]) & 0xFFFF;
                    if (sized) {
                        if (!footprint_free(blocked, cx + ord[k][0], cy + ord[k][1], size))
                            continue;
                    } else if (blocked[n]) {
                        continue;
                    }
                    unsigned step;
                    if (cost) {
                        unsigned kc = cost[n];
                        step = straight[k] ? kc : kc + (kc >> 1);
                    } else {
                        step = straight[k] ? 2u : 3u;
                    }
                    unsigned nw = (cur + step) & 0xFFFFu;
                    unsigned old = fld[n];
                    if (nw < old) {
                        if (old == UNSEEN)
                            searched[ns++] = n;
                        fld[n] = (uint16_t)nw;
                        if (!push(&nx, n)) {
                            ok = 0;
                            break;
                        }
                    }
                }
            }
            vec t = fr;
            fr = nx;
            nx = t;
        }
        it += 2;
    }
    free(fr.v);
    free(nx.v);
    free(last);
    *nsearched = ns;
    return ok ? it : -1;
}

/* FUN_0054e58c / FUN_0054e886 (`_walk_back`): `route` receives the cells from the first step to the end cell
 * (indices).  Returns their count, or -1 when the walk exceeds MAX_STEPS. */
int a2_walk_back(const uint16_t *fld, const uint8_t *cost, int walker_cost, int sx, int sy, int ex, int ey,
                 int32_t *route)
{
    int32_t buf[MAX_STEPS + 1];
    int n = 0, steps = 0;
    int cx = ex, cy = ey;
    buf[n++] = cy * GRID + cx;
    while (cx != sx || cy != sy) {
        steps++;
        if (steps > MAX_STEPS)
            return -1;
        unsigned best = UNSEEN;
        int px = 0, py = 0;
        int c = cy * GRID + cx;
        for (int k = 0; k < 9; k++) {
            int dx = ORDS[k][0], dy = ORDS[k][1];
            int nx = cx + dx, ny = cy + dy;
            if (!(8 <= nx && nx <= GRID - 8 && 8 <= ny && ny <= GRID - 8))
                continue;
            unsigned v = fld[ny * GRID + nx];
            if (v == UNSEEN)
                continue;
            if (dx == 0 || dy == 0) {
                unsigned cand = (v + (walker_cost ? (unsigned)cost[c] : 2u)) & 0xFFFFu;
                if (cand <= best) {
                    best = cand;
                    px = dx;
                    py = dy;
                }
            } else {
                unsigned kc = walker_cost ? (unsigned)cost[c] : 0u;
                unsigned cand = (v + (walker_cost ? kc + (kc >> 1) : 3u)) & 0xFFFFu;
                if (cand < best) {
                    best = cand;
                    px = dx;
                    py = dy;
                }
            }
        }
        cx += px;
        cy += py;
        buf[n++] = cy * GRID + cx;
    }
    /* buf = end ... start; the route is start excluded, first step ... end */
    for (int i = 0; i < n - 1; i++)
        route[i] = buf[n - 2 - i];
    return n - 1;
}

/* FUN_005585f4 (`_nearest_reached`): packed index of the cheapest labelled cell of the first ring around
 * the target that has one, or -1. */
static int nearest_reached(const uint16_t *fld, int tx, int ty, int radius)
{
    int t = (ty << 8) + tx;
    unsigned best = UNSEEN;
    int found = -1;
    for (int r = 1; r < radius; r++) {
        for (int o = -r; o <= r; o++) {
            int idxs[4] = {(r << 8) + t + o, (-r) * 256 + t + o, o * 256 + t + r, o * 256 + t - r};
            for (int q = 0; q < 4; q++) {
                int idx = (int)((unsigned)idxs[q] & 0xFFFFu);
                if (fld[idx] < best) {
                    best = fld[idx];
                    found = idx;
                }
            }
        }
        if (best < UNSEEN)
            break;
    }
    return found;
}

/* The whole plan after the prelude of `_plan` (limit, order and cost chosen by the caller).
 *   cost: terrain costs when the mover is a walker on a grid with costs, else NULL (2 / 3 apply).
 *   follow: 1 = stop with ST_NEED_FOLLOW when the target stays unlabelled (the caller runs follow_fallback
 *           on `fld` and calls a2_walk_back), 0 = the ring scan with `radius`.
 *   out[0] = searched count, out[1] = levels, out[2] = status, out[3] = end index (-1 none), out[4] = route
 *   length.  fld: CELLS uint16; searched: CELLS int32; route: MAX_STEPS + 1 int32. */
int a2_plan(const uint8_t *blocked, const uint8_t *cost, int sx, int sy, int tx, int ty, int size, int limit,
            int radius, int follow, uint16_t *fld, int32_t *searched, int32_t *route, int32_t *out)
{
    int sidx = sy * GRID + sx, tidx = ty * GRID + tx;
    int32_t ns = 0;
    out[0] = out[1] = out[4] = 0;
    out[3] = -1;
    int levels = wave(blocked, cost, size, sidx, tidx, limit, fld, searched, &ns);
    if (levels < 0) {
        out[2] = ST_NOMEM;
        return ST_NOMEM;
    }
    out[0] = ns;
    out[1] = levels;
    int end = tidx, status = ST_FOUND;
    if (fld[tidx] == UNSEEN) {
        if (follow) {
            out[2] = ST_NEED_FOLLOW;
            return ST_NEED_FOLLOW;
        }
        end = nearest_reached(fld, tx, ty, radius);
        if (end < 0) {
            out[2] = ST_UNREACHABLE;
            return ST_UNREACHABLE;
        }
        status = ST_FALLBACK;
    }
    out[3] = end;
    int n = a2_walk_back(fld, cost, cost != NULL, sx, sy, end & 255, end >> 8, route);
    if (n < 0) {
        out[2] = ST_TOO_LONG;
        return ST_TOO_LONG;
    }
    out[4] = n;
    out[2] = status;
    return status;
}
