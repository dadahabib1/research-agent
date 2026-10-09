"""Network side of fetch_raw: URL and address checks, identity headers, politeness, manual redirects,
size and time caps, and the Firecrawl REST fallback.

Nothing here logs or returns a header value. Error messages name hosts and variables, never values.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
import socket
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
import truststore

from . import __version__

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,application/json;q=0.9,"
          "text/plain;q=0.8,text/csv;q=0.8,*/*;q=0.5")
MAX_REDIRECTS = 5
TIMEOUT_S = 30.0
MAX_BYTES = 25 * 1024 * 1024
FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
FIRECRAWL_TIMEOUT_S = 60.0
FIRECRAWL_MAX_BYTES = 36 * 1024 * 1024  # base64 of a 25 MB body plus JSON
MIN_INTERVAL = {"sec.gov": 0.1}
DEFAULT_INTERVAL = 0.5
ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "application/xml", "text/xml", "application/json",
                 "text/csv", "text/plain", "application/pdf"}
REDIRECT_CODES = {301, 302, 303, 307, 308}
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HOST_SUFFIX = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")

sleep = time.sleep  # tests replace this


class FetchError(Exception):
    """A failure whose message is safe to return. fallback_ok marks failures a bot wall can cause."""

    def __init__(self, message: str, fallback_ok: bool = False):
        super().__init__(message)
        self.fallback_ok = fallback_ok
        self.hosts: list[str] = []


@dataclass
class Raw:
    status: int
    url: str
    content_type: str
    body: bytes
    route: str
    hosts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------- configuration ----------

def identity_rules(env) -> list[tuple[str, str]]:
    """Parse FETCH_RAW_IDENTITY_HOSTS, e.g. "sec.gov=EDGAR_IDENTITY,example.org=OTHER_VAR"."""
    rules = []
    for item in (env.get("FETCH_RAW_IDENTITY_HOSTS") or "").split(","):
        item = item.strip()
        if not item:
            continue
        suffix, sep, var = (x.strip() for x in item.partition("="))
        suffix = suffix.lower().strip(".")
        if not sep or not HOST_SUFFIX.match(suffix) or not ENV_NAME.match(var):
            raise FetchError(f"FETCH_RAW_IDENTITY_HOSTS entry {item!r} is not host-suffix=ENVVAR")
        rules.append((suffix, var))
    return rules


def host_matches(host: str, suffix: str) -> bool:
    host = host.lower().rstrip(".")
    return host == suffix or host.endswith("." + suffix)


def identity_var(host: str, rules) -> str | None:
    for suffix, var in rules:
        if host_matches(host, suffix):
            return var
    return None


# ---------- URL and address checks ----------

def check_url(url: str):
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise FetchError(f"invalid URL: {e}") from None
    if parts.scheme not in ("http", "https"):
        raise FetchError(f"refused: scheme {parts.scheme or '(none)'!r}; only http and https are fetched")
    if not parts.hostname:
        raise FetchError("invalid URL: no host")
    if parts.username is not None or parts.password is not None:
        raise FetchError("refused: URL carries credentials")
    return parts, port or (443 if parts.scheme == "https" else 80)


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%", 1)[0])
    if a.version == 6:
        for embedded in (a.ipv4_mapped, a.sixtofour, (a.teredo or (None, None))[1]):
            if embedded is not None and not _public(str(embedded)):
                return False
    return a.is_global and not a.is_multicast


def resolve(host: str, port: int) -> list[str]:
    """All addresses for host. Tests replace this."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    out = []
    for info in infos:
        ip = info[4][0]
        if ip not in out:
            out.append(ip)
    return out


class DnsFailure(FetchError):
    pass


def check_addresses(host: str, port: int) -> list[str]:
    """Refuse private, loopback, link-local, reserved and other non-public addresses."""
    try:
        ipaddress.ip_address(host.strip("[]"))
        ips = [host.strip("[]")]
    except ValueError:
        try:
            ips = resolve(host.encode("idna").decode("ascii"), port)
        except (OSError, UnicodeError) as e:
            raise DnsFailure(f"DNS lookup failed for {host}: {e}", fallback_ok=False) from None
    if not ips:
        raise DnsFailure(f"DNS lookup returned no address for {host}")
    bad = [ip for ip in ips if not _public(ip)]
    if bad:
        raise FetchError(f"refused: {host} resolves to a non-public address ({bad[0]})")
    return ips


class GuardedBackend(httpcore.SyncBackend):
    """Checks addresses at connect time and connects to the checked address, so a DNS answer that
    changes between the check and the connection (rebinding) cannot reach a private address."""

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        last = None
        for ip in check_addresses(host, port):
            try:
                return super().connect_tcp(ip, port, timeout, local_address, socket_options)
            except httpcore.ConnectError as e:
                last = e
        raise last


