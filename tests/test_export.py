"""Tests for export module."""

import json

import pytest

from pyprof.export import from_json, to_json
from pyprof.profiler import profile_function


class TestToJson:
    def test_roundtrip(self):
        data = profile_function(lambda: sum(range(100)))
        text = to_json(data)
        parsed = json.loads(text)
        assert "command" in parsed
        assert "total_time" in parsed
        assert "functions" in parsed
        assert "flame_tree" in parsed

    def test_indent(self):
        data = profile_function(lambda: 42)
        text = to_json(data)
        assert "\n" in text  # indented
        assert "  " in text


class TestFromJson:
    def test_basic(self):
        data = profile_function(lambda: sum(range(100)))
        text = data.to_json()
        restored = from_json(text)
        assert restored.command == data.command
        assert restored.functions is not None

    def test_flame_tree_present(self):
        data = profile_function(lambda: sum(range(50)))
        text = data.to_json()
        restored = from_json(text)
        assert restored.flame_tree is not None
        assert restored.flame_tree.value > 0

    def test_malformed_json(self):
        with pytest.raises(json.JSONDecodeError):
            from_json("{bad json")

    def test_missing_fields(self):
        with pytest.raises(KeyError):
            from_json('{"command": "test", "total_time": 0}')
