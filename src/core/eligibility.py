"""Eligibility gate: read the ATS application form, not the description.

Why this stage exists (2026-07-30, job 1191): every decisive eligibility
signal lived in the application FORM -- "Are you legally authorized to work
in the United States?", "Will you require sponsorship?" -- never in the
description the scorer reads. No prompt change could have caught it; the
information was never in the scorer's input. So eligibility is a HARD GATE
that runs before scoring, not a scoring dimension: a score answers "how good
a match", this answers "can this person hold the job at all".

Three verdicts, deliberately not two:
  - "blocked": the form asks a question a Turkey-based contractor must answer
    against themselves (right to work in X, sponsorship, relocation, office
    days). Scoring and drafting skip the row.
  - "clear": the form was read and none of the known phrases appeared. This
    is NOT a clearance -- only "no known disqualifier on the form". The human
    gate in src/apply.py still runs.
  - "unknown": no form could be read (the source has no ATS form API, or the
    posting is gone). The row continues to scoring; absence of evidence is not
    a reason to block, and blocking it would empty the pool.

Only Greenhouse exposes its form publicly (`?questions=true`), so today the
gate's reach is exactly as wide as greenhouse.SLUGS. Growing that list is what
widens it.
"""

import re

import requests

from src.adapters.greenhouse import BASE_URL, TIMEOUT

BLOCKED, CLEAR, UNKNOWN = "blocked", "clear", "unknown"

# (pattern, reason). Matched case-insensitively against each form label.
# Each pattern is a question a Turkey-based contractor answers against
# themselves. Keep them narrow: "Where are you based?" is an ordinary
# question on worldwide roles and must NOT block.
BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"right to work in", "right to work in a specific country"),
    (r"authori[sz]ed to work in", "work authorization in a specific country"),
    (r"sponsorship", "visa sponsorship question"),
    (r"based in the country|require relocation", "must be in-country or relocate"),
    (r"days? a week in the office|\bin-office\b", "office attendance required"),
    (r"\bcity,\s*state\b", "US-style 'City, State' location field"),
)


def labels_from_payload(data: dict) -> list[str]:
    """Collect question labels from a Greenhouse job payload.

    Custom questions live under `questions`; some boards add
    `location_questions`. Standard fields (name, email, resume) are labels
    too and simply match nothing.
    """
    labels: list[str] = []
    for key in ("questions", "location_questions"):
        for q in data.get(key) or []:
            label = (q.get("label") or "").strip()
            if label:
                labels.append(label)
    return labels


def classify(labels: list[str]) -> tuple[str, str]:
    """Pure verdict from a list of form labels: (BLOCKED|CLEAR, reason)."""
    hits: list[str] = []
    for label in labels:
        low = label.lower()
        for pattern, reason in BLOCK_PATTERNS:
            if re.search(pattern, low):
                hits.append(f"{reason}: {label[:120]!r}")
                break  # one reason per label is enough
    if hits:
        return BLOCKED, "; ".join(hits)
    return CLEAR, f"{len(labels)} form labels read, no known disqualifier"


def check_greenhouse(external_id: str) -> tuple[str, str] | None:
    """Fetch one Greenhouse form and classify it.

    `external_id` is "<slug>:<job id>" (see normalize_greenhouse). Returns
    None on a transient failure so the row stays unchecked and is retried on
    the next run; a 404 is final (the posting is gone) and returns UNKNOWN.
    """
    slug, _, job_id = external_id.partition(":")
    if not slug or not job_id:
        return UNKNOWN, f"unparseable external_id {external_id!r}"
    url = f"{BASE_URL}/{slug}/jobs/{job_id}"
    try:
        resp = requests.get(url, params={"questions": "true"}, timeout=TIMEOUT,
                            headers={"User-Agent": "job-search-orchestrator (personal use)"})
    except requests.RequestException as e:
        print(f"  [eligibility] {external_id}: network error, will retry ({e})")
        return None
    if resp.status_code == 404:
        return UNKNOWN, "posting no longer on the ATS (404)"
    if not resp.ok:
        print(f"  [eligibility] {external_id}: HTTP {resp.status_code}, will retry")
        return None
    return classify(labels_from_payload(resp.json()))


def run_eligibility(conn) -> dict:
    """Gate prefiltered, not-yet-checked jobs; update rows in place.

    Does NOT commit -- the caller owns the transaction boundary (same rule as
    run_prefilter). No paid call happens here, so losing an uncommitted batch
    to a crash costs only a re-fetch.
    """
    rows = conn.execute(
        "SELECT id, source, external_id, title FROM jobs "
        "WHERE prefilter_pass = 1 AND eligibility IS NULL"
    ).fetchall()

    counts = {BLOCKED: 0, CLEAR: 0, UNKNOWN: 0, "retry": 0}
    for row in rows:
        if row["source"] == "greenhouse":
            verdict = check_greenhouse(row["external_id"])
        else:
            verdict = (UNKNOWN, f"source {row['source']!r} exposes no application form")
        if verdict is None:
            counts["retry"] += 1
            continue
        status, reason = verdict
        conn.execute(
            "UPDATE jobs SET eligibility = %s, eligibility_reason = %s WHERE id = %s",
            (status, reason, row["id"]),
        )
        counts[status] += 1
        if status == BLOCKED:
            print(f"  [blocked] {row['title']} -- {reason}")
    return {"processed": len(rows), **counts}


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.core.storage import get_connection

    load_dotenv()                 # DATABASE_URL -> environment
    conn = get_connection()
    try:
        print(f"[eligibility] {run_eligibility(conn)}")
        conn.commit()
    finally:
        conn.close()