def proxy_for(url: str) -> str | None:
    """The proxy the environment names for this URL (HTTPS_PROXY and the like), honouring NO_PROXY."""
    parts = urlsplit(url)
    proxies = urllib.request.getproxies()
    if not proxies or urllib.request.proxy_bypass(parts.hostname or ""):
        return None
    return proxies.get(parts.scheme) or proxies.get("all")


def _ssl_context() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def make_client(proxy: str | None, timeout: float, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A fresh client per request: no cookie jar survives, redirects are followed by hand."""
    t = httpx.Timeout(timeout)
    if transport is not None:
        return httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=t)
    ctx = _ssl_context()
    if proxy:
        return httpx.Client(proxy=proxy, verify=ctx, trust_env=False, follow_redirects=False, timeout=t)
    guarded = httpx.HTTPTransport(verify=ctx, retries=0)
    guarded._pool = httpcore.ConnectionPool(ssl_context=ctx, network_backend=GuardedBackend())
    return httpx.Client(transport=guarded, trust_env=False, follow_redirects=False, timeout=t)


def precheck(url: str, transport) -> tuple[str, str | None, list[str]]:
    """Check scheme and addresses for one hop. Returns host, proxy and warnings."""
    parts, port = check_url(url)
    host = parts.hostname
    proxy = None if transport is not None else proxy_for(url)
    warnings = []
    try:
        check_addresses(host, port)
    except DnsFailure as e:
        if not proxy:
            raise
        warnings.append(f"{host} does not resolve locally; the proxy resolves it ({e})")
    return host, proxy, warnings


# ---------- politeness ----------

_last: dict[str, float] = {}
_lock = threading.Lock()


def interval_for(host: str) -> float:
    for suffix, seconds in MIN_INTERVAL.items():
        if host_matches(host, suffix):
            return seconds
    return DEFAULT_INTERVAL


def polite_wait(host: str) -> None:
    host = host.lower()
    gap = interval_for(host)
    with _lock:
        now = time.monotonic()
        last = _last.get(host)
        wait = 0.0 if last is None else max(0.0, last + gap - now)
        _last[host] = now + wait
    if wait:
        sleep(wait)


# ---------- content types ----------

def media_type(ct: str) -> str:
    return (ct or "").split(";", 1)[0].strip().lower()


def type_allowed(mt: str) -> bool:
    return (mt in ALLOWED_TYPES or mt.startswith("text/") or mt.endswith("+xml") or mt.endswith("+json"))


def settle_type(ct: str, body: bytes, warnings: list[str]) -> str:
    """Final content type after the allowlist; sniffs only a missing or generic type."""
    mt = media_type(ct)
    if type_allowed(mt):
        return ct
    if mt in ("", "application/octet-stream", "binary/octet-stream"):
        head = body[:1024].lstrip().lower()
        if body[:5] == b"%PDF-":
            warnings.append(f"content type {mt or '(none)'}; body is a PDF")
            return "application/pdf"
        if head.startswith((b"<!doctype html", b"<html")):
            warnings.append(f"content type {mt or '(none)'}; body is HTML")
            return "text/html"
    raise FetchError(f"content type {mt or '(none)'} is not fetched (allowed: html, xhtml, xml, json, text, csv, pdf)")


def _read_capped(resp: httpx.Response, deadline: float, cap: int) -> bytes:
    length = resp.headers.get("content-length")
    if length and length.isdigit() and int(length) > cap:
        raise FetchError(f"body of {int(length)} bytes exceeds the {cap // (1024 * 1024)} MB cap")
    buf = bytearray()
    for chunk in resp.iter_bytes():
        buf += chunk
        if len(buf) > cap:
            raise FetchError(f"body exceeds the {cap // (1024 * 1024)} MB cap")
        if time.monotonic() > deadline:
            raise FetchError(f"timed out after {TIMEOUT_S:.0f} s", fallback_ok=True)
    return bytes(buf)


# ---------- direct fetch ----------

def fetch_direct(url: str, env, rules, transport: httpx.BaseTransport | None = None) -> Raw:
    hosts: list[str] = []
    try:
        return _fetch_direct(url, env, rules, transport, hosts)
    except FetchError as e:
        e.hosts = list(hosts)  # every host contacted, so callers can keep identity hosts off Firecrawl
        raise


def _fetch_direct(url, env, rules, transport, hosts: list[str]) -> Raw:
    deadline = time.monotonic() + TIMEOUT_S
    warnings: list[str] = []
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        host, proxy, w = precheck(current, transport)
        warnings += w
        var = identity_var(host, rules)
        if var:
            ua = (env.get(var) or "").strip()
            if not ua:
                raise FetchError(f"{host} is an identity host (FETCH_RAW_IDENTITY_HOSTS) but environment "
                                 f"variable {var} is not set")
        else:
            ua = BROWSER_UA
        polite_wait(host)
        hosts.append(host)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError(f"timed out after {TIMEOUT_S:.0f} s", fallback_ok=True)
        headers = {"User-Agent": ua, "Accept": ACCEPT, "Accept-Language": "en-US,en;q=0.9",
                   "Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
            with make_client(proxy, remaining, transport) as client:
                with client.stream("GET", current, headers=headers) as resp:
                    location = resp.headers.get("location")
                    if resp.status_code in REDIRECT_CODES and location:
                        current = urljoin(current, location.strip())
                        continue
                    ct = resp.headers.get("content-type", "")
                    mt = media_type(ct)
                    if mt and not type_allowed(mt) and mt not in ("application/octet-stream", "binary/octet-stream"):
                        raise FetchError(f"content type {mt} is not fetched (allowed: html, xhtml, xml, json, "
                                         f"text, csv, pdf)")
                    body = _read_capped(resp, deadline, MAX_BYTES)
                    ct = settle_type(ct, body, warnings)
                    return Raw(status=resp.status_code, url=current, content_type=ct, body=body,
                               route="direct", hosts=hosts, warnings=warnings)
        except httpx.TimeoutException:
            raise FetchError(f"timed out after {TIMEOUT_S:.0f} s", fallback_ok=True) from None
        except httpx.HTTPError as e:
            raise FetchError(f"network error from {host}: {type(e).__name__}: {str(e)[:160]}",
                             fallback_ok=True) from None
    raise FetchError(f"more than {MAX_REDIRECTS} redirects")


# ---------- Firecrawl fallback ----------

def fetch_firecrawl(url: str, key: str, fmt: str, transport: httpx.BaseTransport | None = None) -> Raw:
    """One Firecrawl scrape. fmt "rawBase64" returns the origin's body bytes; "rawHtml" returns the page
    after JavaScript ran. Firecrawl gets the URL and our key only: no identity, no custom headers."""
    check_url(url)
    payload = {"url": url, "formats": [fmt], "maxAge": 0, "storeInCache": False,
               "skipTlsVerification": False, "timeout": 30000}
    if fmt == "rawBase64":
        payload["parsers"] = []
    host, proxy, warnings = precheck(FIRECRAWL_URL, transport)
    headers = {"Authorization": f"Bearer {key}", "User-Agent": f"research-agent-fetch-raw/{__version__}"}

    def clean(msg: str) -> str:
        return msg.replace(key, "[key]") if key else msg

    deadline = time.monotonic() + FIRECRAWL_TIMEOUT_S
    try:
        with make_client(proxy, FIRECRAWL_TIMEOUT_S, transport) as client:
            with client.stream("POST", FIRECRAWL_URL, json=payload, headers=headers) as resp:
                raw = _read_capped(resp, deadline, FIRECRAWL_MAX_BYTES)
                code = resp.status_code
    except httpx.TimeoutException:
        raise FetchError("Firecrawl timed out") from None
    except httpx.HTTPError as e:
        raise FetchError(clean(f"Firecrawl network error: {type(e).__name__}: {str(e)[:160]}")) from None
    try:
        doc = httpx.Response(200, content=raw).json()
    except ValueError:
        raise FetchError(f"Firecrawl returned HTTP {code} with a non-JSON body") from None
    if code != 200 or not doc.get("success", False):
        err = str(doc.get("error") or doc.get("code") or "")[:200]
        raise FetchError(clean(f"Firecrawl returned HTTP {code}: {err}".rstrip(": ")))
    data = doc.get("data") or {}
    meta = data.get("metadata") or {}
    status = int(meta.get("statusCode") or 0)
    final = meta.get("url") or meta.get("sourceURL") or url
    ct = meta.get("contentType") or ""
    if fmt == "rawBase64":
        try:
            body = base64.b64decode(data.get("rawBase64") or "", validate=True)
        except (binascii.Error, ValueError):
            raise FetchError("Firecrawl returned a rawBase64 field that is not base64") from None
        route = "firecrawl (rawBase64: origin bytes)"
    else:
        body = (data.get("rawHtml") or "").encode("utf-8")
        ct = "text/html; charset=utf-8"
        route = "firecrawl (rawHtml: page after JavaScript)"
        warnings.append("rawHtml is Firecrawl's copy of the page after JavaScript ran; sha256 covers that "
                        "copy, not the origin's bytes")
    if len(body) > MAX_BYTES:
        raise FetchError("body exceeds the 25 MB cap")
    credits = doc.get("creditsUsed", meta.get("creditsUsed"))
    if credits is not None:
        warnings.append(f"Firecrawl credits used: {credits}")
    ct = settle_type(ct, body, warnings)
    return Raw(status=status, url=final, content_type=ct, body=body, route=route, warnings=warnings)
