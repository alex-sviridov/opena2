/* Optional C port of the sparse framebuffer blends of engine/backend_pygame/sprites.py (`frame_shadow`, `frame_half`).
 *
 * The numpy code is the reference: this file must give bit-identical frames.  Loaded with ctypes by engine/native/__init__.py;
 * plain C99, no Python headers.
 *
 * A sparse entry is its covered pixels as int32 columns `xs` and rows `ys` inside the box of the sprite (the box starts `dx`
 * left of the sprite; the caller passes x + dx), with the packed source words `vals` for the half overlay.  The framebuffer is
 * `fh` rows of `fw` words, bytes R, G, B, X (pygame "RGBX").  Every write is limited to the frame and to the clip box
 * (cx0, cy0, cx1, cy1) (the caller passes the frame box for "no clip").
 */

#include <stdint.h>

#define A2_BLEND_VERSION 1

int a2_blend_version(void) { return A2_BLEND_VERSION; }

/* Shadow: R, G, B bytes through `lut` (256 entries: v * (16 - level) >> 4); the X byte is left alone. */
void a2_shadow(uint8_t *fb, int fw, int fh, const int32_t *xs, const int32_t *ys, int n, int x, int y, const uint8_t *lut,
               int cx0, int cy0, int cx1, int cy1)
{
    if (cx0 < 0) cx0 = 0;
    if (cy0 < 0) cy0 = 0;
    if (cx1 > fw) cx1 = fw;
    if (cy1 > fh) cy1 = fh;
    for (int i = 0; i < n; i++) {
        int X = xs[i] + x, Y = ys[i] + y;
        if (X < cx0 || X >= cx1 || Y < cy0 || Y >= cy1)
            continue;
        uint8_t *p = fb + ((int64_t)Y * fw + X) * 4;
        p[0] = lut[p[0]];
        p[1] = lut[p[1]];
        p[2] = lut[p[2]];
    }
}

/* Half overlay: dst = vals + ((dst >> 1) & 0x007F7F7F) per word; `vals` is already halved so the fields add without carries. */
void a2_half(uint32_t *fb, int fw, int fh, const int32_t *xs, const int32_t *ys, const uint32_t *vals, int n, int x, int y,
             int cx0, int cy0, int cx1, int cy1)
{
    if (cx0 < 0) cx0 = 0;
    if (cy0 < 0) cy0 = 0;
    if (cx1 > fw) cx1 = fw;
    if (cy1 > fh) cy1 = fh;
    for (int i = 0; i < n; i++) {
        int X = xs[i] + x, Y = ys[i] + y;
        if (X < cx0 || X >= cx1 || Y < cy0 || Y >= cy1)
            continue;
        uint32_t *p = fb + (int64_t)Y * fw + X;
        *p = vals[i] + ((*p >> 1) & 0x007F7F7Fu);
    }
}
