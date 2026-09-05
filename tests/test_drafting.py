from src.core.drafting import _clean_html


def test_clean_html_flattens_blocks_and_unescapes():
    raw = "<h3>Requirements</h3><ul><li>3+ years &amp; SQL</li><li>Python</li></ul>"
    text = _clean_html(raw)
    assert "<" not in text
    assert "3+ years & SQL" in text
    assert "Requirements\n" in text          # block boundary became a newline


def test_clean_html_collapses_blank_runs_and_keeps_full_length():
    raw = "<p>a</p><br><br><br><p>b</p>" + "<p>" + "x" * 5000 + "</p>"
    text = _clean_html(raw)
    assert "\n\n\n" not in text
    assert "x" * 5000 in text                # no length cap here, unlike scoring


def test_clean_html_empty():
    assert _clean_html(None) == ""
    assert _clean_html("") == ""
