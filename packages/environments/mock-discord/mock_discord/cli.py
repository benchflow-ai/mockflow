"""CLI: mock-discord serve|seed|reset|run-task."""

from __future__ import annotations

import sys
from pathlib import Path

import click

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def _default_port(env_name: str = "mock-discord", fallback: int = 9006) -> int:
    """Read default port from config.toml, walking up from cwd."""
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "config.toml"
        if candidate.is_file():
            with open(candidate, "rb") as f:
                cfg = tomllib.load(f)
            return cfg.get(env_name, {}).get("port", fallback)
    return fallback


@click.group()
@click.option("--db", default="mock_discord.db", help="Path to SQLite database file")
@click.pass_context
def cli(ctx, db):
    """Mock Discord — Discord-compatible environment for AI agent evaluation."""
    from mock_discord.models.base import resolve_db_path

    ctx.ensure_object(dict)
    ctx.obj["db_path"] = str(resolve_db_path(db))


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=_default_port(), type=int, help="Bind port")
@click.option("--no-mcp", is_flag=True, help="Disable MCP endpoint")
@click.pass_context
def serve(ctx, host, port, no_mcp):
    """Start the Mock Discord API server."""
    db_path = ctx.obj["db_path"]
    click.echo(f"Starting Mock Discord server on {host}:{port}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  API: http://{host}:{port}/api/v10/guilds")
    click.echo(f"  Docs: http://{host}:{port}/docs")
    if not no_mcp:
        click.echo(f"  MCP: http://{host}:{port}/mcp")
    click.echo()

    from mock_discord.server import run_server

    run_server(host=host, port=port, db_path=db_path, enable_mcp=not no_mcp)


@cli.command()
@click.option("--scenario", default="default", help="Scenario name (default)")
@click.option("--seed", default=42, type=int, help="Random seed for reproducibility")
@click.pass_context
def seed(ctx, scenario, seed):
    """Seed the database with test data."""
    db_path = ctx.obj["db_path"]

    if Path(db_path).exists():
        Path(db_path).unlink()
        click.echo(f"Removed existing database: {db_path}")

    from mock_discord.seed.generator import seed_database

    result = seed_database(scenario=scenario, seed=seed, db_path=db_path)
    click.echo(f"Seeded database with scenario '{scenario}':")
    click.echo(f"  Users: {result['users']}")
    click.echo(f"  Guilds: {result['guilds']}")
    click.echo(f"  Channels: {result['channels']}")
    click.echo(f"  Messages: {result['messages']}")
    click.echo(f"  Database: {db_path}")
    click.echo("  Initial snapshot saved.")


@cli.command()
@click.pass_context
def reset(ctx):
    """Reset database to initial seed state."""
    db_path = ctx.obj["db_path"]

    from mock_discord.models import init_db, reset_engine
    from mock_discord.state.snapshots import restore_snapshot

    reset_engine()
    init_db(db_path)

    success = restore_snapshot("initial")
    if success:
        click.echo("Database reset to initial state.")
    else:
        click.echo("Error: No initial snapshot found. Run `mock-discord seed` first.", err=True)
        sys.exit(1)


@cli.command("run-task")
@click.argument("task_name")
@click.pass_context
def run_task(ctx, task_name):
    """Run a task and evaluate the result."""
    from mock_discord.tasks import get_task, list_tasks

    task = get_task(task_name)
    if not task:
        click.echo(f"Unknown task: {task_name!r}", err=True)
        click.echo(f"Available tasks: {', '.join(list_tasks())}", err=True)
        sys.exit(1)

    click.echo(f"Task: {task.name}")
    click.echo(f"Description: {task.description}")
    click.echo(f"Category: {task.category}")
    click.echo()
    click.echo("Instructions for agent:")
    click.echo(f"  {task.instruction}")
    click.echo()
    click.echo("To evaluate after agent completes task:")
    click.echo(f"  mock-discord eval-task {task_name}")


@cli.command("eval-task")
@click.argument("task_name")
@click.pass_context
def eval_task(ctx, task_name):
    """Evaluate a task's completion."""
    db_path = ctx.obj["db_path"]

    from mock_discord.models import init_db
    from mock_discord.state.action_log import action_log
    from mock_discord.state.snapshots import get_diff, get_state_dump
    from mock_discord.tasks import get_task

    task = get_task(task_name)
    if not task:
        click.echo(f"Unknown task: {task_name!r}", err=True)
        sys.exit(1)

    init_db(db_path)

    final_state = get_state_dump()
    diff = get_diff()
    log_entries = action_log.get_entries()

    reward, done = task.evaluate(final_state, diff, log_entries)
    click.echo(f"Task: {task.name}")
    click.echo(f"Reward: {reward}")
    click.echo(f"Done: {done}")
    if reward > 0:
        click.echo("Result: PASS")
    else:
        click.echo("Result: FAIL")


@cli.command("list-tasks")
def list_tasks_cmd():
    """List all available tasks."""
    from mock_discord.tasks import get_task, list_tasks

    tasks = list_tasks()
    if not tasks:
        click.echo("No tasks available.")
        return

    click.echo(f"Available tasks ({len(tasks)}):\n")
    for name in sorted(tasks):
        task = get_task(name)
        category = task.category if task else "?"
        desc = task.description[:60] if task else ""
        click.echo(f"  {name:<25} [{category}] {desc}")


if __name__ == "__main__":
    cli()
