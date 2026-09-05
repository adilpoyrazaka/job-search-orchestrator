import json
from types import SimpleNamespace

import pytest

import src.core.scoring as scoring
from src.core.scoring import _build_user_message, _extract_text, _parse_score


def test_parse_score_plain_json():
    assert _parse_score('{"score": 72, "reason": " fits "}') == {"score": 72, "reason": "fits"}


def test_parse_score_tolerates_stray_text_around_the_object():
    text = 'Sure! {"score": 40, "reason": "meh"} Hope that helps.'
    assert _parse_score(text)["score"] == 40


@pytest.mark.parametrize("raw, clamped", [(150, 100), (-5, 0), ("88", 88)])
def test_parse_score_clamps_and_coerces(raw, clamped):
    text = json.dumps({"score": raw, "reason": "r"})
    assert _parse_score(text)["score"] == clamped


def test_parse_score_fails_loud_without_json():
    with pytest.raises(ValueError, match="no JSON object"):
        _parse_score("I would rate this highly.")


def test_extract_text_selects_by_type_not_position():
    resp = SimpleNamespace(content=[
        SimpleNamespace(type="thinking", thinking="..."),
        SimpleNamespace(type="text", text='{"score": 1, "reason": "x"}'),
    ])
    assert _extract_text(resp) == '{"score": 1, "reason": "x"}'


def test_extract_text_fails_loud_without_text_block():
    resp = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="...")])
    with pytest.raises(ValueError, match="no text block"):
        _extract_text(resp)


def test_user_message_is_bounded_by_max_desc_chars(monkeypatch):
    monkeypatch.setattr(scoring, "MAX_DESC_CHARS", 10)
    msg = _build_user_message("t", "c", "l", "x" * 50)
    assert msg.endswith("Description: " + "x" * 10)


def test_user_message_is_not_truncated_below_the_cap():
    desc = "short posting"
    assert _build_user_message("t", "c", "l", desc).endswith(desc)
