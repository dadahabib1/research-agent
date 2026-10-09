import base64
import json

import httpx
import pytest
from conftest import Web, fixture_bytes, html

from fetchraw import net, tool
from fetchraw.net import BROWSER_UA, FIRECRAWL_URL

IDENTITY = "Example Research Ltd research@example.com"
SEC_ENV = {"FETCH_RAW_IDENTITY_HOSTS": "sec.gov=EDGAR_IDENTITY", "EDGAR_IDENTITY": IDENTITY}
KEY = "fc-test-key-123"


def fetch(url, env, web, offset=0, max_chars=40000, route="auto"):
    return tool.fetch_page(url, offset, max_chars, route, env, web.transport, web.transport)


def header(out: str) -> dict:
    head = out.split("\n--- content ---\n", 1)[0]
    return dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)


def content(out: str) -> str:
    return out.split("\n--- content ---\n", 1)[1] if "\n--- content ---\n" in out else ""


def firecrawl_ok(body: bytes, ctype="text/html; charset=utf-8", status=200, url="https://www.example.com/p"):
    def handler(request):
        req = json.loads(request.content)
        fmt = req["formats"][0]
        data = {"metadata": {"statusCode": status, "url": url, "sourceURL": req["url"], "contentType": ctype}}
        if fmt == "rawBase64":
            data["rawBase64"] = base64.b64encode(body).decode()
        else:
            data["rawHtml"] = body.decode("utf-8")
        return httpx.Response(200, json={"success": True, "data": data, "creditsUsed": 1})
    return handler


# ---------- OK path and header ----------

def test_ok_header_fields_and_content():
    web = Web({"https://www.example.com/p": html(fixture_bytes("footer_footnotes.html"))})
    out = fetch("https://www.example.com/p", {}, web)
    h = header(out)
    assert h["status"] == "OK (HTTP 200)"
    assert h["final_url"] == "https://www.example.com/p"
    assert h["content_type"].startswith("text/html")
    assert h["route"] == "direct"
    assert h["bytes"] == str(len(fixture_bytes("footer_footnotes.html")))
    assert len(h["sha256"]) == 64 and h["fetched_at"].endswith("Z")
    assert h["next_offset"] == "none"
    assert "Monday, July 3, 2028" in content(out)


def test_http_404_is_error_without_content():
    web = Web({"https://www.example.com/p": html(b"<h1>Not here</h1>", status=404)})
    out = fetch("https://www.example.com/p", {}, web)
    assert header(out)["status"] == "ERROR (HTTP 404)" and content(out) == ""


# ---------- blocked pages ----------

@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_block_status_codes(status):
    web = Web({"https://www.example.com/p": html(b"<p>" + b"words " * 2000 + b"</p>", status=status)})
    out = fetch("https://www.example.com/p", {}, web)
    h = header(out)
    assert h["status"].startswith("BLOCKED") and h["reason"].startswith(f"HTTP {status}")
    assert content(out) == ""


def test_cloudflare_page_with_http_200_is_blocked():
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html"))})
    out = fetch("https://www.example.com/p", {}, web)
    h = header(out)
    assert h["status"] == "BLOCKED (HTTP 200)"
    assert "Attention Required" in h["reason"] and "no FIRECRAWL_API_KEY" in h["reason"]
    assert "Ray ID" not in out and "--- content ---" not in out


def test_js_shell_is_blocked():
    web = Web({"https://www.example.com/app": html(fixture_bytes("js_shell.html"))})
    h = header(fetch("https://www.example.com/app", {}, web))
    assert h["status"].startswith("BLOCKED") and "needs JavaScript" in h["reason"]


def test_long_page_with_a_captcha_widget_is_not_blocked():
    page = (b"<html><head><title>Fees</title></head><body><form><div class='g-recaptcha'></div></form>"
            + b"<p>" + b"Commission USD 0.0035 per share. " * 200 + b"</p></body></html>")
    web = Web({"https://www.example.com/fees": html(page)})
    assert header(fetch("https://www.example.com/fees", {}, web))["status"] == "OK (HTTP 200)"


