"""Matrix runner: every scenario x {defenses OFF, defenses ON}."""

from __future__ import annotations

from .agent import DEFENSES_OFF, DEFENSES_ON, Agent, Defenses
from .scenarios import Scenario, all_scenarios
from .scoring import answer_correct, classify
from .world import World

MODES: list[tuple[str, Defenses]] = [
    ("off", DEFENSES_OFF),
    ("on", DEFENSES_ON),
]


def run_one(scenario: Scenario, mode_name: str, defenses: Defenses) -> dict:
    world = World()
    tools = world.tools()
    hooks: dict = {}
    if scenario.injector is not None:
        tools = scenario.injector.wrap_tools(tools)
        hooks = scenario.injector.hooks()

    agent = Agent(scenario.service, defenses)
    run = agent.run(tools, hooks)
    fault_injected = scenario.injector is not None
    outcome = classify(run, scenario.truth, fault_injected)

    return {
        "scenario": scenario.id,
        "scenario_name": scenario.name,
        "mode": mode_name,
        "fault_injected": fault_injected,
        "fault": scenario.fault,
        "detected": len(run.detections) > 0,
        "detection_step": run.first_detection_step,
        "detections": [
            {"step": e["step"], "kind": e["kind"], "detail": e["detail"]}
            for e in run.detections
        ],
        "outcome": outcome,
        "answer_correct": answer_correct(run.answer, scenario.truth),
        "answer": run.answer,
        "abstained": run.abstained,
        "abstain_reason": run.abstain_reason,
        "truth": {
            "version": scenario.truth["version"],
            "status": scenario.truth["status"],
            "error_rate": scenario.truth["error_rate"],
        },
        "tokens": run.tokens,
        "cost_usd": run.cost_usd,
        "steps": run.steps,
        "tool_calls": run.tool_calls,
        "events": run.events,
    }


def run_matrix(scenarios: list[Scenario] | None = None) -> list[dict]:
    rows = []
    for scenario in scenarios if scenarios is not None else all_scenarios():
        for mode_name, defenses in MODES:
            rows.append(run_one(scenario, mode_name, defenses))
    return rows
