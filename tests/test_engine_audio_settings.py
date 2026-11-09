"""K11: the settings file (docs/engine/audio.md 6)."""

import json
import os

from engine.audio import settings as S


def test_defaults_path_resolution_and_the_exe_default_volume(tmp_path):
    s = S.Settings()
    assert (s.sfx, s.speech, s.music, s.mute, s.music_enabled) == (74, 74, 74, False, True)
    assert -750 < s.bus_mb("sfx") < -650
    assert S.path({"ALLODS2_SETTINGS": "/x/y.json", "XDG_CONFIG_HOME": "/z"}) == "/x/y.json"
    assert S.path({"XDG_CONFIG_HOME": "/z"}) == os.path.join("/z", "allods2-engine", "settings.json")
    assert S.path({"HOME": "/h"}).endswith(os.path.join(".config", "allods2-engine", "settings.json"))


def test_round_trip_and_atomic_write(tmp_path):
    p = str(tmp_path / "sub" / "settings.json")
    s = S.Settings(sfx=10, speech=20, music=30, mute=True, music_enabled=False)
    assert S.save(s, p) and S.load(p) == s
    assert sorted(os.listdir(tmp_path / "sub")) == ["settings.json"]                  # the temp file is gone
    assert json.load(open(p))["sfx"] == 10


def test_missing_or_broken_files_give_defaults_and_bad_values_are_cleaned(tmp_path):
    assert S.load(str(tmp_path / "none.json")) == S.Settings()
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert S.load(str(p)) == S.Settings()
    p.write_text("[1, 2]")
    assert S.load(str(p)) == S.Settings()
    p.write_text(json.dumps({"sfx": 150, "speech": -4, "music": "loud", "mute": 1, "music_enabled": False, "extra": 1}))
    s = S.load(str(p))
    assert (s.sfx, s.speech, s.music, s.mute, s.music_enabled) == (100, 0, 74, False, False)


def test_overrides_are_for_the_run_only():
    s = S.Settings()
    o = s.override(mute=True, sfx=5)
    assert o.mute and o.sfx == 5 and o.music == 74 and not s.mute and s.sfx == 74


def test_save_into_an_unwritable_place_fails_quietly(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    assert S.save(S.Settings(), str(f / "a" / "settings.json")) is False
