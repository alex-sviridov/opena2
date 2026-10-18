"""Game text encoding: the one place that turns text bytes into str and into font codes.

Spec: docs/formats/fonts.md (locale text).  The locale text files and the
.dat/.reg strings are cp1251 (`decode_text`).  The exe hands text to
CharToOemA (cp1251 -> cp866) before it reaches the font (FUN_00474585,
FUN_004741ad); `font_bytes` does the same, so Russian and English both reach
the glyph table.  DECISION: the Cyrillic font remap is always on (fonts.md),
which is harmless for English because its text is ASCII.
"""

TEXT_CODEC = "cp1251"      # text files and string fields
FONT_CODEC = "cp866"        # what CharToOemA produces; the remapped font table is cp866

# INFERRED: Windows best-fit for characters cp866 lacks (only ’ occurs, en/town.txt)
_OEM_BEST_FIT = {"‘": "'", "’": "'", "“": '"', "”": '"',
                 "–": "-", "—": "-", "«": '"', "»": '"'}
# DECISION: the fonts have no ё (cp866 0xF1 would draw the glyph of 'с', 0xF0 that of 'р'),
# so draw the plain letter.  Only `font_bytes` does this; `ansi_to_oem` is the byte-exact one.
_NO_YO = {"ё": "е", "Ё": "Е"}


def decode_text(data):
    """Bytes of a text file or string field -> str (cp1251)."""
    return bytes(data).decode(TEXT_CODEC, errors="replace")


def _oem(text, table):
    out = bytearray()
    for ch in text:
        if ord(ch) < 0x80:
            out.append(ord(ch))
            continue
        ch = table.get(ch, ch)
        out += ch.encode(FONT_CODEC, errors="replace")
    return bytes(out)


def font_bytes(text):
    """str (or cp1251 bytes) -> the byte string a font draws: cp866, ё/Ё as е/Е
    (no glyph), unmappable characters '?'."""
    if isinstance(text, (bytes, bytearray, memoryview)):
        text = decode_text(text)
    return _oem(text, {**_OEM_BEST_FIT, **_NO_YO})


def ansi_to_oem(data):
    """CharToOemA on the Russian locale: cp1251 bytes -> cp866 bytes
    (А 0xC0 -> 0x80, Ё 0xA8 -> 0xF0, ё 0xB8 -> 0xF1)."""
    return _oem(decode_text(data), _OEM_BEST_FIT)
