import os
import re
import sys
from pathlib import Path

import httpx
import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from fetchraw import net, tool  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PUBLIC_IP = "93.184.216.34"
NUM = re.compile(r"\d+(?:[.,:]\d+)*")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: fetches real third-party pages; run with -m live")


def pytest_collection_modifyitems(config, items):
    if "live" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="live test; run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class Web:
    """A fake web for httpx.MockTransport: url -> (status, headers, body). Records every request."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = str(request.url)
        if key not in self.routes:
            return httpx.Response(404, headers={"content-type": "text/plain"}, content=b"not found")
        r = self.routes[key]
        if callable(r):
            return r(request)
        status, headers, body = r
        return httpx.Response(status, headers=headers, content=body)

    @property
    def transport(self):
        return httpx.MockTransport(self)

    def hosts(self):
        return [r.url.host for r in self.requests]


def html(body: bytes, status: int = 200, extra=None):
    h = {"content-type": "text/html; charset=utf-8"}
    h.update(extra or {})
    return (status, h, body)


@pytest.fixture(autouse=True)
def offline(request, monkeypatch):
    """No real DNS, no real sleeping, fresh politeness and page caches. Live tests use the real network."""
    net._last.clear()
    tool._cache.clear()
    if request.node.get_closest_marker("live"):
        yield None
        return
    private = {"intranet.example": "10.1.2.3", "meta.example": "169.254.169.254", "local.example": "127.0.0.1"}

    def fake_resolve(host, port):
        return [private.get(host, PUBLIC_IP)]

    sleeps = []
    monkeypatch.setattr(net, "resolve", fake_resolve)
    monkeypatch.setattr(net, "sleep", sleeps.append)
    yield sleeps


@pytest.fixture
def env():
    return {}


def numeric_tokens(text: str) -> list[str]:
    text = re.sub(r"\]\([^)]*\)", "]", text)  # link targets carry digits that are not page text
    return NUM.findall(text)


def in_order_missing(ref: list[str], out: list[str]) -> list[str]:
    i, missing = 0, []
    for tok in ref:
        j = i
        while j < len(out) and out[j] != tok:
            j += 1
        if j == len(out):
            missing.append(tok)
        else:
            i = j + 1
    return missing


os.environ.pop("FETCH_RAW_IDENTITY_HOSTS", None)
