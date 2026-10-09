"""Live checks against real pages. Skipped unless run with -m live.

Secrets are read inside this process and never printed: EDGAR_IDENTITY and FIRECRAWL_API_KEY from the
environment, else (Windows) from the user environment in the registry, else from the .env file named by
FETCH_RAW_LIVE_ENV_FILE. A Firecrawl test spends about one credit.
"""

import os
import re

import pytest

from fetchraw import tool

pytestmark = pytest.mark.live

NYSE = "https://www.nyse.com/markets/hours-calendars"
IBKR = "https://www.interactivebrokers.com/en/pricing/commissions-stocks.php"
ARXIV = "https://arxiv.org/pdf/1706.03762"
TENK = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"


class Hidden(str):
    """A secret that prints as [hidden], so a failing assertion or traceback cannot show it."""

    def __repr__(self):
        return "'[hidden]'"

    __str__ = __repr__


def secret(name: str) -> str | None:
    value = _secret(name)
    return Hidden(value) if value else None


def _secret(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, name)
            if value:
                return value
    except (ImportError, OSError):
        pass
    path = os.environ.get("FETCH_RAW_LIVE_ENV_FILE")
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def get(url, env, route="direct", offset=0, max_chars=40000):
    out = tool.fetch_page(url, offset, max_chars, route, env)
    head, _, body = out.partition("\n--- content ---\n")
    h = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    return h, body


def read_all(url, env, route="direct"):
    h, body = get(url, env, route)
    assert h["status"].startswith("OK"), h
    parts = [body]
    while h["next_offset"] != "none":
        h, body = get(url, env, route, offset=int(h["next_offset"]))
        assert h["status"].startswith("OK"), h
        parts.append(body)
    return h, "".join(parts)


def report(name, h):
    print(f"\n[{name}] " + " | ".join(f"{k}={h.get(k)}" for k in
          ("status", "final_url", "content_type", "route", "bytes", "total_chars", "sha256")))
    print(f"[{name}] warnings: {h.get('warnings')}")


def test_nyse_early_close_footnote():
    h, text = read_all(NYSE, {})
    report("nyse", h)
    assert "Monday, July 3, 2028" in text
    m = re.search(r"[^\n]*Monday, July 3, 2028[^\n]*", text)
    print("[nyse] footnote:", m.group(0)[:300])


def test_ibkr_commissions_example_and_footnote_markers():
    h, text = read_all(IBKR, {})
    report("ibkr", h)
    assert "HKD 22.40" in text
    marked = re.findall(r"USD \d+\.\d+\^\[\d+(?:,\d+)*\]", text)
    print("[ibkr] footnote-marked values:", marked[:8])
    assert marked
    assert "USD 0.00^[2]" in text or "USD 0.00^[3]" in text


def test_sec_10k_fully_readable_in_pages():
    identity = secret("EDGAR_IDENTITY")
    if not identity:
        pytest.skip("EDGAR_IDENTITY not available")
    env = {"FETCH_RAW_IDENTITY_HOSTS": "sec.gov=EDGAR_IDENTITY", "EDGAR_IDENTITY": identity}
    h, text = read_all(TENK, env)
    report("sec-10k", h)
    assert identity not in text
    assert int(h["total_chars"]) == len(text) > 100_000
    assert "Total net sales" in text
    rows = [ln for ln in text.splitlines() if ln.startswith("| Total net sales")]
    print("[sec-10k] row:", rows[0][:200] if rows else None)
    assert rows and rows[0].count("|") >= 4


def test_arxiv_pdf_decimals_and_exponents():
    h, text = read_all(ARXIV, {})
    report("arxiv", h)
    assert "41.0" in text and "28.4" in text
    assert "3.3 · 10^[18]" in text and "2.3 · 10^[19]" in text
    assert not re.search(r"\b\d+ \.\d+", text)
    print("[arxiv]", re.search(r"Transformer \(base model\)[^\n]*", text).group(0))


def test_firecrawl_route_converts_with_our_converter():
    key = secret("FIRECRAWL_API_KEY")
    if not key:
        pytest.skip("FIRECRAWL_API_KEY not available")
    h, text = read_all(NYSE, {"FIRECRAWL_API_KEY": key}, route="firecrawl")
    report("nyse-via-firecrawl", h)
    assert key not in text and key not in str(h)
    assert h["route"].startswith("firecrawl (rawBase64")
    assert "Monday, July 3, 2028" in text and "\\*\\*" not in text
