"""Deploy gate: assert the operator apply route's gate behaves. Exit 1 on any
failure.

Exercises POST /api/operator/jobs/{id}/apply end to end against a THROWAWAY
Postgres database named by SCRATCH_DATABASE_URL — never DATABASE_URL, the
live store. The probe refuses to run if the two are equal or if the scratch
URL is unset: an 'applied' event is real, semi-terminal data and must never be
fired at the live store by a test.

The database is swapped by monkeypatching storage.get_connection as seen from
src.api.db; the pg_writer_conn DEPENDENCY is left untouched, so the auth this
probe asserts is the REAL Depends(require_operator) that ships. That is
deliberate: the write path is the dependency re-wired at cutover, and if a
future writer dep forgets require_operator, the no-token / wrong-token checks
below turn red. A gate that has only ever passed is untested; this one asserts
the route both REJECTS (401/400/404/409) and APPLIES (200), and that the
resulting trail honors verify_invariants — read back from a SEPARATE
connection after the request has exited, so a missing commit cannot hide
behind the request's own transaction.

Single authority unchanged: the transition still runs through apply_to_job ->
_apply_transition. This probe proves the HTTP surface funnels into it
correctly; it does not reimplement it.

Setup (once, as the schema-owning peer-auth OS user):
    createdb orchestrator_scratch
    SCRATCH_DATABASE_URL=postgresql:///orchestrator_scratch python -m probes.apply_gate
The probe applies db/schema.sql itself (idempotent) and TRUNCATEs both tables
at the start of every run.
"""
import os
import sys

# Dummy env so module-load reads succeed with no live Postgres and a known
# token. setdefault: a configured shell keeps its real values; a fresh shell
# still runs. DATABASE_URL is never connected to by this probe.
os.environ.setdefault("OPERATOR_TOKEN", "probe-token")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/none")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.db as dbmod
from db.apply_schema import apply_schema
from src.api.routes_operator import router
from src.core.storage import get_connection as _real_get_connection
from src.core.tracking import verify_invariants

TOKEN = os.environ["OPERATOR_TOKEN"]
SCRATCH = os.environ.get("SCRATCH_DATABASE_URL")

if not SCRATCH:
    print("apply gate REFUSED: SCRATCH_DATABASE_URL is unset (a throwaway "
          "Postgres database is required; this probe writes 'applied' events)")
    sys.exit(2)
if SCRATCH == os.environ["DATABASE_URL"]:
    print("apply gate REFUSED: SCRATCH_DATABASE_URL equals DATABASE_URL "
          "(would fire 'applied' events at the live store)")
    sys.exit(2)


def _seed():
    """Idempotent scratch setup: ensure schema, wipe, insert two known jobs.

    Job 1 is clean; job 2 carries two red-flag phrases. Explicit ids so the
    assertions below can name them.
    """
    apply_schema(SCRATCH)
    c = _real_get_connection(SCRATCH)
    try:
        c.execute("TRUNCATE job_events, jobs RESTART IDENTITY CASCADE")
        c.execute(
            "INSERT INTO jobs (id, source, external_id, status, title, company, "
            "location, url, description) VALUES "
            "(1, 'probe', 'p1', 'new', 'Data Analyst', 'Acme', 'Remote', "
            " 'http://x', 'Fully remote, work anywhere.'), "
            "(2, 'probe', 'p2', 'new', 'BI Dev', 'Globex', 'US', "
            " 'http://y', 'Must be located in the US. No sponsorship.')"
        )
        c.commit()
    finally:
        c.close()


def main():
    _seed()
    # Swap the DB under the REAL dependency: pg_writer_conn still runs its
    # Depends(require_operator); only the connection it opens points at scratch.
    dbmod.get_connection = lambda: _real_get_connection(SCRATCH)

    app = FastAPI()
    app.include_router(router)
    cl = TestClient(app)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    bad = {"Authorization": "Bearer wrong"}
    U = "/api/operator/jobs/{}/apply"

    violations = []

    def check(label, r, want_status, want_pred=None):
        if r.status_code != want_status:
            violations.append(f"{label}: status {r.status_code} != {want_status} ({r.json()})")
            return
        if want_pred:
            try:
                ok = want_pred(r.json())
            except Exception:
                ok = False
            if not ok:
                violations.append(f"{label}: body predicate failed ({r.json()})")

    # --- auth: the checks that turn red if a cutover drops require_operator ---
    # No confirm: a dropped-auth request must not WRITE while we're proving the
    # gate — it stops at the confirm gate (409), keeping job1 pristine.
    check("no token", cl.post(U.format(1), json={"note": "n"}), 401)
    check("wrong token", cl.post(U.format(1), json={"note": "n"}, headers=bad), 401)

    # --- not found ---
    check("missing job", cl.post(U.format(999), json={"note": "n", "confirm": True}, headers=auth), 404)

    # --- clean job 1: gate then apply ---
    check("no confirm -> surface", cl.post(U.format(1), json={"note": "N"}, headers=auth), 409,
          lambda b: b["detail"]["error"] == "confirmation required" and b["detail"]["red_flags"] == [])
    check("empty note", cl.post(U.format(1), json={"note": "  ", "confirm": True}, headers=auth), 400)
    check("apply", cl.post(U.format(1), json={"note": "Greenhouse 07-22", "confirm": True}, headers=auth), 200,
          lambda b: b["status"] == "applied")
    check("re-apply illegal", cl.post(U.format(1), json={"note": "again", "confirm": True}, headers=auth), 409)

    # --- red-flag job 2: escalation ---
    check("flags, no ack -> refuse", cl.post(U.format(2), json={"note": "x", "confirm": True}, headers=auth), 409,
          lambda b: b["detail"]["red_flags"])
    check("flags, ack -> apply", cl.post(
        U.format(2), json={"note": "x", "confirm": True, "acknowledge_red_flags": True}, headers=auth), 200,
        lambda b: b["status"] == "applied")

    # --- the writes are real, COMMITTED, and honor the invariants ---
    # A fresh connection sees only committed data. If the route reported 200
    # but never committed, both counts below read 0 and this turns red.
    v = _real_get_connection(SCRATCH)
    try:
        applied = v.execute(
            "SELECT count(*) AS n FROM jobs WHERE status = 'applied'"
        ).fetchone()["n"]
        events = v.execute(
            "SELECT count(*) AS n FROM job_events WHERE to_status = 'applied'"
        ).fetchone()["n"]
        inv = verify_invariants(v)
    finally:
        v.close()
    if applied != 2:
        violations.append(f"persisted applied jobs = {applied}, expected 2 (missing commit?)")
    if events != 2:
        violations.append(f"persisted applied events = {events}, expected 2 (missing commit?)")
    if inv:
        violations.append(f"invariants violated after applies: {inv}")

    if violations:
        print(f"apply gate FAILED ({len(violations)}):")
        for x in violations:
            print(f"  {x}")
        sys.exit(1)
    print("apply gate OK: auth 401s, confirm surface, red-flag escalation, "
          "2 applied writes committed and visible from a fresh connection, "
          "invariants clean")
    sys.exit(0)


if __name__ == "__main__":
    main()
