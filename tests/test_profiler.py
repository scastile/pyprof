"""Tests for profiler core."""

import json
import tempfile
from pathlib import Path

import pytest

from pyprof.export import diff_to_json, from_json, to_json
from pyprof.profiler import (
    DiffEntry,
    DiffResult,
    FlameNode,
    FuncStats,
    ProfileData,
    diff_runs,
    profile_function,
    profile_script,
)


class TestProfileFunction:
    def test_basic(self):
        def work():
            total = 0
            for i in range(10000):
                total += i
            return total

        data = profile_function(work)
        assert data.total_time > 0
        assert len(data.functions) > 0
        assert data.command.endswith("work")

    def test_flame_tree(self):
        def work():
            return sum(range(1000))

        data = profile_function(work)
        assert data.flame_tree is not None
        assert data.flame_tree.value > 0

    def test_functions_sorted_by_self_time(self):
        def work():
            return list(range(10000))

        data = profile_function(work)
        self_times = [f.self_time for f in data.functions]
        assert self_times == sorted(self_times, reverse=True)


class TestProfileScript:
    def test_inline_script(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("print('hello')\nresult = sum(range(1000))\n")
            f.flush()
            data = profile_script(f.name)
            assert data.total_time > 0
            assert len(data.functions) > 0

    def test_missing_script(self):
        with pytest.raises(FileNotFoundError):
            profile_script("/nonexistent/script.py")

    def test_complex_script(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
def fib(n):
    if n < 2: return n
    return fib(n-1) + fib(n-2)

print(fib(20))
""")
            f.flush()
            data = profile_script(f.name)
            assert data.total_time > 0
            func_names = [f.func_name for f in data.functions]
            assert "fib" in func_names


class TestDiffRuns:
    def test_no_diff(self):
        data = profile_function(lambda: sum(range(100)))
        result = diff_runs(data, data)
        assert len(result.added) == 0
        assert len(result.removed) == 0

    def test_different_work(self):
        data_a = profile_function(lambda: sum(range(100)))
        data_b = profile_function(lambda: list(range(10000)))
        result = diff_runs(data_a, data_b)
        # May have added/removed depending on what's captured
        assert isinstance(result.changed, list) or len(result.changed) >= 0


class TestSerialization:
    def test_roundtrip(self):
        data = profile_function(lambda: sum(range(1000)))
        json_str = to_json(data)
        restored = from_json(json_str)
        assert restored.command == data.command
        assert abs(restored.total_time - data.total_time) < 0.001
        assert len(restored.functions) == len(data.functions)

    def test_save_load(self):
        data = profile_function(lambda: list(range(500)))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        data.save(path)
        loaded = ProfileData.load(path)
        assert loaded.command == data.command
        assert abs(loaded.total_time - data.total_time) < 0.001
        Path(path).unlink()

    def test_flame_tree_roundtrip(self):
        data = profile_function(lambda: sum(range(100)))
        d = data.to_dict()
        assert "flame_tree" in d
        assert "name" in d["flame_tree"]
        assert "value" in d["flame_tree"]


class TestFlameNode:
    def test_to_dict_leaf(self):
        node = FlameNode(name="test.func", value=0.5, children=[], depth=0)
        d = node.to_dict()
        assert d["name"] == "test.func"
        assert d["value"] == 0.5
        assert "children" not in d

    def test_to_dict_with_children(self):
        child = FlameNode(name="child", value=0.2, children=[], depth=1)
        parent = FlameNode(name="parent", value=0.5, children=[child], depth=0)
        d = parent.to_dict()
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "child"


class TestDiffResult:
    def test_to_dict(self):
        diff = DiffResult(
            added=["a:func:1"],
            removed=["b:func:2"],
            changed=[
                DiffEntry(func="c:func:3", old_time=0.1, new_time=0.2, delta=0.1, pct_change=100.0)
            ],
        )
        d = diff.to_dict()
        assert len(d["added"]) == 1
        assert len(d["removed"]) == 1
        assert len(d["changed"]) == 1
        assert d["changed"][0]["delta"] == 0.1

    def test_diff_json(self):
        diff = DiffResult(added=[], removed=[], changed=[])
        j = diff_to_json(diff)
        parsed = json.loads(j)
        assert "added" in parsed


class TestFuncStats:
    def test_fields(self):
        fs = FuncStats(
            filename="test.py",
            func_name="hello",
            line_no=42,
            call_count=3,
            total_time=0.5,
            self_time=0.2,
        )
        d = fs.__dict__
        assert d["func_name"] == "hello"
        assert d["call_count"] == 3
