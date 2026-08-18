import pytest

from copilot.budget import check


def test_ok_when_well_under():
    r = check("data-eng", 100)
    assert r.verdict == "ok"


def test_warn_near_limit():
    # data-eng: budget 9000, spend 4100 -> need projected > 8100 (90%)
    r = check("data-eng", 4200)
    assert r.verdict == "warn"


def test_over_when_exceeds():
    # growth: budget 1500, spend 1360 -> +200 tips it over
    r = check("growth", 200)
    assert r.verdict == "over"
    assert r.headroom_usd < 0


def test_unknown_team_raises():
    with pytest.raises(ValueError):
        check("nope", 10)
