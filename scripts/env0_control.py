#!/usr/bin/env python3
"""Repo-local control contract for env0 dev sessions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.toml"
EXAMPLE_TASKS = ROOT / "example_tasks"
DATA_ROOT = ROOT / ".data" / "dev"
ORACLE_ROOT = ROOT / ".data" / "oracle"

HEALTH_PATH = "/health"
DEV_PATHS = ("/dev/dashboard", "/dev/db-viewer", "/dev/api-explorer")
TASK_DATA_SERVICES = {"mock-gmail", "mock-gcal", "mock-gdrive", "mock-gdoc", "mock-slack"}
DEVHUB_PORT = 9060


@dataclass(frozen=True)
class Service:
    id: str
    port: int
    db_path: str
    env_var: str
    gws_service: str | None = None

    @property
    def cli(self) -> str:
        return self.id

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def abs_db_path(self) -> Path:
        db_path = Path(self.db_path)
        if db_path.is_absolute():
            return DATA_ROOT / db_path.relative_to("/")
        return DATA_ROOT / db_path

    @property
    def package_dir(self) -> Path:
        return ROOT / "packages" / "environments" / self.id


@dataclass(frozen=True)
class TaskMetadata:
    name: str
    services: list[str]
    tags: list[str]
    instruction: str


def load_services() -> dict[str, Service]:
    data = tomllib.loads(CONFIG_PATH.read_text())
    if data.get("runtime", {}).get("version") != 1:
        raise SystemExit(f"Unsupported runtime version in {CONFIG_PATH}")

    services: dict[str, Service] = {}
    for section, meta in data.items():
        if not section.startswith("mock-"):
            continue
        services[section] = Service(
            id=section,
            port=int(meta["port"]),
            db_path=str(meta["db_path"]),
            env_var=str(meta["env_var"]),
            gws_service=meta.get("gws_service"),
        )
    return dict(sorted(services.items()))


def _parse_yaml_scalar(value: str) -> str:
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1].replace("''", "'")
    return value


def _parse_inline_string_list(value: str) -> list[str] | None:
    value = value.strip()
    if value == "[]":
        return []
    if not (value.startswith("[") and value.endswith("]")):
        return None
    body = value[1:-1].strip()
    if not body:
        return []
    return [_parse_yaml_scalar(item.strip()) for item in body.split(",")]


def _frontmatter_list(frontmatter: list[str], path: tuple[str, ...]) -> list[str] | None:
    stack: list[tuple[int, str]] = []
    collecting = False
    list_indent = -1
    values: list[str] = []

    for raw_line in frontmatter:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        if collecting:
            if indent >= list_indent and stripped.startswith("- "):
                values.append(_parse_yaml_scalar(stripped[2:]))
                continue
            if indent <= list_indent:
                return values

        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        current_path = tuple([item for _, item in stack] + [key])

        if current_path == path:
            inline = _parse_inline_string_list(value)
            if inline is not None:
                return inline
            if value:
                raise SystemExit(f"Invalid list value for {'.'.join(path)} in task.md")
            collecting = True
            list_indent = indent
            values = []

        if not value:
            stack.append((indent, key))

    return values if collecting else None


def _split_task_document(task_md: Path) -> tuple[list[str], str]:
    if not task_md.exists():
        raise SystemExit(f"Task not found: {task_md}")
    lines = task_md.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        raise SystemExit(f"Task document must start with YAML frontmatter: {task_md}")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise SystemExit(f"Task document frontmatter is not closed: {task_md}") from exc
    return lines[1:end], "\n".join(lines[end + 1 :]).strip()


def _instruction_from_body(body: str) -> str:
    lines = body.strip().splitlines()
    if lines and lines[0].strip().lower() == "## prompt":
        return "\n".join(lines[1:]).strip()
    return body.strip()


def load_task_metadata(task_name: str) -> TaskMetadata:
    task_path = EXAMPLE_TASKS / task_name
    task_md = task_path / "task.md"
    frontmatter, body = _split_task_document(task_md)

    services = _frontmatter_list(frontmatter, ("benchflow", "env0", "services"))
    if services is None or not all(isinstance(service, str) for service in services):
        raise SystemExit(f"Invalid benchflow.env0.services in {task_md}")

    tags = _frontmatter_list(frontmatter, ("metadata", "tags")) or []
    return TaskMetadata(
        name=task_name,
        services=services,
        tags=tags,
        instruction=_instruction_from_body(body),
    )


def load_task_services(task_name: str) -> list[str]:
    return load_task_metadata(task_name).services


def task_data_dir(task_name: str) -> Path:
    path = EXAMPLE_TASKS / task_name / "data"
    needles = path / "needles.py"
    if not needles.exists():
        raise SystemExit(f"Task data not found: {needles}")
    return path


def env_for_services(services: Iterable[Service]) -> dict[str, str]:
    env = os.environ.copy()
    env["TASKS_DIR"] = str(EXAMPLE_TASKS)
    env["ENV0_TASKS_DIR"] = str(EXAMPLE_TASKS)
    env["ENV0_CONFIG_PATH"] = str(CONFIG_PATH)
    for service in services:
        env[service.env_var] = service.url
        env[f"{service.env_var.removesuffix('_URL')}_DB_PATH"] = str(service.abs_db_path)
    return env


def runner_for(service: Service) -> list[str]:
    if shutil.which("uv"):
        return ["uv", "run", service.cli]
    venv_cli = service.package_dir / ".venv" / "bin" / service.cli
    if venv_cli.exists():
        return [str(venv_cli)]
    return [service.cli]


def service_subset(names: list[str] | None, all_services: dict[str, Service]) -> list[Service]:
    if not names:
        return list(all_services.values())
    missing = [name for name in names if name not in all_services]
    if missing:
        raise SystemExit("Unknown service(s): " + ", ".join(missing))
    return [all_services[name] for name in names]


def task_subset(task_name: str, all_services: dict[str, Service]) -> list[Service]:
    declared = load_task_services(task_name)
    missing = [name for name in declared if name not in all_services]
    if missing:
        raise SystemExit("Task declares services missing from config.toml: " + ", ".join(missing))
    return [all_services[name] for name in declared]


def task_service_subset(
    task_name: str,
    names: list[str] | None,
    all_services: dict[str, Service],
) -> list[Service]:
    declared = load_task_services(task_name)
    if not names:
        return task_subset(task_name, all_services)
    undeclared = [name for name in names if name not in declared]
    if undeclared:
        raise SystemExit("Task does not declare service(s): " + ", ".join(undeclared))
    return service_subset(names, all_services)


def ordered_for_seed(services: list[Service]) -> list[Service]:
    if not any(service.id == "mock-gdoc" for service in services):
        return services
    return [s for s in services if s.id != "mock-gdoc"] + [s for s in services if s.id == "mock-gdoc"]


def print_card(service: Service, seed_mode: str) -> None:
    print(f"{service.id}")
    print(f"  url:   {service.url}")
    print(f"  docs:  {service.url}/docs")
    print("  dev:   " + ", ".join(f"{service.url}{path}" for path in DEV_PATHS))
    print(f"  db:    {service.abs_db_path}")
    print(f"  seed:  {seed_mode}")
    print(f"  env:   export {service.env_var}={service.url}")
    if service.gws_service:
        print(f"  gws:   {service.gws_service} -> {service.env_var}")


def describe(services: list[Service], seed_modes: dict[str, str]) -> None:
    print(f"config: {CONFIG_PATH}")
    print(f"tasks:  {EXAMPLE_TASKS}")
    for service in services:
        print_card(service, seed_modes.get(service.id, "default"))


def run(args: list[str], cwd: Path, env: dict[str, str], dry_run: bool) -> None:
    if dry_run:
        print("$ " + " ".join(args))
        return
    subprocess.run(args, cwd=cwd, env=env, check=True)


def remove_sqlite_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            path.unlink()


def seed_default(services: list[Service], dry_run: bool) -> dict[str, str]:
    env = env_for_services(services)
    if not dry_run:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for service in services:
        if not dry_run:
            service.abs_db_path.parent.mkdir(parents=True, exist_ok=True)
            remove_sqlite_files(service.abs_db_path)
        cmd = runner_for(service) + ["--db", str(service.abs_db_path), "seed", "--scenario", "default"]
        run(cmd, service.package_dir, env, dry_run)
    return {service.id: "default" for service in services}


def seed_task(task_name: str, services: list[Service], dry_run: bool) -> dict[str, str]:
    env = env_for_services(services)
    data_dir = task_data_dir(task_name)
    if not dry_run:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    seed_modes: dict[str, str] = {}
    by_id = {service.id: service for service in services}

    if dry_run:
        print(f"task_data: {data_dir}")
        print(f"needles:   {data_dir / 'needles.py'}")

    seeded_ids: set[str] = set()
    for service in ordered_for_seed(services):
        if not dry_run:
            service.abs_db_path.parent.mkdir(parents=True, exist_ok=True)
            remove_sqlite_files(service.abs_db_path)
        cmd = runner_for(service) + ["--db", str(service.abs_db_path), "seed"]
        mode = "default"

        if service.id in TASK_DATA_SERVICES:
            gdrive_seeded = "mock-gdrive" in seeded_ids or by_id.get("mock-gdrive", service).abs_db_path.exists()
            if service.id == "mock-gdoc" and "mock-gdrive" in by_id and gdrive_seeded:
                cmd += ["--from-gdrive", str(by_id["mock-gdrive"].abs_db_path)]
                mode = "task-aware:from-gdrive"
            else:
                cmd += ["--task-data", str(data_dir), "--task-name", task_name]
                mode = "task-aware"
                if service.id == "mock-gmail":
                    manifest = ORACLE_ROOT / task_name / "manifest.json"
                    if not dry_run:
                        manifest.parent.mkdir(parents=True, exist_ok=True)
                    cmd += ["--manifest-path", str(manifest)]
        else:
            cmd += ["--scenario", "default"]

        run(cmd, service.package_dir, env, dry_run)
        seed_modes[service.id] = mode
        seeded_ids.add(service.id)

    return seed_modes


def wait_for_health(service: Service, proc: subprocess.Popen, timeout_sec: int = 30) -> None:
    deadline = time.time() + timeout_sec
    url = f"{service.url}{HEALTH_PATH}"
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            raise RuntimeError(f"{service.id} exited before health check passed (exit {exit_code})")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    raise RuntimeError(f"{service.id} did not become healthy at {url}")


def devhub_command() -> list[str]:
    return [sys.executable, str(ROOT / "devhub" / "app.py")]


def serve(services: list[Service], dry_run: bool, with_devhub: bool = False) -> None:
    env = env_for_services(services)
    service_procs: list[tuple[Service, subprocess.Popen]] = []
    procs: list[tuple[str, subprocess.Popen]] = []
    try:
        for service in services:
            cmd = runner_for(service) + [
                "--db",
                str(service.abs_db_path),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(service.port),
                "--no-mcp",
            ]
            print("$ " + " ".join(cmd))
            if not dry_run:
                proc = subprocess.Popen(cmd, cwd=service.package_dir, env=env)
                service_procs.append((service, proc))
                procs.append((service.id, proc))

        if dry_run:
            if with_devhub:
                print("$ " + " ".join(devhub_command()))
            return

        for service, proc in service_procs:
            wait_for_health(service, proc)
        if with_devhub:
            cmd = devhub_command()
            print("$ " + " ".join(cmd))
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
            procs.append(("devhub", proc))
            time.sleep(0.5)
            if proc.poll() is not None:
                raise RuntimeError(f"devhub exited before startup completed (exit {proc.returncode})")
            print(f"devhub: http://127.0.0.1:{DEVHUB_PORT}")
        print("ready")
        while True:
            for name, proc in procs:
                exit_code = proc.poll()
                if exit_code is not None:
                    raise RuntimeError(f"{name} exited unexpectedly (exit {exit_code})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("stopping")
    finally:
        for _, proc in procs:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        for _, proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def post(service: Service, path: str, dry_run: bool) -> dict:
    url = f"{service.url}{path}"
    print(f"POST {url}")
    if dry_run:
        return {"status": "dry-run", "url": url}
    request = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"status": "ok", "body": body}


def admin_action(action: str, services: list[Service], dry_run: bool, name: str | None = None) -> None:
    if action == "reset":
        path = "/_admin/reset"
    elif action == "snapshot":
        if not name:
            raise SystemExit("snapshot requires name")
        path = f"/_admin/snapshot/{name}"
    elif action == "restore":
        if not name:
            raise SystemExit("restore requires name")
        path = f"/_admin/restore/{name}"
    else:
        raise SystemExit(f"Unknown action: {action}")

    for service in services:
        result = post(service, path, dry_run)
        print(f"{service.id}: {json.dumps(result, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print contract without executing commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start-default")
    p.add_argument("--devhub", action="store_true", help="Start repo devhub with services")
    p.add_argument("services", nargs="*")

    p = sub.add_parser("start-task")
    p.add_argument("--devhub", action="store_true", help="Start repo devhub with services")
    p.add_argument("task_name")

    p = sub.add_parser("seed-default")
    p.add_argument("services", nargs="*")

    p = sub.add_parser("seed-task")
    p.add_argument("task_name")
    p.add_argument("services", nargs="*")

    for name in ("reset",):
        p = sub.add_parser(name)
        p.add_argument("services", nargs="*")

    for name in ("snapshot", "restore"):
        p = sub.add_parser(name)
        p.add_argument("name")
        p.add_argument("services", nargs="*")

    p = sub.add_parser("metadata")
    p.add_argument("services", nargs="*")

    ns = parser.parse_args(argv)
    all_services = load_services()

    if ns.command == "metadata":
        services = service_subset(ns.services, all_services)
        describe(services, {service.id: "metadata" for service in services})
        return 0

    if ns.command == "start-default":
        services = service_subset(ns.services, all_services)
        seed_modes = seed_default(services, ns.dry_run)
        describe(services, seed_modes)
        serve(services, ns.dry_run, with_devhub=ns.devhub)
        return 0

    if ns.command == "start-task":
        services = task_subset(ns.task_name, all_services)
        seed_modes = seed_task(ns.task_name, services, ns.dry_run)
        describe(services, seed_modes)
        serve(services, ns.dry_run, with_devhub=ns.devhub)
        return 0

    if ns.command == "seed-default":
        services = service_subset(ns.services, all_services)
        describe(services, seed_default(services, ns.dry_run))
        return 0

    if ns.command == "seed-task":
        selected = task_service_subset(ns.task_name, ns.services, all_services)
        describe(selected, seed_task(ns.task_name, selected, ns.dry_run))
        return 0

    if ns.command == "reset":
        admin_action("reset", service_subset(ns.services, all_services), ns.dry_run)
        return 0

    if ns.command == "snapshot":
        admin_action("snapshot", service_subset(ns.services, all_services), ns.dry_run, ns.name)
        return 0

    if ns.command == "restore":
        admin_action("restore", service_subset(ns.services, all_services), ns.dry_run, ns.name)
        return 0

    raise SystemExit(f"Unhandled command: {ns.command}")


if __name__ == "__main__":
    raise SystemExit(main())
