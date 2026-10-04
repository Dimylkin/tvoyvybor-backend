from app.attempt_service import leading_direction


def test_leading_direction_is_deterministic() -> None:
    assert leading_direction({}) is None
    assert leading_direction({"4": 1, "9": 2}) == 9
    assert leading_direction({"9": 2, "4": 2}) == 4
