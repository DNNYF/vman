"""Console entrypoint for the standalone VMAN worker service."""

from __future__ import annotations

import signal
import sys
import time

from vman.main import _stop_background_worker, start_background_worker
from vman.services.worker import JobWorker


def main() -> int:
    """Run the background worker until systemd sends SIGTERM/SIGINT."""
    worker = start_background_worker()

    def _stop(_signum: int, _frame: object) -> None:
        _stop_background_worker()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        while True:
            time.sleep(60)
            worker_thread_stopped = (
                isinstance(worker, JobWorker)
                and worker._thread is not None
                and not worker._thread.is_alive()
            )
            if worker_thread_stopped:
                print("vman worker thread stopped unexpectedly", file=sys.stderr)
                return 1
    finally:
        _stop_background_worker()


if __name__ == "__main__":
    raise SystemExit(main())
