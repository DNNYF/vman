"""In-process pub/sub broker for job events (Task 17).

The dashboard wants to see logs and status changes in near real time
without polling the database once a second.  We solve that with a tiny
thread-safe broker that lives on ``app.state.events``: a single source
of truth that the worker writes to and the SSE route reads from.

The broker is intentionally minimal:

* topics are per-job-id strings
* a topic carries a fixed-size queue of events; the broker keeps a
  rolling history so a brand-new subscriber can immediately get the
  state of the world up to ``history_size`` events
* subscribers get an :class:`asyncio.Queue` they read from inside a
  FastAPI handler; the queue is closed when the subscriber unsubscribes
  or the broker itself is shut down (e.g. during tests)

The broker is process-local.  For a multi-worker deployment we would
swap this for Redis pub/sub or similar; the surface area is small
enough that the only change would be the implementation of
``publish`` / ``subscribe``.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal["log", "status", "heartbeat"]


@dataclass(frozen=True)
class JobEvent:
    """A single event emitted by the worker.

    ``data`` is a plain dict so we can serialise it to SSE without
    worrying about model classes on the wire.  ``seq`` is monotonic
    per-job; clients can use it to detect gaps and request a backfill
    via the plain ``GET /api/jobs/{id}/logs`` endpoint.
    """

    kind: EventKind
    job_id: str
    data: dict[str, Any]
    seq: int
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Render this event as a single SSE frame.

        Lines inside ``data`` are JSON-encoded; multi-line data blocks
        are emitted as several ``data:`` lines per the SSE spec.
        """

        import json

        payload = json.dumps(
            {
                "kind": self.kind,
                "job_id": self.job_id,
                "seq": self.seq,
                "timestamp": self.timestamp,
                "data": self.data,
            },
            separators=(",", ":"),
        )
        # SSE forbids newlines inside a data field; replace them so a
        # malicious or accidental newline in a log line cannot break the
        # framing.
        safe = payload.replace("\r", "\\r").replace("\n", "\\n")
        return f"event: {self.kind}\nid: {self.seq}\ndata: {safe}\n\n"


class _Topic:
    """Per-job subscription state."""

    __slots__ = ("history", "seq", "subscribers", "lock")

    def __init__(self, history_size: int) -> None:
        self.history: collections.deque[JobEvent] = collections.deque(maxlen=history_size)
        self.seq: int = 0
        self.subscribers: list[asyncio.Queue[JobEvent | None]] = []
        self.lock = threading.Lock()


class JobEventBroker:
    """Thread-safe broker for job events.

    Subscribers are coroutines running in the FastAPI event loop; the
    worker calls :meth:`publish` from a regular thread.  The broker
    bridges the two with a small lock and ``loop.call_soon_threadsafe``
    so subscribers never see a partially initialised event.
    """

    DEFAULT_HISTORY = 256

    def __init__(self, *, history_size: int = DEFAULT_HISTORY) -> None:
        self._history_size = max(1, int(history_size))
        self._topics: dict[str, _Topic] = {}
        self._lock = threading.Lock()
        # ``self._loop`` is set on first subscription; the worker uses
        # it to push events to subscriber queues from its own thread.
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ #
    # Subscription
    # ------------------------------------------------------------------ #

    def subscribe(self, job_id: str) -> tuple[list[JobEvent], asyncio.Queue[JobEvent | None]]:
        """Register a new subscriber for ``job_id``.

        Returns the current history snapshot (so a freshly connected
        client can render without waiting for new events) plus a queue
        that will receive future events.  A ``None`` sentinel on the
        queue indicates the broker is shutting the topic down (e.g.
        the test harness is closing).
        """

        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                topic = _Topic(self._history_size)
                self._topics[job_id] = topic
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop: the caller is not in an async
                # context.  We'll fall back to thread-safe queue
                # injection; subscribers must poll in that case.
                self._loop = None
            queue: asyncio.Queue[JobEvent | None] = asyncio.Queue()
            topic.subscribers.append(queue)
            history = list(topic.history)
        return history, queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[JobEvent | None]) -> None:
        """Remove a previously registered subscriber."""

        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                return
            try:
                topic.subscribers.remove(queue)
            except ValueError:
                return

    def iter_history(self, job_id: str) -> Iterator[JobEvent]:
        """Return an iterator over the current event history."""

        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                return iter(())
            history = list(topic.history)
        return iter(history)

    # ------------------------------------------------------------------ #
    # Publishing
    # ------------------------------------------------------------------ #

    def publish(self, kind: EventKind, job_id: str, data: dict[str, Any]) -> JobEvent:
        """Publish an event for ``job_id`` and notify all subscribers.

        Returns the event that was stored in the history; tests use
        this to assert the event made it into the rolling buffer.
        """

        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                topic = _Topic(self._history_size)
                self._topics[job_id] = topic
            topic.seq += 1
            event = JobEvent(
                kind=kind,
                job_id=job_id,
                data=dict(data),
                seq=topic.seq,
            )
            topic.history.append(event)
            subscribers = list(topic.subscribers)
            loop = self._loop

        # Push the event into each subscriber queue.  When called from
        # the worker's thread we marshal the call through
        # ``call_soon_threadsafe`` so we never touch asyncio primitives
        # from the wrong thread.  When called from within the event
        # loop (e.g. from a test) we just ``put_nowait`` directly.
        for q in subscribers:
            self._enqueue(loop, q, event)
        return event

    @staticmethod
    def _enqueue(
        loop: asyncio.AbstractEventLoop | None,
        queue: asyncio.Queue[JobEvent | None],
        event: JobEvent,
    ) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if loop is not None and loop.is_running() and running_loop is not loop:
            loop.call_soon_threadsafe(queue.put_nowait, event)
            return
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    # ------------------------------------------------------------------ #
    # Lifecycle helpers
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Drop every topic and signal subscribers to stop.

        Used by tests to give each case a clean broker.
        """

        with self._lock:
            topics = list(self._topics.items())
            self._topics.clear()
        for _job_id, topic in topics:
            for q in topic.subscribers:
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(None)

    def subscriber_count(self, job_id: str) -> int:
        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                return 0
            return len(topic.subscribers)

    def history_size(self, job_id: str) -> int:
        with self._lock:
            topic = self._topics.get(job_id)
            if topic is None:
                return 0
            return len(topic.history)


__all__ = ["JobEvent", "JobEventBroker", "EventKind"]
