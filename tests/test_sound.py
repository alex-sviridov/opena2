"""Sound files (docs/formats/sound.md): synthetic cases always run, install
cases skip without the game files."""

import hashlib
import json
import os
import struct

import numpy as np
import pytest

from allods2.formats import sound as S
from allods2.formats import soundtable as T
from helpers import GFS, needs

# the published Microsoft ADPCM adaptation table, typed independently of the decoder
ADAPT = (230, 230, 230, 230, 307, 409, 512, 614, 768, 614, 512, 409, 307, 230, 230, 230)
STD_COEF = [(256, 0), (512, -256), (0, 0), (192, 64), (240, 0), (460, -208), (392, -232)]


def riff(*chunks):
    body = b"WAVE" + b"".join(t + struct.pack("<I", len(d)) + d + b"\0" * (len(d) & 1) for t, d in chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm_fmt(ch=1, rate=22050):
    return b"fmt ", struct.pack("<HHIIHH", 1, ch, rate, rate * ch * 2, ch * 2, 16)


def adpcm_fmt(ch=1, rate=22050, align=512, spb=1012):
    d = struct.pack("<HHIIHHHHH", 2, ch, rate, rate * align // spb, align, 4, 32, spb, 7)
    return b"fmt ", d + b"".join(struct.pack("<hh", *c) for c in STD_COEF)


def ref_adpcm(block, channels=1, nsamp=None):
    """Scalar reference of one MS ADPCM block (from the published algorithm)."""
    adapt = ADAPT
    hdr = 7 * channels
    pred = list(block[:channels])
    delta = [struct.unpack_from("<h", block, channels + 2 * c)[0] for c in range(channels)]
    s1 = [struct.unpack_from("<h", block, channels + 2 * channels + 2 * c)[0] for c in range(channels)]
    s2 = [struct.unpack_from("<h", block, channels + 4 * channels + 2 * c)[0] for c in range(channels)]
    out = [list(s2), list(s1)]
    nib = []
    for byte in block[hdr:]:
        nib += [byte >> 4, byte & 15]
    n = 0
    for _ in range(((len(nib)) // channels)):
        row = []
        for c in range(channels):
            q = nib[n]; n += 1
            sq = q - 16 if q >= 8 else q
            c1, c2 = STD_COEF[pred[c]]
            p = (s1[c] * c1 + s2[c] * c2) >> 8
            p = max(-32768, min(32767, p + sq * delta[c]))
            s2[c], s1[c] = s1[c], p
            delta[c] = max((adapt[q] * delta[c]) >> 8, 16)
            row.append(p)
        out.append(row)
    return np.array(out, np.int16)


def test_pcm_roundtrip():
    pcm = np.array([0, 1, -1, 32767, -32768, 1000], "<i2")
    snd = S.load(riff(pcm_fmt(), (b"data", pcm.tobytes())))
    assert (snd.sample_rate, snd.channels, snd.bits, snd.frames) == (22050, 1, 16, 6)
    assert snd.samples[:, 0].tolist() == pcm.tolist()
    again = S.load(snd.to_wav())
    assert again.samples.tolist() == snd.samples.tolist()
    assert snd.duration == pytest.approx(6 / 22050)


def test_pcm_stereo_and_extra_chunks():
    pcm = np.arange(8, dtype="<i2")
    snd = S.load(riff(pcm_fmt(2, 44100), (b"data", pcm.tobytes()), (b"LIST", b"abc")))
    assert snd.samples.shape == (4, 2) and snd.samples[1].tolist() == [2, 3]
    assert snd.extra["LIST"] == b"abc"


def test_adpcm_block_matches_reference():
    rng = np.random.default_rng(1)
    hdr = bytes([3]) + struct.pack("<hhh", 20, 100, -50)
    # mostly small codes like real data (random nibbles let delta outgrow int32)
    codes = rng.choice([0x00, 0x11, 0x0F, 0xF0, 0x01, 0x10, 0x22, 0xEE, 0x13, 0xFE], 512 - len(hdr))
    block = hdr + bytes(codes.astype(np.uint8))
    wav = riff(adpcm_fmt(), (b"fact", struct.pack("<I", 1012)), (b"data", block))
    snd = S.load(wav)
    assert snd.frames == 1012
    assert snd.samples[:, 0].tolist() == ref_adpcm(block)[:, 0].tolist()
    assert snd.samples[0, 0] == -50 and snd.samples[1, 0] == 100      # s2 then s1


def test_adapt_table_is_the_microsoft_one():
    assert S.ADAPT == ADAPT


def test_adpcm_tiny_hand_built():
    # predictor 0, delta 16, s1 = 100, s2 = 90; codes 1, 0xF (-1), 0, 0:
    # p = (100*256 + 90*0) >> 8 = 100 -> 100 + 1*16 = 116; delta = 307*16 >> 8 = 19
    block = bytes([0]) + struct.pack("<hhh", 16, 100, 90) + bytes([0x1F, 0x00])
    wav = riff(adpcm_fmt(), (b"fact", struct.pack("<I", 6)), (b"data", block))
    snd = S.load(wav)
    assert snd.samples[:2, 0].tolist() == [90, 100]
    assert snd.samples[2, 0] == 116
    assert snd.frames == 6


def test_adpcm_partial_last_block_and_fact_trim():
    rng = np.random.default_rng(2)
    full = bytes([1]) + struct.pack("<hhh", 30, 5, 3) + bytes(rng.integers(0, 256, 505, dtype=np.uint8))
    part = bytes([1]) + struct.pack("<hhh", 30, 5, 3) + bytes(rng.integers(0, 256, 10, dtype=np.uint8))
    data = full + part
    # 1012 + 2 + 20 frames; the game's files may state one frame more
    for total, ok in ((1034, True), (1035, True), (1030, True), (1037, False)):
        wav = riff(adpcm_fmt(), (b"fact", struct.pack("<I", total)), (b"data", data))
        if ok:
            assert S.load(wav).frames == min(total, 1034)
        else:
            with pytest.raises(S.SoundError):
                S.load(wav)


@pytest.mark.parametrize("bad", [
    b"", b"RIFX" + b"\0" * 20,
    riff(pcm_fmt(), (b"data", b"\0\0"))[:-1],                         # RIFF size mismatch
    riff(pcm_fmt(), (b"data", b"\0\0\0")),                            # not whole frames
    riff((b"fmt ", struct.pack("<HHIIHH", 3, 1, 22050, 0, 2, 16)), (b"data", b"\0\0")),   # unknown tag
])
def test_rejects_malformed(bad):
    with pytest.raises(S.SoundError):
        S.load(bad)


def test_leftover_bytes_rejected():
    good = riff(pcm_fmt(), (b"data", b"\0\0"))
    junk = good + b"xx"
    junk = junk[:4] + struct.pack("<I", len(junk) - 8) + junk[8:]
    with pytest.raises(S.SoundError):
        S.load(junk)


# ---- install ------------------------------------------------------------

needs_sfx = needs("sfx", "add.wav")


def wavs():
    return GFS.glob("*.wav") if GFS is not None else []


@needs_sfx
def test_every_file_decodes_exactly():
    files = wavs()
    assert len(files) == 1599
    seen = {"pcm": 0, "adpcm": 0}
    for p in files:
        raw = bytes(GFS.read(p))
        snd = S.load(raw)                      # parse_chunks: no leftover bytes
        fmt = {t: o for t, o, _ in S.parse_chunks(raw)}[b"fmt "]
        rate = struct.unpack_from("<I", raw, fmt + 4)[0]
        assert snd.sample_rate == rate
        data = {t: s for t, _, s in S.parse_chunks(raw)}[b"data"]
        if snd.tag == S.WAVE_PCM:
            assert snd.frames == data // (2 * snd.channels)       # duration = header
            seen["pcm"] += 1
        else:
            fact = {t: o for t, o, _ in S.parse_chunks(raw)}[b"fact"]
            assert snd.frames <= struct.unpack_from("<I", raw, fact)[0] <= snd.frames + 1
            seen["adpcm"] += 1
        assert snd.duration == pytest.approx(snd.frames / rate)
    assert seen == {"pcm": 560, "adpcm": 1039}


@needs_sfx
def test_adpcm_vector_equals_scalar_on_real_blocks():
    n = 0
    for p in GFS.glob("sfx/characters/*/attack/1.wav"):
        raw = bytes(GFS.read(p))
        if S.load(raw).tag != S.WAVE_MSADPCM:
            continue
        if n >= 8:
            break
        ch = {t: (o, s) for t, o, s in S.parse_chunks(raw)}
        o, s = ch[b"data"]
        data = raw[o:o + s]
        snd = S.load(raw)
        for k in range(min(3, len(data) // 512)):
            ref = ref_adpcm(data[k * 512:(k + 1) * 512])[:, 0]
            assert snd.samples[k * 1012:(k + 1) * 1012, 0].tolist() == ref.tolist()
            n += 1
    assert n


@needs_sfx
def test_adpcm_blocks_are_continuous_and_unclipped():
    """Each block header restates the first two samples; the previous block must end
    near them.  A wrong table or order makes the decode run away (full-scale noise)."""
    bad = total = 0
    for p in wavs():
        raw = bytes(GFS.read(p))
        snd = S.load(raw)
        if snd.tag != S.WAVE_MSADPCM:
            continue
        if not snd.frames:
            continue
        x = snd.samples[:, 0].astype(int)
        assert (np.abs(x) >= 32767).mean() < 0.05, p
        ch = {t: (o, sz) for t, o, sz in S.parse_chunks(raw)}
        o, sz = ch[b"data"]
        for k in range(1, sz // 512):
            hdr_s2 = struct.unpack_from("<h", raw, o + k * 512 + 5)[0]
            total += 1
            bad += abs(x[k * 1012 - 1] - hdr_s2) > 8000
    assert total > 10000 and bad / total < 0.05    # noisy blocks (predictor 2, no prediction) legitimately jump; a wrong decode is ~100 %


GOLDEN = os.path.join(os.path.dirname(__file__), "golden.json")


@needs_sfx
def test_golden_pcm_hashes():
    with open(GOLDEN, encoding="ascii") as f:
        golden = json.load(f)["sound"]
    assert len(golden) == 10
    for path, digest in golden.items():
        assert hashlib.sha256(S.load(path, GFS).pcm_bytes()).hexdigest() == digest, path


@needs_sfx
def test_sound_table_points_to_files():
    t = T.load(GFS)
    assert t.count == 660 and len(t.ids) == 192
    for sid, path in t.ids.items():
        assert GFS.exists(path) and 1 <= sid <= t.count, (sid, path)
    # the 8 entries whose file is absent from the install: silent in the exe (REA 0x4c4a48, 0x45aa2f)
    assert sorted(t.missing.values()) == sorted(
        "sfx/monsters/%s.wav" % n for n in ("daemon/dead", "daemon/easy", "daemon/hard", "skeleton/attack",
                                            "mage_skel/attack", "necrom/attack", "succubus/attack", "zombie/attack"))


@needs_sfx
def test_unit_sound_sets_and_voice_banks_resolve():
    t = T.load(GFS)
    sets = T.unit_sound_sets(GFS)
    assert len(sets) == 61
    for name, slots in sets.items():
        for slot, sid in slots.items():
            assert sid == 0 or sid in t.ids or sid in t.missing, (name, slot, sid)
    banks = T.hero_banks(GFS)
    assert list(banks) == list(T.BANKS)
    assert len(banks["aldor"]["select"]) == 3       # consecutive files from 1, like the exe's probe
    for cats in banks.values():
        for files in cats.values():
            assert all(GFS.exists(f) for f in files)
    music = [p for p in GFS.files("music") if p.endswith(".wav")]
    assert len(music) == 21 and set(T.PLAYLIST_MISSION) <= set(music)


def test_purpose_classifier():
    assert T.purpose("music/b00.wav") == "music"
    assert T.purpose("speech/talk/0001t000p01.wav") == "speech: dialogue"
    assert T.purpose("sfx/characters/aldor/dead.wav") == "hero / class voice"
    assert T.purpose("sfx/click00.wav") == "UI / misc"
