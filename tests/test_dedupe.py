
import unittest

from apps.worker.dedupe import should_create_pr
from lib.findings import Finding


class TestDedupe(unittest.TestCase):
    def test_should_create_pr_with_critical_findings(self):
        """Test that critical findings trigger PR creation."""
        findings = [
            Finding(
                severity="critical",
                category="security",
                file="test.py",
                line=10,
                message="SQL injection vulnerability",
                tool="bandit",
            )
        ]
        self.assertTrue(should_create_pr(findings))

    def test_should_create_pr_with_error_findings(self):
        """Test that error findings trigger PR creation."""
        findings = [
            Finding(
                severity="error",
                category="correctness",
                file="test.sh",
                line=5,
                message="Syntax error",
                tool="shellcheck",
            )
        ]
        self.assertTrue(should_create_pr(findings))

    def test_should_create_pr_with_fix_available(self):
        """Test that findings with available fixes trigger PR creation."""
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="test.py",
                line=3,
                message="Missing docstring",
                tool="pylint",
                fix_available=True,
            )
        ]
        self.assertTrue(should_create_pr(findings))

    def test_should_create_pr_with_only_warnings(self):
        """Test that only warnings do NOT trigger PR creation."""
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="test.py",
                line=1,
                message="Line too long",
                tool="pylint",
            )
        ]
        self.assertFalse(should_create_pr(findings))

    def test_should_create_pr_with_only_info(self):
        """Test that only info findings do NOT trigger PR creation."""
        findings = [
            Finding(
                severity="info",
                category="style",
                file="test.py",
                line=2,
                message="Consider refactoring",
                tool="pylint",
            )
        ]
        self.assertFalse(should_create_pr(findings))

    def test_should_create_pr_with_mixed_findings(self):
        """Test that mixed findings with at least one actionable triggers PR creation."""
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="test.py",
                line=1,
                message="Line too long",
                tool="pylint",
            ),
            Finding(
                severity="error",
                category="correctness",
                file="test.py",
                line=10,
                message="Undefined variable",
                tool="pylint",
            ),
            Finding(
                severity="info",
                category="style",
                file="test.py",
                line=20,
                message="Consider using f-string",
                tool="pylint",
            ),
        ]
        self.assertTrue(should_create_pr(findings))

    def test_should_create_pr_with_empty_findings(self):
        """Test that empty findings do NOT trigger PR creation."""
        findings = []
        self.assertFalse(should_create_pr(findings))

    def test_should_create_pr_with_iterator(self):
        """Test that the function works with iterators (consuming them safely)."""
        findings_list = [
            Finding(
                severity="error",
                category="correctness",
                file="test.py",
                line=5,
                message="Error",
                tool="test",
            )
        ]
        findings_iter = iter(findings_list)
        self.assertTrue(should_create_pr(findings_iter))


if __name__ == "__main__":
    unittest.main()
