from celery import Celery
from app.config import settings

celery_app = Celery(
    "postulio",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "worker.tasks.pipeline_tasks",
        "worker.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,
    task_track_started=True,

    # Reliability settings
    task_acks_late=True,                    # Ack after task finishes (not before) → safe on crash
    worker_prefetch_multiplier=1,           # One task at a time per worker process
    task_reject_on_worker_lost=True,        # Re-queue task if worker dies mid-execution

    # Timeouts — prevent hung Playwright sessions from blocking a worker indefinitely
    task_soft_time_limit=1800,             # 30 min: sends SIGUSR1 → worker can clean up
    task_time_limit=2100,                  # 35 min: hard kill if soft limit ignored

    # Results
    result_expires=86400,                  # 24h result TTL

    # RedBeat for distributed-safe Beat scheduling (prevents duplicate tasks on restart)
    # Install: pip install redbeat
    redbeat_redis_url=settings.redis_url,
    redbeat_lock_timeout=5 * 60,           # Lock expires after 5 min (auto-recovery)
)

# Import beat schedule after app creation
from worker.beat_schedule import setup_beat_schedule
setup_beat_schedule(celery_app)
