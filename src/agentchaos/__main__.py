"""CLI: ``python -m agentchaos run [--out results]``."""

from __future__ import annotations

import argparse
import sys

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
    args = parser.parse_args(argv)

    if args.command == "run":
        rows = run_matrix()
        report = build_report(rows)
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
