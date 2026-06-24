"""Unit tests for the in-process job event broker."""

from __future__ import annotations

import asyncio
import threading

from vman.services.events import JobEventBroker


def test_publish_buffers_history() -> None:
    broker = JobEventBroker(history_size=8)
    broker.publish("log", "job-1", {"line_redacted": "a"})
    broker.publish("log", "job-1", {"line_redacted": "b"})
    broker.publish("status", "job-1", {"status": "running"})

    history = list(broker.iter_history("job-1"))
    assert [ev.kind for ev in history] == ["log", "log", "status"]
    assert [ev.seq for ev in history] == [1, 2, 3]
    assert history[2].data == {"status": "running"}


def test_history_is_per_job() -> None:
    broker = JobEventBroker()
    broker.publish("log", "a", {"line_redacted": "x"})
    broker.publish("log", "b", {"line_redacted": "y"})
    assert len(list(broker.iter_history("a"))) == 1
    assert len(list(broker.iter_history("b"))) == 1
    assert len(list(broker.iter_history("missing"))) == 0


def test_history_caps_at_size() -> None:
    broker = JobEventBroker(history_size=2)
    for i in range(5):
        broker.publish("log", "job-x", {"line_redacted": str(i)})
    history = list(broker.iter_history("job-x"))
    assert [ev.data["line_redacted"] for ev in history] == ["3", "4"]


def test_subscribe_receives_history_and_new_events() -> None:
    """A fresh subscriber gets the history snapshot then live updates."""

    broker = JobEventBroker()
    broker.publish("log", "job-y", {"line_redacted": "first"})

    async def driver() -> list[dict]:
        history, queue = broker.subscribe("job-y")
        # Replay history.
        received: list[dict] = [ev.data for ev in history]
        # Wait for a new event published from another thread.
        event = await asyncio.wait_for(queue.get(), timeout=2.0)
        received.append(event.data)
        broker.unsubscribe("job-y", queue)
        return received

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(driver())
        # Give the subscription a moment to register.
        loop.run_until_complete(asyncio.sleep(0.05))

        def publish() -> None:
            broker.publish("log", "job-y", {"line_redacted": "second"})

        t = threading.Thread(target=publish)
        t.start()
        t.join()
        result = loop.run_until_complete(task)
    finally:
        loop.close()

    assert result[0] == {"line_redacted": "first"}
    assert result[1] == {"line_redacted": "second"}


def test_unsubscribe_stops_delivery() -> None:
    broker = JobEventBroker()
    history, queue = broker.subscribe("job-z")
    assert broker.subscriber_count("job-z") == 1
    broker.unsubscribe("job-z", queue)
    assert broker.subscriber_count("job-z") == 0
    # Publishing now should not raise.
    broker.publish("log", "job-z", {"line_redacted": "noop"})


def test_reset_closes_all_subscribers() -> None:
    broker = JobEventBroker()
    _h1, q1 = broker.subscribe("a")
    _h2, q2 = broker.subscribe("b")

    async def drain(q: asyncio.Queue) -> object | None:
        return await asyncio.wait_for(q.get(), timeout=2.0)

    loop = asyncio.new_event_loop()
    try:
        t1 = loop.create_task(drain(q1))
        t2 = loop.create_task(drain(q2))
        loop.run_until_complete(asyncio.sleep(0.05))
        broker.reset()
        # Both queues should now have the sentinel ``None`` and the
        # tasks should finish.
        r1 = loop.run_until_complete(t1)
        r2 = loop.run_until_complete(t2)
    finally:
        loop.close()
    assert r1 is None
    assert r2 is None


def test_event_sse_format_escapes_newlines() -> None:
    """The wire format MUST keep newlines out of the data field."""

    broker = JobEventBroker()
    ev = broker.publish("log", "job-w", {"line_redacted": "line1\nline2"})
    sse = ev.to_sse()
    # Newlines inside data are escaped to literal \n; the only
    # actual newlines in the frame are the SSE field separators.
    assert sse.count("\n") == 4  # event: \n id: \n data: \n \n
    assert "\\n" in sse
    assert "line1" in sse and "line2" in sse
