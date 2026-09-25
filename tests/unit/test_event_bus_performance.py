"""
Performance Throughput Benchmark for JARVIS Event Bus (Batch 5).
"""

import asyncio
import pytest
import time
from jarvis.core.events import EventBus, Event


@pytest.mark.asyncio
async def test_event_bus_throughput_benchmark():
    """
    Measures empirical event publishing & delivery throughput over a burst of events.
    """
    total_events = 500
    delivered_count = 0
    bus = EventBus(max_queue_size=1000, history_size=100)

    async def benchmark_handler(evt: Event) -> None:
        nonlocal delivered_count
        delivered_count += 1

    await bus.start()
    bus.subscribe("BenchEvent", benchmark_handler)

    start_time = time.perf_counter()

    # Publish burst of events
    for i in range(total_events):
        await bus.publish(Event(event_type="BenchEvent", payload={"seq": i}))

    # Wait for queue to drain
    timeout_limit = 5.0
    wait_start = time.perf_counter()
    while delivered_count < total_events and (time.perf_counter() - wait_start) < timeout_limit:
        await asyncio.sleep(0.01)

    elapsed = round(time.perf_counter() - start_time, 4)
    throughput = round(delivered_count / elapsed, 2) if elapsed > 0 else 0.0

    metrics = bus.get_metrics()
    await bus.stop()

    print("\n==================================================")
    print("       JARVIS EVENT BUS PERFORMANCE BENCHMARK     ")
    print("==================================================")
    print(f"Events Published: {metrics['published_count']}")
    print(f"Events Delivered: {delivered_count}")
    print(f"Events Failed:    {metrics['failed_count']}")
    print(f"Elapsed Time:     {elapsed} seconds")
    print(f"Throughput:       {throughput} events/sec")
    print("==================================================")

    assert metrics["published_count"] == total_events
    assert delivered_count == total_events
    assert metrics["failed_count"] == 0
