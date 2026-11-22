---
mode: agent
description: Review the current diff against agent-chaos's invariants
---

Review my current diff against this repo's invariants:

- Every scenario runs twice — defenses OFF and defenses ON; never collapse the paired structure into a single run.
- Scorers compare the agent's answer against the sandbox world's ground truth, never the agent's self-report.
- Report identity (run_id, generated_at) and the report JSON shape stay stable — AgentTrace ingests reports by that identity.
- Everything is deterministic and offline: no API keys, no network, no unseeded randomness.

Flag every violation with file and line. Also flag any change that
alters a documented behavior contract (output shapes, exit codes,
event schemas, recorded artifacts) without updating the docs and
tests that describe it. No style nitpicks — correctness and contract
violations only.
