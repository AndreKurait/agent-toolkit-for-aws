"""Smoke tests for the Bedrock eval harness.

These tests verify the harness CLI structure, YAML loader, and assertion
engine WITHOUT calling Bedrock. The actual Bedrock end-to-end run is
gated by AWS credentials and lives in `evals/run_bedrock.py --dry-run` /
without `--dry-run`. The unit tests here ensure the harness itself
doesn't regress.
"""
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
HARNESS = SKILL_ROOT / "evals" / "run_bedrock.py"


class TestBedrockHarnessSmoke(unittest.TestCase):
    """Exercise the harness in dry-run mode (no Bedrock call)."""

    def test_harness_help(self):
        r = subprocess.run([sys.executable, str(HARNESS), "--help"],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--model", r.stdout)
        self.assertIn("--region", r.stdout)
        self.assertIn("--dry-run", r.stdout)
        self.assertIn("--tests", r.stdout)

    def test_dry_run_discovers_all_fixtures(self):
        """Dry-run finds every YAML under evals/tests/ and exits 1
        because the placeholder output doesn't satisfy the assertions —
        but the discovery itself must succeed cleanly."""
        r = subprocess.run([sys.executable, str(HARNESS), "--dry-run"],
                           capture_output=True, text=True, timeout=20,
                           cwd=str(SKILL_ROOT))
        # exit 1 is expected — assertions shouldn't pass in dry-run.
        self.assertIn(r.returncode, (0, 1),
                      f"unexpected rc={r.returncode}\nstderr={r.stderr}")
        self.assertIn("tests:   8", r.stdout)
        self.assertIn("Results:", r.stdout)

    def test_dry_run_with_specific_fixture(self):
        fixture = SKILL_ROOT / "evals" / "tests" / "citations-required.yaml"
        r = subprocess.run(
            [sys.executable, str(HARNESS), "--dry-run",
             "--tests", str(fixture)],
            capture_output=True, text=True, timeout=10,
            cwd=str(SKILL_ROOT))
        self.assertIn(r.returncode, (0, 1))
        self.assertIn("citations-required", r.stdout)
        self.assertIn("tests:   1", r.stdout)


class TestBedrockHarnessYAMLLoader(unittest.TestCase):
    """Direct test of the minimal YAML loader."""

    def setUp(self):
        sys.path.insert(0, str(SKILL_ROOT / "evals"))
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_bedrock", HARNESS)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_minimal_yaml_loader_handles_fixture(self):
        fixture = SKILL_ROOT / "evals" / "tests" / "citations-required.yaml"
        spec = self.mod._load_yaml_minimal(fixture.read_text())
        self.assertIn("vars", spec)
        self.assertIn("scenario", spec["vars"])
        self.assertIn("assert", spec)
        self.assertGreater(len(spec["assert"]), 0)
        for a in spec["assert"]:
            self.assertIn("type", a)
            self.assertIn("value", a)

    def test_assertion_types(self):
        cases = [
            ({"type": "contains", "value": "foo"},   "x foo y", True),
            ({"type": "contains", "value": "FOO"},   "x foo y", False),
            ({"type": "icontains", "value": "FOO"},  "x foo y", True),
            ({"type": "not-contains", "value": "z"}, "x foo y", True),
            ({"type": "not-contains", "value": "x"}, "x foo y", False),
            ({"type": "regex", "value": r"\d{4}"},   "as of 2026", True),
            ({"type": "regex", "value": r"\d{4}"},   "no digits", False),
        ]
        for assertion, output, expected in cases:
            ok, _ = self.mod.run_assertion(assertion, output)
            self.assertEqual(ok, expected,
                             f"{assertion} on {output!r} expected {expected}")


if __name__ == "__main__":
    unittest.main()
