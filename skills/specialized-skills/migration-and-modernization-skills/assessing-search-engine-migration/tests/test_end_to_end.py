"""End-to-end smoke test: run report generation against the sample profile."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SAMPLE = SCRIPTS / "sample_profile.json"


class TestEndToEnd(unittest.TestCase):
    def test_validate_passes_on_sample(self) -> None:
        out = subprocess.run(
            [sys.executable, "source_assessor.py", "validate", "--profile-json", str(SAMPLE)],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(out.stdout)
        self.assertTrue(result["ok"], msg=result)

    def test_decide_target_runs(self) -> None:
        out = subprocess.run(
            [sys.executable, "decision_engine.py", "target", "--profile-json", str(SAMPLE)],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(out.stdout)
        self.assertIn(result["choice"], {
            "service-general", "service-large-scale", "service-ultrawarm",
            "aoss-search", "aoss-time-series", "aoss-vector",
        })

    def test_decide_path_runs(self) -> None:
        out = subprocess.run(
            [sys.executable, "decision_engine.py", "path", "--profile-json", str(SAMPLE)],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(out.stdout)
        self.assertIn(result["choice"], {
            "migration-assistant", "snapshot-and-restore", "osi", "direct-from-source",
        })

    def test_pricing_estimator_runs(self) -> None:
        out = subprocess.run(
            [sys.executable, "pricing_estimator.py", "both",
             "--profile-json", str(SAMPLE),
             "--target", "service-general"],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(out.stdout)
        self.assertIn("sizing", result)
        self.assertIn("pricing", result)
        self.assertIn("steady_state", result["pricing"])
        self.assertIn("disclaimer", result["pricing"])

    def test_report_renders_and_includes_disclaimer(self) -> None:
        out = subprocess.run(
            [sys.executable, "source_assessor.py", "report",
             "--profile-json", str(SAMPLE)],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            check=True,
        )
        md = out.stdout
        self.assertIn("# Migration Assessment", md)
        self.assertIn("Pricing disclaimer", md)
        self.assertIn("AWS Knowledge MCP", md)
        self.assertIn("Recommended target", md)
        self.assertIn("Recommended migration path", md)


if __name__ == "__main__":
    unittest.main()
