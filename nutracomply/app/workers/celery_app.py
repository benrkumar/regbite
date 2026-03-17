from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "regbite",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.scrape_task", "app.workers.recheck_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        # Run FSSAI scraper daily at 00:30 IST
        "daily-fssai-scrape": {
            "task": "app.workers.scrape_task.run_fssai_scrape",
            "schedule": crontab(hour=0, minute=30),
        },
    },
)
