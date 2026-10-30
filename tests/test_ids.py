import pytest

from graphrag.common.ids import base_id, make_id, make_vid, parse_id


def test_make_and_parse_roundtrip():
    uid = make_id("ND168_2024", 6, 5, "a")
    assert uid == "ND168_2024.D6.K5.a"
    p = parse_id(uid)
    assert (p.doc, p.dieu, p.khoan, p.diem) == ("ND168_2024", "6", "5", "a")
    assert p.level == "Diem"
    assert str(p.parent()) == "ND168_2024.D6.K5"


def test_invalid():
    with pytest.raises(ValueError):
        make_id("L36_2024", None, 2)
    with pytest.raises(ValueError):
        parse_id("khong-hop-le")


def test_inserted_units():
    assert parse_id("ND168_2024.D6.K1a").khoan == "1a"
    assert parse_id("ND168_2024.D41.K4.k1").diem == "k1"
    assert parse_id("ND151_2024.D25a").dieu == "25a"


def test_version_ids():
    from datetime import date

    vid = make_vid("ND168_2024.D6.K3.m", date(2026, 8, 15))
    assert vid == "ND168_2024.D6.K3.m@2026-08-15"
    assert base_id(vid) == "ND168_2024.D6.K3.m"
    assert base_id("ND168_2024.D6.K3.m") == "ND168_2024.D6.K3.m"
