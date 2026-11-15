"""Length of a game wav in ms from its RIFF headers (pure, no device): the audio backend and the town scenes (the exe does not retrigger a sound slot that still plays) use it."""

import struct

from allods2.formats import sound as snd


def wav_duration_ms(data):
    """Length of a RIFF wav in ms from its headers (PCM: data / frame size; MS ADPCM: the `fact` frame count); None for a file with no samples or no
    readable header."""
    try:
        b = bytes(data)
        by = {}
        for t, o, s in snd.parse_chunks(b):
            by.setdefault(t, (o, s))
        o, _ = by[b"fmt "]
        tag, channels, rate, _bps, align, _bits = struct.unpack_from("<HHIIHH", b, o)
        if b"fact" in by:
            frames = struct.unpack_from("<I", b, by[b"fact"][0])[0]
        elif tag == snd.WAVE_PCM and align:
            frames = by[b"data"][1] // align
        else:
            frames = snd.decode(b).frames
        ms = frames * 1000 // rate if rate else 0
        return ms if ms > 0 else None
    except (KeyError, ValueError, struct.error, snd.SoundError):
        return None
