import pytest

from graphrag.common.ids import make_id, parse_id


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
