"""
Dynamic Celery Beat schedule.
Registers a daily pipeline task per active user at 08:00 Europe/Paris (07:00 UTC).
A refresh task runs every 5 minutes to pick up new users.
"""
from celery import Celery
from celery.schedules import crontab


def setup_beat_schedule(app: Celery) -> None:
    """Configure the static beat schedule entries."""
    app.conf.beat_schedule = {
        # Refresh dynamic user schedules every 5 minutes
        "refresh-user-schedules": {
            "task": "worker.tasks.maintenance_tasks.refresh_user_beat_schedules",
            "schedule": crontab(minute="*/5"),
        },
        # Follow-up emails: daily at 09:00 Paris (08:00 UTC)
        "process-followups": {
            "task": "worker.tasks.pipeline_tasks.process_all_followups",
            "schedule": crontab(hour=8, minute=0),
        },
        # Cleanup old data: weekly on Sunday at 02:00 UTC
        "cleanup-old-data": {
            "task": "worker.tasks.maintenance_tasks.cleanup_old_data",
            "schedule": crontab(hour=2, minute=0, day_of_week=0),
        },
    }
