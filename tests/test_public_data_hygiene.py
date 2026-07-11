from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
MOCK_PRIVATE_KEY_PATH = (
    "packages/environments/mock-auth/mock_auth/seed/keys/"
    "env-0-auth-key-001.pem"
)
INTENTIONAL_PEM_FIXTURES = {
    MOCK_PRIVATE_KEY_PATH,
    "packages/environments/mock-auth/mock_auth/seed/keys/"
    "env-0-auth-key-001.pub.pem",
}
HIGH_RISK_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "OpenAI key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "Anthropic key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Stripe live key": re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}\b"),
    "JWT": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "assignable SSN": re.compile(
        r"(?<!\d)(?!000|666|9\d\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)"
    ),
    "credentialed database URL": re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
        r"[^/\s:@]+:[^@\s/]+@",
        re.IGNORECASE,
    ),
    "local macOS path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "Codex worktree path": re.compile(r"\.codex/worktrees/[A-Za-z0-9._-]+"),
    "private repository URL": re.compile(
        r"github\.com/benchflow-ai/(?:env-0|env-0-experiment|cbench-test)"
        r"(?:/|\b)"
    ),
    "unsanitized Slack capture email": re.compile(r"@andrew\.cmu\.edu\b"),
}
SENSITIVE_FILE_PATTERN = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\..*)?|auth\.json|token.*\.json|"
    r"client_secret.*\.json|credentials.*\.json|id_rsa.*|"
    r".*\.(?:p12|pfx|kdbx|key|pem|sqlite3?|db))$"
)


def candidate_files() -> list[Path]:
    command = [
        "git",
        "-C",
        str(ROOT),
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    ]
    output = subprocess.check_output(command)
    paths = []
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path.decode()
        if path.is_file():
            paths.append(path)
    return paths


class PublicDataHygieneTests(unittest.TestCase):
    def test_no_sensitive_files_are_tracked_or_pending(self) -> None:
        findings = []
        for path in candidate_files():
            relative = path.relative_to(ROOT).as_posix()
            if relative in INTENTIONAL_PEM_FIXTURES:
                continue
            if SENSITIVE_FILE_PATTERN.search(relative):
                findings.append(relative)
        self.assertEqual(findings, [])

    def test_no_high_risk_values_or_private_paths(self) -> None:
        findings = []
        for path in candidate_files():
            if path.resolve() == THIS_FILE:
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in INTENTIONAL_PEM_FIXTURES:
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for label, pattern in HIGH_RISK_PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{label}: {relative}")
        self.assertEqual(findings, [])

    def test_mock_private_key_is_loudly_non_secret(self) -> None:
        key_path = ROOT / MOCK_PRIVATE_KEY_PATH
        header = "\n".join(key_path.read_text().splitlines()[:8])
        self.assertIn("NOT A SECRET", header)
        self.assertIn("fake users on localhost", header)


if __name__ == "__main__":
    unittest.main()
