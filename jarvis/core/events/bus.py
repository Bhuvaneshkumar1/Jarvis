"""
Authoritative Internal Event Bus & Messaging Infrastructure for JARVIS (Batch 5).
"""

import asyncio
import inspect
import time
from collections import deque
from typing import Dict, List, Optional, Callable, Any
from jarvis.core.enums import RuntimeState, HealthState, EventPriority
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.logging import JarvisLogger, redact_sensitive_data
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.events.contracts import Event, Subscription, RetryPolicy
from jarvis.core.exceptions import (
    EventPublishError,
    EventSubscriptionError,
    QueueOverflowError,
)


class EventBus(LifecycleComponent):
    """
    Authoritative Async Event Bus for JARVIS Core Subsystems.
    Provides typed event pub/sub, handler error isolation, retries, bounded queues,
    bounded diagnostic history, and lifecycle management.
    """

    def __init__(
        self,
        max_queue_size: int = 1000,
        history_size: int = 100,
        default_handler_timeout: float = 5.0,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self._max_queue_size: int = max_queue_size
        self._history_size: int = history_size
        self._default_handler_timeout: float = default_handler_timeout
        self.logger: JarvisLogger = logger or JarvisLogger(component="EventBus")

        self._state: RuntimeState = RuntimeState.STOPPED
        self._queue: Optional[asyncio.PriorityQueue] = None
        self._subscriptions: Dict[str, Dict[str, Subscription]] = {}
        self._history: deque = deque(maxlen=self._history_size)
        self._dispatch_task: Optional[asyncio.Task] = None
        self._sequence_counter: int = 0
        self._context: Optional[RuntimeContext] = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._metrics: Dict[str, int] = {
            "published_count": 0,
            "delivered_count": 0,
            "failed_count": 0,
            "dropped_count": 0,
            "retry_count": 0,
        }

    @property
    def name(self) -> str:
        return "EventBus"

    @property
    def state(self) -> RuntimeState:
        return self._state

    async def initialize(self, context: RuntimeContext) -> None:
        """Initialize EventBus component."""
        self._context = context
        self.logger.info("Initializing EventBus component...")

    async def start(self) -> None:
        """Start EventBus worker queue and dispatch loop."""
        if self._state == RuntimeState.RUNNING:
            return

        self._queue = asyncio.PriorityQueue(maxsize=self._max_queue_size)
        self._state = RuntimeState.RUNNING
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        self.logger.info("EventBus started and dispatch loop active.")

    async def stop(self) -> None:
        """Gracefully stop EventBus, drain queue, and cancel worker task."""
        if self._state in (RuntimeState.STOPPING, RuntimeState.STOPPED):
            return

        self._state = RuntimeState.STOPPING
        self.logger.info("EventBus stopping, draining event queue...")

        # Allow queue to drain briefly if items remain
        if self._queue and not self._queue.empty():
            try:
                await asyncio.wait_for(self._queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("EventBus queue drain timed out during shutdown.")

        if self._dispatch_task and not self._dispatch_task.done():
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        self._state = RuntimeState.STOPPED
        self.logger.info("EventBus stopped cleanly.")

    def subscribe(
        self,
        event_type: str,
        handler: Callable,
        retry_policy: Optional[RetryPolicy] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Subscribe a callback handler to an event type or '*' wildcard.
        Returns subscription_id string.
        """
        if not callable(handler):
            raise EventSubscriptionError("Event handler must be callable.")

        if not event_type or not isinstance(event_type, str):
            raise EventSubscriptionError("event_type must be a non-empty string.")

        sub_timeout = timeout if timeout is not None else self._default_handler_timeout
        sub_policy = retry_policy or RetryPolicy()

        handler_name = getattr(handler, "__name__", str(handler))
        is_async = inspect.iscoroutinefunction(handler)

        sub = Subscription(
            event_type=event_type,
            handler=handler,
            handler_name=handler_name,
            is_async=is_async,
            retry_policy=sub_policy,
            timeout=sub_timeout,
        )

        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = {}

        self._subscriptions[event_type][sub.subscription_id] = sub
        self.logger.info(f"Subscribed handler '{handler_name}' to event '{event_type}' (id: {sub.subscription_id})")
        return sub.subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by subscription_id."""
        for event_type, subs in self._subscriptions.items():
            if subscription_id in subs:
                handler_name = subs[subscription_id].handler_name
                del subs[subscription_id]
                self.logger.info(f"Unsubscribed handler '{handler_name}' (id: {subscription_id})")
                return True
        return False

    def has_subscription(self, subscription_id: str) -> bool:
        """Check if subscription_id is registered."""
        for subs in self._subscriptions.values():
            if subscription_id in subs:
                return True
        return False

    async def publish(self, event: Event) -> None:
        """
        Publish an immutable Event to the bus.
        Enqueues event according to priority and queue capacity limits.
        """
        if self._state != RuntimeState.RUNNING:
            raise EventPublishError(f"Cannot publish event when EventBus is in '{self._state.value}' state.")

        if not isinstance(event, Event):
            raise EventPublishError("Only valid Event contract instances can be published.")

        if self._queue is None:
            raise EventPublishError("EventBus queue is not initialized.")

        # Check queue backpressure
        if self._queue.full():
            if event.priority == EventPriority.CRITICAL:
                # Force critical event delivery by making space or logging
                self.logger.warning(f"Queue full! Priority CRITICAL event '{event.event_type}' forced.")
            else:
                self._metrics["dropped_count"] += 1
                raise QueueOverflowError(f"EventBus queue capacity ({self._max_queue_size}) exceeded.")

        self._sequence_counter += 1
        priority_val = event.priority.value

        # PriorityQueue entry: (priority, sequence, event)
        await self._queue.put((priority_val, self._sequence_counter, event))
        self._metrics["published_count"] += 1

        # Record diagnostic history entry
        history_entry = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "timestamp": event.timestamp,
            "correlation_id": event.correlation_id,
            "priority": event.priority.name,
            "payload_summary": redact_sensitive_data(str(event.payload)),
        }
        self._history.append(history_entry)

    def publish_sync(self, event: Event) -> None:
        """
        Synchronous publish helper for non-async callers.
        If an event loop is running, schedules publish as a task.
        """
        if self._state != RuntimeState.RUNNING:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            if self._queue and not self._queue.full():
                self._sequence_counter += 1
                self._queue.put_nowait((event.priority.value, self._sequence_counter, event))
                self._metrics["published_count"] += 1

    async def _dispatch_loop(self) -> None:
        """Background worker loop fetching and dispatching queued events."""
        while self._state == RuntimeState.RUNNING:
            try:
                if self._queue is None:
                    break

                priority_val, seq, event = await self._queue.get()
                try:
                    await self._dispatch_event(event)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as ex:
                self.logger.error(f"Unexpected error in EventBus dispatch loop: {str(ex)}")

    async def _dispatch_event(self, event: Event) -> None:
        """Dispatch single event to all registered subscribers for event_type and '*'."""
        targets: List[Subscription] = []

        if event.event_type in self._subscriptions:
            targets.extend(self._subscriptions[event.event_type].values())
        if "*" in self._subscriptions:
            targets.extend(self._subscriptions["*"].values())

        if not targets:
            return

        # Execute target handlers concurrently with isolated error handling
        tasks = [asyncio.create_task(self._dispatch_to_subscriber(sub, event)) for sub in targets]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _dispatch_to_subscriber(self, sub: Subscription, event: Event) -> None:
        """Dispatch event to single subscriber with retries, timeout, and error isolation."""
        attempts = 0
        max_attempts = sub.retry_policy.max_attempts
        delay = sub.retry_policy.retry_delay

        while attempts < max_attempts:
            attempts += 1
            start_time = time.time()
            try:
                if sub.is_async:
                    await asyncio.wait_for(sub.handler(event), timeout=sub.timeout)
                else:
                    # Run sync handler in threadpool executor to avoid blocking event loop
                    loop = asyncio.get_running_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(None, sub.handler, event),
                        timeout=sub.timeout,
                    )

                self._metrics["delivered_count"] += 1
                return

            except Exception as exc:
                elapsed = round(time.time() - start_time, 4)
                exc_type_name = type(exc).__name__

                is_non_retryable = exc_type_name in sub.retry_policy.non_retryable_exceptions or isinstance(exc, (ValueError, TypeError, KeyError))

                if is_non_retryable or attempts >= max_attempts:
                    self._metrics["failed_count"] += 1
                    self.logger.error(
                        f"Handler '{sub.handler_name}' failed for event '{event.event_type}' "
                        f"(attempt {attempts}/{max_attempts}, elapsed {elapsed}s): {str(exc)}"
                    )
                    return

                self._metrics["retry_count"] += 1
                self.logger.warning(f"Handler '{sub.handler_name}' error (attempt {attempts}/{max_attempts}), retrying in {delay}s: {str(exc)}")
                await asyncio.sleep(delay)
                delay *= sub.retry_policy.backoff

    async def health(self) -> HealthStatusContract:
        """Report EventBus health status."""
        q_size = self._queue.qsize() if self._queue else 0
        q_ratio = q_size / self._max_queue_size if self._max_queue_size > 0 else 0.0

        status = HealthState.HEALTHY
        err: Optional[str] = None

        if self._state == RuntimeState.FAILED:
            status = HealthState.UNHEALTHY
            err = "EventBus in FAILED state"
        elif q_ratio > 0.8:
            status = HealthState.DEGRADED
            err = f"Queue high water mark: {q_size}/{self._max_queue_size}"
        elif self._dispatch_task and self._dispatch_task.done():
            status = HealthState.UNHEALTHY
            err = "Dispatch loop task died unexpectedly"

        return HealthStatusContract(
            component=self.name,
            status=status,
            error=err,
            metadata={
                "state": self._state.value,
                "queue_size": q_size,
                "queue_max": self._max_queue_size,
                "metrics": dict(self._metrics),
            },
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return event processing metrics."""
        return {
            "state": self._state.value,
            "queue_size": self._queue.qsize() if self._queue else 0,
            "active_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
            **self._metrics,
        }

    def get_history(self) -> List[Dict[str, Any]]:
        """Return diagnostic history entries."""
        return list(self._history)
