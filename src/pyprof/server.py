"""FastAPI server for the profiling dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from pyprof.profiler import DiffResult, ProfileData

app = FastAPI(title="pyprof", version="0.1.0")

# In-memory storage for current session data
_current_data: ProfileData | None = None
_current_diff: DiffResult | None = None

_static_dir = Path(__file__).parent / "static"


def save_data(data: ProfileData) -> None:
    """Store profile data for the dashboard."""
    global _current_data
    _current_data = data


def save_diff(diff: DiffResult) -> None:
    """Store diff result for the dashboard."""
    global _current_diff
    _current_diff = diff


@app.get("/api/data")
def get_data() -> JSONResponse:
    """Return current profile data as JSON."""
    if _current_data is None:
        raise HTTPException(status_code=404, detail="No profile data loaded")
    return JSONResponse(content=_current_data.to_dict())


@app.get("/api/diff")
def get_diff() -> JSONResponse:
    """Return current diff result as JSON."""
    if _current_diff is None:
        raise HTTPException(status_code=404, detail="No diff data loaded")
    return JSONResponse(content=_current_diff.to_dict())


@app.get("/api/functions")
def get_functions(sort: str = "time", limit: int = 100) -> JSONResponse:
    """Return top functions sorted by criterion."""
    if _current_data is None:
        raise HTTPException(status_code=404, detail="No profile data loaded")

    key_map = {
        "cumulative": lambda f: f.total_time,
        "time": lambda f: f.self_time,
        "calls": lambda f: f.call_count,
        "name": lambda f: f.func_name,
    }
    key = key_map.get(sort, lambda f: f.self_time)
    reverse = sort != "name"

    sorted_funcs = sorted(_current_data.functions, key=key, reverse=reverse)[:limit]
    return JSONResponse(content=[{
        "filename": f.filename,
        "func_name": f.func_name,
        "line_no": f.line_no,
        "call_count": f.call_count,
        "total_time": f.total_time,
        "self_time": f.self_time,
    } for f in sorted_funcs])


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the dashboard SPA."""
    html_path = _static_dir / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return _default_html()


def _default_html() -> str:
    """Return a minimal dashboard HTML if static file is missing."""
    return """<!DOCTYPE html>
<html><head><title>pyprof</title></head>
<body><h1>pyprof dashboard</h1><p>Loading...</p></body></html>"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def start_server(port: int = 8000) -> None:
    """Start the uvicorn server."""
    import uvicorn  # noqa: PLC0415
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
