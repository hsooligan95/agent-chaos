# Copilot instructions — agent-chaos

You are working in **AgentChaos**, chaos engineering for AI agents: it
injects real failure modes (flaky tools, hallucinating tools, prompt
injection in retrieved content, poisoned results, corrupted context) into
a sample agent and measures whether it recovers, fails loudly, or fails
silently.

## Stack

- Python >= 3.10, standard library only — zero runtime dependencies.
- Entry points: `run.py` / `python -m agentchaos`; scenario matrix writes
  `results/report.md` and `results/report.json`.

## Tests

```bash
pip install -e ".[test]"
python -m pytest
python run.py run   # full matrix: scenarios x defenses off/on
```

## Architecture notes

- The headline metric is the silent-failure rate. Every scenario runs
  twice — defenses OFF and defenses ON — and that paired structure is
  the product; never collapse it into a single run.
- Scorers compare the agent's answer against the sandbox world's known
  ground truth, never against the agent's self-report.
- Each report carries its own identity: `run_id` (`--run-id` >
  `AGENTCHAOS_RUN_ID` env > minted, the agent-canary pattern) and
  `generated_at`. AgentTrace ingests reports by that identity — keep
  the report JSON shape stable.
- Everything is deterministic and offline: no API keys, no network, no
  unseeded randomness.

## Shared rules

- Use Unix LF line endings in every file; never CRLF.
- Never commit secrets, tokens, or credentials — real or synthetic-looking.
- Tests must pass before you describe a change as complete; run the test
  command above and report honestly if you cannot.
- Prefer the smallest complete implementation: reuse what already exists in
  this repo before adding new code, files, or dependencies.
