"""Decoded views of the game's data files; specs in docs/formats/."""

from .map import Map, MapHeader, decode_text
from .objects import MapObject, Structure
