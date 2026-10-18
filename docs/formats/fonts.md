# Fonts: `fontN.dat` metrics + `fontN.16` / `fontN.16a` glyphs

Code: `allods2/graphics/font.py`, text encoding `allods2/text.py`, pygame
blitter `engine/backend_pygame/text.py`. Tools: `tools/validate_fonts.py`;
`tools/font_contact.py` → `out/contact/fonts.png`;
`python -m allods2 font sample FONT DEST "text" [--width N]`.

A font = a sprite file with one glyph per character ([sprites](sprites.md),
`.16` or `.16a`) + a `.dat` with one width per glyph, same stem.

## Files

| Font | Glyphs | Cell (w × h) | Chars | `.dat` | Global (`FUN_0045f589`) |
|---|---:|---|---|---:|---|
| `font1/font1.16` | 224 | 16 × 15 | 0x20–0xFF | 896 B | `DAT_0061fac0` |
| `font2/font2.16` | 224 | 8 × 10 (char 0x80: 9 × 10) | 0x20–0xFF | 896 B | `DAT_00620500` |
| `font3/font3.16` | 64 | 8 × 6 | 0x20–0x5F (digits, a few signs drawn) | 256 B | `DAT_00620e30` |
| `font4/font4.16a` | 224 | 16 × 16 | 0x20–0xFF | 896 B | `DAT_00620dc8` |

CONFIRMED (all four, `tools/validate_fonts.py`): each `.dat` is exactly 4
bytes per glyph, every glyph stream consumed exactly, no header.

## `.dat` layout

`u32 width[g]` at `4·g` for character `0x20 + g`.

- CONFIRMED (`FUN_0045e39e` `.16`, `FUN_0045e756` `.16a`): the constructor
  appends `.16`/`.16a` (strings `0x5f10b8`/`0x5f10c4`), loads the sprite
  (`FUN_00424498` → vtable `0x5cb340`, or `FUN_00427ecb` → `0x5cb458`),
  reads the **whole** `.dat` (`FUN_004e2fc3`/`FUN_004e329c`; no length
  check). Object `{vtable, sprites, widths, spacing}`, spacing = 2 for all
  four (`FUN_0045f589`).
- CONFIRMED (`FUN_0045e756`): font4 rebuilds its shade table with
  `FUN_00424390(16, 4, 0)` (FADE16, [palettes §5](palettes.md)).
- CONFIRMED (data, all 736 glyphs): `width[g]` = index of the glyph's
  **last drawn column** (0 for blank); ink starts at column 0, so with
  spacing 2 one empty column follows each glyph.

## Character codes

NUL-terminated bytes; glyph `g = (map(c) − 0x20) & 0xFF`. CONFIRMED
(`FUN_0045cae1`):

```
map(c):
    if DAT_006227fc != 1: return c                 # remap off
    if 0x80 <= c <= 0xAF: return c + 0x30
    if 0xE0 <= c <= 0xEF: return c + 0x10
    return c
```

INFERRED (glyph shapes): 0x20–0x7F ASCII, 0x80–0xA5 cp437 Latin (Ç ü é …
ñ Ñ), 0xB0–0xDF Cyrillic А–п, 0xF0–0xFF р–я. With the remap on, text is
cp866: А 0x80 → glyph 0xB0, р 0xE0 → 0xF0. font2 has small capitals for
lower case. Implementation: `map_char(c, cyrillic)`.

### The remap switch `DAT_006227fc`

CONFIRMED (`0x4748b8`–`0x47490a`): the font setup reads `main\id`
(string `0x5f1a5c`) and stores its **last character − `'0'`**. The install
ships `english 0`, so the remap is **off**: every byte is its own font
code. Implementation: `locale_flag(fs)`; `Font.load` defaults to it.

Other users of the flag (CONFIRMED):

| Routine | Does |
|---|---|
| `FUN_00474c85` | one typed char, only when the flag is 1: `0xC0–0xEF − 0x40`, `0xF0–0xFF − 0x10` (cp1251 → cp866); `< 0x80` and flag 0 unchanged. Used by text inputs (6 callers, e.g. the key filter `0x43a8fe`) |
| `FUN_00474cf9` | lower-case one cp866 byte: `0x80–0x8F + 0x20`, `0x90–0x9F + 0x50`, else C `tolower` |
| `FUN_00474b12` | same on a string (name completion `FUN_0043adcd`) |

