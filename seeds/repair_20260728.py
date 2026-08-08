"""One-off repair: undo the accidental applied transition on job 1191.

House style: seeds/repair_20260718.py -- precondition-gated, dry-run-first,
single transaction, post-conditions verified before commit.

WHAT HAPPENED (2026-07-28): a verification run of the freshly ported
apply.py was answered 'y' at the confirm prompt instead of 'N'. Job 1191
moved drafted -> applied and event id 13 was appended carrying the note
'port verification, aborting at prompt'. No application was ever submitted
to Buyers Edge Platform, so both the status and the event are false.

WHY THIS RUNS AS THE OWNER: orchestrator_app is append-only on job_events
by permission -- it holds no DELETE. That is the design working correctly,
not an obstacle. This is a deliberate, documented owner-role repair.

WHAT IT DOES:
  - DELETE the job_events row id 13
  - restore jobs.status to 'drafted'
  - restore jobs.status_updated_at to event 12's `at`, read from the row
    itself rather than hardcoded

WHAT IT DELIBERATELY DOES NOT DO: reset the job_events sequence. The next
event will be id 14, leaving a visible gap at 13. That gap is the honest
trace that a row was removed; closing it would hide the repair.

Usage:
  python -m seeds.repair_20260728              # dry run (default)
  python -m seeds.repair_20260728 --execute    # performs the repair
  PG_DSN env var overrides the default DSN.
"""
import os
import sys

import psycopg

PG_DSN = os.environ.get("PG_DSN", "postgresql:///orchestrator")

JOB_ID = 1191
BAD_EVENT_ID = 13
PRIOR_EVENT_ID = 12
EXPECTED_JOBS = 440
EXPECTED_EVENTS_BEFORE = 13
EXPECTED_EVENTS_AFTER = 12
BAD_NOTE = "port verification, aborting at prompt"


def _one(pg, sql, params=()):
    with pg.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def preconditions(pg):
    n_jobs = _one(pg, "SELECT count(*) FROM jobs")[0]
    n_events = _one(pg, "SELECT count(*) FROM job_events")[0]
    if (n_jobs, n_events) != (EXPECTED_JOBS, EXPECTED_EVENTS_BEFORE):
        raise RuntimeError(
            f"store is {n_jobs} jobs / {n_events} events, expected "
            f"{EXPECTED_JOBS}/{EXPECTED_EVENTS_BEFORE}. Refusing."
        )

    status = _one(pg, "SELECT status FROM jobs WHERE id = %s", (JOB_ID,))
    if status is None or status[0] != "applied":
        raise RuntimeError(f"job {JOB_ID} is {status!r}, expected 'applied'. Refusing.")

    bad = _one(
        pg,
        "SELECT job_id, from_status, to_status, note FROM job_events WHERE id = %s",
        (BAD_EVENT_ID,),
    )
    if bad != (JOB_ID, "drafted", "applied", BAD_NOTE):
        raise RuntimeError(f"event {BAD_EVENT_ID} is {bad!r}, not the row to remove. Refusing.")

    latest = _one(
        pg,
        "SELECT id FROM job_events WHERE job_id = %s ORDER BY at DESC, id DESC LIMIT 1",
        (JOB_ID,),
    )
    if latest[0] != BAD_EVENT_ID:
        raise RuntimeError(f"latest event for {JOB_ID} is {latest[0]}, not {BAD_EVENT_ID}. Refusing.")

    prior = _one(
        pg,
        "SELECT at, to_status FROM job_events WHERE id = %s AND job_id = %s",
        (PRIOR_EVENT_ID, JOB_ID),
    )
    if prior is None or prior[1] != "drafted":
        raise RuntimeError(f"event {PRIOR_EVENT_ID} is {prior!r}, expected a 'drafted' row. Refusing.")

    print("preconditions OK")
    return prior[0]


def postconditions(pg):
    checks = [
        ("job count", f"SELECT count(*) = {EXPECTED_JOBS} FROM jobs"),
        ("event count", f"SELECT count(*) = {EXPECTED_EVENTS_AFTER} FROM job_events"),
        ("bad event gone", f"SELECT NOT EXISTS (SELECT 1 FROM job_events WHERE id = {BAD_EVENT_ID})"),
        ("job restored to drafted", f"SELECT status = 'drafted' FROM jobs WHERE id = {JOB_ID}"),
        ("non-new jobs evidenced",
         "SELECT NOT EXISTS (SELECT 1 FROM jobs j WHERE j.status <> 'new' "
         "AND NOT EXISTS (SELECT 1 FROM job_events e WHERE e.job_id = j.id))"),
        ("status matches latest event",
         "SELECT NOT EXISTS (SELECT 1 FROM jobs j JOIN LATERAL "
         "(SELECT to_status, at FROM job_events e WHERE e.job_id = j.id "
         "ORDER BY at DESC, id DESC LIMIT 1) le ON TRUE "
         "WHERE j.status <> le.to_status OR j.status_updated_at <> le.at)"),
    ]
    for name, sql in checks:
        if not _one(pg, sql)[0]:
            raise RuntimeError(f"POST-CONDITION FAILED: {name} (transaction rolls back)")
        print(f"  post-check OK: {name}")


def main() -> int:
    execute = "--execute" in sys.argv
    pg = psycopg.connect(PG_DSN)
    try:
        prior_at = preconditions(pg)
        print(f"  will DELETE job_events id {BAD_EVENT_ID} (job {JOB_ID}, drafted->applied)")
        print(f"  will SET jobs.status = 'drafted' for job {JOB_ID}")
        print(f"  will SET jobs.status_updated_at = {prior_at} (event {PRIOR_EVENT_ID}'s at)")

        if not execute:
            pg.rollback()
            print("DRY RUN -- nothing written. Re-run with --execute.")
            return 0

        with pg.cursor() as cur:
            cur.execute("DELETE FROM job_events WHERE id = %s", (BAD_EVENT_ID,))
            if cur.rowcount != 1:
                raise RuntimeError(f"DELETE touched {cur.rowcount} rows, expected 1.")
            cur.execute(
                "UPDATE jobs SET status = 'drafted', status_updated_at = %s WHERE id = %s",
                (prior_at, JOB_ID),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"UPDATE touched {cur.rowcount} rows, expected 1.")

        postconditions(pg)
        pg.commit()
        print("REPAIRED. Transaction committed.")
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
