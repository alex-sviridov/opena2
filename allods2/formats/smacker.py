"""Smacker 2 video (`.smk`, `SMK2`): header, palette, 8-bit frames, the audio track.

    v = load("video/intro/01.smk", fs)          # game path, bytes or a disk path
    v.width, v.height, v.frames, v.fps          # 640, 360, 773, 15.0
    for f in v.decode():                        # Frame: .index, .pixels (h, w) uint8, .palette (256, 3) uint8, .audio (n, 2) int16 | None
        ...

Spec: docs/engine/cutscenes.md 2.  numpy only.  The bit stream is read LSB first; the video is 4x4 blocks (mono / full / skip / fill with
run lengths) coded by four Huffman trees (type, mono map, mono colours, full) whose 16-bit leaves are built from two 8-bit trees and a
3-entry recent-value cache (starts at zero each frame; the header values are the escape codes); the audio is delta-coded by up to four Huffman trees per track.  Y-doubling / interlace (flags 2 / 4) and
SMK4 are not used by the install and are refused.
"""

import ctypes
import struct
from dataclasses import dataclass

import numpy as np

from .. import native

SIGNATURE = b"SMK2"
RUNS = tuple(range(1, 60)) + (128, 256, 512, 1024, 2048)        # block run lengths (type >> 2 & 63)
PAL6 = tuple((i << 2) + (i >> 4) for i in range(64))            # a palette byte is 6 bits: 0x00 .. 0xff in steps of 4 (+1 per 16)
MONO, FULL, SKIP, FILL = 0, 1, 2, 3


class SmackerError(ValueError):
    pass


class _Bits:
    """LSB-first bit reader."""

    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos * 8
        self.end = len(data) * 8

    def bit(self):
        p = self.pos
        if p >= self.end:
            raise SmackerError("bit stream overrun")
        self.pos = p + 1
        return (self.data[p >> 3] >> (p & 7)) & 1

    def bits(self, n):
        v = 0
        for i in range(n):
            v |= self.bit() << i
        return v


def _small_tree(b):
    """A tree with 8-bit leaves: a 0 bit is a leaf (8 bits follow), a 1 bit a node (left subtree, right subtree).  Returns nested tuples
    (left, right) with int leaves."""
    if not b.bit():
        return b.bits(8)
    left = _small_tree(b)
    right = _small_tree(b)
    return (left, right)


def _walk(b, tree):
    while isinstance(tree, tuple):
        tree = tree[b.bit()]
    return tree


def _big_tree(b, lo, hi, last):
    """The 16-bit tree: a leaf is read as `lo | hi << 8` through the two small trees; a value equal to a header cache entry is a cache marker."""
    if not b.bit():
        lv = _walk(b, lo) if lo is not None else 0
        hv = _walk(b, hi) if hi is not None else 0
        v = lv | (hv << 8)
        for k in range(3):
            if v == last[k]:
                return ("cache", k)
        return v
    left = _big_tree(b, lo, hi, last)
    right = _big_tree(b, lo, hi, last)
    return (left, right)


class _Tree:
    """One of the four video trees plus its per-frame cache."""

    def __init__(self, b):
        self.root = None
        self.last = [0, 0, 0]
        if not b.bit():
            return                                      # no tree: every code is 0
        lo = _small_tree(b) if b.bit() else None
        b.bit()
        hi = _small_tree(b) if b.bit() else None
        b.bit()
        self.last = [b.bits(16), b.bits(16), b.bits(16)]          # the three "cache" escape values: a leaf equal to last[k] means cache[k]
        self.root = _big_tree(b, lo, hi, self.last)
        b.bit()
        self.cache = [0, 0, 0]

    def reset(self):
        self.cache = [0, 0, 0]

    def code(self, b):
        t = self.root
        if t is None:
            return 0
        while isinstance(t, tuple) and not (len(t) == 2 and t[0] == "cache"):
            t = t[b.bit()]
        c = self.cache
        v = c[t[1]] if isinstance(t, tuple) else t
        if v != c[0]:
            c[2] = c[1]
            c[1] = c[0]
            c[0] = v
        return v


def _flatten(root):
    """The nested tree as the flat int32 node array of `smk.c` (leaf = ~code, cache marker = ~(0x10000 + k)); None for no tree."""
    if root is None:
        return None
    out = []

    def add(t):
        i = len(out)
        out.extend((0, 0))
        for bit in (0, 1):
            c = t[bit]
            if isinstance(c, tuple) and len(c) == 2 and c[0] == "cache":
                out[i + bit] = ~(0x10000 + c[1])
            elif isinstance(c, tuple):
                out[i + bit] = add(c)
            else:
                out[i + bit] = ~c
        return i // 2

    add(root)
    return np.array(out, np.int32)


