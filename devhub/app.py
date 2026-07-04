#!/usr/bin/env python3
"""Tiny env0 devhub for inspecting already-started dev services."""

from __future__ import annotations

import argparse
import html
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlencode


ROOT = Path(__file__).resolve().parents[1]
DEVHUB_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = DEVHUB_ROOT / "templates"
STATIC_DIR = DEVHUB_ROOT / "static"
sys.path.insert(0, str(ROOT / "scripts"))

import env0_control as control  # noqa: E402


DEVHUB_PORT = 9060
SNAPSHOT_NAME = "devhub"
ADMIN_ACTIONS = {"reset", "snapshot", "restore", "seed-default", "seed-task"}
HTTP_TIMEOUT = 0.2


def request_json(method: str, url: str, timeout: float = HTTP_TIMEOUT) -> tuple[bool, object]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return False, {"error": f"HTTP {exc.code}", "url": url}
    except urllib.error.URLError as exc:
        return False, {"error": str(exc.reason), "url": url}
    except TimeoutError:
        return False, {"error": "timeout", "url": url}

    try:
        return True, json.loads(body)
    except json.JSONDecodeError:
        return True, body


def service_status(service: control.Service) -> dict:
    ok, payload = request_json("GET", f"{service.url}{control.HEALTH_PATH}")
    return {
        "ok": ok,
        "label": "healthy" if ok else "offline",
        "payload": payload,
    }


def dev_links(service: control.Service) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for path in control.DEV_PATHS:
        url = f"{service.url}{path}"
        ok, _ = request_json("GET", url)
        if ok:
            links.append((path.removeprefix("/dev/"), url))
    return links


def list_tasks() -> list[dict]:
    tasks = []
    for task_dir in sorted(control.EXAMPLE_TASKS.iterdir()):
        if not task_dir.is_dir():
            continue
        task_md = task_dir / "task.md"
        if not task_md.exists():
            continue
        metadata = control.load_task_metadata(task_dir.name)
        tasks.append({
            "name": task_dir.name,
            "services": metadata.services,
            "tags": metadata.tags,
            "instruction": read_instruction_preview(metadata.instruction),
            "has_needles": (task_dir / "data" / "needles.py").exists(),
            "command": f"scripts/dev.sh task {task_dir.name}",
        })
    return tasks


