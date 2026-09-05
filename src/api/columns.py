"""The public/private column boundary. Single authority.

PUBLIC is the allowlist the public API selects and the columns build_demo
copies into the demo database. WITHHELD documents the refusals. A column in
neither list is unclassified: build_demo refuses to run, and
tests/test_public_boundary.py fails against db/schema.sql. A new column is
therefore private until someone lists it here.

The same lists are mirrored by db/roles.sql: public_reader is granted SELECT
on exactly PUBLIC / EVENT_PUBLIC. tests/test_public_boundary.py checks the
committed SQL; probes/grant_parity.py checks the live database.

Tuples, not sets: the public API joins these into SQL text, and column order
should not depend on Python's hash seed.
"""

# 'id' is public deliberately: job_events.job_id points at job ids. If a
# mirror re-numbered rows, an event would silently attach to whatever landed
# at its job_id -- a false claim, rendered confidently.
#
# score_reason is public by decision: every reason making a checkable claim
# was verified against the stored posting text (probes/reason_audit.py):
# 32/34 grounded; rows 412 and 616 carry unsupported eligibility claims and
# are published as evidence of the failure mode. Both errors favor the
# candidate, not the company. The dashboard flags those two rows.
PUBLIC: tuple[str, ...] = (
    "id", "source", "external_id", "url", "title", "company", "category",
    "job_type", "location", "salary", "description", "publication_date",
    "fetched_at", "content_hash", "prefilter_pass", "ladder_match",
    "relevance_score", "score_reason", "status", "status_updated_at",
)
WITHHELD: tuple[str, ...] = (
    # profile.md restated in prose; the one file that never enters the repo.
    "cover_letter",
    # hand-written private commentary on individual applications.
    "notes",
)

# job_events: the transitions ARE the public evidence; the notes are running
# commentary, including on in-progress hiring processes. Disclosing the state
# of an open negotiation is a choice, and this makes it deliberate.
EVENT_PUBLIC: tuple[str, ...] = ("id", "job_id", "from_status", "to_status", "at")
EVENT_WITHHELD: tuple[str, ...] = ("note",)

# Rows whose published score_reason failed the audit above. Rendered with a
# caveat by the dashboard; kept here so the list lives beside the decision.
FLAGGED_REASONS: tuple[int, ...] = (412, 616)
