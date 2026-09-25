"""
Unit and Negative Tests for JARVIS Internal Event Bus (Batch 5).
"""

import asyncio
import pytest
from typing import List
from jarvis.core.enums import EventPriority, HealthState
from jarvis.core.events import (
    Event,
    EventBus,
    RetryPolicy,
    RuntimeStartingEvent,
)
from jarvis.core.runtime import JarvisApplication
from jarvis.core.exceptions import (
    EventPublishError,
    EventSubscriptionError,
    QueueOverflowError,
)


@pytest.mark.asyncio
async def test_event_bus_publish_and_subscribe_success():
    bus = EventBus()
    received_events: List[Event] = []

    async def sample_handler(event: Event) -> None:
        received_events.append(event)

    await bus.start()
    sub_id = bus.subscribe("RuntimeStarting", sample_handler)
    assert bus.has_subscription(sub_id)

    evt = RuntimeStartingEvent(source="test", payload={"data": "hello"})
    await bus.publish(evt)

    # Wait for async dispatch loop to process
    await asyncio.sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0].event_id == evt.event_id
    assert received_events[0].payload["data"] == "hello"

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    bus = EventBus()
    received: List[Event] = []

    async def h(evt: Event) -> None:
        received.append(evt)

    await bus.start()
    sub_id = bus.subscribe("TestEvent", h)
    assert bus.unsubscribe(sub_id) is True
    assert bus.has_subscription(sub_id) is False

    await bus.publish(Event(event_type="TestEvent"))
    await asyncio.sleep(0.05)

    assert len(received) == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_multiple_handlers_and_error_isolation():
    bus = EventBus()
    success_results: List[str] = []

    async def handler_a(evt: Event) -> None:
        success_results.append("A")

    async def handler_failing(evt: Event) -> None:
        raise ValueError("Simulated handler crash")

    async def handler_b(evt: Event) -> None:
        success_results.append("B")

    await bus.start()
    bus.subscribe("MultiEvent", handler_a)
    bus.subscribe("MultiEvent", handler_failing)
    bus.subscribe("MultiEvent", handler_b)

    await bus.publish(Event(event_type="MultiEvent"))
    await asyncio.sleep(0.1)

    # Failing handler should not stop A and B from executing cleanly
    assert "A" in success_results
    assert "B" in success_results

    metrics = bus.get_metrics()
    assert metrics["delivered_count"] >= 2
    assert metrics["failed_count"] >= 1

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_retry_policy():
    bus = EventBus()
    attempts = 0

    async def retryable_handler(evt: Event) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("Transient failure")

    await bus.start()
    retry_pol = RetryPolicy(max_attempts=4, retry_delay=0.01)
    bus.subscribe("RetryEvent", retryable_handler, retry_policy=retry_pol)

    await bus.publish(Event(event_type="RetryEvent"))
    await asyncio.sleep(0.2)

    assert attempts == 3
    metrics = bus.get_metrics()
    assert metrics["retry_count"] >= 2
    assert metrics["delivered_count"] >= 1

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_non_retryable_exception_fails_immediately():
    bus = EventBus()
    attempts = 0

    async def non_retryable_handler(evt: Event) -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("Non-retryable validation error")

    await bus.start()
    retry_pol = RetryPolicy(max_attempts=5, retry_delay=0.01, non_retryable_exceptions=["ValueError"])
    bus.subscribe("NonRetryEvent", non_retryable_handler, retry_policy=retry_pol)

    await bus.publish(Event(event_type="NonRetryEvent"))
    await asyncio.sleep(0.1)

    # Should fail on attempt 1 without retrying 5 times
    assert attempts == 1
    metrics = bus.get_metrics()
    assert metrics["failed_count"] == 1

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_handler_timeout():
    bus = EventBus()
    executed = False

    async def slow_handler(evt: Event) -> None:
        nonlocal executed
        await asyncio.sleep(0.5)
        executed = True

    await bus.start()
    bus.subscribe("SlowEvent", slow_handler, timeout=0.05)

    await bus.publish(Event(event_type="SlowEvent"))
    await asyncio.sleep(0.15)

    assert executed is False
    metrics = bus.get_metrics()
    assert metrics["failed_count"] >= 1

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_sync_handler():
    bus = EventBus()
    results: List[int] = []

    def sync_handler(evt: Event) -> None:
        results.append(evt.payload.get("num", 0))

    await bus.start()
    bus.subscribe("SyncEvent", sync_handler)

    await bus.publish(Event(event_type="SyncEvent", payload={"num": 42}))
    await asyncio.sleep(0.1)

    assert results == [42]
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_immutability():
    from pydantic import ValidationError

    evt = Event(event_type="ImmutableEvent", payload={"key": "val"})

    with pytest.raises((ValidationError, TypeError)):
        evt.event_type = "ChangedType"

    with pytest.raises((ValidationError, TypeError)):
        evt.payload = {"new": "data"}


@pytest.mark.asyncio
async def test_event_bus_history_tracking():
    bus = EventBus(history_size=5)
    await bus.start()

    for i in range(10):
        await bus.publish(Event(event_type=f"Event_{i}"))

    await asyncio.sleep(0.05)
    history = bus.get_history()

    # Should be bounded by history_size (5)
    assert len(history) == 5
    assert history[-1]["event_type"] == "Event_9"

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_queue_overflow_negative_test():
    bus = EventBus(max_queue_size=2)
    await bus.start()

    # Fill queue
    await bus.publish(Event(event_type="E1"))
    await bus.publish(Event(event_type="E2"))

    # Publishing normal priority event past capacity should raise QueueOverflowError
    with pytest.raises(QueueOverflowError):
        await bus.publish(Event(event_type="E3", priority=EventPriority.NORMAL))

    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_publish_after_shutdown_negative_test():
    bus = EventBus()
    await bus.start()
    await bus.stop()

    with pytest.raises(EventPublishError):
        await bus.publish(Event(event_type="PostShutdownEvent"))


def test_event_bus_invalid_subscription_negative_tests():
    bus = EventBus()

    with pytest.raises(EventSubscriptionError):
        bus.subscribe("ValidType", "not_callable")

    with pytest.raises(EventSubscriptionError):
        bus.subscribe("", lambda e: None)


@pytest.mark.asyncio
async def test_event_bus_health_reporting():
    bus = EventBus(max_queue_size=10)
    h_before = await bus.health()
    assert h_before.status == HealthState.HEALTHY

    await bus.start()
    h_started = await bus.health()
    assert h_started.status == HealthState.HEALTHY
    assert h_started.metadata["state"] == "RUNNING"

    await bus.stop()


@pytest.mark.asyncio
async def test_runtime_kernel_event_bus_integration():
    app = JarvisApplication()
    published_events: List[str] = []

    async def runtime_event_listener(evt: Event) -> None:
        published_events.append(evt.event_type)

    app.event_bus.subscribe("*", runtime_event_listener)

    await app.start()
    await asyncio.sleep(0.1)
    await app.shutdown("Integration test done")
    await asyncio.sleep(0.1)

    assert "ComponentStarted" in published_events
    assert "RuntimeStarted" in published_events
