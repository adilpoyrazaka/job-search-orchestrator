"""Test environment: the API modules fail closed at import without these two
variables, so set dummies before any test imports them. No test in this
directory opens a database connection; the deploy gates in probes/ do that."""
import os

os.environ.setdefault("OPERATOR_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/none")
