"""The story window's script (docs/engine/ui-layout.md 11.5): tag parser `engine.ui.story`, pages, window layout.  Synthetic rules plus the install's texts."""

import re

import pytest
from helpers import GFS, needs

from engine.ui import Layout, MainText, modal, story
from engine.ui.widgets import widget_rect

MAIN = MainText(["m%02x" % i for i in range(0x100)])
CR = "\r\n"


def sec(*lines):
    return CR.join(lines) + CR


def test_section_cuts_from_the_key_to_the_next_hash_and_skips_the_key_line():
    t = "#a" + CR + "one" + CR + "#" + CR + "#EVENT1" + CR + "<part=1>" + CR + "x" + CR + "#" + CR + "tail" + CR
    assert story.section(t, "event1") == "<part=1>" + CR + "x" + CR      # case-insensitive find (INFERRED), the CR LF after the key is skipped
    assert story.section(t, "event2") == ""
    assert story.section("#event1x" + CR + "y#z", "event1") == "\ny"      # plain substring search: `#event1` finds `#event1x`; the skip is key length + 2, so `x` and the CR go, the LF stays


def test_speaker_layout_is_any_npc_substring_of_the_section():
    assert story.has_speaker_layout("<NPC=21, part=1>") and story.has_speaker_layout("<npcalive:5, part=1>")
    assert not story.has_speaker_layout("<part=1>" + CR + "text")


def test_a_page_is_the_first_tag_with_that_part_whose_conditions_hold():
    s = sec("<NPC=21, IAMMALE, IAMFIGHTER, PART=1>", "mf", "<NPC=21, IAMFEMALE, IAMFIGHTER, PART=1>", "ff", "<NPC=21, IAMMALE, IAMMAGE, PART=1>", "mm",
            "<NPC=21, IAMFEMALE, IAMMAGE, PART=1>", "fm", "<npc=7, part=2>", "any")
    flags = story.hero_flags
    assert [story.page(s, 1, flags(f, m)).text.strip() for f, m in ((0, 0), (1, 0), (0, 1), (1, 1))] == ["mf", "ff", "mm", "fm"]
    assert story.page(s, 2, flags(1, 1)).text.strip() == "any" and story.page(s, 2, 0).npc == 7
    assert story.page(s, 3, 0) is None
    twice = sec("<part=1>", "first", "<part=1>", "second")
    assert story.page(twice, 1, 0).text.strip() == "first"                          # file order: the first qualifying tag wins


def test_iam_tags_are_independent_conditions():
    s = sec("<IAMFEMALE, part=1>", "any female", "<IAMMAGE, part=1>", "any mage", "<part=1>", "anyone")
    assert story.page(s, 1, story.hero_flags(1, 0)).text.strip() == "any female"
    assert story.page(s, 1, story.hero_flags(0, 1)).text.strip() == "any mage"
    assert story.page(s, 1, story.hero_flags(0, 0)).text.strip() == "anyone"


def test_page_text_ends_before_the_cr_of_the_line_in_front_of_the_next_tag():
    s = sec("<part=1>", "line one", "line two", "", "<part=2>", "last")
    assert story.page(s, 1, 0).text == "line one" + CR + "line two" + CR
    assert story.page(s, 2, 0).text == "last" + CR                           # no tag after it: up to the end of the section


def test_tag_matching_is_a_substring_search_on_the_lowercase_tag():
    s = sec("<NPC=3, PART=10>", "ten", "<part=2>", "two")
    assert story.page(s, 1, 0).text == "ten"                                 # `part=1` is inside `part=10`: the exe's quirk
    assert story.page(sec("<part4=>", "x"), 4, 0) is None                    # the install's typo `part4=` never matches
    assert story.page(sec("<Part=1, NpC=5>", "x"), 1, 0).npc == 5


