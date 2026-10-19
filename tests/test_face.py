import pytest

from contexta.face import NoFaceError, any_face_matches, is_same_person, select_largest_face

THRESHOLD = 0.55


def test_select_largest_face_면적이_가장_큰_얼굴을_고른다():
    facial_areas = [
        {"w": 100, "h": 1},
        {"w": 9, "h": 12},
    ]
    assert select_largest_face(facial_areas) == {"w": 9, "h": 12}


def test_select_largest_face_빈_목록이면_재업로드를_요구한다():
    with pytest.raises(NoFaceError, match="다시 업로드"):
        select_largest_face([])


def test_is_same_person_거리_0_55_이하면_같은_사람():
    assert is_same_person(THRESHOLD, THRESHOLD) is True
    assert is_same_person(0.2, THRESHOLD) is True


def test_is_same_person_거리_0_55_초과면_다른_사람():
    assert is_same_person(0.56, THRESHOLD) is False


def test_any_face_matches_여러_얼굴_중_하나만_가까우면_매칭():
    assert any_face_matches([0.9, THRESHOLD, 0.8], THRESHOLD) is True


def test_any_face_matches_모두_임계값을_넘으면_불일치():
    assert any_face_matches([0.9, 0.56, 0.8], THRESHOLD) is False
