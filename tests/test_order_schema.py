"""The output schema ``LLMAgent.get_orders`` hands the model must limit orders to the legal set."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from diplomacy_agents.agents import LLMAgent, order_list_type
from diplomacy_agents.engine import DiplomacyEngine, Orders
from diplomacy_agents.enums import Power


@pytest.mark.parametrize(
    ("orders", "items"),
    [
        (("A PAR H", "F BRE H"), {"enum": ["A PAR H", "F BRE H"], "type": "string"}),
        (("A PAR H",), {"const": "A PAR H", "type": "string"}),
        (("WAIVE", "A PAR B", "WAIVE"), {"enum": ["WAIVE", "A PAR B"], "type": "string"}),
    ],
)
def test_schema_lists_exactly_the_legal_orders(orders: Orders, items: dict[str, object]) -> None:
    """Pydantic renders the legal set as it would a ``Literal``: enum, const for one, no repeats."""
    assert TypeAdapter(order_list_type(orders, 1_000)).json_schema() == {"items": items, "type": "array"}


def test_oversize_list_falls_back_to_plain_strings() -> None:
    """Above *max_schema_size* the schema names no orders and validation accepts any string."""
    adapter = TypeAdapter(order_list_type(("A PAR H", "F BRE H"), 1))
    assert adapter.json_schema() == {"items": {"type": "string"}, "type": "array"}
    assert adapter.validate_python(["anything"]) == ["anything"]


def test_illegal_order_fails_validation() -> None:
    """An order outside the legal set is rejected with Pydantic's literal error."""
    adapter = TypeAdapter(order_list_type(("A PAR H", "F BRE H"), 1_000))
    assert adapter.validate_python(["F BRE H"]) == ["F BRE H"]
    with pytest.raises(ValidationError, match="literal_error"):
        adapter.validate_python(["A XXX H"])


@pytest.mark.parametrize("native", [False, True])
def test_get_orders_sends_the_legal_set(monkeypatch: pytest.MonkeyPatch, *, native: bool) -> None:
    """End to end, the request carries the legal set and an illegal reply is retried."""
    engine = DiplomacyEngine()
    legal = engine.flat_possible_orders[Power.FRANCE]
    replies = [["A XXX H"], [legal[0]]]
    requests: list[ModelRequestParameters] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests.append(info.model_request_parameters)
        args = {"response": replies[len(requests) - 1]}
        if native:
            return ModelResponse(parts=[TextPart(TypeAdapter(dict[str, list[str]]).dump_json(args).decode())])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    fake = FunctionModel(respond, profile=ModelProfile(supports_json_schema_output=native))

    def infer_fake(_model: str) -> FunctionModel:
        return fake

    monkeypatch.setattr(models, "infer_model", infer_fake)

    orders = asyncio.run(LLMAgent(Power.FRANCE, "openai:gpt-4.1").get_orders(engine))

    assert orders == (legal[0],)
    assert len(requests) == len(replies)
    params = requests[0]
    if native:
        assert params.output_object is not None
        schema = params.output_object.json_schema
    else:
        schema = params.output_tools[0].parameters_json_schema
    assert schema == {
        "properties": {"response": {"items": {"enum": list(legal), "type": "string"}, "type": "array"}},
        "required": ["response"],
        "type": "object",
    }
