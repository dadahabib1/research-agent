import copy
import io
import json
import re

import pytest
from bs4 import BeautifulSoup
from conftest import fixture_bytes, in_order_missing, numeric_tokens

from fetchraw.convert import _is_hidden, convert, html_to_markdown

BASE = "https://example.com/en/pricing/page.php"
BLOCKS = {"p", "div", "td", "th", "tr", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section",
          "article", "header", "footer", "nav", "main", "ul", "ol", "sup", "sub", "caption", "thead",
          "tbody", "tfoot", "aside", "figure", "figcaption", "hr", "dt", "dd"}


def visible_reference(raw: bytes) -> list[str]:
    """Numeric tokens of the visible text, joined as a browser joins inline runs."""
    soup = BeautifulSoup(raw, "html5lib")
    for t in soup(["script", "style", "template", "title"]):
        t.decompose()
    for t in soup.find_all(True):
        if not getattr(t, "decomposed", False) and _is_hidden(t):
            t.decompose()
    for t in soup.find_all(BLOCKS):
        t.insert_before(" ")
        t.insert_after(" ")
    return re.findall(r"\d+(?:[.,:]\d+)*", soup.get_text(""))


def md_rows(text: str) -> list[int]:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and not ("---" in s and re.fullmatch(r"\|[\s:|-]+\|", s)):
            rows.append(len(re.findall(r"(?<!\\)\|", s)) - 1)
    return rows


def html_rows(raw: bytes) -> list[int]:
    soup = BeautifulSoup(raw, "html5lib")
    return [sum(int(c.get("colspan", 1)) for c in tr.find_all(["td", "th"], recursive=False))
            for tr in soup.find_all("tr")]


@pytest.mark.parametrize("name", ["sup_table.html", "footer_footnotes.html", "tenk_table.html"])
def test_every_visible_number_survives_in_order(name):
    raw = fixture_bytes(name)
    out = html_to_markdown(raw, BASE).text
    ref = visible_reference(raw)
    assert ref, "fixture has numbers"
    assert in_order_missing(ref, numeric_tokens(out)) == []


def test_superscripts_and_subscripts_are_marked():
    out = html_to_markdown(fixture_bytes("sup_table.html"), BASE).text
    for s in ["Monthly Volume (shares)^[1,7]", "USD 0.00056^[5]", "USD 0.00^[2]", "USD 0.35^[12]",
              "1% of Trade Value^[4,8]", "IB SmartRouting^[SM]", "H_[2]O", "12 m^[2]", "^[1] Tiers follow"]:
        assert s in out, s
    # the failure this replaces: superscripts merged into the number
    assert "0.000565" not in out and "USD 0.002" not in out


@pytest.mark.parametrize("name", ["sup_table.html", "footer_footnotes.html", "tenk_table.html"])
def test_table_cell_counts_kept(name):
    raw = fixture_bytes(name)
    assert md_rows(html_to_markdown(raw, BASE).text) == html_rows(raw)


def test_tenk_table_keeps_empty_cells_dashes_and_pipes():
    out = html_to_markdown(fixture_bytes("tenk_table.html"), BASE).text
    assert "| Net sales | $ | 416,161 |  | $ | 391,035 |" in out
    assert "| Other income/(expense), net |  | — |  |  | (269) |" in out
    assert "| Effective tax rate |  | 15.6 | % |  | 24.1 % |" in out
    assert r"| Shares used, a \| b split |" in out
    assert "|  | Years ended | | |" in out  # colspan=3 keeps three separators
    assert "fasb.org" not in out  # the hidden ix:header block


def test_footer_footnotes_nav_kept_and_hidden_dropped():
    conv = html_to_markdown(fixture_bytes("footer_footnotes.html"), "https://www.example-exchange.com/markets/hours")
    out = conv.text
    assert "** Each market will close early at 1:00 p.m. (1:15 p.m. for eligible options) on Monday, July 3, 2028." in out
    assert "*** Each market will close early at 1:00 p.m. (1:15 p.m. for eligible options) on Friday, November 27, 2026." in out
    assert "[Holidays & Trading Hours](https://www.example-exchange.com/markets/hours-calendars)" in out
    for hidden in ["77.7", "66.6", "55.5", "12345", "July 3, 2026"]:
        assert hidden not in out, hidden
    assert any("hidden element" in w for w in conv.warnings)


