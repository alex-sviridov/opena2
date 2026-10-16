"""PNG output for exports and previews (the game itself reads no PNG)."""

import numpy as np
from PIL import Image


def write_png(path, image):
    """image: (h, w, 3) RGB or (h, w, 4) RGBA uint8 array."""
    Image.fromarray(np.ascontiguousarray(image, np.uint8)).save(path)