def test_npc_fields_sound_tune_tips():
    p = story.page(sec('<npc=623, part=1, sound:"a b.wav", tune:4, tips:12>', "t"), 1, 0)
    assert (p.npc, p.has_npc, p.sound, p.tune, p.tips) == (623, True, "a b.wav", 4, 12)
    q = story.page(sec("<part=1>", "t"), 1, 0)
    assert (q.npc, q.has_npc, q.sound, q.tune, q.tips) == (0, False, "", -1, 0)
    assert story.page(sec("<part=1, sound:x.wav;y>", "t"), 1, 0).sound == "x.wav"


def test_npcalive_and_npcdead_conditions():
    s = sec("<part=1, npcalive:5>", "alive", "<part=1, npcdead:5>", "dead", "<part=1>", "fallback")
    assert story.page(s, 1, 0, alive=lambda n: True).text.strip() == "alive"
    assert story.page(s, 1, 0, alive=lambda n: False).text.strip() == "dead"
    both = sec("<part=1, npcalive:5, npcalive:6>", "both", "<part=1>", "else")
    assert story.page(both, 1, 0, alive=lambda n: n == 5).text.strip() == "else"


def test_pages_run_in_order_and_stop_at_the_first_gap():
    s = sec("<part=1>", "a", "<part=2>", "b", "<part=4>", "d")
    assert [p.text.strip() for p in story.pages(s, 0)] == ["a", "b"]


def test_portrait_crop_default_and_table():
    assert story.crop_of(21) == (0x24, 8, 0x48, 92) and story.crop_of(0x46) == (0x24, 8, 0x48, 92)      # table entry (-1, -1)
    assert story.crop_of(0x40) == (30, 72, 0x48, 0x60) and story.crop_of(0x66) == (15, 21, 0x48, 0x60) and story.crop_of(0x67) == (0x24, 8, 0x48, 92)


# --- the window ---------------------------------------------------------------------------------------------------------------------

def dialog(sec_text, flags=0, alive=lambda n: True, picture=lambda n: n):
    return modal.story_dialog(Layout.for_size(640, 480), MAIN.line, sec_text, flags, alive, modal.plain_wrap, picture)


def test_layout_without_npc_has_the_wide_text_and_no_picture():
    d = dialog(sec("<part=1>", "hello"))
    f, t = d.frame, d.text_rect
    assert d.picture is None and d.text == "hello" and d.lines == ("hello",)
    assert (t.x - f.x, t.y - f.y, t.w, t.h) == (0x30, 0x24, 380, 136)
    ok = d.buttons[0].rect
    assert (ok.x - f.x, ok.y - f.y, ok.w, ok.h) == (200, 172, 80, 26) and d.buttons[0].action == modal.NEXT


def test_layout_with_npc_narrows_the_text_and_adds_the_picture():
    d = dialog(sec("<npc=21, part=1>", "hello"))
    f, t, p = d.frame, d.text_rect, d.picture
    assert (t.x - f.x, t.y - f.y, t.w, t.h) == (0x80, 0x24, 300, 136)
    assert (p.x - f.x, p.y - f.y, p.w, p.h) == (30, 54, 88, 114) and d.picture_unit == 21


def test_ok_shows_the_next_page_and_the_picture_changes_only_with_npc_pages():
    d = dialog(sec("<npc=21, part=1>", "one", "<part=2>", "two", "<npc=22, part=3>", "three"))
    assert d.text == "one" and d.picture_unit == 21
    assert modal.advance(d) and d.text == "two" and d.picture_unit == 21          # a page without npc= keeps the old picture
    assert modal.advance(d) and d.text == "three" and d.picture_unit == 22
    assert not modal.advance(d)                                                    # page 4: none, the window closes


def test_missing_first_page_shows_nothing_to_say_but_the_counter_goes_on():
    d = dialog(sec("<part=2>", "second"))
    assert d.text == "Nothing to say" and d.story.n == 1
    assert modal.advance(d) and d.text == "second"
    assert dialog("").text == "Nothing to say"


