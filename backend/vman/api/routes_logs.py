"""System logs API route (Phase 2)."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, Query

from vman.api.deps import CurrentUser

router = APIRouter(prefix="/api/logs", tags=["logs"])


class InMemoryLogHandler(logging.Handler):
    """A logging handler that stores formatted log records in a circular buffer."""

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self.buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.buffer.append(
                {
                    "timestamp": record.created,
                    "name": record.name,
                    "level": record.levelname,
                    "message": msg,
                }
            )
        except Exception:
            self.handleError(record)


# Create global handler and set format
log_handler = InMemoryLogHandler()
log_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

# Register to the main loggers
logging.getLogger("vman").addHandler(log_handler)
logging.getLogger("uvicorn").addHandler(log_handler)
logging.getLogger("uvicorn.access").addHandler(log_handler)


@router.get("")
def list_logs(
    user: CurrentUser,
    level: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Get the most recent system logs, newest first."""
    logs = list(log_handler.buffer)

    if level:
        level_upper = level.upper()
        logs = [log for log in logs if log["level"] == level_upper]

    if search:
        search_lower = search.lower()
        logs = [
            log
            for log in logs
            if search_lower in log["message"].lower() or search_lower in log["name"].lower()
        ]

    # Return the logs (oldest to newest, capped at limit)
    return logs[-limit:]
