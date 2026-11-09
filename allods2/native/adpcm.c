/* Optional C port of the MS ADPCM decoder of allods2/formats/sound.py (`_decode_msadpcm`).
 *
 * The numpy code is the reference: this file must give bit-identical samples.  Loaded with ctypes by allods2/native;
 * plain C99.  Blocks: per channel predictor u8, then delta i16, sample1 i16, sample2 i16 (each channel after channel), then
 * 4-bit codes, high nibble first, channels interleaved.  64-bit arithmetic like the reference (delta is unbounded).
 */

#include <stdint.h>
#include <stddef.h>

#define A2_ADPCM_VERSION 1

int a2_adpcm_version(void) { return A2_ADPCM_VERSION; }

static const int ADAPT[16] = {230, 230, 230, 230, 307, 409, 512, 614, 768, 614, 512, 409, 307, 230, 230, 230};

/* Decodes one block of `size` bytes into out (frames x channels); returns the frame count or -1 (bad predictor). */
static int block(const uint8_t *b, int size, int channels, int nsamp_max, const int16_t *coef, int ncoef, int16_t *out)
{
    int hdr = 7 * channels;
    int64_t delta[8], s1[8], s2[8];
    int c1[8], c2[8];
    int nframes = 2 + (size - hdr) * 2 / channels;
    if (nframes > nsamp_max)
        nframes = nsamp_max;
    for (int c = 0; c < channels; c++) {
        int pred = b[c];
        if (pred >= ncoef)
            return -1;
        c1[c] = coef[pred * 2];
        c2[c] = coef[pred * 2 + 1];
        const uint8_t *q = b + channels + 2 * c;
        delta[c] = (int16_t)(q[0] | (q[1] << 8));
        q = b + channels + 2 * channels + 2 * c;
        s1[c] = (int16_t)(q[0] | (q[1] << 8));
        q = b + channels + 4 * channels + 2 * c;
        s2[c] = (int16_t)(q[0] | (q[1] << 8));
        out[c] = (int16_t)s2[c];
        out[channels + c] = (int16_t)s1[c];
    }
    const uint8_t *codes = b + hdr;
    for (int n = 2; n < nframes; n++) {
        for (int c = 0; c < channels; c++) {
            int idx = (n - 2) * channels + c;
            int q = (idx & 1) ? (codes[idx >> 1] & 15) : (codes[idx >> 1] >> 4);
            int sq = q >= 8 ? q - 16 : q;
            int64_t p = (s1[c] * c1[c] + s2[c] * c2[c]) >> 8;
            p += sq * delta[c];
            if (p > 32767) p = 32767;
            if (p < -32768) p = -32768;
            out[n * channels + c] = (int16_t)p;
            s2[c] = s1[c];
            s1[c] = p;
            int64_t d = (ADAPT[q] * delta[c]) >> 8;
            delta[c] = d < 16 ? 16 : d;
        }
    }
    return nframes;
}

/* Whole data chunk: full blocks of `align` bytes (`spb` frames) and a short final block.  Returns the frames written
 * (<= cap) or -1 bad predictor, -2 final block shorter than its header, -3 cap too small, -4 `spb` larger than a block holds. */
int64_t a2_msadpcm(const uint8_t *data, int64_t len, int channels, int align, int spb, const int16_t *coef, int ncoef,
                   int16_t *out, int64_t cap)
{
    if (channels < 1 || channels > 8)
        return -1;
    int64_t pos = 0, frames = 0;
    int hdr = 7 * channels;
    while (pos < len) {
        int size = (len - pos >= align) ? align : (int)(len - pos);
        if (size < hdr)
            return -2;
        int want = (size == align) ? spb : 2 + (size - hdr) * 2 / channels;
        if (frames + want > cap)
            return -3;
        int n = block(data + pos, size, channels, want, coef, ncoef, out + frames * channels);
        if (n < 0)
            return n;
        if (n < want)
            return -4;
        frames += n;
        pos += size;
    }
    return frames;
}
