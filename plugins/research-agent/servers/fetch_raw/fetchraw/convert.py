"""Turn fetched bytes into text without summarising.

HTML: the whole visible document as markdown (html5lib parse, markdownify render). Only script,
style, template and hidden elements are dropped; nav, footer and footnotes stay. Table cells keep
every separator, empty cells included; <sup>/<sub> become ^[x]/_[x]; links become [text](absolute url).
PDF: see pdftext.py. JSON, XML, CSV and plain text: decoded and returned as is.
"""

from __future__ import annotations

import codecs
import re
import warnings
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, XMLParsedAsHTMLWarning
from markdownify import MarkdownConverter

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


@dataclass
class Converted:
    kind: str  # html | pdf | text
    text: str
    warnings: list[str] = field(default_factory=list)
    visible_chars: int = 0  # visible text length, links' targets excluded (HTML only)
    title: str = ""


def media_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def charset_of(content_type: str | None) -> str | None:
    m = re.search(r"charset\s*=\s*\"?([\w.:-]+)", content_type or "", re.I)
    if not m:
        return None
    try:
        return codecs.lookup(m.group(1)).name
    except LookupError:
        return None


def kind_of(content_type: str | None, body: bytes) -> str:
    mt = media_type(content_type)
    if mt == "application/pdf" or body[:5] == b"%PDF-":
        return "pdf"
    if mt in ("text/html", "application/xhtml+xml"):
        return "html"
    return "text"


class _Markdown(MarkdownConverter):
    def convert_sup(self, el, text, parent_tags):
        t = " ".join(text.split())
        return f"^[{t}]" if t else ""

    def convert_sub(self, el, text, parent_tags):
        t = " ".join(text.split())
        return f"_[{t}]" if t else ""

    def _cell(self, el, text):
        colspan = 1
        if "colspan" in el.attrs and str(el["colspan"]).isdigit():
            colspan = max(1, min(1000, int(el["colspan"])))
        t = UNESCAPED_PIPE.sub(r"\\|", " ".join(text.split()))
        return " " + t + " |" * colspan

    def convert_td(self, el, text, parent_tags):
        return self._cell(el, text)

    def convert_th(self, el, text, parent_tags):
        return self._cell(el, text)


_MD = dict(escape_asterisks=False, escape_underscores=False, escape_misc=False,
           heading_style="ATX", autolinks=False, table_infer_header=True)


def _is_hidden(tag) -> bool:
    if tag.attrs is None:
        return False
    if tag.has_attr("hidden"):
        return True
    if tag.name == "input" and str(tag.get("type", "")).lower() == "hidden":
        return True
    return bool(HIDDEN_STYLE.search(str(tag.get("style", "") or "")))


def html_to_markdown(body: bytes, base_url: str, charset: str | None = None) -> Converted:
    soup = BeautifulSoup(body, "html5lib", from_encoding=charset)
    out = Converted(kind="html", text="")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    out.title = title

    for tag in soup(["script", "style", "template"]):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    hidden_n = hidden_chars = 0
    for tag in soup.find_all(True):
        if getattr(tag, "decomposed", False):
            continue
        if _is_hidden(tag):
            hidden_n += 1
            hidden_chars += len(" ".join(tag.get_text(" ").split()))
            tag.decompose()
    if hidden_n:
        out.warnings.append(f"dropped {hidden_n} hidden element(s) holding {hidden_chars} chars of text")

    base = base_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        base = urljoin(base_url, base_tag["href"].strip())
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href and not href.lower().startswith(("javascript:", "data:")):
            a["href"] = urljoin(base, href)
        elif "href" in a.attrs:
            del a["href"]
        a.attrs.pop("title", None)
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        img["src"] = "data:(inline image omitted)" if src.lower().startswith("data:") else urljoin(base, src)
        img.attrs.pop("title", None)

    body_el = soup.body or soup
    out.visible_chars = len(" ".join(body_el.get_text(" ").split()))
    text = _Markdown(**_MD).convert_soup(soup)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    out.text = text
    return out


def decode_text(body: bytes, content_type: str | None) -> tuple[str, list[str]]:
    warn = []
    cs = charset_of(content_type)
    if body.startswith(codecs.BOM_UTF8):
        cs, body = "utf-8", body[len(codecs.BOM_UTF8):]
    elif body[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        cs = "utf-16"
    for enc in ([cs] if cs else []) + ["utf-8"]:
        try:
            return body.decode(enc), warn
        except (UnicodeDecodeError, LookupError):
            continue
    warn.append("body is not valid UTF-8 and names no charset; decoded as cp1252 with replacements")
    return body.decode("cp1252", errors="replace"), warn


def convert(body: bytes, content_type: str | None, base_url: str) -> Converted:
    kind = kind_of(content_type, body)
    if kind == "pdf":
        from .pdftext import pdf_to_text
        return pdf_to_text(body)
    if kind == "html":
        return html_to_markdown(body, base_url, charset_of(content_type))
    text, warn = decode_text(body, content_type)
    return Converted(kind="text", text=text, warnings=warn, visible_chars=len(text))
