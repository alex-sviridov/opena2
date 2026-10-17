"""Text drawing: the single entry point (G3c replaces the font with the game's)."""

import pygame

_font = None
SIZE = 14


def get_font():
    global _font
    if not pygame.font.get_init():                        # pygame.quit() invalidates the font
        pygame.font.init()
        _font = None
    if _font is None:
        _font = pygame.font.Font(None, SIZE)        # pygame's bundled font until G3c
    return _font


def draw_text(surface, text, x, y, colour=(255, 255, 255), align="left"):
    """Draw `text` with its top at `y`; `align` 'left' (x = left), 'center' or 'right' (x = right edge)."""
    try:
        img = get_font().render(str(text), False, colour)
    except pygame.error:                                   # the font module was quit and re-initialised
        global _font
        _font = None
        img = get_font().render(str(text), False, colour)
    if align == "center":
        x -= img.get_width() // 2
    elif align == "right":
        x -= img.get_width()
    surface.blit(img, (x, y))
    return img.get_width()
