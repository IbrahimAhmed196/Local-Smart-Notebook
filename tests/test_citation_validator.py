from app.agents.citation_validator import (
    collect_source_ids,
    find_invalid_source_ids,
    strip_invalid_source_ids,
)
from app.schemas.slide_content import Bullet


def bullets():
    return [
        Bullet(text="a", source_ids=["S1", "S2"]),
        Bullet(text="b", source_ids=["S2", "S9"]),
        Bullet(text="c", source_ids=[]),
    ]


def test_collect_source_ids_lists_each_id_once_in_order():
    assert collect_source_ids(bullets()) == ["S1", "S2", "S9"]


def test_find_invalid_source_ids_reports_only_unknown_ids():
    assert find_invalid_source_ids(bullets(), ["S1", "S2"]) == ["S9"]
    assert find_invalid_source_ids(bullets(), ["S1", "S2", "S9"]) == []
    assert find_invalid_source_ids(bullets(), []) == ["S1", "S2", "S9"]


def test_strip_invalid_source_ids_keeps_text_and_valid_ids_and_does_not_change_the_input():
    original = bullets()
    cleaned = strip_invalid_source_ids(original, ["S1", "S2"])
    assert [b.text for b in cleaned] == ["a", "b", "c"]
    assert [b.source_ids for b in cleaned] == [["S1", "S2"], ["S2"], []]
    assert original[1].source_ids == ["S2", "S9"]


def test_strip_invalid_source_ids_removes_duplicates_inside_a_bullet():
    cleaned = strip_invalid_source_ids([Bullet(text="x", source_ids=["S1", "S1"])], ["S1"])
    assert cleaned[0].source_ids == ["S1"]
