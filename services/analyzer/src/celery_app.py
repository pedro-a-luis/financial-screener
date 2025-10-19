"""
Celery Application Configuration

This module configures Celery for distributed task processing across
the Raspberry Pi cluster. Each Pi node runs Celery workers that execute
analysis tasks using Polars for high-performance data processing.
"""

from celery import Celery
from kombu import Queue

from config import Settings

# Load settings
settings = Settings()

# Create Celery app
app = Celery(
    "financial-screener-analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Celery configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
    },
    # Task routing
    task_routes={
        "tasks.analyze_stock": {"queue": "stock_analysis"},
        "tasks.analyze_etf": {"queue": "etf_analysis"},
        "tasks.analyze_bond": {"queue": "bond_analysis"},
        "tasks.screen_stocks": {"queue": "screening"},
        "tasks.calculate_recommendations": {"queue": "recommendations"},
    },
    # Queue definitions
    task_queues=(
        Queue("stock_analysis", routing_key="stock.#"),
        Queue("etf_analysis", routing_key="etf.#"),
        Queue("bond_analysis", routing_key="bond.#"),
        Queue("screening", routing_key="screening.#"),
        Queue("recommendations", routing_key="recommendations.#"),
    ),
    # Performance tuning for Raspberry Pi
    broker_pool_limit=10,
    broker_connection_timeout=30,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# Auto-discover tasks
# Since PYTHONPATH includes /app/src, we can import directly
app.autodiscover_tasks(["tasks"])

if __name__ == "__main__":
    app.start()
