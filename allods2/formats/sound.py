"""Sound and music files: RIFF/WAVE, PCM 16-bit or Microsoft ADPCM (tag 2).

    snd = load("sfx/add.wav", fs)      # game path, or bytes / disk path
    snd.samples                        # int16 array, shape (frames, channels)
    open("x.wav", "wb").write(snd.to_wav())

Spec: docs/formats/sound.md.  numpy only; no audio backend.
"""

import dataclasses
import struct

import numpy as np

WAVE_PCM = 1
WAVE_MSADPCM = 2

# Microsoft ADPCM tables (the standard ones; the files carry the same 7 pairs).
ADAPT = (230, 230, 230, 230, 307, 409, 512, 614, 768, 614, 512, 409, 307, 230, 230, 230)


class SoundError(ValueError):
    pass


@dataclasses.dataclass
class Sound:
    sample_rate: int
    channels: int
    bits: int                      # of the decoded samples (always 16)
    samples: np.ndarray            # int16, (frames, channels)
    tag: int = WAVE_PCM            # source wFormatTag
    extra: dict = dataclasses.field(default_factory=dict)   # chunk ids -> bytes (LIST, ...)

    @property
    def frames(self):
        return self.samples.shape[0]

    @property
    def duration(self):
        return self.frames / self.sample_rate

    def pcm_bytes(self):
        return self.samples.astype("<i2").tobytes()

    def to_wav(self):
        """Standard 16-bit PCM WAV bytes."""
        data = self.pcm_bytes()
        ba = self.channels * 2
        fmt = struct.pack("<HHIIHH", WAVE_PCM, self.channels, self.sample_rate,
                          self.sample_rate * ba, ba, 16)
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        body += b"data" + struct.pack("<I", len(data)) + data + b"\0" * (len(data) & 1)
        return b"RIFF" + struct.pack("<I", len(body)) + body


def parse_chunks(b):
    """[(id, offset, size)] of every chunk; checks that the RIFF accounts for
    the whole file (no leftover bytes)."""
    if len(b) < 12 or b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise SoundError("not a RIFF/WAVE file")
    riff = struct.unpack_from("<I", b, 4)[0]
    if riff + 8 != len(b):
        raise SoundError("RIFF size %d does not match file size %d" % (riff + 8, len(b)))
    out, i = [], 12
    while i < len(b):
        if i + 8 > len(b):
            raise SoundError("%d leftover bytes after the last chunk" % (len(b) - i))
        t, s = struct.unpack_from("<4sI", b, i)
        if i + 8 + s > len(b):
            raise SoundError("chunk %r runs past the end of the file" % t)
        out.append((t, i + 8, s))
        i += 8 + s + (s & 1)
    return out