def read_instruction_preview(instruction: str, limit: int = 220) -> str:
    text = " ".join(instruction.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def render_index(message: str = "") -> str:
    services = control.load_services()
    cards = "\n".join(
        render_service_card(service)
        for service in sorted(services.values(), key=lambda service: service.port)
    )
    task_cards = "\n".join(render_task_card(task) for task in list_tasks())
    escaped_message = html.escape(message)
    message_html = f'<p class="notice">{escaped_message}</p>' if message else ""
    template = Template((TEMPLATE_DIR / "index.html").read_text())
    return template.safe_substitute(
        message_html=message_html,
        cards=cards,
        task_cards=task_cards,
    )


def render_service_card(service: control.Service) -> str:
    status = service_status(service)
    pill_class = "ok" if status["ok"] else "bad"
    links = [
        ("root", service.url),
        ("docs", f"{service.url}/docs"),
        ("state", f"{service.url}/_admin/state"),
        ("diff", f"{service.url}/_admin/diff"),
        ("action log", f"{service.url}/_admin/action_log"),
    ]
    if status["ok"]:
        links.extend(dev_links(service))
    links_html = "\n".join(
        f'<a href="{html.escape(url)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>'
        for label, url in links
    )
    actions_html = "\n".join(
        action_form(service.id, action, label)
        for action, label in (
            ("seed-default", "Seed Default"),
            ("reset", "Reset"),
            ("snapshot", "Snapshot"),
            ("restore", "Restore"),
        )
    )
    return f"""<article class="card">
  <div class="card-head">
    <div class="id-wrap">
      <div class="service-icon"><span class="material-symbols-outlined">cloud</span></div>
      <a class="id" href="{html.escape(service.url)}" target="_blank" rel="noreferrer">{html.escape(service.id)}</a>
    </div>
    <span class="pill {pill_class}">{html.escape(status["label"])}</span>
  </div>
  <div class="card-body">
  <dl>
    <dt>Port</dt><dd>{service.port}</dd>
    <dt>DB</dt><dd>{html.escape(str(service.abs_db_path))}</dd>
    <dt>Env</dt><dd><code>{html.escape(service.env_var)}={html.escape(service.url)}</code></dd>
    <dt>GWS</dt><dd>{html.escape(service.gws_service or "-")}</dd>
  </dl>
  <div class="links">{links_html}</div>
  <div class="actions">{actions_html}</div>
  </div>
</article>"""


def render_task_card(task: dict) -> str:
    service_chips = "".join(
        f'<span class="chip blue">{html.escape(service)}</span>'
        for service in task["services"]
    )
    tag_chips = "".join(
        f'<span class="chip">{html.escape(tag)}</span>'
        for tag in task["tags"]
    )
    needle_class = "green" if task["has_needles"] else "red"
    needle_text = "needles.py" if task["has_needles"] else "no needles.py"
    return f"""<article class="card task-card">
  <div class="card-head">
    <div class="id-wrap">
      <div class="service-icon"><span class="material-symbols-outlined">assignment</span></div>
      <div class="id">{html.escape(task["name"])}</div>
    </div>
    <span class="pill ok">task</span>
  </div>
  <div class="card-body">
    <p class="preview">{html.escape(task["instruction"])}</p>
    <div class="chips">{service_chips}<span class="chip {needle_class}">{needle_text}</span>{tag_chips}</div>
    <div class="command"><span class="material-symbols-outlined">terminal</span><code>{html.escape(task["command"])}</code></div>
    <div class="actions task-actions">{task_action_form(task["name"])}</div>
  </div>
</article>"""


def task_action_form(task_name: str) -> str:
    return f"""<form method="post" action="/action">
  <input type="hidden" name="action" value="seed-task" />
  <input type="hidden" name="task" value="{html.escape(task_name)}" />
  <button class="action primary" type="submit">Seed Running Services</button>
</form>"""


def action_form(service_id: str, action: str, label: str) -> str:
    return f"""<form method="post" action="/action">
  <input type="hidden" name="service" value="{html.escape(service_id)}" />
  <input type="hidden" name="action" value="{html.escape(action)}" />
  <button class="action {'primary' if action == 'seed-default' else ''}" type="submit">{html.escape(label)}</button>
</form>"""


def perform_action(service_id: str, action: str, task_name: str | None = None) -> str:
    if action not in ADMIN_ACTIONS:
        return f"Unsupported action: {action}"

    if action == "seed-task":
        if not task_name:
            return "Task-aware seed requires a task name"
        return perform_seed_task(task_name)

    services = control.load_services()
    service = services.get(service_id)
    if not service:
        return f"Unknown service: {service_id}"

    if action == "seed-default":
        ok, payload = request_json("POST", f"{service.url}/_admin/seed?scenario=default", timeout=15)
    elif action == "reset":
        ok, payload = request_json("POST", f"{service.url}/_admin/reset", timeout=5)
    elif action == "snapshot":
        ok, payload = request_json("POST", f"{service.url}/_admin/snapshot/{SNAPSHOT_NAME}", timeout=5)
    elif action == "restore":
        ok, payload = request_json("POST", f"{service.url}/_admin/restore/{SNAPSHOT_NAME}", timeout=5)
    else:
        return f"Unsupported action: {action}"

    status = "ok" if ok else "error"
    return f"{service_id}: {action} {status}: {payload}"


def perform_seed_task(task_name: str) -> str:
    services = control.load_services()
    try:
        declared = control.task_subset(task_name, services)
        control.task_data_dir(task_name)
    except SystemExit as exc:
        return str(exc)

    results = []
    declared_by_id = {service.id: service for service in declared}
    for service in declared:
        if service.id == "mock-gdoc" and "mock-gdrive" in declared_by_id:
            query = urlencode({"from_gdrive": "true"})
            seed_label = f"task:{task_name}:from-gdrive"
        elif service.id in control.TASK_SCENARIO_SERVICES:
            query = urlencode({"scenario": f"task:{task_name}"})
            seed_label = f"task:{task_name}"
        elif service.id in control.TASK_DATA_SERVICES:
            query = urlencode({"task_name": task_name})
            seed_label = f"task:{task_name}"
        else:
            query = urlencode({"scenario": "default"})
            seed_label = "default"
        ok, payload = request_json("POST", f"{service.url}/_admin/seed?{query}", timeout=15)
        status = "ok" if ok else "error"
        if ok:
            results.append(f"{service.id} {seed_label} {status}")
        else:
            results.append(f"{service.id} {seed_label} {status}: {payload}")

    return f"task={task_name}; " + " | ".join(results)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/static/devhub.css":
            self.respond_static(STATIC_DIR / "devhub.css", "text/css; charset=utf-8")
            return
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.respond_html(render_index())

    def do_POST(self) -> None:
        if self.path != "/action":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        service_id = params.get("service", [""])[0]
        action = params.get("action", [""])[0]
        task_name = params.get("task", [""])[0] or None
        message = perform_action(service_id, action, task_name=task_name)
        self.respond_html(render_index(message=message))

    def respond_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def respond_static(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("devhub: " + (format % args) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=DEVHUB_PORT, type=int)
    parser.add_argument("--render-once", action="store_true", help="Print one HTML render and exit")
    args = parser.parse_args(argv)

    if args.render_once:
        print(render_index())
        return 0

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"env0 Devhub: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
