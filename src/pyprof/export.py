"""Export and import for profile data."""

from __future__ import annotations

import json
from typing import Any

from pyprof.profiler import (
    DiffResult,
    FlameNode,
    FuncStats,
    ProfileData,
)


def to_json(data: ProfileData) -> str:
    """Serialize ProfileData to JSON string."""
    return json.dumps(data.to_dict(), indent=2)


def from_json(text: str) -> ProfileData:
    """Deserialize ProfileData from JSON string."""
    raw = json.loads(text)
    return _from_dict(raw)


def _from_dict(raw: dict[str, Any]) -> ProfileData:
    functions = [
        FuncStats(
            filename=f["filename"],
            func_name=f["func_name"],
            line_no=f["line_no"],
            call_count=f["call_count"],
            total_time=f["total_time"],
            self_time=f["self_time"],
        )
        for f in raw["functions"]
    ]
    flame_tree = _flame_from_dict(raw["flame_tree"])
    return ProfileData(
        command=raw["command"],
        total_time=raw["total_time"],
        functions=functions,
        flame_tree=flame_tree,
    )


def _flame_from_dict(raw: dict[str, Any]) -> FlameNode:
    children = [_flame_from_dict(c) for c in raw.get("children", [])]
    return FlameNode(
        name=raw["name"],
        value=raw["value"],
        children=children,
        depth=0,
    )


def diff_to_json(diff: DiffResult) -> str:
    """Serialize DiffResult to JSON string."""
    return json.dumps(diff.to_dict(), indent=2)
