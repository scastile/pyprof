"""CLI — profile, diff, report, web commands."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

import click

from pyprof import __version__
from pyprof.profiler import FuncStats, ProfileData, diff_runs


@click.group()
@click.version_option(version=__version__, prog_name="pyprof")
def main() -> None:
    """Real-time cProfile visualization — flame graphs, call trees, diffs."""


@main.command("profile")
@click.argument("script", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Save profile data to JSON file")
@click.option(
    "--sort",
    type=click.Choice(["cumulative", "time", "calls", "name"]),
    default="time",
    help="Sort order",
)
@click.option("--limit", type=int, default=50, help="Max functions to display")
@click.option("--port", "-p", type=int, default=8000, help="Dashboard port")
@click.option("--no-browser", is_flag=True, default=False, help="Don't auto-open browser")
def profile_cmd(
    script: str,
    output: str | None,
    sort: str,
    limit: int,
    port: int,
    no_browser: bool,
) -> None:
    """Profile a Python script and launch the dashboard."""
    from pyprof.profiler import profile_script  # noqa: PLC0415

    click.echo(f"Profiling {script}...")

    try:
        data = profile_script(script)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if output:
        data.save(output)
        click.echo(f"Saved to {output}")

    click.echo(f"Total time: {data.total_time:.4f}s across {len(data.functions)} functions")

    funcs = _sort_functions(data.functions, sort)
    click.echo(f"\nTop {limit} functions by {sort}:")
    for f in funcs[:limit]:
        click.echo(
            f"  {f.self_time:8.4f}s  {f.call_count:6d} calls  "
            f"{f.func_name} ({f.filename}:{f.line_no})"
        )

    if not no_browser:
        _launch_dashboard(data, port)


@main.command()
@click.argument("run_a", type=click.Path(exists=True))
@click.argument("run_b", type=click.Path(exists=True))
@click.option("--port", "-p", type=int, default=8000, help="Dashboard port")
@click.option("--no-browser", is_flag=True, default=False, help="Don't auto-open browser")
def diff(run_a: str, run_b: str, port: int, no_browser: bool) -> None:
    """Compare two profile runs and show differences."""
    try:
        data_a = ProfileData.load(run_a)
        data_b = ProfileData.load(run_b)
    except (json.JSONDecodeError, KeyError) as e:
        click.echo(f"Error loading profile data: {e}", err=True)
        sys.exit(1)

    result = diff_runs(data_a, data_b)

    click.echo(f"Comparing {run_a} vs {run_b}")
    click.echo(f"\n  Added:   {len(result.added)} functions")
    click.echo(f"  Removed: {len(result.removed)} functions")
    click.echo(f"  Changed: {len(result.changed)} functions")

    if result.changed:
        click.echo("\n  Top changes:")
        for entry in result.changed[:20]:
            direction = "+" if entry.delta > 0 else ""
            click.echo(
                f"    {direction}{entry.delta:.4f}s ({entry.pct_change:+.1f}%)  {entry.func}"
            )

    from pyprof.server import save_diff  # noqa: PLC0415
    save_diff(result)

    if not no_browser:
        _launch_dashboard(data_a, port, diff_path=run_b)


@main.command()
@click.argument("run", type=click.Path(exists=True))
@click.option(
    "--format", "fmt",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file (default: stdout)")
def report(run: str, fmt: str, output: str | None) -> None:
    """Export a profile report."""
    try:
        data = ProfileData.load(run)
    except (json.JSONDecodeError, KeyError) as e:
        click.echo(f"Error loading profile data: {e}", err=True)
        sys.exit(1)

    if fmt == "json":
        text = data.to_json()
    else:
        lines = [
            f"Profile: {data.command}",
            f"Total time: {data.total_time:.4f}s",
            f"Functions: {len(data.functions)}",
            "",
            f"{'Self Time':>10s}  {'Total Time':>10s}  {'Calls':>8s}  Function",
            "-" * 70,
        ]
        for f in data.functions[:50]:
            lines.append(
                f"{f.self_time:10.4f}  {f.total_time:10.4f}  "
                f"{f.call_count:8d}  {f.func_name} ({f.filename}:{f.line_no})"
            )
        text = "\n".join(lines)

    if output:
        Path(output).write_text(text)
        click.echo(f"Report saved to {output}")
    else:
        click.echo(text)


@main.command()
@click.argument("run", type=click.Path(exists=True))
@click.option("--port", "-p", type=int, default=8000, help="Dashboard port")
@click.option("--no-browser", is_flag=True, default=False, help="Don't auto-open browser")
def web(run: str, port: int, no_browser: bool) -> None:
    """Launch the dashboard for a saved profile run."""
    try:
        data = ProfileData.load(run)
    except (json.JSONDecodeError, KeyError) as e:
        click.echo(f"Error loading profile data: {e}", err=True)
        sys.exit(1)

    _launch_dashboard(data, port)


def _sort_functions(functions: list[FuncStats], sort: str) -> list[FuncStats]:
    """Sort functions by the given criterion."""
    key_map = {
        "cumulative": lambda f: f.total_time,
        "time": lambda f: f.self_time,
        "calls": lambda f: f.call_count,
        "name": lambda f: f.func_name,
    }
    key_fn = key_map.get(sort, lambda f: f.self_time)
    reverse = sort != "name"
    return sorted(functions, key=key_fn, reverse=reverse)


def _launch_dashboard(data: ProfileData, port: int, diff_path: str | None = None) -> None:
    """Start the dashboard server and open browser."""
    import threading
    import time

    from pyprof.server import save_data, save_diff, start_server  # noqa: PLC0415

    save_data(data)
    if diff_path:
        diff_data = ProfileData.load(diff_path)
        diff_result = diff_runs(data, diff_data)
        save_diff(diff_result)

    url = f"http://localhost:{port}"
    click.echo(f"\nDashboard: {url}")

    if diff_path:
        url += "?diff=1"

    server_thread = threading.Thread(target=lambda: start_server(port), daemon=True)
    server_thread.start()
    time.sleep(0.5)

    webbrowser.open(url)

    click.echo("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down")
