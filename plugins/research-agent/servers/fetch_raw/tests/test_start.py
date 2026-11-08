"""The server's start (issue #61). Claude Code gives a stdio server 30 s to connect unless MCP_TIMEOUT
is set; this one took 14 to 36 s on a busy machine, and a session whose server timed out ran without
fetch_raw. The handshake must not wait for the fetcher's imports or for recompiling the libraries."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest
from conftest import SERVER_DIR

SERVER = SERVER_DIR / "server.py"
INITIALIZE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "start-test", "version": "0"}}}) + "\n"
# A guard on the failure itself: a warm start answers initialize well inside Claude Code's default
# connect timeout of 30 s. It is not the red test for issue #61: 0.7.0 also passes it on a quiet machine
# (its starts took 6.9 to 40.8 s on 2026-11-08 as the load changed). The two tests above check the
# mechanism, and the 0.8.0 pull request has the measured times.
WARM_START_BOUND_S = 10.0

HANDSHAKE_PROBE = r"""
import json
import server
at_start = sorted(m for m in ('fetchraw.tool', 'fetchraw.net', 'fetchraw.convert', 'bs4', 'httpx',
                              'pdfplumber', 'markdownify', 'truststore') if m in sys.modules)
fetch = getattr(server, 'fetch', None)
first = fetch('http://127.0.0.1:9/', 0, 1000, 'auto').split('\n')[0] if fetch else None
print(json.dumps({'at_start': at_start, 'first': first, 'loaded': 'fetchraw.tool' in sys.modules}))
"""

BYTECODE_PROBE = r"""
import importlib.util, json, os
import server
import bs4, fetchraw.tool, mcp
def cached(module): return os.path.exists(importlib.util.cache_from_source(module.__file__))
print(json.dumps({'mcp': cached(mcp), 'bs4': cached(bs4), 'fetchraw.tool': cached(fetchraw.tool),
                  'fetchraw': cached(sys.modules['fetchraw'])}))
"""


def in_fresh_python(code: str, **env: str) -> dict:
    """Run code in a new interpreter beside server.py and return the JSON it prints last."""
    full = {**os.environ, **env}
    full.pop("PYTHONDONTWRITEBYTECODE", None)
    out = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(SERVER_DIR)!r})\n{code}"],
                         cwd=SERVER_DIR, env=full, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().split("\n")[-1])


def test_the_handshake_does_not_import_the_fetcher():
    seen = in_fresh_python(HANDSHAKE_PROBE)
    assert seen["at_start"] == []
    assert seen["first"] == "status: ERROR" and seen["loaded"]


def test_library_bytecode_is_cached_and_the_plugin_folder_gets_none(tmp_path):
    prefix = tmp_path / "pyc"  # every bytecode read and write goes here, whoever does it
    seen = in_fresh_python(BYTECODE_PROBE, PYTHONPYCACHEPREFIX=str(prefix))
    assert seen["mcp"] and seen["bs4"], seen  # the libraries' bytecode is kept for the next start
    assert not seen["fetchraw.tool"] and not seen["fetchraw"], seen  # the plugin's own modules write none
    assert [p for p in prefix.rglob("*.pyc") if "fetchraw" in p.parts] == []


def start_once(timeout_s: float = 120.0) -> float:
    """Start the server as Claude Code does (.mcp.json) and time the reply to one initialize."""
    proc = subprocess.Popen(["uv", "run", "--quiet", "--script", "--locked", str(SERVER)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timer = threading.Timer(timeout_s, proc.kill)
    timer.start()
    try:
        t0 = time.perf_counter()
        proc.stdin.write(INITIALIZE.encode())
        proc.stdin.flush()
        line = proc.stdout.readline()
        elapsed = time.perf_counter() - t0
    finally:
        timer.cancel()
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    reply = json.loads(line) if line else {}
    assert reply.get("id") == 1 and reply["result"]["serverInfo"]["name"] == "fetch-raw", proc.stderr.read()[-2000:]
    return elapsed


def test_a_warm_start_answers_initialize_well_inside_the_connect_timeout():
    if shutil.which("uv") is None:
        pytest.skip("uv is not on the PATH")
    sync = subprocess.run(["uv", "sync", "--quiet", "--locked", "--script", str(SERVER)], capture_output=True,
                          text=True, timeout=600)
    if sync.returncode != 0:
        pytest.skip(f"uv could not prepare the server's environment: {sync.stderr.strip()[-300:]}")
    start_once()  # the first start after an install writes the libraries' bytecode
    times = [start_once() for _ in range(3)]
    assert min(times) < WARM_START_BOUND_S, f"starts took {', '.join(f'{t:.1f}' for t in times)} s"