def test_links_absolute_and_inline_images_omitted():
    raw = (b'<html><head><base href="https://cdn.example.org/docs/"></head><body>'
           b'<a href="a/b.html" title="tip">rel</a> <a href="javascript:void(0)">js</a> '
           b'<img alt="chart" src="data:image/png;base64,AAAA"> <img alt="logo" src="/l.png"></body></html>')
    out = html_to_markdown(raw, BASE).text
    assert "[rel](https://cdn.example.org/docs/a/b.html)" in out
    assert "tip" not in out
    assert "js" in out and "javascript:" not in out
    assert "data:(inline image omitted)" in out and "AAAA" not in out
    assert "![logo](https://cdn.example.org/l.png)" in out


def test_charset_from_header_and_meta():
    body = "<p>Prix : 12,50 €</p>".encode("cp1252")
    assert "12,50 €" in convert(body, "text/html; charset=windows-1252", BASE).text
    body2 = '<meta charset="iso-8859-1"><p>Café 3½</p>'.encode("latin-1")
    assert "Café 3½" in convert(body2, "text/html", BASE).text


@pytest.mark.parametrize("ctype,body", [
    ("application/json", json.dumps({"rate": 0.00056, "note": "x^2"}, indent=1).encode()),
    ("text/csv", b"date,close\n2028-07-03,101.25\n"),
    ("application/xml", b"<?xml version='1.0'?><r><v>4.91</v></r>"),
    ("text/plain; charset=utf-8", "line 1\n  41.0 · 10^18\n".encode()),
])
def test_text_formats_returned_as_is(ctype, body):
    conv = convert(body, ctype, BASE)
    assert conv.kind == "text" and conv.text == body.decode("utf-8")


# ---------- PDF ----------

@pytest.fixture(scope="module")
def sample_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))

    def line(y, runs):
        x = 72
        for text, size, rise in runs:
            t = c.beginText(x, y + rise)
            t.setFont("Helvetica", size)
            t.textOut(text)
            c.drawText(t)
            x += c.stringWidth(text, "Helvetica", size)

    line(700, [("Our big model achieves a BLEU score of 41.0, and 28.4 on the second task.", 10, 0)])
    line(680, [("Training cost 3.3 · 10", 10, 0), ("18", 6.5, 4), (" FLOPs, versus 2.3 · 10", 10, 0),
               ("19", 6.5, 4), (" for the big model.", 10, 0)])
    line(660, [("Water is H", 10, 0), ("2", 6.5, -2), ("O and the rate is 0.00056 per share.", 10, 0)])
    # a dense two-row table whose columns sit close together
    for y, row in [(630, ["4", "128", "5.00", "25.5"]), (618, ["16", "32", "4.91", "25.8"])]:
        for x, cell in zip([72, 100, 130, 160], row):
            c.setFont("Helvetica", 8)
            c.drawString(x, y, cell)
    c.showPage()
    line(700, [("Page two: total 1,234.56 and −0.75 (negative).", 10, 0)])
    c.save()
    return buf.getvalue()


def test_pdf_pages_decimals_and_exponents(sample_pdf):
    conv = convert(sample_pdf, "application/pdf", "https://example.org/p.pdf")
    out = conv.text
    assert conv.kind == "pdf"
    assert "--- page 1 ---" in out and "--- page 2 ---" in out
    assert "41.0," in out and "28.4" in out and "0.00056" in out and "1,234.56" in out
    assert "3.3 · 10^[18] FLOPs" in out and "2.3 · 10^[19]" in out
    assert "H_[2]O" in out
    assert not re.search(r"\b\d+ \.\d+", out), "a decimal was split"
    assert "4 128 5.00 25.5" in out and "16 32 4.91 25.8" in out  # stacked rows stay apart
    assert "1018" not in out and "5.004.91" not in out


def test_pdf_page_without_text_is_flagged():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(100, 100, 50, 50)
    c.showPage()
    c.save()
    conv = convert(buf.getvalue(), "application/pdf", "https://example.org/scan.pdf")
    assert any("no text layer on page(s) 1" in w for w in conv.warnings)


def test_reference_helper_is_not_vacuous():
    raw = fixture_bytes("sup_table.html")
    ref = visible_reference(copy.copy(raw))
    assert "0.00056" in ref and "5" in ref and "22.40" in ref
