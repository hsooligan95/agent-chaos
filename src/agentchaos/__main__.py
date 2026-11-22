"""CLI: ``python -m agentchaos run [--out results] [--run-id <id>]``.

The run ID comes from --run-id, else the AGENTCHAOS_RUN_ID env var,
else a freshly minted one — the pattern agent-canary established. It is
stamped into the report alongside the generation time so an AgentTrace
ingestor can key the report to a fleet trace without inventing either.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

from .report import build_report, write_reports
from .runner import run_matrix
from .scoring import silent_failure_rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentchaos")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="run the full scenario matrix")
    run_parser.add_argument(
        "--out", default="results", help="directory for report.md / report.json"
    )
    run_parser.add_argument(
        "--run-id", default=None,
        help="run ID stamped into the report "
             "(default: AGENTCHAOS_RUN_ID env var, else a minted ID)",
    )
    args = parser.parse_args(argv)

    if args.command == "run":
        run_id = (
            args.run_id
            or os.environ.get("AGENTCHAOS_RUN_ID")
            or f"chaos-{uuid.uuid4().hex[:8]}"
        )
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # Instance identity for fleet rollups (AgentTrace): the
        # shared AGENT_INSTANCE env var; "default" when unset.
        instance = os.environ.get("AGENT_INSTANCE") or "default"
        rows = run_matrix()
        report = build_report(rows, run_id=run_id,
                              generated_at=generated_at, instance=instance)
        md_path, json_path = write_reports(report, args.out)
        off = silent_failure_rate([r for r in rows if r["mode"] == "off"])
        on = silent_failure_rate([r for r in rows if r["mode"] == "on"])
        for r in rows:
            det = (
                f"detected@step{r['detection_step']}" if r["detected"] else "not detected"
            )
            print(
                f"{r['scenario']:<22} mode={r['mode']:<3} {r['outcome']:<16} {det}"
            )
        print(f"\nSilent-failure rate: defenses OFF {off:.0%} -> defenses ON {on:.0%}")
        print(f"Reports written: {md_path}, {json_path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