@dataclass
class Frame:
    index: int
    pixels: np.ndarray                  # (h, w) uint8, palette indices
    palette: np.ndarray                 # (256, 3) uint8
    audio: np.ndarray = None            # (n, 2) int16 interleaved, None when the frame has no audio chunk
    key: bool = False


class Smacker:
    def __init__(self, data):
        self.data = data = bytes(data)
        if data[:4] != SIGNATURE:
            raise SmackerError("not a Smacker 2 file: %r" % data[:4])
        (self.width, self.height, self.frames) = struct.unpack_from("<3I", data, 4)
        self.flags = struct.unpack_from("<I", data, 20)[0]
        rate = struct.unpack_from("<i", data, 16)[0]
        if self.flags & 6:
            raise SmackerError("Y-interlace / Y-double flags are not supported")
        # frame time: > 0 ms, < 0 hundredths of a ms (-6666 = 66.66 ms), 0 = 100 ms
        self.frame_ms = 100.0 if rate == 0 else (rate if rate > 0 else -rate / 100.0)
        self.fps = 1000.0 / self.frame_ms
        self.audio_size = struct.unpack_from("<7I", data, 24)
        self.treesize = struct.unpack_from("<I", data, 52)[0]
        self.audio_rate = struct.unpack_from("<7I", data, 72)
        pos = 104
        n = self.frames + (1 if self.flags & 1 else 0)
        sizes = struct.unpack_from("<%dI" % n, data, pos)
        pos += 4 * n
        self.types = data[pos:pos + n]
        pos += n
        self.sizes = [s & ~3 for s in sizes]
        self.keys = [bool(s & 1) for s in sizes]
        tb = _Bits(data[pos:pos + self.treesize])
        self._trees = [_Tree(tb) for _ in range(4)]       # mmap, mclr, full, type
        self.data_pos = pos + self.treesize
        self._flat = [_flatten(t.root) for t in self._trees]

    @property
    def sample_rate(self):
        """Hz of the first audio track (0 = none)."""
        for r in self.audio_rate:
            if r & 0xFFFFFF:
                return r & 0xFFFFFF
        return 0

    def audio_tracks(self):
        return [i for i in range(7) if self.audio_rate[i] & 0x40000000]   # bit 30: the track exists

    # -- decoding ---------------------------------------------------------------------------------------------------------------
    def decode(self):
        """Yield every `Frame` in order (the picture and the palette persist between frames, as the library's)."""
        w, h = self.width, self.height
        pix = np.zeros((h, w), np.uint8)
        pal = np.zeros((256, 3), np.uint8)
        pos = self.data_pos
        for i in range(self.frames):
            size = self.sizes[i]
            chunk = self.data[pos:pos + size]
            pos += size
            ft = self.types[i]
            p = 0
            if ft & 1:
                n = chunk[0] * 4
                pal = self._palette(chunk[1:n], pal)
                p = n
            audio = None
            for t in range(7):
                if ft & (2 << t):
                    n = struct.unpack_from("<I", chunk, p)[0]
                    a = self._audio(chunk[p + 4:p + n], self.audio_rate[t])
                    if t == 0 or audio is None:
                        audio = a
                    p += n
            self._video(chunk[p:], pix)
            yield Frame(i, pix.copy(), pal.copy(), audio, self.keys[i])

    @staticmethod
    def _palette(buf, old):
        pal = old.copy()
        i = 0
        p = 0
        while i < 256 and p < len(buf):
            c = buf[p]
            p += 1
            if c & 0x80:
                i += (c & 0x7F) + 1
            elif c & 0x40:
                n = (c & 0x3F) + 1
                off = buf[p]
                p += 1
                pal[i:i + n] = old[off:off + n]
                i += n
            else:
                pal[i] = (PAL6[c & 63], PAL6[buf[p] & 63], PAL6[buf[p + 1] & 63])
                p += 2
                i += 1
        return pal

    def _video(self, buf, pix):
        lib = native.smk()
        if lib is not None:
            return self._video_native(lib, buf, pix)
        return self._video_py(buf, pix)

    def _video_native(self, lib, buf, pix):
        cache = np.zeros(12, np.int32)
        ptrs = (ctypes.c_void_p * 4)(*[0 if f is None else f.ctypes.data for f in self._flat])
        data = np.frombuffer(buf, np.uint8) if len(buf) else np.zeros(1, np.uint8)
        if lib.a2_smk_video(data.ctypes.data, len(buf), self.width, self.height, pix.ctypes.data, ctypes.addressof(ptrs), cache.ctypes.data):
            raise SmackerError("bit stream overrun")

    def _video_py(self, buf, pix):
        w, h = self.width, self.height
        bw = w // 4
        blocks = bw * (h // 4)
        b = _Bits(buf)
        mmap, mclr, full, typ = self._trees
        for t in self._trees:
            t.reset()
        blk = 0
        while blk < blocks:
            tv = typ.code(b)
            run = RUNS[(tv >> 2) & 63]
            kind = tv & 3
            while run > 0 and blk < blocks:
                run -= 1
                y0, x0 = (blk // bw) * 4, (blk % bw) * 4
                if kind == MONO:
                    clr = mclr.code(b)
                    m = mmap.code(b)
                    hi_c, lo_c = clr >> 8, clr & 0xFF
                    for r in range(4):
                        for c in range(4):
                            pix[y0 + r, x0 + c] = hi_c if (m >> (r * 4 + c)) & 1 else lo_c
                elif kind == FULL:
                    for r in range(4):
                        v1 = full.code(b)
                        v2 = full.code(b)
                        pix[y0 + r, x0 + 2] = v1 & 0xFF
                        pix[y0 + r, x0 + 3] = v1 >> 8
                        pix[y0 + r, x0] = v2 & 0xFF
                        pix[y0 + r, x0 + 1] = v2 >> 8
                elif kind == FILL:
                    pix[y0:y0 + 4, x0:x0 + 4] = tv >> 8
                blk += 1
        return b.pos

    @staticmethod
    def _audio(buf, rate_word):
        """One track's chunk -> (n, 2) int16 (mono is doubled).  Packed (bit 31): size, flags, up to four trees, predictors, deltas."""
        flags = rate_word >> 24
        packed = bool(flags & 0x80)
        stereo = bool(flags & 0x10)
        bits16 = bool(flags & 0x20)
        if not packed:
            dt = "<i2" if bits16 else "u1"
            a = np.frombuffer(buf, dt)
            a = a if bits16 else ((a.astype(np.int16) - 128) << 8)
            return np.repeat(a.reshape(-1, 1), 2, 1) if not stereo else a.reshape(-1, 2)
        unp = struct.unpack_from("<I", buf, 0)[0]
        b = _Bits(buf, 4)
        if not b.bit():
            return np.zeros((0, 2), np.int16)
        stereo = bool(b.bit())
        bits16 = bool(b.bit())
        ntree = 1 << (int(bits16) + int(stereo))
        trees = []
        for _ in range(ntree):
            trees.append(_small_tree(b) if b.bit() else None)
            b.bit()
        nch = 2 if stereo else 1
        step = 2 if bits16 else 1
        count = unp // step
        out = np.zeros(count, np.int16 if bits16 else np.uint8)
        pred = [0, 0]
        if bits16:
            for i in range(nch - 1, -1, -1):
                pred[i] = b.bits(16)
        else:
            for i in range(nch - 1, -1, -1):
                pred[i] = b.bits(8)
        k = 0
        for ch in range(nch):
            out[k] = np.int16(np.uint16(pred[ch])) if bits16 else pred[ch]
            k += 1
        while k < count:
            ch = k % nch if stereo else 0
            base = ch * (2 if bits16 else 1)
            lo = _walk(b, trees[base]) if trees[base] is not None else 0
            if bits16:
                hi = _walk(b, trees[base + 1]) if trees[base + 1] is not None else 0
                d = lo | (hi << 8)
                pred[ch] = (pred[ch] + d) & 0xFFFF
                out[k] = np.int16(np.uint16(pred[ch]))
            else:
                pred[ch] = (pred[ch] + lo) & 0xFF
                out[k] = pred[ch]
            k += 1
        if not bits16:
            out = (out.astype(np.int16) - 128) << 8
        return np.repeat(out.reshape(-1, 1), 2, 1) if not stereo else out.reshape(-1, 2)


def load(src, fs=None):
    """`src`: a game path (needs `fs`), bytes or a disk path."""
    if isinstance(src, (bytes, bytearray, memoryview)):
        return Smacker(src)
    if fs is not None and fs.exists(src):
        return Smacker(fs.read(src))
    with open(src, "rb") as f:
        return Smacker(f.read())
