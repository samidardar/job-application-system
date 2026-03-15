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
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=86400,  # 24h
)

# Import beat schedule after app creation
from worker.beat_schedule import setup_beat_schedule
setup_beat_schedule(celery_app)
