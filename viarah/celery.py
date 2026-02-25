import os
import threading
import time

from celery import Celery
from celery.signals import worker_ready
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "viarah.settings.dev")

app = Celery("viarah")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

_heartbeat_started = False
_heartbeat_lock = threading.Lock()


def _heartbeat_seconds() -> int:
    raw = os.environ.get("CELERY_HEARTBEAT_SECONDS", "30")
    try:
        value = int(raw)
    except ValueError:
        return 30
    return max(value, 1)


def _heartbeat_loop() -> None:
    seconds = _heartbeat_seconds()
    while True:
        print("celery-heartbeat: alive", flush=True)
        time.sleep(seconds)


@worker_ready.connect
def _start_heartbeat(**_kwargs: object) -> None:
    global _heartbeat_started
    with _heartbeat_lock:
        if _heartbeat_started:
            return
        _heartbeat_started = True

    print("celery-worker: ready", flush=True)
    thread = threading.Thread(target=_heartbeat_loop, daemon=True, name="celery-heartbeat")
    thread.start()
