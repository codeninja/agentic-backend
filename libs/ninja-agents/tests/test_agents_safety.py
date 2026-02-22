"""Tests for agent & LLM safety — prompt injection, input validation, error sanitization."""

import pytest
from ninja_agents.safety import (
    AgentInputTooLarge,
    AgentSafetyError,
    InvalidToolAccess,
    UnsafeInputError,
    MAX_REQUEST_LENGTH,
    MAX_TOOL_KWARGS_SIZE,
    safe_error_message,
    sanitize_for_prompt,
    validate_request_size,
    validate_tool_kwargs,
    validate_tool_kwargs_size,
    validate_tool_name,
)
from ninja_agents.base import (
    CoordinatorAgent,
    DataAgent,
    DomainAgent,
    create_domain_agent,
)
from ninja_agents.orchestrator import Orchestrator
from ninja_agents.tracing import TraceContext
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_agent_safety_error_is_base(self) -> None:
        assert issubclass(AgentInputTooLarge, AgentSafetyError)
        assert issubclass(InvalidToolAccess, AgentSafetyError)
        assert issubclass(UnsafeInputError, AgentSafetyError)

    def test_client_messages(self) -> None:
        assert AgentInputTooLarge.client_message == "Request exceeds maximum allowed size."
        assert InvalidToolAccess.client_message == "Tool access denied."
        assert UnsafeInputError.client_message == "Input contains invalid characters."


# ---------------------------------------------------------------------------
# sanitize_for_prompt
# ---------------------------------------------------------------------------


