"""Regression test guard: publishing_queue must never contain test artifacts.

The revenue-engine tests leaked real rows into the LIVE publishing_queue
(they use the real DB, no fakes). Assert the live queue has no 'test-' titles.
"""
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from database.connection import engine


def test_live_queue_has_no_test_artifacts():
    """Whatever else is queued, tests must never have left 'test-*' rows."""
    with engine.connect() as c:
        count = c.execute(text(
            "SELECT count(*) FROM publishing_queue WHERE title LIKE 'test-%'"
        )).scalar_one()
    assert count == 0, f"{count} test artifact row(s) leaked into publishing_queue"
