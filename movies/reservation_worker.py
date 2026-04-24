import logging
import threading
import time

from django.conf import settings

from .payments import cleanup_expired_payment_holds


logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_thread = None


def start_reservation_cleanup_worker():
    global _worker_thread

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return False

        _worker_thread = threading.Thread(
            target=run_reservation_cleanup_worker,
            name='seat-reservation-cleanup-worker',
            daemon=True,
        )
        _worker_thread.start()
        return True


def run_reservation_cleanup_worker():
    interval_seconds = int(getattr(settings, 'SEAT_RESERVATION_CLEANUP_INTERVAL_SECONDS', 5))
    logger.info("Seat reservation cleanup worker started")

    while True:
        try:
            cleanup_expired_payment_holds()
        except Exception as exc:
            logger.exception("Seat reservation cleanup worker failed: %s", exc)

        time.sleep(max(interval_seconds, 1))