### Locale text: `CharToOemA`

CONFIRMED: every text file goes through one of two exe loaders, and both
call `CharToOemA(buf, buf)` (user32, IAT `0x6cf008`, `0x47422d` /
`0x47468e`) in place:

| Loader | Result | Files (`main\text\…` unless noted) |
|---|---|---|
| `FUN_00474585` (ecx = list) | split at each CR (CR → NUL, the next byte skipped unchecked), each line converted | `main` `0x622730`, `heropicture`, `stats`, `spells`, `spell`, `dialogs` `0x621888`, `unitname`, `building`, `itemname`, `npcnames`, `cutscene`, `cutpaths`, `tunes` (`0x481635`–`0x4816f3`), `patch\patch.txt` `0x621878` (`0x481702`), `credits` (`0x43c089`) |
| `FUN_004741ad(path, CString*)` | whole file, NUL-terminated, converted | `help` (`0x48162d`), `globalmap` (`0x46fabc`), `town` (3 callers), `quest` (`0x48da6a`), `mission%d`, `docs\%d` |

The reverse `OemToCharA` (`0x6cf004`) has 7 sites (e.g. `0x4817a4`,
main.txt line 0x96). INFERRED: text handed back to Windows.

`CharToOemA` converts the **system** ANSI code page to the OEM one, so
the result depends on the Windows locale; with the remap off, the font
glyph for byte `b` is cp437-like (0x80–0xA5 Latin). INFERRED: on an
English system cp1252 → cp437. The implementation's `ansi_to_oem` is the
Russian-locale variant (cp1251 → cp866); the English text files are ASCII
apart from a few typographic quotes.

A byte past the glyph table (≥ 0x60 in font3, or < 0x20 when drawn) reads
past the game's tables (undefined); the implementation draws nothing and
advances by `spacing`.

## Measuring: `FUN_0045cb59`

CONFIRMED.

```
measure(s):
    total = 0
    for i over s:
        c = s[i]
        if c < 0x20: continue                      # control bytes count 0
        if c == '~':
            if s[i+1] != '~': continue             # lone '~' counts 0
            i += 1                                 # '~~' counts one '~'
        g = map(c) - 0x20
        total += width[g] + spacing
        if g == 0: total += height(glyph 0) >> 1   # space
    return total
```

### DECISION: the remap is always on

The exe leaves the remap off on the English install, so a cp866 Cyrillic
byte would draw a Latin cp437 glyph. The reimplementation supports Russian
by default: `Font.load(cyrillic=None)` = True. English is unaffected:
the remap only touches 0x80–0xAF and 0xE0–0xEF, and every text file of the
install is ASCII there (the few bytes ≥ 0x80 are stray cp1251 Cyrillic in
comments and typos, no accented Latin). Cost: the cp437 Latin glyphs
(é, ñ, …) are no longer reachable; no shipped text uses them.
`Font.load(cyrillic=False)` and `locale_flag` give the exe's behaviour.

## Text encoding: `allods2/text.py`

One module for all text: `decode_text(bytes) -> str` (cp1251: text files, map
and data strings), `font_bytes(str | cp1251 bytes) -> bytes` (cp866 as
`CharToOemA` makes it, then drawn through the remapped font table),
`ansi_to_oem` (the byte-exact conversion). INFERRED glyph coverage: the fonts
have no ё/Ё (0xF1/0xF0 would draw с/р), so `font_bytes` draws е/Е (DECISION);
characters cp866 lacks become `?`; typographic quotes/dashes are
best-fitted. font3 has no Cyrillic or lower case (0x20–0x5F only).
Glyph coverage per byte: control bytes < 0x20 (and, in font3, everything
outside 0x20–0x5F) read past the table in the exe, nothing is drawn
(`tests/test_fonts.py`).

## Wrapping (our own, the exe has none)

`Font.wrap(text, width) -> [line]`: break at spaces by `measure`, `\n`
forces a break, spaces at a break are dropped, a word wider than `width`
is split between characters (`~x` and `~~` stay together), a single
character wider than `width` gets its own line. `Font.layout_block` stacks
lines `line_height() = cell height + 1` apart (one row for the `~`
underline). `engine.backend_pygame.text.draw_text(..., width=, wrap=True)`.

## Engine drawing