def _decode_msadpcm(blob, channels, block_align, spb, coefs, total):
    """Vectorised over blocks: every block starts with predictors, deltas and
    two raw samples per channel, then 4-bit codes (high nibble first,
    channels interleaved)."""
    hdr = 7 * channels
    nfull, rem = divmod(len(blob), block_align)
    blocks = [np.frombuffer(blob, np.uint8, block_align, k * block_align) for k in range(nfull)]
    last_spb = 0
    if rem:
        if rem < hdr:
            raise SoundError("final block of %d bytes is shorter than its header" % rem)
        blocks.append(np.frombuffer(blob, np.uint8, rem, nfull * block_align))
        last_spb = 2 + (rem - hdr) * 2 // channels
    out = np.zeros((len(blocks), spb, channels), np.int64)
    coef = np.array(coefs, np.int64)
    adapt = np.array(ADAPT, np.int64)

    def run(idx, nsamp, size):
        if not len(idx):
            return
        m = np.stack([blocks[i][:size] for i in idx]).astype(np.int64)
        pred = m[:, :channels]
        if (pred >= len(coef)).any():
            raise SoundError("predictor index out of range")
        raw = m[:, channels:hdr].copy()
        h = lambda off: (raw[:, off:off + 2 * channels:2] | (raw[:, off + 1:off + 2 * channels:2] << 8))
        s16 = lambda a: np.where(a >= 32768, a - 65536, a)
        delta = h(0)
        s1 = s16(h(2 * channels))
        s2 = s16(h(4 * channels))
        c1 = coef[pred, 0]
        c2 = coef[pred, 1]
        res = np.zeros((len(idx), nsamp, channels), np.int64)
        res[:, 0] = s2
        res[:, 1] = s1
        codes = m[:, hdr:]
        nib = np.empty((len(idx), codes.shape[1] * 2), np.int64)
        nib[:, 0::2] = codes >> 4
        nib[:, 1::2] = codes & 15
        for n in range(2, nsamp):
            for c in range(channels):
                q = nib[:, (n - 2) * channels + c]
                sq = np.where(q >= 8, q - 16, q)
                p = (s1[:, c] * c1[:, c] + s2[:, c] * c2[:, c]) >> 8
                p = np.clip(p + sq * delta[:, c], -32768, 32767)
                res[:, n, c] = p
                s2[:, c] = s1[:, c]
                s1[:, c] = p
                delta[:, c] = np.maximum((adapt[q] * delta[:, c]) >> 8, 16)
        out[idx, :nsamp] = res

    run(range(nfull), spb, block_align)
    if rem:
        run([nfull], last_spb, rem)
    frames = np.concatenate([out[:nfull].reshape(-1, channels),
                             out[nfull, :last_spb] if rem else out[:0, 0]])
    if total is not None:
        # fact = the true length: it trims a padded final block (52 files) and
        # is one frame longer than a partial final block can hold in ~500
        # files (the encoder counts the padding nibble); anything else is bad.
        if total < len(frames) and len(frames) - total < spb:
            frames = frames[:total]
        elif total - len(frames) not in (0, 1):
            raise SoundError("fact says %d frames, decoded %d" % (total, len(frames)))
    return frames.astype(np.int16)


def decode(b):
    """Decode RIFF/WAVE bytes to a Sound."""
    b = bytes(b)
    ch = parse_chunks(b)
    by = {}
    for t, o, s in ch:
        by.setdefault(t, (o, s))
    if b"fmt " not in by or b"data" not in by:
        raise SoundError("missing fmt or data chunk")
    o, s = by[b"fmt "]
    if s < 16:
        raise SoundError("fmt chunk too short")
    tag, channels, rate, _bps, align, bits = struct.unpack_from("<HHIIHH", b, o)
    do, ds = by[b"data"]
    data = b[do:do + ds]
    extra = {t.decode("latin1"): b[o2:o2 + s2] for t, o2, s2 in ch if t not in (b"fmt ", b"data", b"fact")}
    total = struct.unpack_from("<I", b, by[b"fact"][0])[0] if b"fact" in by else None
    if tag == WAVE_PCM:
        if bits != 16:
            raise SoundError("only 16-bit PCM is used by the game, got %d" % bits)
        if align != channels * 2 or len(data) % align:
            raise SoundError("PCM data is not a whole number of frames")
        pcm = np.frombuffer(data, "<i2").astype(np.int16).reshape(-1, channels)
    elif tag == WAVE_MSADPCM:
        if bits != 4 or s < 22:
            raise SoundError("bad MS ADPCM fmt chunk")
        spb, ncoef = struct.unpack_from("<HH", b, o + 18)
        if s < 22 + 4 * ncoef:
            raise SoundError("fmt chunk too short for %d coefficients" % ncoef)
        coefs = struct.unpack_from("<%dh" % (2 * ncoef), b, o + 22)
        coefs = list(zip(coefs[0::2], coefs[1::2]))
        pcm = _decode_msadpcm(data, channels, align, spb, coefs, total)
    else:
        raise SoundError("unsupported wFormatTag %d" % tag)
    return Sound(rate, channels, 16, pcm, tag, extra)


def load(source, fs=None):
    """load(game path, fs) | load(disk path) | load(bytes)."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return decode(source)
    if fs is not None:
        return decode(fs.read(source))
    with open(source, "rb") as f:
        return decode(f.read())