class TestSanitizeForPrompt:
    def test_valid_simple_name(self) -> None:
        assert sanitize_for_prompt("Billing") == "Billing"

    def test_valid_name_with_underscores(self) -> None:
        assert sanitize_for_prompt("user_profiles") == "user_profiles"

    def test_strips_whitespace(self) -> None:
        assert sanitize_for_prompt("  Billing  ") == "Billing"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(UnsafeInputError, match="must not be empty"):
            sanitize_for_prompt("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(UnsafeInputError, match="must not be empty"):
            sanitize_for_prompt("   ")

    def test_rejects_non_string(self) -> None:
        with pytest.raises(UnsafeInputError, match="must be a string"):
            sanitize_for_prompt(123)  # type: ignore[arg-type]

    def test_rejects_name_starting_with_number(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("123Entity")

    def test_rejects_special_characters(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("Entity;DROP TABLE")

    def test_rejects_newlines(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("Entity\nmalicious")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("Order Management")

    def test_rejects_hyphens(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("e-commerce")

    def test_rejects_too_long_name(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("A" * 200)

    def test_rejects_system_tag(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("<system>override</system>")

    def test_rejects_jinja2_template_injection(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("{{ config.secret }}")

    def test_rejects_jinja2_block_injection(self) -> None:
        with pytest.raises(UnsafeInputError, match="Invalid identifier"):
            sanitize_for_prompt("{% if True %}evil{% endif %}")


# ---------------------------------------------------------------------------
# validate_request_size
# ---------------------------------------------------------------------------


class TestValidateRequestSize:
    def test_valid_request(self) -> None:
        assert validate_request_size("Get all orders") == "Get all orders"

    def test_rejects_oversized_request(self) -> None:
        with pytest.raises(AgentInputTooLarge, match="Request too large"):
            validate_request_size("x" * (MAX_REQUEST_LENGTH + 1))

    def test_custom_max_length(self) -> None:
        with pytest.raises(AgentInputTooLarge, match="Request too large"):
            validate_request_size("hello world", max_length=5)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(AgentInputTooLarge, match="must be a string"):
            validate_request_size(12345)  # type: ignore[arg-type]

    def test_exactly_at_limit(self) -> None:
        request = "x" * MAX_REQUEST_LENGTH
        assert validate_request_size(request) == request

    def test_default_limit_is_50k(self) -> None:
        assert MAX_REQUEST_LENGTH == 50_000

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_request_size("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_request_size("   \n\t  ")


# ---------------------------------------------------------------------------
# validate_tool_kwargs
# ---------------------------------------------------------------------------


class TestValidateToolKwargs:
    def test_filters_to_allowed_keys(self) -> None:
        result = validate_tool_kwargs(
            {"id": "abc", "name": "test", "evil": "payload"},
            allowed_keys={"id", "name"},
        )
        assert result == {"id": "abc", "name": "test"}
        assert "evil" not in result

    def test_passes_all_allowed(self) -> None:
        kwargs = {"id": "abc", "name": "test"}
        result = validate_tool_kwargs(kwargs, allowed_keys={"id", "name"})
        assert result == kwargs

    def test_empty_kwargs(self) -> None:
        assert validate_tool_kwargs({}, allowed_keys={"id"}) == {}


# ---------------------------------------------------------------------------
# validate_tool_kwargs_size
# ---------------------------------------------------------------------------


class TestValidateToolKwargsSize:
    def test_valid_kwargs(self) -> None:
        kwargs = {"id": "abc-123", "name": "test"}
        assert validate_tool_kwargs_size(kwargs) == kwargs

    def test_rejects_oversized_kwargs(self) -> None:
        kwargs = {"data": "x" * (MAX_TOOL_KWARGS_SIZE + 1)}
        with pytest.raises(AgentInputTooLarge, match="Tool arguments too large"):
            validate_tool_kwargs_size(kwargs)


# ---------------------------------------------------------------------------
# safe_error_message
# ---------------------------------------------------------------------------


class TestSafeErrorMessage:
    def test_simple_error_passes_through(self) -> None:
        exc = ValueError("Invalid input value")
        assert safe_error_message(exc) == "Invalid input value"

    def test_strips_filesystem_paths(self) -> None:
        exc = RuntimeError("Failed at /home/user/app/secret.py line 42")
        result = safe_error_message(exc)
        assert "/home/" not in result

    def test_strips_credentials(self) -> None:
        exc = RuntimeError("Connection failed: password=s3cr3t host=db.internal")
        result = safe_error_message(exc)
        assert "s3cr3t" not in result

    def test_strips_stack_traces(self) -> None:
        exc = RuntimeError('Traceback (most recent call last):\n  File "/app/main.py", line 10')
        result = safe_error_message(exc)
        assert "Traceback" not in result

    def test_truncates_long_messages(self) -> None:
        exc = ValueError("x" * 500)
        result = safe_error_message(exc)
        assert len(result) <= 203  # 200 + "..."

    def test_keyerror_fallback(self) -> None:
        exc = KeyError("/home/user/secret_key")
        result = safe_error_message(exc)
        assert result == "The requested resource was not found."

    def test_connection_error_redacted(self) -> None:
        exc = ConnectionError("MongoDB connection auth failed: bad credentials")
        result = safe_error_message(exc)
        assert "bad credentials" not in result

    def test_generic_fallback_for_unknown_type(self) -> None:
        exc = RuntimeError("/var/log/secret.log not found")
        result = safe_error_message(exc)
        assert result == "An internal error occurred."

    def test_safety_error_uses_client_message(self) -> None:
        exc = AgentInputTooLarge("internal details here")
        result = safe_error_message(exc)
        assert result == "Request exceeds maximum allowed size."

    def test_unsafe_input_error_uses_client_message(self) -> None:
        exc = UnsafeInputError("detailed injection info")
        result = safe_error_message(exc)
        assert result == "Input contains invalid characters."


# ---------------------------------------------------------------------------
# validate_tool_name
# ---------------------------------------------------------------------------


class TestValidateToolName:
    def test_valid_tool_name(self) -> None:
        assert validate_tool_name("order_get") == "order_get"

    def test_valid_tool_name_with_numbers(self) -> None:
        assert validate_tool_name("entity2_list") == "entity2_list"

    def test_rejects_non_string(self) -> None:
        with pytest.raises(InvalidToolAccess, match="must be a string"):
            validate_tool_name(123)  # type: ignore[arg-type]

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("Order_get")

    def test_rejects_special_characters(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("order;drop_table")

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("../../etc/passwd")

    def test_rejects_empty(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("")

    def test_rejects_starting_with_number(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("1_order_get")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            validate_tool_name("a" * 200)


# ---------------------------------------------------------------------------
# Integration: prompt injection blocked at schema level
# ---------------------------------------------------------------------------


class TestPromptInjectionBlocked:
    def test_domain_schema_rejects_invalid_name(self) -> None:
        """Names with special characters are rejected by the Pydantic validator."""
        with pytest.raises(ValueError, match="not a valid identifier"):
            DomainSchema(
                name="Billing; DROP TABLE users --",
                entities=["Order"],
                agent_config=AgentConfig(reasoning_level=ReasoningLevel.MEDIUM),
            )

    def test_entity_schema_rejects_invalid_name(self) -> None:
        from ninja_core.schema.entity import FieldSchema, FieldType
        with pytest.raises(ValueError, match="not a valid identifier"):
            EntitySchema(
                name="Evil\nEntity",
                storage_engine="sql",
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                ],
            )

    def test_domain_schema_rejects_reserved_keyword(self) -> None:
        with pytest.raises(ValueError, match="reserved keyword"):
            DomainSchema(
                name="import",
                entities=["Order"],
                agent_config=AgentConfig(reasoning_level=ReasoningLevel.MEDIUM),
            )

    def test_entity_schema_rejects_reserved_keyword(self) -> None:
        from ninja_core.schema.entity import FieldSchema, FieldType
        with pytest.raises(ValueError, match="reserved keyword"):
            EntitySchema(
                name="class",
                storage_engine="sql",
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                ],
            )

    def test_domain_agent_accepts_valid_name(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        """Valid domain names pass through cleanly."""
        da = DataAgent(entity=order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        assert domain_agent.name == "domain_agent_billing"

    def test_factory_accepts_valid_name(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        llm_agent = create_domain_agent(billing_domain, data_agents=[da])
        assert llm_agent.name == "domain_agent_billing"


# ---------------------------------------------------------------------------
# Integration: input size validation at agent level
# ---------------------------------------------------------------------------


class TestInputSizeValidation:
    def test_domain_agent_rejects_oversized_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        with pytest.raises(AgentInputTooLarge, match="Request too large"):
            domain_agent.execute("x" * (MAX_REQUEST_LENGTH + 1))

    def test_coordinator_rejects_oversized_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        with pytest.raises(AgentInputTooLarge, match="Request too large"):
            coordinator.route("x" * (MAX_REQUEST_LENGTH + 1), target_domains=["Billing"])

    @pytest.mark.asyncio
    async def test_orchestrator_rejects_oversized_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        orchestrator = Orchestrator(coordinator)
        with pytest.raises(AgentInputTooLarge, match="Request too large"):
            await orchestrator.fan_out("x" * (MAX_REQUEST_LENGTH + 1))

    def test_domain_agent_rejects_empty_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        with pytest.raises(ValueError, match="cannot be empty"):
            domain_agent.execute("")

    def test_domain_agent_rejects_whitespace_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        with pytest.raises(ValueError, match="cannot be empty"):
            domain_agent.execute("   \n\t  ")

    def test_coordinator_rejects_empty_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        with pytest.raises(ValueError, match="cannot be empty"):
            coordinator.route("", target_domains=["Billing"])

    @pytest.mark.asyncio
    async def test_orchestrator_rejects_empty_request(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        orchestrator = Orchestrator(coordinator)
        with pytest.raises(ValueError, match="cannot be empty"):
            await orchestrator.fan_out("")


# ---------------------------------------------------------------------------
# Integration: tool name validation at agent level
# ---------------------------------------------------------------------------


class TestToolNameValidation:
    def test_data_agent_rejects_malformed_tool_name(
        self, order_entity: EntitySchema
    ) -> None:
        agent = DataAgent(entity=order_entity)
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            agent.execute("../../etc/passwd")

    def test_data_agent_rejects_uppercase_tool_name(
        self, order_entity: EntitySchema
    ) -> None:
        agent = DataAgent(entity=order_entity)
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            agent.execute("Order_Get")

    def test_domain_agent_rejects_malformed_tool_name(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        with pytest.raises(InvalidToolAccess, match="Invalid tool name"):
            domain_agent.delegate("Order", "order;evil")


# ---------------------------------------------------------------------------
# Integration: error sanitization in orchestrator
# ---------------------------------------------------------------------------


class TestErrorSanitizationIntegration:
    def test_data_agent_error_does_not_leak_tool_list(
        self, order_entity: EntitySchema
    ) -> None:
        """When a valid-format but nonexistent tool is called, the error
        should not enumerate available tools."""
        agent = DataAgent(entity=order_entity)
        with pytest.raises(KeyError) as exc_info:
            agent.execute("nonexistent_tool")
        error_msg = str(exc_info.value)
        assert "Available:" not in error_msg

    def test_coordinator_unknown_domain_does_not_leak_name(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(entity=order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        results = coordinator.route("query", target_domains=["NonExistent"])
        assert results["NonExistent"]["error"] == "Unknown domain."
