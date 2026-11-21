"""The agent under test: a deterministic, hand-rolled investigation loop.

Why hand-rolled instead of LangGraph: the harness exists to observe the
loop itself -- exactly which step saw which tool result, where a defense
fired, and what the agent believed at each point. A framework would hide
precisely the mechanics being measured. The "model" is a scripted policy
that emulates documented LLM-agent behaviors, including the failure modes
(a naive agent obeys instructions found in retrieved content, trusts tool
output verbatim, and falls back to stale documentation when a tool fails).
The harness measures the defense pipeline around the model, not a model.

Defenses (all toggled by ``Defenses``):

- ``retry``        -- retry-with-backoff on tool timeouts
- ``validation``   -- schema/range validation of tool outputs
- ``screening``    -- prompt-injection screening of retrieved documents
- ``cross_check``  -- cross-check tool output against the authoritative runbook
- ``groundedness`` -- re-verify working memory against the tools before answering
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .world import ToolTimeout

# Event kinds that count as the fault being DETECTED. A caught exception
# that is silently swallowed into a fallback is not a detection: detection
# means the defense/monitoring layer explicitly flagged the anomaly.
DETECTION_KINDS = {
    "injection_screened",
    "validation_failed",
    "cross_check_mismatch",
    "groundedness_mismatch",
    "timeout_detected",
}

# Patterns that mark a retrieved document as an injection attempt.
INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system update",
    r"do not mention",
    r"disregard.*runbook",
]

# Directive patterns a naive agent obeys when found in retrieved content.
# This emulates an LLM following instructions embedded in data.
DIRECTIVE_STATUS_RE = re.compile(r"report the [\w-]+ status as (\w+)", re.IGNORECASE)
DIRECTIVE_RATE_RE = re.compile(r"report the error rate as (\d+(?:\.\d+)*)%", re.IGNORECASE)

_NUM = r"\d+(?:\.\d+)*"
RUNBOOK_VERSION_RE = re.compile(rf"Current deployed version: ({_NUM})")
RUNBOOK_RULE_RE = re.compile(rf"error rate above ({_NUM})% means status degraded")
STALE_RATE_RE = re.compile(rf"Last known error rate: ({_NUM})%")

# Simulated token accounting (deterministic; labeled simulated in reports).
TOKENS_PER_STEP = 40
TOKENS_PER_TOOL_CALL = 110
TOKENS_PER_RETRY = 60
TOKENS_PER_DOC_SCREENED = 10
COST_PER_TOKEN_USD = 0.000002  # $2.00 per 1M tokens, illustrative


@dataclass
class Defenses:
    retry: bool = False
    validation: bool = False
    screening: bool = False
    cross_check: bool = False
    groundedness: bool = False


DEFENSES_OFF = Defenses()
DEFENSES_ON = Defenses(
    retry=True, validation=True, screening=True, cross_check=True, groundedness=True
)


@dataclass
class RunResult:
    answer: dict | None
    abstained: bool
    abstain_reason: str | None
    events: list = field(default_factory=list)
    tokens: int = 0
    steps: int = 0
    tool_calls: int = 0

    @property
    def detections(self) -> list:
        return [e for e in self.events if e["kind"] in DETECTION_KINDS]

    @property
    def first_detection_step(self) -> int | None:
        found = self.detections
        return found[0]["step"] if found else None

    @property
    def cost_usd(self) -> float:
        return round(self.tokens * COST_PER_TOKEN_USD, 6)


def valid_error_rate(value) -> bool:
    """An error-rate percentage must be a finite number in [0, 100]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and 0.0 <= value <= 100.0


