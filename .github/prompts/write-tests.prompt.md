---
mode: agent
description: Write tests for a named module in agent-chaos
---

Write tests for the module I name, following this repo's existing test
style, layout, and fixtures. Cover the behavior the module documents,
including these invariants where they apply:

- Every scenario runs twice — defenses OFF and defenses ON; never collapse the paired structure into a single run.
- Scorers compare the agent's answer against the sandbox world's ground truth, never the agent's self-report.
- Report identity (run_id, generated_at) and the report JSON shape stay stable — AgentTrace ingests reports by that identity.

Then run the test suite:

    python -m pytest

Show the result. Do not claim done unless the suite is green; if a
test cannot pass, say why instead of weakening the assertion.
