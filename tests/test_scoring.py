"""Detection/scoring logic and the end-to-end matrix contract."""

from agentchaos.agent import RunResult
from agentchaos.runner import run_matrix
from agentchaos.scenarios import all_scenarios
from agentchaos.scoring import answer_correct, classify, silent_failure_rate
from agentchaos.world import TRUTH

TRUTH_ROW = TRUTH["payments-api"]
CORRECT = {"version": "2.4.1", "status": "degraded", "error_rate": 4.2}
WRONG = {"version": "9.9.9", "status": "healthy", "error_rate": 0.0}


def make_run(answer, abstained=False):
    return RunResult(
        answer=answer,
        abstained=abstained,
        abstain_reason="test" if abstained else None,
    )


def test_answer_correct_requires_all_fields():
    assert answer_correct(CORRECT, TRUTH_ROW)
    assert not answer_correct(WRONG, TRUTH_ROW)
    assert not answer_correct(None, TRUTH_ROW)
    almost = dict(CORRECT, error_rate=4.3)
    assert not answer_correct(almost, TRUTH_ROW)


def test_classify_buckets():
    assert classify(make_run(CORRECT), TRUTH_ROW, fault_injected=False) == "success"
    assert classify(make_run(CORRECT), TRUTH_ROW, fault_injected=True) == "recovered"
    assert (
        classify(make_run(None, abstained=True), TRUTH_ROW, fault_injected=True)
        == "failed_loudly"
    )
    assert classify(make_run(WRONG), TRUTH_ROW, fault_injected=True) == "failed_silently"


def test_silent_failure_rate_ignores_baseline_rows():
    rows = [
        {"fault_injected": False, "outcome": "failed_silently"},
        {"fault_injected": True, "outcome": "failed_silently"},
        {"fault_injected": True, "outcome": "recovered"},
    ]
    assert silent_failure_rate(rows) == 0.5


def test_matrix_baseline_succeeds_in_both_modes():
    rows = run_matrix()
    baseline = [r for r in rows if r["scenario"] == "baseline"]
    assert len(baseline) == 2
    assert all(r["outcome"] == "success" for r in baseline)
    assert all(r["answer_correct"] for r in baseline)


def test_matrix_defenses_off_every_fault_fails_silently():
    rows = run_matrix()
    off_faults = [r for r in rows if r["mode"] == "off" and r["fault_injected"]]
    assert len(off_faults) == 5
    assert all(r["outcome"] == "failed_silently" for r in off_faults)
    assert all(not r["detected"] for r in off_faults)
    assert silent_failure_rate([r for r in rows if r["mode"] == "off"]) == 1.0


def test_matrix_defenses_on_no_silent_failures():
    rows = run_matrix()
    on_faults = [r for r in rows if r["mode"] == "on" and r["fault_injected"]]
    assert len(on_faults) == 5
    assert all(r["outcome"] != "failed_silently" for r in on_faults)
    assert all(r["detected"] for r in on_faults)
    assert silent_failure_rate([r for r in rows if r["mode"] == "on"]) == 0.0
    # Four faults are fully recovered; the poisoned metric cannot be
    # recovered (the tool never returns a valid value), so the agent
    # must fail loudly instead -- which is the correct behavior.
    recovered = {r["scenario"] for r in on_faults if r["outcome"] == "recovered"}
    assert recovered == {
        "flaky-timeout",
        "hallucinating-status",
        "prompt-injection",
        "context-corruption",
    }
    poisoned = next(r for r in on_faults if r["scenario"] == "poisoned-metric")
    assert poisoned["outcome"] == "failed_loudly"
    assert poisoned["abstained"]


def test_matrix_covers_every_scenario_in_both_modes():
    rows = run_matrix()
    assert len(rows) == len(all_scenarios()) * 2
