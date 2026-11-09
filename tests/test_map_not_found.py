"""A wrong MAP argument gives a one-line error listing the campaign maps, not a traceback, and `play` leaves no session behind."""

import pytest

from allods2.cli import MapNotFound, open_map
from engine.__main__ import main
from helpers import GFS

pytestmark = pytest.mark.skipif(GFS is None, reason="no game install")


def test_open_map_names_the_choices():
    with pytest.raises(MapNotFound) as e:
        open_map("999")
    assert "scenario/999.alm" in str(e.value) and " 32 " in str(e.value)


def test_play_wrong_map_exits_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ALLODS2_SESSIONS", str(tmp_path))
    with pytest.raises(SystemExit) as e:
        main(["play", "999"])
    assert e.value.code == 2
    assert "no such map" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_maps_lists_32(capsys):
    assert main(["maps"]) == 0
    assert any(l.split()[0] == "32" for l in capsys.readouterr().out.splitlines())
