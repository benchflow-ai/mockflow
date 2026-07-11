from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
MANIFEST_PATH = TASKS_DIR / "STANDARD60_MANIFEST.txt"
PUBLIC_SERVICE_PATTERN = re.compile(
    r"(?m)^RUN\s+(mock-(?:auth|gmail|gcal|gdrive|gdoc|slack|stripe))\s+--db\b"
)
PRIVATE_NAMESPACE_PATTERN = re.compile(
    r"env_0_(?:auth|gcal|gdrive|gmail|stripe)"
)
ASSIGNABLE_SSN_PATTERN = re.compile(
    r"(?<!\d)(?!000|666|9\d\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)"
)
REAL_SECRET_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
)


def task_services(task_md: Path) -> set[str]:
    lines = task_md.read_text().splitlines()
    for index, line in enumerate(lines):
        if line != "  env0:":
            continue
        if index + 1 >= len(lines) or lines[index + 1] != "    services:":
            break
        services: set[str] = set()
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].startswith("    - "):
            services.add(lines[cursor][6:])
            cursor += 1
        return services
    return set()


class Standard60TaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.version = (ROOT / "VERSION").read_text().strip()
        cls.expected = tuple(
            line.strip()
            for line in MANIFEST_PATH.read_text().splitlines()
            if line.strip()
        )

    def test_manifest_is_sorted_unique_standard60(self) -> None:
        self.assertEqual(len(self.expected), 60)
        self.assertEqual(tuple(sorted(set(self.expected))), self.expected)

    def test_task_directories_exactly_match_manifest(self) -> None:
        actual = tuple(
            sorted(
                path.name
                for path in TASKS_DIR.iterdir()
                if path.is_dir() and path.name != "_manifests"
            )
        )
        self.assertEqual(actual, self.expected)
        self.assertFalse((TASKS_DIR / "discord-incident-followup").exists())
        self.assertTrue(
            (ROOT / "example_tasks" / "discord-incident-followup").is_dir()
        )

    def test_all_public_tasks_use_native_task_md_layout(self) -> None:
        expected_from = f"FROM ghcr.io/benchflow-ai/env0:{self.version}"
        for task_root in (TASKS_DIR, ROOT / "example_tasks"):
            for task_dir in sorted(task_root.iterdir()):
                if not task_dir.is_dir() or task_dir.name == "_manifests":
                    continue
                with self.subTest(root=task_root.name, task=task_dir.name):
                    self.assertTrue((task_dir / "task.md").is_file())
                    self.assertFalse((task_dir / "task.toml").exists())
                    self.assertFalse((task_dir / "instruction.md").exists())
                    self.assertFalse((task_dir / "solution").exists())
                    self.assertFalse((task_dir / "tests").exists())
                    dockerfile = task_dir / "environment" / "Dockerfile"
                    self.assertTrue(dockerfile.is_file())
                    self.assertEqual(
                        dockerfile.read_text().splitlines()[0],
                        expected_from,
                    )

    def test_packages_use_public_native_contract(self) -> None:
        required = (
            "task.md",
            "environment/Dockerfile",
            "oracle/solve.sh",
            "verifier/evaluate.py",
            "verifier/test.sh",
        )
        expected_from = f"FROM ghcr.io/benchflow-ai/env0:{self.version}"

        for task_name in self.expected:
            with self.subTest(task=task_name):
                task_dir = TASKS_DIR / task_name
                for relative_path in required:
                    self.assertTrue((task_dir / relative_path).is_file())

                self.assertFalse((task_dir / "tests").exists())
                self.assertFalse((task_dir / "solution").exists())
                self.assertFalse((task_dir / "task.toml").exists())
                self.assertFalse((task_dir / "instruction.md").exists())

                dockerfile = task_dir / "environment" / "Dockerfile"
                docker_text = dockerfile.read_text()
                self.assertEqual(docker_text.splitlines()[0], expected_from)
                self.assertIn("RUN chmod -R 700 /tasks", docker_text)
                self.assertNotIn("ghcr.io/benchflow-ai/env-0-base", docker_text)
                self.assertNotIn("/etc/env-0/", docker_text)

                declared_services = task_services(task_dir / "task.md")
                seeded_services = set(PUBLIC_SERVICE_PATTERN.findall(docker_text))
                self.assertEqual(declared_services, seeded_services)

                for path in task_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    try:
                        text = path.read_text()
                    except UnicodeDecodeError:
                        continue
                    self.assertIsNone(
                        PRIVATE_NAMESPACE_PATTERN.search(text),
                        f"private runtime namespace in {path}",
                    )

    def test_environment_manifest_uses_current_public_image(self) -> None:
        manifest = (TASKS_DIR / "_manifests" / "env-0.toml").read_text()
        self.assertIn(
            f'base_image     = "ghcr.io/benchflow-ai/env0:{self.version}"',
            manifest,
        )

    def test_snapshot_has_no_realistic_sensitive_values(self) -> None:
        for task_name in self.expected:
            task_dir = TASKS_DIR / task_name
            for path in task_dir.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text()
                except UnicodeDecodeError:
                    continue
                with self.subTest(task=task_name, path=path):
                    self.assertIsNone(ASSIGNABLE_SSN_PATTERN.search(text))
                    self.assertNotIn("/Users/", text)
                    self.assertNotIn(".codex/worktrees", text)
                    for pattern in REAL_SECRET_PATTERNS:
                        self.assertIsNone(pattern.search(text))

    def test_contributor_fixture_identities_are_synthetic(self) -> None:
        path = (
            TASKS_DIR
            / "multi-mail-slack-invite"
            / "data"
            / "skillsbench_tasks.csv"
        )
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertRegex(
                row["author_email"],
                r"^contributor\d{2}@skillsbench\.test$",
            )
            self.assertRegex(
                row["author_github_handle"],
                r"^contributor-\d{2}$",
            )


if __name__ == "__main__":
    unittest.main()
