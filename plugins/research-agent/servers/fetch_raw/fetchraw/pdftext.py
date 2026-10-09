"""PDF text per page, rebuilt from glyph positions with pdfplumber.

Plain extractors (pypdf, pdfminer.six, pdfplumber's extract_text) all merge exponents into the base
number ("3.3 · 10^18" comes out as "3.3 · 1018"). Here each line is built from words on one baseline;
a smaller word that sits above or below that baseline, touching a word of the line, is marked
^[x] (superscript) or _[x] (subscript). Words on different baselines never merge, so stacked table
rows stay apart.
"""

from __future__ import annotations

import io
import logging
from collections import Counter

from .convert import Converted

logging.getLogger("pdfminer").setLevel(logging.ERROR)

WORD_GAP_RATIO = 0.15   # a gap wider than this share of the font size splits two words
SPACE_GAP_RATIO = 0.12  # words split by a font change but closer than this are joined without a space
SMALL_RATIO = 0.85      # a word this much smaller than its line's main size can be a sup/sub
SHIFT_RATIO = 0.2       # ...if its baseline is shifted by at least this share of the main size
TOUCH_RATIO = 0.35      # ...and it touches a word of the line within this share of the main size


def _lines(words: list[dict]) -> list[list[dict]]:
    """Group words by baseline (bottom), with a tolerance of a fifth of the font size."""
    rows: list[dict] = []
    for w in sorted(words, key=lambda w: (w["bottom"], w["x0"])):
        tol = 0.2 * w["size"]
        for r in rows[-4:]:
            if abs(r["bottom"] - w["bottom"]) <= tol and abs(r["size"] - w["size"]) <= 0.15 * max(r["size"], w["size"]):
                r["words"].append(w)
                break
        else:
            rows.append({"bottom": w["bottom"], "size": w["size"], "words": [w]})
    return [r["words"] for r in rows]


def _main_size(line: list[dict]) -> float:
    c = Counter()
    for w in line:
        c[round(w["size"], 1)] += len(w["text"])
    return c.most_common(1)[0][0]


def _attach_scripts(lines: list[list[dict]]) -> list[list[dict]]:
    """Move small, shifted words that touch a word of a bigger line into that line as sup/sub."""
    info = []
    for ln in lines:
        size = _main_size(ln)
        main = [w for w in ln if round(w["size"], 1) == size]
        info.append({"size": size, "top": min(w["top"] for w in main),
                     "bottom": max(w["bottom"] for w in main), "words": ln})
    for small in info:
        for w in list(small["words"]):
            best = None
            for big in info:
                if big is small or w["size"] > SMALL_RATIO * big["size"]:
                    continue
                if not (big["top"] - 0.6 * big["size"] <= w["top"] and w["bottom"] <= big["bottom"] + 0.6 * big["size"]):
                    continue
                shift_up = big["bottom"] - w["bottom"]
                shift_down = w["top"] - big["top"]
                if shift_up >= SHIFT_RATIO * big["size"]:
                    role = "sup"
                elif shift_down >= SHIFT_RATIO * big["size"]:
                    role = "sub"
                else:
                    continue
                touch = TOUCH_RATIO * big["size"]
                if any(-0.5 <= w["x0"] - b["x1"] <= touch or -0.5 <= b["x0"] - w["x1"] <= touch
                       for b in big["words"] if b.get("role") is None):
                    best = (big, role)
                    break
            if best:
                big, role = best
                small["words"].remove(w)
                w = dict(w, role=role)
                big["words"].append(w)
    return [i["words"] for i in info if i["words"]]


def _render(line: list[dict]) -> str:
    size = _main_size([w for w in line if w.get("role") is None] or line)
    parts, prev = [], None
    for w in sorted(line, key=lambda w: w["x0"]):
        t = w["text"]
        if w.get("role") == "sup":
            t = f"^[{t}]"
        elif w.get("role") == "sub":
            t = f"_[{t}]"
        if prev is not None:
            gap = w["x0"] - prev["x1"]
            joined = gap < (TOUCH_RATIO if w.get("role") else SPACE_GAP_RATIO) * size
            parts.append("" if joined else " ")
        parts.append(t)
        prev = w
    return "".join(parts)


def _rotated_runs(chars: list[dict]) -> list[str]:
    """Vertical text (margin stamps, axis labels): one run per column, read along its direction."""
    cols: list[list[dict]] = []
    for c in sorted(chars, key=lambda c: c["x0"]):
        if cols and abs(cols[-1][-1]["x0"] - c["x0"]) <= 0.2 * c["size"]:
            cols[-1].append(c)
        else:
            cols.append([c])
    runs = []
    for col in cols:
        upward = (col[0].get("matrix") or (0, 1))[1] > 0  # rotated 90 degrees counter-clockwise
        col.sort(key=lambda c: -c["bottom"] if upward else c["top"])
        parts, prev = [], None
        for c in col:
            if prev is not None:
                gap = (prev["top"] - c["bottom"]) if upward else (c["top"] - prev["bottom"])
                if gap > WORD_GAP_RATIO * c["size"]:
                    parts.append(" ")
            parts.append(c["text"])
            prev = c
        run = " ".join("".join(parts).split())
        if run:
            runs.append(run)
    return runs


def page_text(page) -> str:
    words = page.extract_words(x_tolerance_ratio=WORD_GAP_RATIO, y_tolerance=1,
                               keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"])
    upright = [w for w in words if w.get("upright", True)]
    lines = _attach_scripts(_lines(upright))
    lines.sort(key=lambda ln: min(w["top"] for w in ln))
    out = [_render(ln) for ln in lines]
    rotated = [c for c in page.chars if not c.get("upright", True)]
    runs = _rotated_runs(rotated)
    if runs:
        out.append("[rotated text] " + " | ".join(runs))
    return "\n".join(out)


def pdf_to_text(body: bytes) -> Converted:
    import pdfplumber

    out = Converted(kind="pdf", text="")
    empty = []
    pages = []
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            t = page_text(page)
            if not t.strip():
                empty.append(i)
            pages.append(f"--- page {i} ---\n{t}")
    out.text = "\n".join(pages) + "\n"
    out.visible_chars = len(out.text)
    out.warnings.append("pdf: text rebuilt from glyph positions; table columns are space-separated; "
                        "superscripts and subscripts are marked from font size and baseline")
    if empty:
        shown = ", ".join(map(str, empty[:20])) + (" ..." if len(empty) > 20 else "")
        out.warnings.append(f"pdf: no text layer on page(s) {shown} (scanned image?); not OCR'd")
    return out
