"""Recognise block, challenge and JavaScript-only pages, so they never come back as OK."""

from __future__ import annotations

BLOCK_STATUS = {401, 403, 429, 503}

# Phrases that bot walls (Cloudflare, Akamai, Imperva, PerimeterX, DataDome) put in titles and headings.
PHRASES = [
    "just a moment",
    "attention required",
    "why have i been blocked",
    "sorry, you have been blocked",
    "access denied",
    "you don't have permission to access",
    "request unsuccessful. incapsula",
    "pardon our interruption",
    "verify you are human",
    "are you a robot",
    "checking your browser",
    "please enable cookies",
    "security check",
]
# Markup of challenge and captcha widgets. Ordinary pages can embed a captcha (a login form), so these
# count only on short pages.
MARKERS = [
    "cf-chl", "challenge-platform", "cf-turnstile", "g-recaptcha", "h-captcha", "hcaptcha",
    "px-captcha", "_incapsula_resource", "errors.edgesuite.net", "captcha-delivery.com", "geo.captcha",
]
JS_PHRASES = ["enable javascript", "javascript is required", "javascript is disabled",
              "requires javascript", "turn on javascript", "javascript must be enabled"]

SHORT_PAGE = 3000     # visible chars under which challenge markup or a block phrase anywhere counts
NEAR_EMPTY = 600      # visible chars under which a JavaScript notice means the content never rendered


def detect(status: int | None, kind: str, raw: bytes, title: str, visible_chars: int,
           text: str) -> str | None:
    """Return a one-line reason if this response is a block or challenge page, else None."""
    if status in BLOCK_STATUS:
        return f"HTTP {status}"
    if kind != "html":
        return None
    t = (title or "").lower()
    for p in PHRASES:
        if p in t:
            return f'block page: title "{title.strip()[:80]}"'
    low_text = text.lower()
    head = raw[:300_000].decode("utf-8", errors="ignore").lower()
    if visible_chars < SHORT_PAGE:
        for p in PHRASES:
            if p in low_text:
                return f'block page: short page says "{p}"'
        for m in MARKERS:
            if m in head:
                return f"challenge page: short page carries {m} markup"
    if visible_chars < NEAR_EMPTY:
        for p in JS_PHRASES:
            if p in low_text:
                return f"needs JavaScript: near-empty page ({visible_chars} visible chars) says \"{p}\""
    return None


def is_js_shell(reason: str | None) -> bool:
    return bool(reason) and reason.startswith("needs JavaScript")


def near_empty_warning(kind: str, visible_chars: int) -> str | None:
    if kind == "html" and visible_chars < 200:
        return f"near-empty page: {visible_chars} visible chars; content may load with JavaScript"
    return None

