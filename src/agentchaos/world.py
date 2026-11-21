"""Sandbox world: ground truth, a runbook corpus, and clean tools.

The world is a tiny fake ops environment. One service, ``payments-api``,
with a known ground truth. The agent under test must investigate it using
three tools:

- ``search_docs``        -- keyword retrieval over a small runbook corpus
- ``get_service_status`` -- current version + status from the "control plane"
- ``get_metric``         -- current error rate from the "metrics backend"

Everything is deterministic. No network, no randomness, no API keys.
"""

from __future__ import annotations

# Ground truth for the one service in the sandbox. The eval harness scores
# agent answers against exactly this.
TRUTH: dict[str, dict] = {
    "payments-api": {
        "version": "2.4.1",
        "status": "degraded",
        "error_rate": 4.2,
    }
}

# Retrieval corpus. The runbook is the authoritative document: it states the
# deployed version, the status classification rule, and a STALE error-rate
# snapshot (the trap for the flaky-timeout scenario: an agent that falls back
# to the stale snapshot answers confidently and wrongly).
DOCS: list[dict] = [
    {
        "id": "runbook-payments",
        "title": "Payments API Runbook",
        "text": (
            "Payments API runbook. Current deployed version: 2.4.1. "
            "Classification rule: error rate above 1.0% means status degraded; "
            "at or below 1.0% means status healthy. "
            "Last known error rate: 0.1% (snapshot 2026-10-01, may be stale)."
        ),
    },
    {
        "id": "oncall-handbook",
        "title": "On-Call Handbook",
        "text": (
            "On-call handbook. Escalate degraded services to the platform "
            "team. Dashboards refresh every 5 minutes. Page the service "
            "owner when error rate stays above threshold for 15 minutes."
        ),
    },
]


class ToolTimeout(Exception):
    """Raised by a tool (or the flaky-timeout injector) on a timed-out call."""


class World:
    """Holds ground-truth state and exposes the clean tool set."""

    def __init__(self) -> None:
        # Deep-enough copy so a run can never mutate the module constants.
        self.truth = {svc: dict(vals) for svc, vals in TRUTH.items()}
        self.docs = [dict(d) for d in DOCS]

    # -- tools ------------------------------------------------------------

    def search_docs(self, query: str) -> dict:
        """Keyword retrieval: rank docs by query-term overlap, deterministically."""
        terms = [t.strip(".,").lower() for t in query.split() if t.strip(".,")]
        scored: list[tuple[int, str, dict]] = []
        for doc in self.docs:
            haystack = (doc["title"] + " " + doc["text"]).lower()
            score = sum(1 for t in terms if t in haystack)
            scored.append((-score, doc["id"], doc))
        scored.sort(key=lambda item: (item[0], item[1]))
        return {"docs": [doc for _neg, _id, doc in scored]}

    def get_service_status(self, service: str) -> dict:
        truth = self.truth[service]
        return {
            "service": service,
            "version": truth["version"],
            "status": truth["status"],
        }

    def get_metric(self, service: str, metric: str) -> dict:
        truth = self.truth[service]
        return {
            "service": service,
            "metric": metric,
            "value": truth["error_rate"],
        }

    def tools(self) -> dict:
        """The clean tool dict the agent receives (injectors wrap this)."""
        return {
            "search_docs": self.search_docs,
            "get_service_status": self.get_service_status,
            "get_metric": self.get_metric,
        }
