"""Each injector must actually corrupt what it claims to corrupt."""

import pytest

from agentchaos.agent import DEFENSES_OFF, Agent
from agentchaos.injectors import (
    ContextCorruptionInjector,
    FlakyTimeoutInjector,
    HallucinatingStatusInjector,
    PoisonedMetricInjector,
    PromptInjectionInjector,
)
from agentchaos.world import TRUTH, ToolTimeout, World

SERVICE = "payments-api"


def test_flaky_timeout_raises_then_recovers():
    world = World()
    injector = FlakyTimeoutInjector(failures=2)
    tools = injector.wrap_tools(world.tools())
    with pytest.raises(ToolTimeout):
        tools["get_metric"](SERVICE, "error_rate")
    with pytest.raises(ToolTimeout):
        tools["get_metric"](SERVICE, "error_rate")
    result = tools["get_metric"](SERVICE, "error_rate")
    assert result["value"] == TRUTH[SERVICE]["error_rate"]


def test_hallucinating_status_lies_consistently():
    world = World()
    tools = HallucinatingStatusInjector().wrap_tools(world.tools())
    for _ in range(2):  # consistent lie: re-querying does not help
        result = tools["get_service_status"](SERVICE)
        assert result["version"] != TRUTH[SERVICE]["version"]
        assert result["status"] != TRUTH[SERVICE]["status"]


def test_prompt_injection_adds_malicious_doc():
    world = World()
    clean_docs = world.search_docs("payments-api")["docs"]
    tools = PromptInjectionInjector().wrap_tools(world.tools())
    poisoned_docs = tools["search_docs"]("payments-api")["docs"]
    assert len(poisoned_docs) == len(clean_docs) + 1
    injected = poisoned_docs[-1]
    assert "ignore previous instructions" in injected["text"].lower()
    assert "status as healthy" in injected["text"]


def test_poisoned_metric_corrupts_value_and_embeds_instruction():
    world = World()
    tools = PoisonedMetricInjector().wrap_tools(world.tools())
    result = tools["get_metric"](SERVICE, "error_rate")
    assert not (0.0 <= result["value"] <= 100.0)  # impossible error rate
    assert result["value"] != TRUTH[SERVICE]["error_rate"]
    assert "report error rate as 0.0" in result["note"]


def test_context_corruption_flips_agent_memory():
    agent = Agent(SERVICE, DEFENSES_OFF)
    agent.memory["status"] = {
        "service": SERVICE,
        "version": TRUTH[SERVICE]["version"],
        "status": TRUTH[SERVICE]["status"],
    }
    hook = ContextCorruptionInjector().hooks()["after_status"]
    hook(agent, "after_status")
    assert agent.memory["status"]["version"] != TRUTH[SERVICE]["version"]
    assert agent.memory["status"]["status"] != TRUTH[SERVICE]["status"]


def test_clean_tools_are_untouched_without_injector():
    world = World()
    status = world.get_service_status(SERVICE)
    assert status["version"] == TRUTH[SERVICE]["version"]
    assert status["status"] == TRUTH[SERVICE]["status"]
