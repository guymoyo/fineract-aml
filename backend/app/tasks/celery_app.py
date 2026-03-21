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
        "compute-credit-scores": {
            "task": "app.tasks.credit_scoring.compute_all_credit_scores",
            "schedule": 86400.0,  # Daily (nightly)
        },
        "retrain-credit-cluster-model": {
            "task": "app.tasks.credit_scoring.retrain_credit_cluster_model",
            "schedule": 604800.0,  # Weekly
        },
        "poll-fineract-transactions": {
            "task": "app.tasks.polling.poll_fineract_transactions",
            "schedule": 60.0,  # Every 60 seconds (fallback if webhooks fail)
        },
        "enforce-data-retention": {
            "task": "app.tasks.retention.enforce_data_retention",
            "schedule": 2592000.0,  # Monthly (30 days)
        },
        "sync-watchlists": {
            "task": "app.tasks.watchlist_sync.sync_all_watchlists",
            "schedule": 21600.0,  # Every 6 hours
        },
    },
)

celery_app.conf.update(include=[
    "app.tasks.analysis",
    "app.tasks.training",
    "app.tasks.credit_scoring",
    "app.tasks.polling",
    "app.tasks.retention",
    "app.tasks.watchlist_sync",
])
