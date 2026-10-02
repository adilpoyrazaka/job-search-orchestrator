import pytest

from src.core.eligibility import BLOCKED, CLEAR, classify, labels_from_payload

STANDARD = ["First Name", "Last Name", "Email", "Phone", "Resume/CV", "LinkedIn Profile"]

# Real labels, Tripledot Studios Data Analyst (Greenhouse EU), seen 2026-10-02.
TRIPLEDOT = STANDARD + [
    "Our hybrid working policy includes working 4 days a week in the office, "
    "please confirm you are happy to proceed on this basis.",
    "Do you have right to work in the country this role is being advertised in?",
    "Are you based in the country advertised for this role? Or do you require relocation?",
    "Are you able to work in English at B2 level or above?",
]

# Real labels, job 1191 (Buyers Edge, Greenhouse), seen 2026-07-30.
JOB_1191 = STANDARD + [
    "Are you legally authorized to work in the United States?",
    "Will you now, or in the future, require sponsorship for employment visa status (e.g. H-1B)?",
    "City, State location",
]


def test_tripledot_form_is_blocked():
    status, reason = classify(TRIPLEDOT)
    assert status == BLOCKED
    assert "right to work" in reason and "office" in reason


def test_1191_form_is_blocked():
    status, reason = classify(JOB_1191)
    assert status == BLOCKED
    assert "sponsorship" in reason and "City, State" in reason


@pytest.mark.parametrize("label", [
    "Where are you based?",
    "Which time zone do you work in?",
    "Are you comfortable working remotely across time zones?",
    "What are your salary expectations?",
    "Office 365 proficiency level",
])
def test_ordinary_questions_do_not_block(label):
    assert classify(STANDARD + [label])[0] == CLEAR


def test_standard_form_only_is_clear_not_cleared():
    status, reason = classify(STANDARD)
    assert status == CLEAR
    assert "no known disqualifier" in reason


def test_labels_from_payload_reads_both_question_lists():
    data = {
        "questions": [{"label": "First Name"}, {"label": "  Do you have right to work in the UK?  "}],
        "location_questions": [{"label": "Location (City)"}],
        "compliance": [{"questions": [{"label": "Gender"}]}],   # EEOC block: ignored
    }
    assert labels_from_payload(data) == [
        "First Name", "Do you have right to work in the UK?", "Location (City)",
    ]


def test_labels_from_payload_tolerates_missing_keys():
    assert labels_from_payload({}) == []
    assert labels_from_payload({"questions": None}) == []