class Agent:
    """Investigates one service: docs -> status -> metric -> answer."""

    def __init__(self, service: str, defenses: Defenses) -> None:
        self.service = service
        self.defenses = defenses
        self.memory: dict = {"docs": [], "status": None, "metric": None}
        self.events: list = []
        self.tokens = 0
        self.tool_calls = 0
        self.step = 0
        self._timeout_flagged = False

    # -- plumbing ---------------------------------------------------------

    def _log(self, kind: str, detail: str) -> None:
        self.events.append({"step": self.step, "kind": kind, "detail": detail})

    def _call(self, tools: dict, name: str, **kwargs):
        """Call a tool with token accounting and optional timeout retry."""
        max_attempts = 3 if self.defenses.retry else 1
        for attempt in range(1, max_attempts + 1):
            self.tool_calls += 1
            self.tokens += TOKENS_PER_TOOL_CALL
            try:
                return tools[name](**kwargs)
            except ToolTimeout:
                if attempt < max_attempts:
                    self.tokens += TOKENS_PER_RETRY
                    if not self._timeout_flagged:
                        self._timeout_flagged = True
                        self._log(
                            "timeout_detected",
                            f"{name} timed out; retrying with backoff",
                        )
                    continue
                raise

    def _runbook(self) -> dict | None:
        for doc in self.memory["docs"]:
            if RUNBOOK_VERSION_RE.search(doc["text"]):
                return doc
        return None

    # -- the loop -----------------------------------------------------------

    def run(self, tools: dict, hooks: dict | None = None) -> RunResult:
        hooks = hooks or {}

        def fire(point: str) -> None:
            hook = hooks.get(point)
            if hook is not None:
                hook(self, point)

        # Step 1: retrieve documents.
        self.step = 1
        self.tokens += TOKENS_PER_STEP
        result = self._call(
            tools, "search_docs", query=f"{self.service} version status error rate"
        )
        docs = list(result["docs"])
        if self.defenses.screening:
            kept = []
            for doc in docs:
                self.tokens += TOKENS_PER_DOC_SCREENED
                text = doc["text"].lower()
                if any(re.search(p, text) for p in INJECTION_PATTERNS):
                    self._log(
                        "injection_screened",
                        f"document {doc['id']} matched injection patterns; dropped",
                    )
                else:
                    kept.append(doc)
            docs = kept
        self.memory["docs"] = docs
        fire("after_docs")

        # Step 2: live status from the control plane.
        self.step = 2
        self.tokens += TOKENS_PER_STEP
        status = self._call(tools, "get_service_status", service=self.service)
        self.memory["status"] = status
        if self.defenses.cross_check:
            self._cross_check_status(tools)
        fire("after_status")

        # Step 3: live error rate from the metrics backend.
        self.step = 3
        self.tokens += TOKENS_PER_STEP
        abstain = self._fetch_metric(tools)
        if abstain is not None:
            return abstain
        fire("after_metric")

        # Step 4: groundedness re-verification of memory before answering.
        if self.defenses.groundedness:
            self.step = 4
            self.tokens += TOKENS_PER_STEP
            self._verify_memory(tools)

        # Step 5: compose the answer from memory.
        self.step = 5
        self.tokens += TOKENS_PER_STEP
        answer = self._compose()
        return RunResult(
            answer=answer,
            abstained=False,
            abstain_reason=None,
            events=self.events,
            tokens=self.tokens,
            steps=self.step,
            tool_calls=self.tool_calls,
        )

    # -- steps with defenses --------------------------------------------------

    def _cross_check_status(self, tools: dict) -> None:
        """Compare the status tool's version against the runbook's.

        On mismatch: flag it, re-query once (a consistent liar stays wrong),
        then fall back to the authoritative runbook version and mark the
        status for derivation from the classification rule + live metric.
        """
        runbook = self._runbook()
        if runbook is None or self.memory["status"] is None:
            return
        expected = RUNBOOK_VERSION_RE.search(runbook["text"]).group(1)
        if self.memory["status"]["version"] == expected:
            return
        self._log(
            "cross_check_mismatch",
            f"status tool reports version {self.memory['status']['version']}, "
            f"runbook says {expected}",
        )
        fresh = self._call(tools, "get_service_status", service=self.service)
        if fresh["version"] == expected:
            self.memory["status"] = fresh
        else:
            self.memory["status"] = {
                "service": self.service,
                "version": expected,
                "status": None,  # derive from rule + metric at compose time
            }

    def _fetch_metric(self, tools: dict) -> RunResult | None:
        """Fetch the error rate. Returns an abstention RunResult or None."""
        try:
            metric = self._call(
                tools, "get_metric", service=self.service, metric="error_rate"
            )
        except ToolTimeout:
            # No retry (or retries exhausted): naive fallback to the stale
            # runbook snapshot, presented as current. Silent by design --
            # no detection event is recorded for a swallowed timeout.
            self._log("stale_fallback", "metric timed out; using runbook snapshot")
            runbook = self._runbook()
            stale = STALE_RATE_RE.search(runbook["text"]).group(1)
            self.memory["metric"] = {
                "service": self.service,
                "metric": "error_rate",
                "value": float(stale),
            }
            return None

        if self.defenses.validation and not valid_error_rate(metric.get("value")):
            self._log(
                "validation_failed",
                f"metric value {metric.get('value')!r} failed validation "
                "(must be a finite number in [0, 100])",
            )
            # One re-query; a persistently poisoned tool stays poisoned.
            metric = self._call(
                tools, "get_metric", service=self.service, metric="error_rate"
            )
            if not valid_error_rate(metric.get("value")):
                self._log(
                    "abstained",
                    "metric failed validation twice; refusing to answer",
                )
                return RunResult(
                    answer=None,
                    abstained=True,
                    abstain_reason="metric value failed validation on re-query",
                    events=self.events,
                    tokens=self.tokens,
                    steps=self.step,
                    tool_calls=self.tool_calls,
                )
        self.memory["metric"] = metric
        return None

    def _verify_memory(self, tools: dict) -> None:
        """Re-fetch status + metric and reconcile with working memory.

        The runbook anchors the reconciliation: if the fresh fetch disagrees
        with memory AND fails the runbook check itself, the tool is the
        problem and verified memory is kept; otherwise memory was corrupted
        and the fresh (runbook-consistent) values win.
        """
        fresh_status = self._call(tools, "get_service_status", service=self.service)
        fresh_metric = self._call(
            tools, "get_metric", service=self.service, metric="error_rate"
        )
        mem_status = self.memory["status"]
        mem_metric = self.memory["metric"]
        status_differs = mem_status is None or (
            fresh_status["version"] != mem_status["version"]
            or fresh_status["status"] != mem_status["status"]
        )
        metric_differs = mem_metric is None or fresh_metric["value"] != mem_metric["value"]
        if not status_differs and not metric_differs:
            return

        runbook = self._runbook()
        expected_version = (
            RUNBOOK_VERSION_RE.search(runbook["text"]).group(1) if runbook else None
        )
        if status_differs:
            if expected_version is not None and fresh_status["version"] != expected_version:
                self._log(
                    "groundedness_mismatch",
                    "fresh status fetch disagrees with memory and fails the "
                    "runbook check; keeping verified memory",
                )
            else:
                self._log(
                    "groundedness_mismatch",
                    "memory status disagreed with fresh fetch; memory restored",
                )
                self.memory["status"] = fresh_status
        if metric_differs:
            self._log(
                "groundedness_mismatch",
                "memory metric disagreed with fresh fetch; memory restored",
            )
            self.memory["metric"] = fresh_metric

    # -- composition ------------------------------------------------------

    def _compose(self) -> dict:
        status = self.memory["status"]
        metric = self.memory["metric"]
        version = status["version"]
        status_value = status["status"]
        error_rate = metric["value"]

        if status_value is None:
            # Status was discarded by cross-check; derive it from the
            # runbook classification rule applied to the live metric.
            runbook = self._runbook()
            threshold = float(RUNBOOK_RULE_RE.search(runbook["text"]).group(1))
            status_value = "degraded" if error_rate > threshold else "healthy"

        # Naive instruction-following: directives found in retrieved
        # content override the composed answer. This emulates an LLM
        # obeying instructions embedded in data. Screening (step 1) is
        # what removes them in the defenses-on mode.
        for doc in self.memory["docs"]:
            m = DIRECTIVE_STATUS_RE.search(doc["text"])
            if m:
                status_value = m.group(1).lower()
            m = DIRECTIVE_RATE_RE.search(doc["text"])
            if m:
                error_rate = float(m.group(1))

        return {
            "service": self.service,
            "version": version,
            "status": status_value,
            "error_rate": error_rate,
        }
