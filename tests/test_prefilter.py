import pytest

from src.core.prefilter import evaluate, is_relevant_title, is_remote_eligible, match_ladder


@pytest.mark.parametrize(
    "location, expected",
    [
        ("Worldwide", True),
        ("Americas, Europe", True),
        ("Türkiye", False),          # diacritic form is not in the allowlist
        ("Turkey", True),
        ("United States", False),
        ("", True),                  # unspecified: ambiguous, left to the scorer
        (None, True),
    ],
)
def test_is_remote_eligible(location, expected):
    assert is_remote_eligible(location) is expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Senior Data Analyst", "data_analyst"),
        ("Product Analyst (Intermediate)", "data_analyst"),
        ("Analytics Engineer", "analytics_engineer"),
        ("Machine Learning Engineer", "ai_engineer"),
        ("Sales Manager", None),
        (None, None),
    ],
)
def test_match_ladder(title, expected):
    assert match_ladder(title) == expected


def test_ladder_first_match_wins():
    # contains both a data_analyst term and an analytics_engineer term;
    # LADDER order decides
    assert match_ladder("Data Analyst / Analytics Engineer") == "data_analyst"


@pytest.mark.parametrize(
    "title, expected",
    [
        ("SQL Developer", True),                 # data signal, no ladder
        ("Marketing Data Specialist", False),    # hard exclusion beats signal
        ("Product Manager, Data Platform", False),
        ("Backend Engineer", False),             # no signal at all
    ],
)
def test_is_relevant_title_without_ladder(title, expected):
    assert is_relevant_title(title, ladder=None) is expected


def test_ladder_role_always_relevant():
    assert is_relevant_title("Sales Data Analyst", ladder="data_analyst") is True


@pytest.mark.parametrize(
    "title, location, passes, ladder",
    [
        ("Data Analyst", "Worldwide", 1, "data_analyst"),
        ("Data Analyst", "United States", 0, "data_analyst"),
        ("Sales Manager", "Worldwide", 0, None),
        ("Reporting Analyst", "", 1, "data_analyst"),
    ],
)
def test_evaluate(title, location, passes, ladder):
    assert evaluate(title, location) == {"prefilter_pass": passes, "ladder_match": ladder}
