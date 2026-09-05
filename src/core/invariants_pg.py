"""Standalone deploy gate: the event-trail invariants, as a process that
exits 1 on violation. The check itself is tracking.verify_invariants; this
module only owns the DSN policy and the exit code.

Clauses (see tracking.verify_invariants):
  1. every non-'new' job has at least one event (no unevidenced state)
  2. every evented job's status equals its latest event's to_status
  3. every evented job's status_updated_at equals its latest event's at
  4. no event references a missing job (structurally impossible under the
     FK in db/schema.sql; kept as insurance against a dropped constraint)

Latest event: ORDER BY at DESC, id DESC -- the id tie-break is load-bearing
(two early events share an identical timestamp).

Clause 3 compares with IS DISTINCT FROM, so an evented job whose
status_updated_at is NULL is a violation, not a silent pass (a plain !=
would skip it: NULL != x is not true).

Standalone: python -m src.core.invariants_pg   (exit 1 on violations)
DSN: DATABASE_URL, with PG_DSN as an explicit override for pointing the
gate at a scratch store. Neither set raises at import -- a deploy gate
that can silently verify the wrong database is worse than no gate.
"""

import os
import sys

from src.core.storage import get_connection
from src.core.tracking import verify_invariants

PG_DSN = os.environ.get("PG_DSN") or os.environ["DATABASE_URL"]


def main() -> int:
    conn = get_connection(PG_DSN)
    try:
        problems = verify_invariants(conn)
    finally:
        conn.close()
    if problems:
        for p in problems:
            print(f"INVARIANT VIOLATION: {p}", file=sys.stderr)
        return 1
    print("invariants OK: 4 clauses, 0 violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