def test_fallback_to_firecrawl_on_block(offline):
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: firecrawl_ok(fixture_bytes("footer_footnotes.html"))})
    out = fetch("https://www.example.com/p", {"FIRECRAWL_API_KEY": KEY}, web)
    h = header(out)
    assert h["status"] == "OK (HTTP 200)"
    assert h["route"] == "firecrawl (rawBase64: origin bytes)"
    assert "Monday, July 3, 2028" in content(out)
    assert "direct fetch failed" in h["warnings"] and "Firecrawl credits used: 1" in h["warnings"]
    fc = [r for r in web.requests if r.url.host == "api.firecrawl.dev"]
    assert len(fc) == 1
    body = json.loads(fc[0].content)
    assert body == {"url": "https://www.example.com/p", "formats": ["rawBase64"], "maxAge": 0,
                    "storeInCache": False, "skipTlsVerification": False, "timeout": 30000, "parsers": []}
    assert fc[0].headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in out


def test_firecrawl_js_shell_retries_as_rawhtml():
    calls = []

    def handler(request):
        fmt = json.loads(request.content)["formats"][0]
        calls.append(fmt)
        page = fixture_bytes("js_shell.html") if fmt == "rawBase64" else fixture_bytes("sup_table.html")
        return firecrawl_ok(page)(request)

    web = Web({"https://www.example.com/app": html(fixture_bytes("js_shell.html")), FIRECRAWL_URL: handler})
    out = fetch("https://www.example.com/app", {"FIRECRAWL_API_KEY": KEY}, web)
    h = header(out)
    assert calls == ["rawBase64", "rawHtml"]
    assert h["status"] == "OK (HTTP 200)" and h["route"] == "firecrawl (rawHtml: page after JavaScript)"
    assert "after JavaScript ran" in h["warnings"]
    assert "USD 0.00056^[5]" in content(out)


def test_firecrawl_also_blocked_gives_blocked():
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: firecrawl_ok(fixture_bytes("cloudflare_block.html"))})
    out = fetch("https://www.example.com/p", {"FIRECRAWL_API_KEY": KEY}, web)
    h = header(out)
    assert h["status"].startswith("BLOCKED") and h["reason"].startswith("direct: ") and "firecrawl: " in h["reason"]
    assert "--- content ---" not in out


def test_firecrawl_api_error_is_reported_without_key():
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: (402, {"content-type": "application/json"},
                               json.dumps({"success": False, "error": f"Payment required for {KEY}"}).encode())})
    out = fetch("https://www.example.com/p", {"FIRECRAWL_API_KEY": KEY}, web)
    assert header(out)["status"] == "ERROR" and "HTTP 402" in out and KEY not in out


def test_route_direct_never_falls_back():
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: firecrawl_ok(fixture_bytes("footer_footnotes.html"))})
    out = fetch("https://www.example.com/p", {"FIRECRAWL_API_KEY": KEY}, web, route="direct")
    assert header(out)["status"].startswith("BLOCKED") and "api.firecrawl.dev" not in web.hosts()


def test_route_firecrawl_needs_key():
    web = Web()
    out = fetch("https://www.example.com/p", {}, web, route="firecrawl")
    assert header(out)["status"] == "ERROR" and "FIRECRAWL_API_KEY" in out and web.requests == []


def test_network_failure_falls_back_in_auto():
    def boom(request):
        raise httpx.ConnectError("connection reset")

    web = Web({"https://www.example.com/p": boom, FIRECRAWL_URL: firecrawl_ok(fixture_bytes("sup_table.html"))})
    h = header(fetch("https://www.example.com/p", {"FIRECRAWL_API_KEY": KEY}, web))
    assert h["status"] == "OK (HTTP 200)" and h["route"].startswith("firecrawl")


# ---------- identity ----------

def ua_by_host(web):
    return [(r.url.host, r.headers["user-agent"]) for r in web.requests]


