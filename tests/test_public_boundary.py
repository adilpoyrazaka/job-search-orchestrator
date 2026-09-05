"""The public/private boundary, checked from the committed artifacts alone.

probes/grant_parity.py asks a live database the same question; this test asks
db/roles.sql, so it runs on a clean clone with no Postgres.
"""
import re
from pathlib import Path

from seeds.build_demo import EVENT_PUBLIC, EVENT_WITHHELD, PUBLIC, WITHHELD

ROLES_SQL = (Path(__file__).resolve().parents[1] / "db" / "roles.sql").read_text()


def _granted(table: str) -> set[str]:
    m = re.search(
        r"GRANT SELECT \(([^)]*)\)\s+ON " + table + r" TO public_reader", ROLES_SQL
    )
    assert m, f"no column-scoped SELECT grant for {table} in roles.sql"
    return {c.strip() for c in m.group(1).split(",")}


def test_withheld_columns_never_appear_in_the_public_allowlist():
    assert PUBLIC.isdisjoint(WITHHELD)
    assert EVENT_PUBLIC.isdisjoint(EVENT_WITHHELD)
    assert {"notes", "cover_letter"} <= WITHHELD
    assert "note" in EVENT_WITHHELD


def test_roles_sql_grants_exactly_the_public_allowlist():
    assert _granted("jobs") == set(PUBLIC)
    assert _granted("job_events") == set(EVENT_PUBLIC)


def test_public_reader_has_no_table_level_select():
    # a table-level SELECT would silently widen the boundary to every column
    assert not re.search(r"GRANT SELECT ON (jobs|job_events) TO public_reader", ROLES_SQL)
