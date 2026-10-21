from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from .config import settings

_pool: ConnectionPool | None = None


def _configure(conn):
    register_vector(conn)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=8,
                               kwargs={"row_factory": dict_row}, configure=_configure, open=True)
    return _pool


@contextmanager
def session_cursor(session_id: str):
    """API connections run as the low-privilege role; RLS keys off app.session_id."""
    with pool().connection() as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SELECT set_config('app.session_id', %s, true)", (session_id,))
            yield cur


def owner_connection():
    """Worker/ingestion connection as table owner (bypasses RLS)."""
    conn = psycopg.connect(settings.database_owner_url, row_factory=dict_row)
    register_vector(conn)
    return conn
