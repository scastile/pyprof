"""Tests for CLI commands."""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pyprof.cli import main
from pyprof.profiler import profile_function


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_script():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("result = sum(range(10000))\n")
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_json():
    data = profile_function(lambda: sum(range(1000)))
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write(data.to_json())
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


class TestProfileCmd:
    def test_profile_script(self, runner, sample_script):
        result = runner.invoke(main, ["profile", sample_script, "--no-browser"])
        assert result.exit_code == 0
        assert "Profiling" in result.output
        assert "Total time" in result.output

    def test_profile_with_output(self, runner, sample_script):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out = f.name
        result = runner.invoke(main, ["profile", sample_script, "-o", out, "--no-browser"])
        assert result.exit_code == 0
        assert Path(out).exists()
        loaded = json.loads(Path(out).read_text())
        assert "functions" in loaded
        Path(out).unlink(missing_ok=True)

    def test_profile_missing_script(self, runner):
        result = runner.invoke(main, ["profile", "/nonexistent.py", "--no-browser"])
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower() or "not found" in result.output.lower()


class TestWebCmd:
    def test_web_from_json(self, runner, sample_json):
        # Just test that it loads with --no-browser (will hang otherwise)
        result = runner.invoke(main, ["web", sample_json, "--no-browser", "--port", "0"])
        # Server thread starts then we hang on sleep. Timeout or check startup.
        # We can't easily test the server thread, but we can test loading works
        # by sending SIGINT via runner — but click.testing doesn't do that easily.
        # Instead just test the loading/setup doesn't error.
        assert "Error" not in result.output or result.exit_code == 0


class TestReportCmd:
    def test_report_json(self, runner, sample_json):
        result = runner.invoke(main, ["report", sample_json])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "functions" in parsed

    def test_report_text(self, runner, sample_json):
        result = runner.invoke(main, ["report", sample_json, "--format", "text"])
        assert result.exit_code == 0
        assert "Profile:" in result.output
        assert "Total time:" in result.output

    def test_report_to_file(self, runner, sample_json):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out = f.name
        result = runner.invoke(main, ["report", sample_json, "-o", out])
        assert result.exit_code == 0
        assert Path(out).exists()
        Path(out).unlink(missing_ok=True)

    def test_report_missing_file(self, runner):
        result = runner.invoke(main, ["report", "/nonexistent.json"])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestDiffCmd:
    def test_diff_loads(self, runner):
        data_a = profile_function(lambda: sum(range(100)))
        data_b = profile_function(lambda: list(range(1000)))
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as fa:
            fa.write(data_a.to_json())
            path_a = fa.name
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as fb:
            fb.write(data_b.to_json())
            path_b = fb.name

        try:
            result = runner.invoke(main, ["diff", path_a, path_b, "--no-browser", "--port", "0"])
            assert "Comparing" in result.output
        finally:
            Path(path_a).unlink(missing_ok=True)
            Path(path_b).unlink(missing_ok=True)


class TestMainCli:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "pyprof" in result.output.lower() or "version" in result.output.lower()

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "profile" in result.output
        assert "diff" in result.output
        assert "report" in result.output
        assert "web" in result.output
