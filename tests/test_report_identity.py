"""Report identity: run_id + generated_at stamping (emit-side only).

The matrix itself is unchanged; the report now names its own run so an
AgentTrace ingestor can key it to a fleet trace without inventing an
identity. Without a supplied ID the CLI mints one; build_report adds
the keys only when given them.
"""

import json
from pathlib import Path

from agentchaos.__main__ import main
from agentchaos.report import build_report
from agentchaos.runner import run_matrix


def test_build_report_omits_identity_by_default():
    report = build_report(run_matrix())
    assert "run_id" not in report
    assert "generated_at" not in report


def test_build_report_stamps_identity_when_given():
    report = build_report(run_matrix(), run_id="trace-x",
                          generated_at="2026-11-21T00:00:00Z")
    assert report["run_id"] == "trace-x"
    assert report["generated_at"] == "2026-11-21T00:00:00Z"
    assert report["headline"]["fault_scenarios"] == 5


def test_cli_stamps_supplied_run_id(tmp_path):
    assert main(["run", "--out", str(tmp_path), "--run-id", "trace-cli-1"]) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == "trace-cli-1"
    assert report["generated_at"].endswith("Z")
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "trace-cli-1" in md


def test_cli_env_run_id(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTCHAOS_RUN_ID", "trace-env-1")
    assert main(["run", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == "trace-env-1"
