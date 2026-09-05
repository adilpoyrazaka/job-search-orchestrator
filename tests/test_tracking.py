import pytest

from src.core.tracking import (
    REQUIRES_NOTE,
    TRANSITIONS,
    TransitionError,
    apply_to_job,
    scan_red_flags,
    status_domain_sql,
    transition,
)


def test_transition_graph_is_closed():
    # every destination is itself a known state (no dangling targets)
    for src, dests in TRANSITIONS.items():
        for d in dests:
            assert d in TRANSITIONS, f"{src} -> {d}: unknown state"


def test_terminal_states_have_no_exits():
    assert TRANSITIONS["archived"] == set()
    assert TRANSITIONS["rejected"] == set()


def test_applied_is_reachable_only_from_new_or_drafted():
    sources = {s for s, dests in TRANSITIONS.items() if "applied" in dests}
    assert sources == {"new", "drafted"}


def test_every_state_can_reach_archived_except_terminals():
    for state, dests in TRANSITIONS.items():
        if dests:
            assert "archived" in dests, state


def test_status_domain_sql_names_every_state_once():
    sql = status_domain_sql()
    states = set(TRANSITIONS) | {d for ds in TRANSITIONS.values() for d in ds}
    assert sql.startswith("CHECK (status IN (")
    for s in states:
        assert sql.count(f"'{s}'") == 1


def test_requires_note_destinations_exist():
    assert REQUIRES_NOTE <= set(TRANSITIONS)


@pytest.mark.parametrize(
    "text",
    [
        "Must be located in the US. No sponsorship.",
        "U.S. only",
        "Candidates must reside within the EU",
        "Working hours UTC+1 to UTC+3",
        "We are unable to sponsor visas",
    ],
)
def test_scan_red_flags_hits(text):
    assert scan_red_flags(text)


@pytest.mark.parametrize("text", ["Fully remote, work anywhere.", "", None])
def test_scan_red_flags_clean(text):
    assert scan_red_flags(text) == []


def test_scan_red_flags_is_case_insensitive_and_returns_matched_text():
    hits = scan_red_flags("NO SPONSORSHIP available")
    assert hits == ["NO SPONSORSHIP"]


def test_transition_refuses_applied_before_touching_the_db():
    # conn=None: if the guard ran after any DB access this would raise
    # AttributeError, not TransitionError.
    with pytest.raises(TransitionError, match="apply_to_job"):
        transition(None, 1, "applied", note="x")


def test_apply_to_job_refuses_unauthorized_before_touching_the_db():
    with pytest.raises(TransitionError, match="not authorized"):
        apply_to_job(None, 1, "note", authorized=False)
