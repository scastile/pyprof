"""Shared fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_browser(monkeypatch):
    """Prevent browser.open during tests."""
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
