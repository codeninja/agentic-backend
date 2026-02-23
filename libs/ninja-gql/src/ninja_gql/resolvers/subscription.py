"""Subscription resolver factories for per-entity change streams.

Each entity in the ASD gets an ``on_{entity}_changed`` subscription
field that yields :class:`EntityChangeEvent` payloads via the
:class:`EventBus`.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Callable

import strawberry
from ninja_core.schema.entity import EntitySchema

from ninja_gql.event_bus import EntityChangeEvent, EventBus, get_event_bus
from ninja_gql.resolvers.crud import _snake


# Strawberry type mirroring EntityChangeEvent for the public schema.
@strawberry.type(description="An entity-change event delivered via subscription.")
class EntityChangePayload:
    entity_name: str
    change_type: str
    entity_id: str
    data: strawberry.scalars.JSON | None = None


def make_subscription_resolver(
    entity: EntitySchema,
    event_bus: EventBus | None = None,
) -> Callable[..., AsyncGenerator[EntityChangePayload, None]]:
    """Return an async-generator resolver for ``on_{entity}_changed``."""
    bus = event_bus or get_event_bus()
    topic = _snake(entity.name)

    async def _resolver(self: Any) -> AsyncGenerator[EntityChangePayload, None]:  # noqa: ANN401
        async for event in bus.subscribe(topic):
            yield EntityChangePayload(
                entity_name=event.entity_name,
                change_type=event.change_type.value,
                entity_id=event.entity_id,
                data=event.data,
            )

    _resolver.__name__ = f"on_{topic}_changed"
    _resolver.__qualname__ = f"Subscription.on_{topic}_changed"
    return _resolver
