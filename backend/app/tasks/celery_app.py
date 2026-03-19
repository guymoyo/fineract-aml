"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fineract_aml",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "retrain-anomaly-detector": {
            "task": "app.tasks.training.retrain_anomaly_detector",
            "schedule": 86400.0,  # Daily
        },
        "retrain-fraud-classifier": {
            "task": "app.tasks.training.retrain_fraud_classifier",
            "schedule": 604800.0,  # Weekly
        },
    },
)

celery_app.conf.update(include=["app.tasks.analysis", "app.tasks.training"])
