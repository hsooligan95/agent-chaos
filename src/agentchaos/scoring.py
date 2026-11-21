"""Outcome classification: the heart of the harness.

Every run lands in exactly one bucket:

- ``success``         -- no fault injected, answer correct
- ``recovered``       -- fault injected, answer still correct
- ``failed_loudly``   -- fault injected, agent abstained / surfaced the
                         problem instead of answering wrongly
- ``failed_silently`` -- fault injected, agent delivered a wrong answer
                         as if it were correct. The dangerous case.

The headline metric is the silent-failure rate over fault scenarios.
"""

from __future__ import annotations

from .agent import RunResult

OUTCOMES = ("success", "recovered", "failed_loudly", "failed_silently")


def answer_correct(answer: dict | None, truth: dict) -> bool:
    if answer is None:
        return False
    return (
        answer.get("version") == truth["version"]
        and answer.get("status") == truth["status"]
        and answer.get("error_rate") == truth["error_rate"]
    )


def classify(run: RunResult, truth: dict, fault_injected: bool) -> str:
    if answer_correct(run.answer, truth):
        return "recovered" if fault_injected else "success"
    if run.abstained:
        return "failed_loudly"
    return "failed_silently"


def silent_failure_rate(rows: list[dict]) -> float:
    """Fraction of fault-scenario rows that failed silently."""
    fault_rows = [r for r in rows if r["fault_injected"]]
    if not fault_rows:
        return 0.0
    silent = sum(1 for r in fault_rows if r["outcome"] == "failed_silently")
    return silent / len(fault_rows)