def test_identity_sent_only_to_sec_gov():
    web = Web({"https://www.sec.gov/a": html(b"<p>filing</p>" * 50),
               "https://www.example.com/b": html(b"<p>page</p>" * 50),
               "https://efts.sec.gov/c": html(b"<p>search</p>" * 50),
               "https://notsec.gov/d": html(b"<p>lookalike</p>" * 50),
               "https://sec.gov.example.net/e": html(b"<p>lookalike</p>" * 50)})
    outs = [fetch(u, SEC_ENV, web) for u in ["https://www.sec.gov/a", "https://www.example.com/b",
                                             "https://efts.sec.gov/c", "https://notsec.gov/d",
                                             "https://sec.gov.example.net/e"]]
    assert ua_by_host(web) == [("www.sec.gov", IDENTITY), ("www.example.com", BROWSER_UA),
                               ("efts.sec.gov", IDENTITY), ("notsec.gov", BROWSER_UA),
                               ("sec.gov.example.net", BROWSER_UA)]
    assert all(IDENTITY not in o for o in outs)


def test_identity_rechecked_after_redirects():
    web = Web({"https://www.sec.gov/r": (302, {"location": "https://www.example.com/landing"}, b""),
               "https://www.example.com/landing": html(b"<p>ok</p>" * 50),
               "https://www.example.com/go": (301, {"location": "https://www.sec.gov/doc"}, b""),
               "https://www.sec.gov/doc": html(b"<p>doc</p>" * 50)})
    fetch("https://www.sec.gov/r", SEC_ENV, web)
    fetch("https://www.example.com/go", SEC_ENV, web)
    assert ua_by_host(web) == [("www.sec.gov", IDENTITY), ("www.example.com", BROWSER_UA),
                               ("www.example.com", BROWSER_UA), ("www.sec.gov", IDENTITY)]


def test_identity_host_never_goes_to_firecrawl():
    env = dict(SEC_ENV, FIRECRAWL_API_KEY=KEY)
    web = Web({"https://www.sec.gov/a": html(b"denied", status=403),
               "https://www.example.com/go": (302, {"location": "https://www.sec.gov/a"}, b""),
               FIRECRAWL_URL: firecrawl_ok(b"<p>should not be used</p>")})
    out1 = fetch("https://www.sec.gov/a", env, web)
    out2 = fetch("https://www.example.com/go", env, web)
    out3 = fetch("https://www.sec.gov/a", env, web, route="firecrawl")
    assert "identity host" in header(out1)["reason"] and "identity host" in header(out2)["reason"]
    assert header(out3)["status"] == "ERROR" and "never routed through Firecrawl" in out3
    assert "api.firecrawl.dev" not in web.hosts()
    assert all(IDENTITY not in o for o in (out1, out2, out3))


def test_failure_after_redirect_to_identity_host_does_not_fall_back():
    def hang(request):
        raise httpx.ReadTimeout("read timed out")

    env = dict(SEC_ENV, FIRECRAWL_API_KEY=KEY)
    web = Web({"https://www.example.com/go": (302, {"location": "https://www.sec.gov/slow"}, b""),
               "https://www.sec.gov/slow": hang, FIRECRAWL_URL: firecrawl_ok(b"<p>x</p>")})
    out = fetch("https://www.example.com/go", env, web)
    assert header(out)["status"] == "ERROR" and "timed out" in out
    assert "api.firecrawl.dev" not in web.hosts()


def test_firecrawl_landing_on_identity_host_is_not_used():
    env = dict(SEC_ENV, FIRECRAWL_API_KEY=KEY)
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: firecrawl_ok(b"<p>filing</p>" * 50, url="https://www.sec.gov/landing")})
    out = fetch("https://www.example.com/p", env, web)
    assert header(out)["status"] == "ERROR" and "identity host www.sec.gov" in out
    assert "--- content ---" not in out


def test_identity_never_in_firecrawl_request():
    env = dict(SEC_ENV, FIRECRAWL_API_KEY=KEY)
    web = Web({"https://www.example.com/p": html(fixture_bytes("cloudflare_block.html")),
               FIRECRAWL_URL: firecrawl_ok(fixture_bytes("sup_table.html"))})
    fetch("https://www.example.com/p", env, web)
    fc = [r for r in web.requests if r.url.host == "api.firecrawl.dev"]
    assert fc and all(IDENTITY not in (str(r.headers) + r.content.decode()) for r in fc)


