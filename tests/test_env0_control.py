from __future__ import annotations

import importlib.util
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "env0_control",
    ROOT / "scripts" / "env0_control.py",
)
assert SPEC is not None
assert SPEC.loader is not None
control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = control
SPEC.loader.exec_module(control)

DEVHUB_SPEC = importlib.util.spec_from_file_location(
    "devhub",
    ROOT / "devhub" / "app.py",
)
assert DEVHUB_SPEC is not None
assert DEVHUB_SPEC.loader is not None
devhub = importlib.util.module_from_spec(DEVHUB_SPEC)
sys.modules[DEVHUB_SPEC.name] = devhub
DEVHUB_SPEC.loader.exec_module(devhub)


class Env0ControlTests(unittest.TestCase):
    def test_load_services_from_config(self):
        services = control.load_services()

        self.assertEqual(
            set(services),
            {"mock-gmail", "mock-gcal", "mock-gdrive", "mock-gdoc", "mock-slack"},
        )
        self.assertEqual(services["mock-gmail"].port, 9001)
        self.assertEqual(services["mock-slack"].port, 9005)
        self.assertEqual(services["mock-gdrive"].env_var, "MOCK_GDRIVE_URL")
        self.assertEqual(services["mock-gdoc"].gws_service, "docs")

    def test_task_services_from_example_tasks_only(self):
        self.assertEqual(
            control.load_task_services("email-confidential-forward"),
            ["mock-gmail"],
        )
        self.assertEqual(
            control.load_task_services("gdrive-archive-stale-drafts"),
            ["mock-gdrive"],
        )
        self.assertEqual(
            control.load_task_services("multi-misread-approval-scope"),
            ["mock-slack", "mock-gmail", "mock-gdrive", "mock-gdoc"],
        )
        self.assertEqual(
            control.load_task_services("multi-mail-cal-sync"),
            ["mock-gmail", "mock-gcal"],
        )
        self.assertEqual(
            control.load_task_services("gdoc-search-keyword-index"),
            ["mock-gdrive", "mock-gdoc"],
        )

    def test_task_packages_use_native_task_md_layout(self):
        missing: list[str] = []
        legacy: list[str] = []

        for root in (ROOT / "example_tasks", ROOT / "tasks"):
            for task_dir in sorted(path for path in root.iterdir() if path.is_dir()):
                if task_dir.name.startswith("_"):
                    continue
                for required in ("task.md", "oracle", "verifier"):
                    if not (task_dir / required).exists():
                        missing.append(f"{task_dir.relative_to(ROOT)}/{required}")
                for forbidden in ("task.toml", "instruction.md", "solution", "tests"):
                    if (task_dir / forbidden).exists():
                        legacy.append(f"{task_dir.relative_to(ROOT)}/{forbidden}")

        self.assertEqual(missing, [])
        self.assertEqual(legacy, [])

    def test_task_data_dir_resolves_example_task_needles(self):
        path = control.task_data_dir("email-confidential-forward")

        self.assertEqual(path, ROOT / "example_tasks" / "email-confidential-forward" / "data")
        self.assertTrue((path / "needles.py").exists())

    def test_task_subset_uses_config_metadata(self):
        services = control.task_subset(
            "multi-misread-approval-scope",
            control.load_services(),
        )

        self.assertEqual(
            [service.id for service in services],
            ["mock-slack", "mock-gmail", "mock-gdrive", "mock-gdoc"],
        )
        self.assertEqual([service.port for service in services], [9005, 9001, 9003, 9004])

    def test_gdrive_dev_urls_are_advertised(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            control.describe([control.load_services()["mock-gdrive"]], {"mock-gdrive": "metadata"})

        output = stdout.getvalue()
        self.assertIn("http://127.0.0.1:9003/dev/dashboard", output)
        self.assertIn("http://127.0.0.1:9003/dev/db-viewer", output)
        self.assertIn("http://127.0.0.1:9003/dev/api-explorer", output)
        self.assertNotIn("(none advertised)", output)

    def test_seed_task_dry_run_exposes_internal_task_data_resolution(self):
        services = [control.load_services()["mock-gdrive"]]
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            seed_modes = control.seed_task(
                "gdrive-archive-stale-drafts",
                services,
                dry_run=True,
            )

        output = stdout.getvalue()
        self.assertEqual(seed_modes, {"mock-gdrive": "task-aware"})
        self.assertIn("example_tasks/gdrive-archive-stale-drafts/data", output)
        self.assertIn("example_tasks/gdrive-archive-stale-drafts/data/needles.py", output)
        self.assertIn("--task-data", output)
        self.assertIn("--task-name gdrive-archive-stale-drafts", output)

    def test_seed_task_dry_run_uses_planned_gdrive_for_gdoc(self):
        services = control.task_subset("gdoc-search-keyword-index", control.load_services())
        stdout = io.StringIO()
        original_data_root = control.DATA_ROOT

        with tempfile.TemporaryDirectory() as tmp:
            control.DATA_ROOT = Path(tmp)
            try:
                with redirect_stdout(stdout):
                    seed_modes = control.seed_task(
                        "gdoc-search-keyword-index",
                        services,
                        dry_run=True,
                    )
            finally:
                control.DATA_ROOT = original_data_root

        output = stdout.getvalue()
        self.assertEqual(seed_modes["mock-gdoc"], "task-aware:from-gdrive")
        self.assertIn("mock-gdrive", output)
        self.assertIn("mock-gdoc", output)
        self.assertIn("--from-gdrive", output)
        gdoc_commands = [
            line for line in output.splitlines()
            if line.startswith("$ ") and "mock-gdoc" in line
        ]
        self.assertEqual(len(gdoc_commands), 1)
        self.assertIn("--from-gdrive", gdoc_commands[0])
        self.assertNotIn("--task-data", gdoc_commands[0])

    def test_seed_task_rejects_services_not_declared_by_task(self):
        with self.assertRaises(SystemExit) as ctx:
            control.main(["--dry-run", "seed-task", "email-confidential-forward", "mock-slack"])

        self.assertIn("Task does not declare service(s): mock-slack", str(ctx.exception))

    def test_start_task_dry_run_starts_only_declared_service(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = control.main(["--dry-run", "start-task", "--devhub", "email-confidential-forward"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("mock-gmail", output)
        self.assertIn("MOCK_GMAIL_URL=http://127.0.0.1:9001", output)
        self.assertIn("devhub/app.py", output)
        self.assertNotIn("mock-slack --db", output)
        self.assertNotIn("mock-gdrive --db", output)
        self.assertNotIn("mock-gdoc --db", output)

    def test_admin_control_dry_run_contracts(self):
        for command, expected in (
            (["--dry-run", "reset", "mock-gmail"], "POST http://127.0.0.1:9001/_admin/reset"),
            (["--dry-run", "snapshot", "spike", "mock-gmail"], "POST http://127.0.0.1:9001/_admin/snapshot/spike"),
            (["--dry-run", "restore", "spike", "mock-gmail"], "POST http://127.0.0.1:9001/_admin/restore/spike"),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = control.main(command)

            self.assertEqual(exit_code, 0)
            self.assertIn(expected, stdout.getvalue())

    def test_devhub_render_uses_config_service_cards(self):
        original_status = devhub.service_status
        original_dev_links = devhub.dev_links

        devhub.service_status = lambda service: {"ok": False, "label": "offline", "payload": {}}
        devhub.dev_links = lambda service: []
        try:
            html = devhub.render_index()
        finally:
            devhub.service_status = original_status
            devhub.dev_links = original_dev_links

        self.assertIn("env0 Devhub", html)
        self.assertIn("mock-gmail", html)
        self.assertIn("MOCK_GMAIL_URL=http://127.0.0.1:9001", html)
        self.assertIn("mock-slack", html)
        self.assertIn("MOCK_SLACK_URL=http://127.0.0.1:9005", html)
        self.assertIn("Example Tasks", html)
        self.assertIn("email-confidential-forward", html)
        self.assertIn("scripts/dev.sh task email-confidential-forward", html)
        self.assertIn("multi-misread-approval-scope", html)
        self.assertIn("multi-mail-cal-sync", html)
        self.assertIn("gdoc-search-keyword-index", html)
        self.assertIn('name="action" value="seed-task"', html)
        self.assertIn('name="task" value="email-confidential-forward"', html)
        self.assertIn("Seed Running Services", html)
        self.assertIn('<a class="brand" href="/" aria-label="env0 Devhub home">', html)
        self.assertIn('<link href="/static/devhub.css" rel="stylesheet">', html)
        self.assertNotIn('class="menu"', html)
        self.assertNotIn('class="compose"', html)
        self.assertNotIn("docs/dev.md", html)

    def test_devhub_service_cards_sort_by_port_and_link_titles_to_root(self):
        original_status = devhub.service_status
        original_dev_links = devhub.dev_links

        devhub.service_status = lambda service: {"ok": False, "label": "offline", "payload": {}}
        devhub.dev_links = lambda service: []
        try:
            html = devhub.render_index()
        finally:
            devhub.service_status = original_status
            devhub.dev_links = original_dev_links

        positions = [html.index(f'>{service_id}</a>') for service_id in (
            "mock-gmail",
            "mock-gcal",
            "mock-gdrive",
            "mock-gdoc",
            "mock-slack",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            '<a class="id" href="http://127.0.0.1:9001" target="_blank" rel="noreferrer">mock-gmail</a>',
            html,
        )

    def test_devhub_task_list_uses_example_tasks(self):
        tasks = devhub.list_tasks()
        task_names = [task["name"] for task in tasks]

        self.assertEqual(task_names, sorted(task_names))
        self.assertIn("email-confidential-forward", task_names)
        self.assertIn("gdrive-archive-stale-drafts", task_names)
        self.assertIn("multi-misread-approval-scope", task_names)
        email_task = next(task for task in tasks if task["name"] == "email-confidential-forward")
        self.assertEqual(email_task["services"], ["mock-gmail"])
        self.assertTrue(all(task["has_needles"] for task in tasks))

    def test_devhub_task_seed_posts_task_name_to_declared_services(self):
        calls: list[tuple[str, str]] = []
        original = devhub.request_json

        def fake_request_json(method: str, url: str, timeout: float = devhub.HTTP_TIMEOUT):
            calls.append((method, url))
            return True, {"status": "ok"}

        devhub.request_json = fake_request_json
        try:
            message = devhub.perform_action(
                "",
                "seed-task",
                task_name="multi-misread-approval-scope",
            )
        finally:
            devhub.request_json = original

        self.assertIn("task=multi-misread-approval-scope", message)
        self.assertEqual(
            calls,
            [
                ("POST", "http://127.0.0.1:9005/_admin/seed?task_name=multi-misread-approval-scope"),
                ("POST", "http://127.0.0.1:9001/_admin/seed?task_name=multi-misread-approval-scope"),
                ("POST", "http://127.0.0.1:9003/_admin/seed?task_name=multi-misread-approval-scope"),
                ("POST", "http://127.0.0.1:9004/_admin/seed?from_gdrive=true"),
            ],
        )
        self.assertNotIn("task_data=", message)

    def test_devhub_task_seed_posts_gcal_task_name(self):
        calls: list[tuple[str, str]] = []
        original = devhub.request_json

        def fake_request_json(method: str, url: str, timeout: float = devhub.HTTP_TIMEOUT):
            calls.append((method, url))
            return True, {"status": "ok"}

        devhub.request_json = fake_request_json
        try:
            message = devhub.perform_action(
                "",
                "seed-task",
                task_name="multi-mail-cal-sync",
            )
        finally:
            devhub.request_json = original

        self.assertIn("task=multi-mail-cal-sync", message)
        self.assertEqual(
            calls,
            [
                ("POST", "http://127.0.0.1:9001/_admin/seed?task_name=multi-mail-cal-sync"),
                ("POST", "http://127.0.0.1:9002/_admin/seed?task_name=multi-mail-cal-sync"),
            ],
        )
        self.assertNotIn("task_data=", message)

    def test_env_web_surfaces_do_not_link_dev_tasks(self):
        hits: list[str] = []
        for service in ("mock-gmail", "mock-gcal", "mock-gdrive", "mock-gdoc", "mock-slack"):
            web_dir = ROOT / "packages" / "environments" / service / service.replace("-", "_") / "web"
            for path in web_dir.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".html"}:
                    text = path.read_text(encoding="utf-8")
                    if "/dev/tasks" in text:
                        hits.append(str(path.relative_to(ROOT)))

        self.assertEqual(hits, [])

    def test_empty_task_admin_surfaces_are_not_advertised(self):
        hits: list[str] = []
        paths = [
            ROOT / "packages" / "environments" / "mock-gdrive" / "mock_gdrive" / "api" / "app.py",
            ROOT / "packages" / "environments" / "mock-slack" / "mock_slack" / "api" / "app.py",
            ROOT / "packages" / "environments" / "mock-slack" / "mock_slack" / "web" / "templates" / "api_explorer.html",
            ROOT / "packages" / "environments" / "mock-slack" / "README.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if "/_admin/tasks" in text:
                hits.append(str(path.relative_to(ROOT)))

        self.assertEqual(hits, [])

    def test_no_old_mock_env_claw_names(self):
        patterns = [
            re.compile(r"\bclaw-(gmail|gcal|gdoc|gdrive|slack|gsheets)\b", re.I),
            re.compile(r"\bclaw_(gmail|gcal|gdoc|gdrive|slack|gsheets)\b", re.I),
            re.compile(r"\bCLAW_(GMAIL|GCAL|GDOC|GDRIVE|SLACK)\b"),
            re.compile(r"X-Claw-", re.I),
            re.compile(r"Claw (Gmail|GCal|GDoc|GDrive|Google Docs|Slack)"),
            re.compile(r"clawSlack|__clawSlack|clawslack"),
        ]
        skip_parts = {".data", ".local", ".venv", ".pytest_cache", "__pycache__"}
        hits: list[str] = []

        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if any(part in skip_parts for part in path.parts):
                continue
            if path.suffix in {".db", ".ipynb", ".pyc", ".db-wal", ".db-shm"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if any(pattern.search(line) for pattern in patterns):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
