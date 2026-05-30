# pyprof

Real-time cProfile visualization — interactive flame graphs, call trees, diff comparison.

## Install

```bash
pip install pyprof
```

## Quick Start

```bash
# Profile a script, auto-launch dashboard
pyprof profile my_app.py

# Compare two runs
pyprof diff run_a.json run_b.json

# Export report
pyprof report run.json --format json

# Launch dashboard from saved file
pyprof web run.json --port 8000
```

## License

MIT