def test_missing_identity_variable_is_an_error_naming_it():
    web = Web({"https://www.sec.gov/a": html(b"<p>x</p>")})
    out = fetch("https://www.sec.gov/a", {"FETCH_RAW_IDENTITY_HOSTS": "sec.gov=EDGAR_IDENTITY"}, web)
    assert header(out)["status"] == "ERROR" and "EDGAR_IDENTITY is not set" in out
    assert web.requests == []


def test_malformed_identity_config_is_an_error():
    out = fetch("https://www.example.com/", {"FETCH_RAW_IDENTITY_HOSTS": "sec.gov"}, Web())
    assert header(out)["status"] == "ERROR" and "host-suffix=ENVVAR" in out


# ---------- security ----------

@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/x", "http://[::1]/", "http://169.254.169.254/latest",
                                 "http://[::ffff:192.168.0.1]/", "http://100.64.0.1/", "http://0.0.0.0/",
                                 "https://intranet.example/", "https://meta.example/", "http://local.example:8080/"])
def test_private_addresses_refused(url):
    web = Web()
    out = fetch(url, {}, web)
    assert header(out)["status"] == "ERROR" and "non-public address" in out and web.requests == []


def test_private_address_refused_after_redirect():
    web = Web({"https://www.example.com/r": (302, {"location": "http://169.254.169.254/latest/meta-data"}, b""),
               "https://www.example.com/r2": (302, {"location": "https://intranet.example/admin"}, b"")})
    for u in ["https://www.example.com/r", "https://www.example.com/r2"]:
        out = fetch(u, {}, web)
        assert header(out)["status"] == "ERROR" and "non-public address" in out
    assert web.hosts() == ["www.example.com", "www.example.com"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/",
                                 "https://user:pw@www.example.com/", "not a url"])
def test_bad_urls_refused(url):
    out = fetch(url, {}, Web())
    assert header(out)["status"] == "ERROR"


def test_guarded_backend_checks_at_connect_time(monkeypatch):
    monkeypatch.setattr(net, "resolve", lambda host, port: ["127.0.0.1"])
    with pytest.raises(net.FetchError, match="non-public"):
        net.GuardedBackend().connect_tcp("rebind.example", 443)


def test_public_address_rules():
    assert net._public("8.8.8.8") and net._public("2606:4700::1111")
    for ip in ["10.0.0.1", "172.16.0.1", "192.168.1.1", "127.0.0.1", "169.254.1.1", "100.64.0.1", "0.0.0.0",
               "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:10.0.0.1", "2002:0a00:0001::1"]:
        assert not net._public(ip), ip


def test_redirect_limit():
    routes = {f"https://www.example.com/{i}": (302, {"location": f"/{i + 1}"}, b"") for i in range(7)}
    out = fetch("https://www.example.com/0", {}, Web(routes))
    assert header(out)["status"] == "ERROR" and "more than 5 redirects" in out


def test_five_redirects_are_allowed():
    routes = {f"https://www.example.com/{i}": (302, {"location": f"/{i + 1}"}, b"") for i in range(5)}
    routes["https://www.example.com/5"] = html(b"<p>arrived</p>" * 40)
    out = fetch("https://www.example.com/0", {}, Web(routes))
    assert header(out)["status"] == "OK (HTTP 200)" and header(out)["final_url"] == "https://www.example.com/5"


def test_size_cap(monkeypatch):
    monkeypatch.setattr(net, "MAX_BYTES", 1000)
    big = b"<p>" + b"x" * 5000 + b"</p>"
    web = Web({"https://www.example.com/big": html(big),
               "https://www.example.com/chunked": lambda r: httpx.Response(
                   200, headers={"content-type": "text/html"}, content=iter([b"<p>", b"y" * 3000]))})
    assert "exceeds the" in fetch("https://www.example.com/big", {}, web)
    assert "exceeds the" in fetch("https://www.example.com/chunked", {}, web)


