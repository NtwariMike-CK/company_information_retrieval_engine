"""Async PostgreSQL access. Every request runs inside a transaction that sets the
Row-Level-Security context (company or bypass), so RLS in schema.sql is enforced."""
from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .settings import settings

pool = AsyncConnectionPool(
    settings.database_url.replace("postgres://", "postgresql://", 1),
    min_size=1, max_size=settings.db_pool_max, open=False,
    kwargs={"row_factory": dict_row},
)


@asynccontextmanager
async def tx(company_id=None, bypass: bool = False):
    async with pool.connection() as conn:
        async with conn.transaction():
            if bypass:
                await conn.execute("SELECT set_config('app.bypass_rls','on',true)")
            elif company_id is not None:
                await conn.execute("SELECT set_config('app.current_company_id',%s,true)", (str(company_id),))
            yield conn


async def q(conn, sql, *args):
    cur = await conn.execute(sql, args or None)
    return await cur.fetchall()


async def q1(conn, sql, *args):
    cur = await conn.execute(sql, args or None)
    return await cur.fetchone()


async def ex(conn, sql, *args):
    await conn.execute(sql, args or None)
