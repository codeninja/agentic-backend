"""Simple async pub/sub event bus for GraphQL subscriptions.

Provides an in-process event bus that subscription resolvers use to
stream entity-change events to connected clients.  Each entity gets
its own topic; publishers call :meth:`EventBus.publish` and
subscribers iterate over :meth:`EventBus.subscribe`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator


class ChangeType(str, Enum):
    """Kind of mutation that triggered the event."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"


@dataclass
class EntityChangeEvent:
    """Payload delivered to subscription listeners."""

    entity_name: str
    change_type: ChangeType
    entity_id: str
    data: dict[str, Any] | None = None


class EventBus:
    """In-process async pub/sub bus keyed by topic string.

    Thread-safe for asyncio — each subscriber gets its own
    :class:`asyncio.Queue` so back-pressure is per-client.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[EntityChangeEvent]]] = {}

    async def publish(self, topic: str, event: EntityChangeEvent) -> None:
        """Push *event* to every queue registered under *topic*."""
        for queue in self._subscribers.get(topic, []):
            await queue.put(event)

    async def subscribe(self, topic: str) -> AsyncGenerator[EntityChangeEvent, None]:
        """Yield events for *topic* as they arrive."""
        queue: asyncio.Queue[EntityChangeEvent] = asyncio.Queue()
        self._subscribers.setdefault(topic, []).append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers[topic].remove(queue)


# Module-level singleton so the whole process shares one bus.
_default_bus = EventBus()


def get_event_bus() -> EventBus:
    """Return the process-wide default :class:`EventBus`."""
    return _default_bus
