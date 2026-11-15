/* Optional C port of the Smacker 2 video block loop of allods2/formats/smacker.py (`Smacker._video`).
 *
 * The Python code is the reference: this file must give bit-identical pictures.  Loaded with ctypes by allods2/native; plain C99.
 * A tree is a flat int32 array of node pairs: entry 2 * n + bit is a node index (>= 0) or a leaf `~code` (< 0), code = the 16-bit
 * value, or 0x10000 + k for "cache entry k".  `cache` is the 3-entry recent-value list of each of the four trees (mmap, mclr, full,
 * type), already reset to the header values by the caller.  Returns 0, or -1 when the bit stream runs out.
 */

#include <stdint.h>
#include <stddef.h>

#define A2_SMK_VERSION 1

int a2_smk_version(void) { return A2_SMK_VERSION; }

typedef struct {
    const uint8_t *d;
    size_t pos, end;            /* bit positions */
    int bad;
} bits_t;

static inline int getbit(bits_t *b)
{
    if (b->pos >= b->end) {
        b->bad = 1;
        return 0;
    }
    int v = (b->d[b->pos >> 3] >> (b->pos & 7)) & 1;
    b->pos++;
    return v;
}

static inline int code(bits_t *b, const int32_t *tree, int32_t *cache)
{
    int n = 0, v;
    if (!tree)
        return 0;
    for (;;) {
        int e = tree[2 * n + getbit(b)];
        if (b->bad)
            return 0;
        if (e >= 0) {
            n = e;
            continue;
        }
        v = ~e;
        break;
    }
    if (v >= 0x10000)
        v = cache[v - 0x10000];
    if (v != cache[0]) {
        cache[2] = cache[1];
        cache[1] = cache[0];
        cache[0] = v;
    }
    return v;
}

int a2_smk_video(const uint8_t *buf, size_t len, int w, int h, uint8_t *pix, const int32_t *const *trees, int32_t *cache)
{
    static const int runs[64] = {1,  2,  3,  4,  5,  6,  7,  8,  9,  10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22,
                                 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
                                 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 128, 256, 512, 1024, 2048};
    bits_t b = {buf, 0, len * 8, 0};
    int bw = w / 4, blocks = bw * (h / 4), blk = 0;
    while (blk < blocks) {
        int tv = code(&b, trees[3], cache + 9);
        int run = runs[(tv >> 2) & 63], kind = tv & 3;
        if (b.bad)
            return -1;
        while (run-- > 0 && blk < blocks) {
            uint8_t *o = pix + (size_t)(blk / bw) * 4 * w + (size_t)(blk % bw) * 4;
            if (kind == 0) {
                int clr = code(&b, trees[1], cache + 3), m = code(&b, trees[0], cache);
                uint8_t hi = (uint8_t)(clr >> 8), lo = (uint8_t)clr;
                for (int r = 0; r < 4; r++, o += w, m >>= 4) {
                    o[0] = (m & 1) ? hi : lo;
                    o[1] = (m & 2) ? hi : lo;
                    o[2] = (m & 4) ? hi : lo;
                    o[3] = (m & 8) ? hi : lo;
                }
            } else if (kind == 1) {
                for (int r = 0; r < 4; r++, o += w) {
                    int v1 = code(&b, trees[2], cache + 6), v2 = code(&b, trees[2], cache + 6);
                    o[2] = (uint8_t)v1;
                    o[3] = (uint8_t)(v1 >> 8);
                    o[0] = (uint8_t)v2;
                    o[1] = (uint8_t)(v2 >> 8);
                }
            } else if (kind == 3) {
                uint8_t c = (uint8_t)(tv >> 8);
                for (int r = 0; r < 4; r++, o += w)
                    o[0] = o[1] = o[2] = o[3] = c;
            }
            if (b.bad)
                return -1;
            blk++;
        }
    }
    return 0;
}
