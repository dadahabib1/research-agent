"""fetch_raw: fetch one URL, convert it without summarising, detect blocks, page the text."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import blocked
from .convert import convert
from .net import FetchError, Raw, check_url, fetch_direct, fetch_firecrawl, identity_rules, identity_var

ROUTES = ("auto", "direct", "firecrawl")
MAX_CHARS_LIMIT = 100_000
PAGE_CACHE_SECONDS = 15 * 60
PAGE_CACHE_ENTRIES = 8


@dataclass
class Result:
    status: str  # OK | BLOCKED | ERROR
    reason: str = ""
    http: int | None = None
    final_url: str = ""
    content_type: str = ""
    fetched_at: str = ""
    sha256: str = ""
    route: str = ""
    nbytes: int | None = None
    text: str = ""
    warnings: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assess(raw: Raw) -> tuple[Result, bool]:
    """Convert one response and classify it. Returns the result and whether it is a JS-only shell."""
    res = Result(status="OK", http=raw.status, final_url=raw.url, content_type=raw.content_type,
                 sha256=hashlib.sha256(raw.body).hexdigest(), route=raw.route, nbytes=len(raw.body),
                 warnings=list(raw.warnings))
    try:
        conv = convert(raw.body, raw.content_type, raw.url)
    except Exception as e:  # noqa: BLE001 - a parser failure is reported, never raised to the client
        res.status, res.reason = "ERROR", f"could not convert {raw.content_type or 'body'}: {type(e).__name__}: {str(e)[:160]}"
        return res, False
    reason = blocked.detect(raw.status, conv.kind, raw.body, conv.title, conv.visible_chars, conv.text)
    if reason:
        res.status, res.reason = "BLOCKED", reason
        return res, blocked.is_js_shell(reason)
    if raw.status >= 400:
        res.status, res.reason = "ERROR", f"HTTP {raw.status}"
        return res, False
    res.text = conv.text
    res.warnings += conv.warnings
    w = blocked.near_empty_warning(conv.kind, conv.visible_chars)
    if w:
        res.warnings.append(w)
    return res, False


def _firecrawl(url: str, key: str, transport, rules, prior: str = "") -> Result:
    def scrape(fmt: str) -> Raw:
        raw = fetch_firecrawl(url, key, fmt, transport)
        host = urlsplit(raw.url).hostname or ""
        if identity_var(host, rules):
            raise FetchError(f"Firecrawl ended on identity host {host}; its copy is not used")
        return raw

    try:
        res, js_shell = _assess(scrape("rawBase64"))
        if js_shell:
            first = res.reason
            res, _ = _assess(scrape("rawHtml"))
            res.warnings.insert(0, f"Firecrawl rawBase64: {first}; retried as rawHtml")
    except FetchError as e:
        return Result(status="ERROR", reason=(prior + "; " if prior else "") + str(e))
    if prior and res.status != "OK":
        res.reason = f"direct: {prior}; firecrawl: {res.reason}"
    elif prior:
        res.warnings.insert(0, f"direct fetch failed ({prior}); fetched through Firecrawl")
    return res


def run(url: str, route: str, env, transport=None, firecrawl_transport=None) -> Result:
    """One fetch. transport/firecrawl_transport exist for tests (httpx.MockTransport)."""
    fetched_at = _now()

    def done(res: Result) -> Result:
        res.fetched_at = res.fetched_at or fetched_at
        if res.status != "OK":
            res.text = ""
        return res

    if route not in ROUTES:
        return done(Result(status="ERROR", reason=f"route must be one of {', '.join(ROUTES)}"))
    try:
        rules = identity_rules(env)
        parts, _port = check_url(url)
    except FetchError as e:
        return done(Result(status="ERROR", reason=str(e)))
    key = (env.get("FIRECRAWL_API_KEY") or "").strip()
    identity_target = identity_var(parts.hostname, rules) is not None

    if route == "firecrawl":
        if identity_target:
            return done(Result(status="ERROR", reason=f"{parts.hostname} is an identity host; it is never "
                                                       "routed through Firecrawl"))
        if not key:
            return done(Result(status="ERROR", reason="route firecrawl needs FIRECRAWL_API_KEY, which is not set"))
        return done(_firecrawl(url, key, firecrawl_transport, rules))

    try:
        raw = fetch_direct(url, env, rules, transport)
    except FetchError as e:
        touched_identity = identity_target or any(identity_var(h, rules) for h in e.hosts)
        if route == "auto" and e.fallback_ok and key and not touched_identity:
            return done(_firecrawl(url, key, firecrawl_transport, rules, prior=str(e)))
        return done(Result(status="ERROR", reason=str(e), route="direct"))

    res, _ = _assess(raw)
    if res.status != "BLOCKED" or route == "direct":
        return done(res)
    if identity_target or any(identity_var(h, rules) for h in raw.hosts):
        res.reason += "; identity host, so no Firecrawl fallback"
        return done(res)
    if not key:
        res.reason += "; no FIRECRAWL_API_KEY for a fallback"
        return done(res)
    return done(_firecrawl(url, key, firecrawl_transport, rules, prior=res.reason))


# ---------- paging ----------

_cache: OrderedDict[tuple[str, str], tuple[float, Result]] = OrderedDict()
_cache_lock = threading.Lock()


def fetch_page(url: str, offset: int, max_chars: int, route: str, env, transport=None,
               firecrawl_transport=None) -> str:
    if not isinstance(offset, int) or offset < 0:
        return render(Result(status="ERROR", reason="offset must be a whole number of 0 or more",
                             fetched_at=_now()), 0, 1)
    if not isinstance(max_chars, int) or not 1 <= max_chars <= MAX_CHARS_LIMIT:
        return render(Result(status="ERROR", reason=f"max_chars must be between 1 and {MAX_CHARS_LIMIT}",
                             fetched_at=_now()), 0, 1)
    key = (url, route)
    res = None
    if offset > 0:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < PAGE_CACHE_SECONDS:
            res = hit[1]
            note = (f"page served from this server's copy fetched at {res.fetched_at}; "
                    "fetch offset 0 for a fresh copy")
            res = Result(**{**res.__dict__, "warnings": res.warnings + [note]})
    if res is None:
        res = run(url, route, env, transport, firecrawl_transport)
        if res.status == "OK":
            with _cache_lock:
                _cache[key] = (time.monotonic(), res)
                _cache.move_to_end(key)
                while len(_cache) > PAGE_CACHE_ENTRIES:
                    _cache.popitem(last=False)
    return render(res, offset, max_chars)


def render(res: Result, offset: int, max_chars: int) -> str:
    ok = res.status == "OK"
    total = len(res.text) if ok else 0
    end = min(total, offset + max_chars)
    next_offset = str(end) if ok and end < total else "none"
    warnings = list(res.warnings)
    if ok and offset >= total and total:
        warnings.append(f"offset {offset} is past the end ({total} chars)")
    lines = [
        f"status: {res.status}" + (f" (HTTP {res.http})" if res.http else ""),
        *([f"reason: {res.reason}"] if res.reason else []),
        f"final_url: {res.final_url or 'none'}",
        f"content_type: {res.content_type or 'none'}",
        f"fetched_at: {res.fetched_at}",
        f"sha256: {res.sha256 or 'none'}",
        f"route: {res.route or 'none'}",
        f"bytes: {res.nbytes if res.nbytes is not None else 'none'}",
        f"total_chars: {total}",
        f"next_offset: {next_offset}",
        f"warnings: {' | '.join(warnings) if warnings else 'none'}",
    ]
    head = "\n".join(lines)
    if not ok:
        return head + "\n"
    return head + "\n--- content ---\n" + res.text[offset:end]
