"""Tests for GraphQL subscription generation and the event bus."""

from __future__ import annotations

import asyncio

import pytest
from ninja_gql.event_bus import ChangeType, EntityChangeEvent, EventBus, get_event_bus
from ninja_gql.resolvers.subscription import EntityChangePayload, make_subscription_resolver
from ninja_gql.schema import build_schema

# ---------------------------------------------------------------------------
# EventBus unit tests
# ---------------------------------------------------------------------------


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self) -> None:
        bus = EventBus()
        event = EntityChangeEvent(
            entity_name="Customer",
            change_type=ChangeType.CREATED,
            entity_id="abc",
            data={"name": "Alice"},
        )
        received: list[EntityChangeEvent] = []

        async def _collect() -> None:
            async for e in bus.subscribe("customer"):
                received.append(e)
                break  # stop after first

        task = asyncio.create_task(_collect())
        await asyncio.sleep(0)  # let subscriber register

        await bus.publish("customer", event)
        await task

        assert len(received) == 1
        assert received[0].entity_id == "abc"
        assert received[0].change_type == ChangeType.CREATED

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        event = EntityChangeEvent(
            entity_name="Order",
            change_type=ChangeType.UPDATED,
            entity_id="o1",
        )
        results_a: list[EntityChangeEvent] = []
        results_b: list[EntityChangeEvent] = []

        async def _sub(target: list[EntityChangeEvent]) -> None:
            async for e in bus.subscribe("order"):
                target.append(e)
                break

        ta = asyncio.create_task(_sub(results_a))
        tb = asyncio.create_task(_sub(results_b))
        await asyncio.sleep(0)

        await bus.publish("order", event)
        await ta
        await tb

        assert len(results_a) == 1
        assert len(results_b) == 1

    @pytest.mark.asyncio
    async def test_no_cross_topic_delivery(self) -> None:
        bus = EventBus()
        event = EntityChangeEvent(
            entity_name="Product",
            change_type=ChangeType.DELETED,
            entity_id="p1",
        )
        received: list[EntityChangeEvent] = []

        async def _sub() -> None:
            async for e in bus.subscribe("customer"):
                received.append(e)
                break

        task = asyncio.create_task(_sub())
        await asyncio.sleep(0)

        await bus.publish("product", event)
        await asyncio.sleep(0.05)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_subscriber_cleanup_on_cancel(self) -> None:
        bus = EventBus()

        async def _sub() -> None:
            async for _ in bus.subscribe("topic"):
                break

        task = asyncio.create_task(_sub())
        await asyncio.sleep(0)

        assert len(bus._subscribers.get("topic", [])) == 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(bus._subscribers.get("topic", [])) == 0


class TestGetEventBus:
    def test_returns_singleton(self) -> None:
        assert get_event_bus() is get_event_bus()


# ---------------------------------------------------------------------------
# Subscription resolver tests
# ---------------------------------------------------------------------------


class TestSubscriptionResolver:
    @pytest.mark.asyncio
    async def test_resolver_yields_payload(self, sample_asd) -> None:
        bus = EventBus()
        entity = sample_asd.entities[0]  # Customer
        resolver = make_subscription_resolver(entity, event_bus=bus)

        event = EntityChangeEvent(
            entity_name="Customer",
            change_type=ChangeType.CREATED,
            entity_id="c1",
            data={"name": "Bob"},
        )

        payloads: list[EntityChangePayload] = []

        async def _collect() -> None:
            async for p in resolver(None):
                payloads.append(p)
                break

        task = asyncio.create_task(_collect())
        await asyncio.sleep(0)

        await bus.publish("customer", event)
        await task

        assert len(payloads) == 1
        assert payloads[0].entity_name == "Customer"
        assert payloads[0].change_type == "CREATED"
        assert payloads[0].entity_id == "c1"
        assert payloads[0].data == {"name": "Bob"}

    @pytest.mark.asyncio
    async def test_resolver_function_name(self, sample_asd) -> None:
        entity = sample_asd.entities[0]
        resolver = make_subscription_resolver(entity)
        assert resolver.__name__ == "on_customer_changed"


# ---------------------------------------------------------------------------
# Schema integration tests
# ---------------------------------------------------------------------------


class TestSchemaSubscriptions:
    def test_schema_has_subscription_type(self, sample_asd) -> None:
        schema = build_schema(sample_asd)
        sdl = str(schema)
        assert "Subscription" in sdl

    def test_schema_has_per_entity_subscription_fields(self, sample_asd) -> None:
        schema = build_schema(sample_asd)
        sdl = str(schema)
        assert "onCustomerChanged" in sdl
        assert "onOrderChanged" in sdl
        assert "onProductChanged" in sdl

    def test_subscription_field_returns_payload_type(self, sample_asd) -> None:
        schema = build_schema(sample_asd)
        sdl = str(schema)
        assert "EntityChangePayload" in sdl

    @pytest.mark.asyncio
    async def test_subscription_execution(self, sample_asd) -> None:
        bus = EventBus()

        # Patch the default bus for this test
        import ninja_gql.resolvers.subscription as sub_mod

        original = sub_mod.get_event_bus
        sub_mod.get_event_bus = lambda: bus
        try:
            schema = build_schema(sample_asd)
        finally:
            sub_mod.get_event_bus = original

        sub_query = """
            subscription {
                onCustomerChanged {
                    entityName
                    changeType
                    entityId
                    data
                }
            }
        """

        result = await schema.subscribe(sub_query)

        event = EntityChangeEvent(
            entity_name="Customer",
            change_type=ChangeType.UPDATED,
            entity_id="c99",
            data={"name": "Updated"},
        )

        async def _publish_after_delay() -> None:
            await asyncio.sleep(0)
            await bus.publish("customer", event)

        asyncio.create_task(_publish_after_delay())

        async for gql_result in result:
            assert gql_result.data is not None
            payload = gql_result.data["onCustomerChanged"]
            assert payload["entityName"] == "Customer"
            assert payload["changeType"] == "UPDATED"
            assert payload["entityId"] == "c99"
            break
