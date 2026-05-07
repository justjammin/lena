from __future__ import annotations

import os
from pathlib import Path

from psycopg_pool import ConnectionPool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _dsn_from_config() -> str:
    """Construct a postgresql+psycopg:// DSN from lena.config.yaml vector_store block."""
    from ..config import load_config  # local import avoids circular deps at module load
    cfg = load_config()
    vc = cfg.memory.mem0.vector_store.get("config", {})
    user = vc.get("user", "lena")
    password = vc.get("password", "")
    host = vc.get("host", "localhost")
    port = vc.get("port", 5432)
    dbname = vc.get("dbname", "lena")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = _dsn_from_config()
    return url


def _psycopg_dsn() -> str:
    """Return a plain libpq DSN for psycopg3 (no SQLAlchemy driver prefix)."""
    url = _database_url()
    # Strip sqlalchemy driver prefix if present so psycopg can parse it.
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def get_engine() -> AsyncEngine:
    """Return a SQLAlchemy async engine backed by psycopg3.

    The engine is created fresh on each call; cache it at call-site if needed.
    Connection URL is read from DATABASE_URL with scheme postgresql+psycopg://.
    """
    url = _database_url()
    # Ensure the correct async driver prefix for SQLAlchemy.
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = "postgresql+psycopg" + url[url.index("://"):]
    elif not url.startswith("postgresql+psycopg"):
        raise ValueError(
            f"DATABASE_URL must use postgresql+psycopg:// scheme, got: {url[:30]}..."
        )
    return create_async_engine(url, pool_pre_ping=True)


def get_pool(min_size: int = 2, max_size: int = 10) -> ConnectionPool:
    """Return a psycopg3 ConnectionPool.

    Caller is responsible for opening (pool.open()) and closing (pool.close()).
    """
    dsn = _psycopg_dsn()
    return ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False)


def run_migrations(engine: AsyncEngine | None = None) -> None:  # noqa: ARG001
    """Apply all *.sql migrations in lena/db/migrations/ in filename-sorted order.

    Tracks applied migrations in a `lena_migrations` table so each file is only
    executed once.  Safe to call multiple times — fully idempotent.

    Uses a direct psycopg3 connection (sync) so it can be called from
    application startup before the async event loop is running.

    Files matching '003_hnsw*' are never auto-applied (reference/future only).
    """
    import psycopg  # local import keeps startup cost zero when DB unused

    dsn = _psycopg_dsn()

    with psycopg.connect(dsn, autocommit=True) as conn:
        # Ensure the migration tracking table exists.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lena_migrations (
                filename   text        PRIMARY KEY,
                applied_at timestamptz DEFAULT now()
            )
            """
        )

        sql_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for migration_path in sql_files:
            # 003_hnsw_migration.sql is a reference-only file — never auto-apply.
            if migration_path.name.startswith("003_hnsw"):
                continue

            # Skip if already recorded in lena_migrations.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM lena_migrations WHERE filename = %s",
                    (migration_path.name,),
                )
                if cur.fetchone():
                    continue

            # Apply migration + record it atomically.
            migration_sql = migration_path.read_text()
            with conn.transaction():
                conn.autocommit = False
                conn.execute(migration_sql)
                conn.execute(
                    "INSERT INTO lena_migrations (filename) VALUES (%s)"
                    " ON CONFLICT DO NOTHING",
                    (migration_path.name,),
                )
            conn.autocommit = True
