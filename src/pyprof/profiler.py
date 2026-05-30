"""Profiler core — wraps cProfile, builds flame graph tree and call tree from pstats."""

from __future__ import annotations

import cProfile
import json
import pstats
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CallEdge:
    """Represents a call relationship between two functions."""

    caller: str
    callee: str
    call_count: int
    total_time: float
    self_time: float


@dataclass(frozen=True)
class FuncStats:
    """Stats for a single function."""

    filename: str
    func_name: str
    line_no: int
    call_count: int
    total_time: float
    self_time: float


@dataclass(slots=True)
class FlameNode:
    """Node in a flame graph tree."""

    name: str
    value: float
    children: list[FlameNode]
    depth: int

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "value": round(self.value, 6)}
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass(slots=True)
class DiffEntry:
    """A function that changed between two runs."""

    func: str
    old_time: float
    new_time: float
    delta: float
    pct_change: float


@dataclass(slots=True)
class DiffResult:
    """Result of comparing two profile runs."""

    added: list[str]
    removed: list[str]
    changed: list[DiffEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": [asdict(d) for d in self.changed],
        }


@dataclass(slots=True)
class ProfileData:
    """Complete profile run data."""

    command: str
    total_time: float
    functions: list[FuncStats]
    flame_tree: FlameNode

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "total_time": round(self.total_time, 6),
            "functions": [asdict(f) for f in self.functions],
            "flame_tree": self.flame_tree.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str | Path) -> None:
        """Save profile data to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @staticmethod
    def load(path: str | ProfileData) -> ProfileData:
        """Load profile data from JSON file."""
        from pyprof.export import from_json  # noqa: PLC0415

        if isinstance(path, ProfileData):
            return path
        return from_json(Path(path).read_text())


def _func_id(filename: str, func_name: str, line_no: int) -> str:
    """Create a unique function identifier."""
    # Shorten stdlib paths for readability
    short_file = filename
    for prefix in [sys.prefix, sys.base_prefix]:
        if prefix and short_file.startswith(prefix):
            short_file = ".../" + short_file[len(prefix) + 1 :]
            break
    return f"{short_file}:{func_name}:{line_no}"


def profile_script(script_path: str, args: tuple[str, ...] = ()) -> ProfileData:
    """Profile a Python script using cProfile and return structured data.

    Args:
        script_path: Path to the Python script to profile
        args: Additional arguments to pass to the script

    Returns:
        ProfileData with functions, flame tree, and metadata
    """
    script = Path(script_path).resolve()
    if not script.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    prof = cProfile.Profile()

    # Build the command
    cmd = [sys.executable, str(script)] + list(args)

    # Run with profiling
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    try:
        sys.argv = [str(script)] + list(args)
        sys.path.insert(0, str(script.parent))

        # Read and compile with proper filename for traceability
        code = compile(script.read_text(), str(script), "exec")

        prof.enable()
        exec(code, {"__name__": "__main__", "__file__": str(script)})
        prof.disable()
    finally:
        sys.argv = old_argv
        sys.path = old_path

    return _build_profile_data(" ".join(cmd), prof)


def profile_function(func: Callable[..., Any], *args: Any, **kwargs: Any) -> ProfileData:
    """Profile a single callable and return structured data.

    Args:
        func: The callable to profile
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        ProfileData with functions, flame tree, and metadata
    """
    prof = cProfile.Profile()
    prof.enable()
    func(*args, **kwargs)
    prof.disable()
    name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))
    return _build_profile_data(name, prof)


def _build_profile_data(command: str, prof: cProfile.Profile) -> ProfileData:
    """Convert raw cProfile data into structured ProfileData."""
    stream = StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stream.close()

    functions: list[FuncStats] = []
    func_map: dict[str, FuncStats] = {}
    callee_map: dict[str, list[tuple[str, int, float]]] = {}  # caller -> [(callee, cc, tt)]

    for (file, line, func), (cc, _nc, tt, ct, callers) in stats.stats.items():  # type: ignore[attr-defined]
        func_id = _func_id(file, func, line)
        fs = FuncStats(
            filename=file,
            func_name=func,
            line_no=line,
            call_count=cc,
            total_time=ct,
            self_time=tt,
        )
        functions.append(fs)
        func_map[func_id] = fs

        for (caller_file, caller_line, caller_func), (caller_cc, _, caller_tt, _) in callers.items():
            caller_id = _func_id(caller_file, caller_func, caller_line)
            if caller_id not in callee_map:
                callee_map[caller_id] = []
            callee_map[caller_id].append((func_id, caller_cc, caller_tt))

    # Sort by self time descending
    functions.sort(key=lambda f: f.self_time, reverse=True)

    # Build flame tree (call stack aggregation)
    flame_tree = _build_flame_tree(functions, func_map, callee_map)

    total_time = sum(f.self_time for f in functions) if functions else 0.0

    return ProfileData(
        command=command,
        total_time=round(total_time, 6),
        functions=functions,
        flame_tree=flame_tree,
    )


def _build_flame_tree(
    functions: list[FuncStats],
    func_map: dict[str, FuncStats],
    callee_map: dict[str, list[tuple[str, int, float]]],
) -> FlameNode:
    """Build a flame graph tree from profiled function data.

    The flame tree is a hierarchical representation where each node's value
    is its self time, and children are callees.
    """
    # Find root functions (those not called by anything profiled, or called most)
    # Use the function with most self time as the virtual root
    all_callees: set[str] = set()
    for callees in callee_map.values():
        for callee_id, _, _ in callees:
            all_callees.add(callee_id)

    # Root = functions not called by anything else
    roots = [f for f in functions if _func_id(f.filename, f.func_name, f.line_no) not in all_callees]

    if not roots and functions:
        roots = [functions[0]]

    return _build_node(roots, func_map, callee_map, 0)


MAX_FLAME_DEPTH = 50

def _build_node(
    funcs: list[FuncStats],
    func_map: dict[str, FuncStats],
    callee_map: dict[str, list[tuple[str, int, float]]],
    depth: int,
) -> FlameNode:
    """Recursively build flame tree nodes with depth limit."""
    if not funcs:
        return FlameNode(name="<idle>", value=0.0, children=[], depth=depth)

    if depth >= MAX_FLAME_DEPTH:
        total_value = sum(f.self_time for f in funcs)
        return FlameNode(name="<truncated>", value=total_value, children=[], depth=depth)

    children: list[FlameNode] = []
    total_value = 0.0

    for f in funcs:
        func_id = _func_id(f.filename, f.func_name, f.line_no)
        total_value += f.self_time

        # Build children from callees
        child_nodes: list[FlameNode] = []
        if func_id in callee_map:
            for callee_id, _cc, _tt in callee_map[func_id]:
                if callee_id in func_map:
                    child_nodes.append(
                        _build_node([func_map[callee_id]], func_map, callee_map, depth + 1)
                    )

        node = FlameNode(
            name=f"{f.func_name} ({f.filename}:{f.line_no})",
            value=f.self_time,
            children=child_nodes,
            depth=depth,
        )
        children.append(node)

    return FlameNode(
        name=funcs[0].func_name if len(funcs) == 1 else "<root>",
        value=total_value,
        children=children,
        depth=depth,
    )


def diff_runs(run_a: ProfileData, run_b: ProfileData) -> DiffResult:
    """Compare two profile runs and return differences.

    Args:
        run_a: First (baseline) profile run
        run_b: Second (comparison) profile run

    Returns:
        DiffResult with added, removed, and changed functions
    """
    map_a: dict[str, float] = {}
    map_b: dict[str, float] = {}

    for f in run_a.functions:
        fid = _func_id(f.filename, f.func_name, f.line_no)
        map_a[fid] = f.self_time

    for f in run_b.functions:
        fid = _func_id(f.filename, f.func_name, f.line_no)
        map_b[fid] = f.self_time

    added = [k for k in map_b if k not in map_a]
    removed = [k for k in map_a if k not in map_b]

    changed: list[DiffEntry] = []
    all_keys = set(map_a.keys()) & set(map_b.keys())
    for key in sorted(all_keys):
        old_t = map_a[key]
        new_t = map_b[key]
        delta = new_t - old_t
        pct = (delta / old_t * 100) if old_t > 0 else (100.0 if new_t > 0 else 0.0)
        if abs(delta) > 1e-9:  # ignore float noise
            changed.append(
                DiffEntry(
                    func=key,
                    old_time=round(old_t, 6),
                    new_time=round(new_t, 6),
                    delta=round(delta, 6),
                    pct_change=round(pct, 2),
                )
            )

    # Sort by absolute delta descending
    changed.sort(key=lambda e: abs(e.delta), reverse=True)

    return DiffResult(
        added=sorted(added),
        removed=sorted(removed),
        changed=changed,
    )
