from celery import Celery
from resonant_common.config import settings

app = Celery("resonant", broker=settings.redis_url, include=["worker.tasks"])
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=240,      # hard ceilings: nothing runs unbounded
    task_time_limit=300,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"socket_timeout": 5, "socket_connect_timeout": 5, "visibility_timeout": 900},
    beat_schedule={"purge-expired": {"task": "resonant.purge_expired", "schedule": 900.0}},
)