def test_content_type_allowlist():
    web = Web({"https://www.example.com/i.png": (200, {"content-type": "image/png"}, b"\x89PNG"),
               "https://www.example.com/d.bin": (200, {"content-type": "application/octet-stream"}, b"%PDF-1.4 junk"),
               "https://www.example.com/z": (200, {"content-type": "application/zip"}, b"PK")})
    assert "image/png is not fetched" in fetch("https://www.example.com/i.png", {}, web)
    assert "application/zip is not fetched" in fetch("https://www.example.com/z", {}, web)
    out = fetch("https://www.example.com/d.bin", {}, web)
    assert header(out)["content_type"] == "application/pdf"  # sniffed; conversion then fails or succeeds


def test_no_cookies_kept_and_no_cache_sent():
    web = Web({"https://www.example.com/a": (302, {"location": "/b", "set-cookie": "sid=abc; Path=/"}, b""),
               "https://www.example.com/b": html(b"<p>b</p>" * 40)})
    fetch("https://www.example.com/a", {}, web)
    fetch("https://www.example.com/b", {}, web)
    assert all("cookie" not in r.headers for r in web.requests)
    assert all(r.headers["cache-control"] == "no-cache" and r.headers["pragma"] == "no-cache" for r in web.requests)


def test_politeness_intervals(offline):
    web = Web({"https://www.example.com/a": html(b"<p>a</p>" * 40), "https://www.sec.gov/a": html(b"<p>a</p>" * 40)})
    for _ in range(2):
        fetch("https://www.example.com/a", {}, web)
    for _ in range(2):
        fetch("https://www.sec.gov/a", SEC_ENV, web)
    assert len(offline) == 2
    assert 0.4 < offline[0] <= 0.5 and 0.05 < offline[1] <= 0.1


def test_timeout_is_reported(monkeypatch):
    def slow(request):
        raise httpx.ReadTimeout("read timed out")

    out = fetch("https://www.example.com/slow", {}, Web({"https://www.example.com/slow": slow}))
    assert header(out)["status"] == "ERROR" and "timed out" in out


# ---------- paging ----------

def big_tenk(rows=4000) -> bytes:
    body = "".join(f"<tr><td>Line item {i}</td><td>$</td><td>{i * 1000 + 7:,}</td><td></td><td>({i}.5)</td></tr>"
                   for i in range(rows))
    return f"<html><body><h1>Annual report</h1><table>{body}</table><p>End of report 99.9</p></body></html>".encode()


def test_paging_reads_the_whole_document_once():
    web = Web({"https://www.example.com/10k": html(big_tenk())})
    pages, offset = [], 0
    while True:
        out = fetch("https://www.example.com/10k", {}, web, offset=offset, max_chars=40000)
        h = header(out)
        assert h["status"] == "OK (HTTP 200)"
        pages.append((h, content(out)))
        if h["next_offset"] == "none":
            break
        offset = int(h["next_offset"])
    text = "".join(c for _, c in pages)
    total = int(pages[0][0]["total_chars"])
    assert len(pages) > 3 and len(text) == total
    assert "| Line item 3999 | $ | 3,999,007 |  | (3999.5) |" in text and text.rstrip().endswith("End of report 99.9")
    assert len({h["sha256"] for h, _ in pages}) == 1
    assert len(web.requests) == 1  # later pages come from the first fetch
    assert "served from this server's copy" in pages[1][0]["warnings"]


def test_offset_zero_refetches():
    web = Web({"https://www.example.com/p": html(b"<p>a</p>" * 40)})
    fetch("https://www.example.com/p", {}, web)
    fetch("https://www.example.com/p", {}, web)
    assert len(web.requests) == 2


@pytest.mark.parametrize("offset,max_chars", [(-1, 10), (0, 0), (0, 100_001)])
def test_bad_paging_arguments(offset, max_chars):
    out = fetch("https://www.example.com/p", {}, Web(), offset=offset, max_chars=max_chars)
    assert header(out)["status"] == "ERROR"
