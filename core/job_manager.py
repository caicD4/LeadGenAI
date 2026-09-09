import threading
import traceback
import uuid

from database.database import (
    create_job_in_db,
    update_job_in_db,
    get_job_from_db,
)


# In-memory cache for fast reads (avoids a DB query on every poll).
# The DB is the source of truth — this cache is rebuilt from the DB
# on server restart via get_job().
_jobs_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _update_cache(job_id: str, data: dict):
    with _cache_lock:
        _jobs_cache[job_id] = data


def create_job() -> str:
    job_id = str(uuid.uuid4())

    initial = {
        "status": "queued",
        "progress": 0,
        "message": "Job queued...",
        "leads": [],
    }

    # Persist to DB first, then cache.
    create_job_in_db(job_id)
    _update_cache(job_id, initial)

    print(f"[JobManager] Created job {job_id[:8]}")
    return job_id


def update_job(
    job_id: str,
    status: str,
    progress: int,
    message: str,
    leads=None,
):
    with _cache_lock:
        existing = _jobs_cache.get(job_id, {})
        updated = {
            "status": status,
            "progress": progress,
            "message": message,
            "leads": leads if leads is not None else existing.get("leads", []),
        }
        _jobs_cache[job_id] = updated

    # Persist to DB (survives server restarts).
    update_job_in_db(job_id, status, progress, message, leads)


def get_job(job_id: str) -> dict | None:
    # 1. Try in-memory cache first (fast path).
    with _cache_lock:
        cached = _jobs_cache.get(job_id)

    if cached is not None:
        return cached

    # 2. Cache miss — server may have restarted; fall back to DB.
    print(
        f"[JobManager] Cache miss for job {job_id[:8]} — reading from DB."
    )
    db_job = get_job_from_db(job_id)

    if db_job is not None:
        # Warm the cache.
        _update_cache(job_id, db_job)

    return db_job  # None if not in DB either.


def run_in_background(job_id: str, function, *args, **kwargs):
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, function, args, kwargs),
        daemon=True,
    )
    thread.start()


def _run_job(job_id: str, function, args, kwargs):
    short = job_id[:8]

    try:
        print(f"[JobManager] Job {short} starting...")

        update_job(job_id, "running", 10, "Starting lead generation...")

        print(f"[JobManager] Job {short} calling worker function...")

        # Pass job_id as keyword arg so the orchestrator can push
        # live progress updates back through update_job().
        result = function(*args, **kwargs, job_id=job_id)

        lead_count = len(result) if result else 0
        print(f"[JobManager] Job {short} returned {lead_count} lead(s).")

        update_job(
            job_id,
            "completed",
            100,
            "Lead generation complete.",
            result,
        )

        print(f"[JobManager] Job {short} -> completed")

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        full_trace = traceback.format_exc()

        print(f"[JobManager] Job {short} -> FAILED: {error_msg}")
        print(full_trace)

        update_job(
            job_id,
            "failed",
            100,
            f"Error: {error_msg}",
        )