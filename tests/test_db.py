"""Integration tests for lena.db.

These tests require a running PostgreSQL instance with the pgvector extension.
They are skipped automatically when LENA_TEST_DB_URL is not set.

Run with:
    LENA_TEST_DB_URL="postgresql+psycopg://lena:secret@localhost:5432/lena_test" \
        pytest tests/test_db.py -m integration
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Skip marker — applied to every test in this module via autouse fixture.
# ---------------------------------------------------------------------------
_TEST_DB_URL = os.environ.get("LENA_TEST_DB_URL")
_SKIP_REASON = (
    "LENA_TEST_DB_URL not set — integration tests require a running PostgreSQL "
    "instance with the pgvector extension installed."
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_test_db():
    if not _TEST_DB_URL:
        pytest.skip(_SKIP_REASON)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_url() -> str:
    return _TEST_DB_URL  # type: ignore[return-value]  # guarded by autouse fixture


@pytest.fixture(scope="module")
def patched_env(db_url: str):
    """Patch DATABASE_URL for the duration of the module."""
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    yield
    if original is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original


@pytest.fixture(scope="module")
def migrated_db(patched_env):  # noqa: ARG001
    """Run migrations once per module; yield nothing (side-effect only)."""
    from lena.db.connection import run_migrations

    run_migrations()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_migrations_succeeds(migrated_db):  # noqa: ARG001
    """run_migrations() completes without raising."""
    # Reaching here means no exception was raised.
    pass


def test_run_migrations_is_idempotent(patched_env):  # noqa: ARG001
    """Calling run_migrations() twice does not raise."""
    from lena.db.connection import run_migrations

    run_migrations()
    run_migrations()  # second call must be a no-op


def test_get_pool_returns_working_connection(patched_env):  # noqa: ARG001
    """get_pool() opens and executes a trivial query."""
    from lena.db.connection import get_pool

    pool = get_pool(min_size=1, max_size=2)
    pool.open()
    try:
        with pool.connection() as conn:
            row = conn.execute("SELECT 1 AS val").fetchone()
            assert row is not None
            assert row[0] == 1
    finally:
        pool.close()


def test_mem0_memories_table_exists_after_migration(migrated_db):  # noqa: ARG001
    """mem0_memories table has the expected columns after migration."""
    import psycopg

    dsn = _psycopg_dsn_from_url()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'mem0_memories'
            ORDER BY ordinal_position
            """
        ).fetchall()

    columns = {r[0]: r[1] for r in rows}
    assert "id" in columns
    assert "user_id" in columns
    assert "session_id" in columns
    assert "memory" in columns
    assert "embedding" in columns
    assert "metadata" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_lena_team_memory_table_exists_after_migration(migrated_db):  # noqa: ARG001
    """lena_team_memory table has the expected columns after migration."""
    import psycopg

    dsn = _psycopg_dsn_from_url()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'lena_team_memory'
            ORDER BY ordinal_position
            """
        ).fetchall()

    columns = {r[0] for r in rows}
    expected = {"id", "team_id", "project", "domain", "type", "content",
                "embedding", "metadata", "created_at", "updated_at"}
    assert expected.issubset(columns)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _psycopg_dsn_from_url() -> str:
    url = _TEST_DB_URL or ""
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url
