"""Postgres-backed job worker (FOR UPDATE SKIP LOCKED). Runs embedded in the API process by default;
can also run standalone:  python -m app.worker"""
import asyncio, logging

from .db import ex, pool, q1, tx
from .services.deletion import process_deletion
from .eval.runner import process_eval_run
from .services.ingest import process_job
from .services.mailer import send_pending

log = logging.getLogger("worker")


async def claim_ingest_job():
    async with tx(bypass=True) as conn:
        return await q1(conn, """UPDATE processing_jobs SET status='running', started_at=now(), attempts=attempts+1, stage='extract', progress_pct=1
                                 WHERE id = (SELECT id FROM processing_jobs WHERE status='queued' ORDER BY created_at
                                             FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""")


async def claim_eval_run():
    async with tx(bypass=True) as conn:
        return await q1(conn, """UPDATE eval_runs SET status='running', started_at=now(), progress_pct=1, message='Starting'
                                 WHERE id = (SELECT id FROM eval_runs WHERE status='queued' ORDER BY created_at
                                             FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""")


async def requeue_stale():
    async with tx(bypass=True) as conn:
        await ex(conn, "UPDATE processing_jobs SET status='queued' WHERE status='running' AND started_at < now() - interval '15 minutes'")
        await ex(conn, "UPDATE eval_runs SET status='failed', error='The worker restarted while this run was in progress.' WHERE status='running' AND started_at < now() - interval '90 minutes'")
        await ex(conn, "UPDATE deletion_jobs SET status='failed' WHERE status='running' AND created_at < now() - interval '30 minutes'")


async def run_worker(stop: asyncio.Event):
    log.info("worker started")
    last_sweep = 0.0
    loop = asyncio.get_event_loop()
    while not stop.is_set():
        try:
            if loop.time() - last_sweep > 60:
                await requeue_stale()
                last_sweep = loop.time()
            job = await claim_ingest_job()
            if job:
                await process_job(job)
                continue
            if await process_deletion():
                continue
            run = await claim_eval_run()
            if run:
                await process_eval_run(run)
                continue
            if await send_pending():
                continue
        except Exception:
            log.exception("worker loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    async def main():
        await pool.open()
        stop = asyncio.Event()
        await run_worker(stop)
    asyncio.run(main())
