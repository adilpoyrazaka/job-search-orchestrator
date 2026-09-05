from src.adapters.himalayas import _location


def test_empty_location_restrictions_is_absence_not_worldwide():
    # An empty array from the API means the employer said nothing; emitting
    # "Worldwide" here would fabricate eligibility. Silence for silence.
    assert _location([]) == ""
    assert _location(None) == ""


def test_location_restrictions_join():
    assert _location(["Turkey", "Germany"]) == "Turkey, Germany"