`draw_text(surface, text, x, y, colour, align, font=2, shadow=True)`:
`colour` is an RGB tuple (16-step ramp black → colour, like the code
tables) or a `TABLES` name (palettes §6: normal, highlight, label,
value, header, tooltip, red, yellow, green); the 1 px shadow is the
(8, 8, 8) table at offset 1; font4 (`.16a`) uses its own palette.
Surfaces are cached (512). Without an install pygame's bundled font is the
stand-in.

## Drawing a `.16` font: `FUN_0045e531`

CONFIRMED (font vtable `0x5cd340` slot 5). `colours` = 16-entry table of
16-bit pixels indexed by the 4-bit glyph pixels (blit `FUN_004540d1` via
vtable `0x5cb340 + 0x34`).

```
draw16(x, y, s, flags, colours):
    if flags & 1: x -= measure(s)                  # right
    if flags & 2: x -= measure(s) >> 1             # centre
    if flags & 4: y -= width(glyph 0)              # bottom   (width, sic)
    if flags & 8: y -= width(glyph 0) >> 1         # middle   (width, sic)
    i = 0
    while i < strlen(s):
        g  = map(s[i]) - 0x20
        g2 = map(s[i+1]) - 0x20                        # s[len] = NUL
        if g == 0x5e and g2 != 0x5e:                   # '~' + char: underline it
            line(x, y + height(0), x + width[g2], y + height(0), colours[15])   # u16 at +0x1e
        else:
            if g == 0: x += height(glyph 0) >> 1       # space
            else: blit16(x, y, glyph g, colours)
            x += width[g] + spacing
            if g == 0x5e and g2 == 0x5e: i += 1        # '~~' draws one '~'
        i += 1
```

- CONFIRMED (`0x5cb340` slots 8/9 = `FUN_004243c6`/`FUN_004243f1`):
  `width(n)`/`height(n)` = sprite record n's `w`/`h`; vertical alignment
  really uses glyph 0's **width**, the space its **height** (equal for
  font4).
- CONFIRMED (`FUN_0045673c`): `line` = clipped Bresenham, one 16-bit
  colour; the underline is horizontal, `width[g2] + 1` px, one row below
  the cell, brightest colour; `~` does not advance the pen (INFERRED:
  button hotkey letter).

## Drawing a `.16a` font: `FUN_0045e8fd`

CONFIRMED, vtable `0x5cd360` slot 5.

```
draw16a(x, y, s, flags, shade):
    alignment as draw16
    for c in s:
        g = map(c) - 0x20
        if g == 0: x += height(glyph 0) >> 1
        else: sprite.draw(x, y, g, shade, 0)       # vtable 0x5cb458 + 0x18
        x += width[g] + spacing
```

No `~` handling (drawn as a glyph). The glyph blit
(`FUN_00427ef0`) uses `shade` or, if null, the font's FADE16 table, and
the `.16a` blitter `FUN_0045889b`. Callers pass a gradient row
([palettes §6](palettes.md)).

## Drop shadow: `FUN_0045d536`

CONFIRMED. Slot 6 of both font vtables returns the **shadow table**:
`.16` → `FUN_0045e746` → `0x620df0` (constant (8, 8, 8)); `.16a` →
`FUN_0045ea58`, a black-gradient row. Most text goes through:

```
draw_shadowed(x, y, s, flags, colours, off):
    draw(x + off, y + off, s, flags, shadow_table())   # slot 5
    draw(x,       y,       s, flags, colours)
```

## Callers: colours and flags

CONFIRMED (all 152 `FUN_0045d536` call sites): with literal arguments
`off` is 1 almost everywhere; `flags` 0 (left), 1 (right) or 2 (centre),
8 (vertical middle) rare. Tables per kind of text:
[palettes §6](palettes.md#which-text-uses-which-table).

## Worked example

font1, grey ramp, `~Ok` at (0, 0) (remap off, as shipped): `~` + `O` (g 0x5e, 0x2f) →
underline x 0…`width[0x2f]` = 0…11 (12 px) at y 15 in colours[15], x
stays 0; `O` → glyph 0x2f at (0, 0), x = 0 + 11 + 2 = 13; `k` (0x4b) at
(13, 0), x = 13 + 7 + 2 = 22. `measure("~Ok")` skips the lone `~` and
also gives 22, so hotkey labels centre correctly. (Shipped font1 values;
`tests/test_fonts.py` checks the rules on synthetic fonts.)

## Open questions

None.