def test_story_dialog_keys_and_unknown_unit_picture():
    d = dialog(sec("<npc=9, part=1>", "x"), picture=lambda n: None)
    assert d.picture_unit is None and d.key("return") == modal.NEXT and d.key("escape") == modal.CLOSE


def test_unknown_speaker_is_the_dummy_unit_with_a_female_mage_doll():
    """`FUN_0041d8bb` (CONFIRMED): no living unit -> flags 0x56 (female mage), face id - 0x50, no equipment: the body layer alone."""
    d = dialog(sec("<npc=89, part=1>", "x"), picture=lambda n: None)
    assert d.picture_unit is None and d.picture_npc == 89
    assert story.dummy_doll_path(89) == "graphics/equipment/fmage/9.256"
    d = dialog(sec("<npc=9, part=1>", "x"), picture=lambda n: 5)
    assert d.picture_unit == 5 and d.picture_npc is None


@needs("graphics", "equipment", "fmage", "1.256")
def test_dummy_doll_faces_exist_for_speaker_ids_0x51_to_0x64():
    assert all(GFS.exists(story.dummy_doll_path(n)) for n in range(0x51, 0x65))
    assert not GFS.exists(story.dummy_doll_path(0x65)) and not GFS.exists(story.dummy_doll_path(21))      # the exe's fatal "can't load"


# --- the install --------------------------------------------------------------------------------------------------------------------

def _missions():
    return sorted(n for n in GFS.listdir("main/text") if re.fullmatch(r"mission\d+\.txt", n))


@needs("main", "text", "mission10.txt")
def test_every_story_section_of_the_install_parses_into_clean_pages():
    total = empty = 0
    classes = [story.hero_flags(f, m) for f in (0, 1) for m in (0, 1)]
    for name in _missions():
        text = bytes(GFS.read("main/text/" + name)).decode("latin-1")
        for key in re.findall(r"(?m)^#(event\d+)[ \t]*\r?$", text):
            s = story.section(text, key)
            assert "#" not in s and story.has_speaker_layout(s) == ("npc" in s.lower())
            for fl in classes:
                ps = story.pages(s, fl)
                empty += not ps
                for p in ps:
                    assert p.text.strip() and "<" not in p.text and p.tips == 0 and p.tune == -1 and p.sound == ""
                total += len(ps)
    assert total > 5000
    assert empty == 3                      # data typos reproduced: mission103 event1 (no female mage page 1), mission30 event5 (no fighter pages)


@needs("main", "text", "mission10.txt")
def test_every_story_text_of_the_install_fits_the_text_widget():
    from allods2 import graphics as gfx
    font = gfx.Font.load("graphics/font1/font1", GFS)
    lines = []
    for name in _missions():
        text = bytes(GFS.read("main/text/" + name)).decode("latin-1")
        for key in re.findall(r"(?m)^#(event\d+)[ \t]*\r?$", text):
            s = story.section(text, key)
            width = 300 if story.has_speaker_layout(s) else 380
            for p in story.pages(s, story.hero_flags(0, 0)):
                lines.append(len(font.wrap(p.text.replace("\r\n", "\n").rstrip("\n"), width)))
    assert max(lines) <= 8                  # the visible rows are 136 / 17 = 8 (our wrap: at most 7 here), so the scroll bar of `FUN_004d51db` is never needed


@needs("main", "text", "mission32.txt")
def test_map32_failure_reasons_from_the_install():
    """mission32.txt has #failure2 / 3 / 5 (no 4): list entries 0..3, entry 2 = the default `main 0x11c`."""
    main = MainText.load(GFS)
    t = bytes(GFS.read("main/text/mission32.txt")).decode("cp1251")
    lst = story.failure_texts(t, main.line)
    assert len(lst) == 4 and lst[0].startswith("Chasing swords") and lst[2] == main.line(0x11C) and lst[3].startswith("The heroes failed")
