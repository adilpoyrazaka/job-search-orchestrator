"""The public/private boundary, checked from the committed artifacts alone.

probes/grant_parity.py asks a live database the same question; this test asks
db/roles.sql, so it runs on a clean clone with no Postgres.
"""
import re
from pathlib import Path

from src.api.columns import EVENT_PUBLIC, EVENT_WITHHELD, PUBLIC, WITHHELD

ROLES_SQL = (Path(__file__).resolve().parents[1] / "db" / "roles.sql").read_text()
SCHEMA_SQL = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text()


def _schema_columns(table: str) -> set[str]:
    body = re.search(r"CREATE TABLE IF NOT EXISTS " + table + r" \((.*?)\n\);", SCHEMA_SQL, re.S)
    assert body, f"no CREATE TABLE for {table} in schema.sql"
    # column lines are indented four spaces and start with a lowercase identifier
    return set(re.findall(r"^    ([a-z_]+)\s+(?:integer|text|timestamptz)", body.group(1), re.M))


def _granted(table: str) -> set[str]:
    m = re.search(
        r"GRANT SELECT \(([^)]*)\)\s+ON " + table + r" TO public_reader", ROLES_SQL
    )
    assert m, f"no column-scoped SELECT grant for {table} in roles.sql"
    return {c.strip() for c in m.group(1).split(",")}


def test_withheld_columns_never_appear_in_the_public_allowlist():
    assert set(PUBLIC).isdisjoint(WITHHELD)
    assert set(EVENT_PUBLIC).isdisjoint(EVENT_WITHHELD)
    assert {"notes", "cover_letter"} <= set(WITHHELD)
    assert "note" in EVENT_WITHHELD


def test_every_schema_column_is_classified():
    # the static twin of build_demo's refuse-on-unclassified gate: a column
    # added to db/schema.sql without a publication decision fails here
    assert _schema_columns("jobs") == set(PUBLIC) | set(WITHHELD)
    assert _schema_columns("job_events") == set(EVENT_PUBLIC) | set(EVENT_WITHHELD)
    assert len(PUBLIC) == len(set(PUBLIC))          # no duplicates


def test_roles_sql_grants_exactly_the_public_allowlist():
    assert _granted("jobs") == set(PUBLIC)
    assert _granted("job_events") == set(EVENT_PUBLIC)


def test_public_reader_has_no_table_level_select():
    # a table-level SELECT would silently widen the boundary to every column
    assert not re.search(r"GRANT SELECT ON (jobs|job_events) TO public_reader", ROLES_SQL)
