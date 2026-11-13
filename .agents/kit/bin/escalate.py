"""The escalation and answer records (contract C8 section 8, C9 section 4; decision 112).

    python -I .agents/kit/bin/escalate.py --ticket <n> --trigger <trigger> --body-file <file>
    python -I .agents/kit/bin/escalate.py answer --escalation <id> --answer <answer> --quote <your words>

**The escalation** `merges/escalation-<id>.md` is the one record per escalation: the review script writes it
at the round cap (C7 section 9), this script for every other trigger, which the orchestrator calls with the
body it wrote. The body file is Markdown: front matter with `headline` and, where they apply, `review`,
`round`, `head`, `verdict`, `holds` and `answers` (each `none` or C9's default when left out), then the
sections `## The choice`, `## Findings`, `## Options`, `## Recommendation`. The script fills `id`, `ticket`,
`trigger`, `by` and `written_at`, checks the shape and writes the record once, through C4 rule 3.

**The answer** `merges/answer-<escalation id>.md` is the orchestrator's account of your words, written once:
`escalation`, `answer` (one of the escalation's `answers`), `headline`, `quote` (verbatim, one line),
`answered_at`. It only releases what a session may do anyway: a `fix` lets the review script run its next
round; it never clears a merge (a known-limitation merge is your `kit merge`, C8 section 1).

Each record is checked twice before it is written: `shape()` below gives the precise refusal (fields, headline
length, section order), then `formats.problems()`, the readers' own check (issue #98). Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I

import formats  # noqa: E402
import kitconfig  # noqa: E402
import workfiles  # noqa: E402

TRIGGERS = ("round-cap", "needs-decision", "paid-or-key", "approach", "high-stakes", "blocked")  # C9 section 4
ANSWERS = ("fix", "defer", "known-limitation", "ask-research", "cancel")
GIVEN = ("headline", "review", "round", "head", "verdict", "holds", "answers")  # from the body file
FIELDS = ("id", "ticket", "trigger", "headline", "by", "review", "round", "head", "verdict", "holds", "answers",
          "written_at")
SECTIONS = ("The choice", "Findings", "Options", "Recommendation")
HEADLINE_LIMIT = 80  # C9 rule 3
KEY = re.compile(r"([a-z][a-z0-9_]*): (.+)")


class Refused(Exception):
    def __init__(self, failed: str, valid: str):
        super().__init__(f"REFUSED (escalate): {failed}. Valid: {valid}. Nothing was written.")


def split(text: str) -> tuple[dict, str]:
    """Flat `key: value` front matter (C9 rule 1) and the body after it; no front matter is ({}, text)."""
    lines = text.removeprefix("﻿").replace("\r\n", "\n").split("\n")
    if lines[0] != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise Refused("the front matter has no closing --- line", "close it") from None
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        m = KEY.fullmatch(line)
        if not m or m.group(1) in fields:
            raise Refused(f"front matter line {line!r} is not one flat key: value", "one key: value per line")
        fields[m.group(1)] = m.group(2).strip()
    return fields, "\n".join(lines[end + 1:])


def headings(body: str) -> list[str]:
    out, fence = [], None
    for line in body.split("\n"):
        f = re.fullmatch(r" {0,3}(`{3,}|~{3,}).*", line)
        if f:
            fence = None if fence and f.group(1)[0] == fence[0] else (fence or f.group(1))
        elif fence is None and line.startswith("## "):
            out.append(line[3:].strip())
    return out


def shape(fields: dict, body: str, need: tuple[str, ...], sections: tuple[str, ...]) -> list[str]:
    """What formats.py would refuse in a record: missing fields, a long headline, sections out of order."""
    found = [f"missing field {k}" for k in need if not fields.get(k)]
    if len(fields.get("headline", "")) >= HEADLINE_LIMIT:
        found.append(f"the headline is {len(fields['headline'])} characters; under {HEADLINE_LIMIT}")
    present, at = headings(body), 0
    for title in sections:
        if title not in present[at:]:
            found.append(f"no ## {title} in its place (the order is {', '.join(sections)})")
            continue
        at = present.index(title, at) + 1
    for chunk in re.split(r"(?m)^## ", body)[1:]:
        title, _, rest = chunk.partition("\n")
        if title.strip() in sections and not rest.strip():
            found.append(f"## {title.strip()} is empty")
    return found


def render(fields: dict, body: str = "") -> str:
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n" + body


def project() -> tuple[Path, Path]:
    """(main checkout, merges folder): the escalation files live in the coordination folder (C4)."""
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise Refused(f"not in a git checkout: {r.stderr.strip()}", "run it from the project")
    main = Path(r.stdout.strip()).parent
    try:
        coordination = main / str(kitconfig.effective(main)["coordination"][0])
    except Exception as e:
        raise Refused("; ".join(str(e).splitlines()), "fix the setting it names (kitconfig.py show)") from None
    return main, coordination / "merges"


def escalate(ticket: int, trigger: str, body_file: Path) -> Path:
    if trigger not in TRIGGERS:
        raise Refused(f"trigger {trigger} is not one of {', '.join(TRIGGERS)}", "a trigger C9 section 4 lists")
    try:
        given, body = split(body_file.read_text(encoding="utf-8"))
    except OSError as e:
        raise Refused(f"the body file cannot be read ({e})", "a readable --body-file") from None
    extra = sorted(set(given) - set(GIVEN))
    if extra:
        raise Refused(f"the body file sets {', '.join(extra)}, which the script fills or C9 does not list",
                      f"front matter with only {', '.join(GIVEN)}")
    answers = [a.strip() for a in given.get("answers", ", ".join(ANSWERS)).split(",") if a.strip()]
    if not answers or any(a not in ANSWERS for a in answers):
        raise Refused(f"answers {given.get('answers')} are not among {', '.join(ANSWERS)}", "a comma-separated list")
    main, merges = project()
    head = given.get("head", "none")
    commit = head if re.fullmatch(r"[0-9a-f]{7,40}", head) else subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=main, capture_output=True, text=True, timeout=60).stdout.strip() or "0000000"
    eid = workfiles.event_id("escalation", ticket, commit)
    fields = {"format": "escalation", "version": 1, "id": eid, "ticket": ticket, "trigger": trigger,
              "headline": given.get("headline", ""), "by": "escalate.py", "review": given.get("review", "none"),
              "round": given.get("round", "none"), "head": head, "verdict": given.get("verdict", "none"),
              "holds": given.get("holds", str(ticket)), "answers": ", ".join(answers),
              "written_at": workfiles.utc_iso()}
    problems = shape(fields, body, FIELDS, SECTIONS)
    if problems:
        raise Refused("; ".join(problems), "the body in C9 section 4's shape")
    path = merges / f"{eid}.md"
    text = render(fields, body.lstrip("\n"))
    if found := formats.problems(text, path.name):  # the readers' check (C8 section 8, issue #98)
        raise Refused("; ".join(found), "the body in C9 section 4's shape, flat front matter values")
    workfiles.write_atomic(path, text)
    return path


def answer(escalation: str, given: str, quote: str) -> Path:
    if not re.fullmatch(r"escalation-[0-9A-Za-z-]+", escalation):
        raise Refused(f"{escalation} is not an escalation id", "the id from merges/escalation-<id>.md")
    _, merges = project()
    source = merges / f"{escalation}.md"
    try:
        esc, _ = split(source.read_text(encoding="utf-8"))
    except OSError:
        raise Refused(f"there is no merges/{escalation}.md", "the id of a written escalation") from None
    allowed = [a.strip() for a in esc.get("answers", "").split(",") if a.strip()]
    if given not in allowed:
        raise Refused(f"answer {given} is not one this escalation offers ({', '.join(allowed)})", "one of those")
    line = quote.strip()  # verbatim (review round 1): inner spaces kept; only the ends a front matter value drops
    if not line or "\n" in line or "\r" in line:
        raise Refused("the quote is empty or more than one line", "your words verbatim, on one line")
    path = merges / f"answer-{escalation}.md"
    if path.exists():
        raise Refused(f"merges/{path.name} exists: an escalation is answered once", "a new escalation")
    fields = {"format": "answer", "version": 1, "escalation": escalation, "answer": given,
              "headline": f"t{esc.get('ticket', '?')} answered: {given}"[:HEADLINE_LIMIT - 1], "quote": line,
              "answered_at": workfiles.utc_iso()}
    problems = shape(fields, "", ("escalation", "answer", "headline", "quote", "answered_at"), ())
    if problems:
        raise Refused("; ".join(problems), "C9 section 4's answer fields")
    text = render(fields)
    if found := formats.problems(text, path.name):  # the readers' check (C8 section 8, issue #98)
        raise Refused("; ".join(found), "C9 section 4's answer fields")
    workfiles.write_atomic(path, text)
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["answer"]:
            ap = argparse.ArgumentParser(prog="escalate.py answer", description="Record your answer once.")
            ap.add_argument("--escalation", required=True)
            ap.add_argument("--answer", required=True, choices=ANSWERS)
            ap.add_argument("--quote", required=True, help="your words verbatim, one line")
            a = ap.parse_args(argv[1:])
            path = answer(a.escalation, a.answer, a.quote)
        else:
            ap = argparse.ArgumentParser(prog="escalate.py", description="Write one escalation record.")
            ap.add_argument("--ticket", type=int, required=True)
            ap.add_argument("--trigger", required=True)
            ap.add_argument("--body-file", type=Path, required=True)
            a = ap.parse_args(argv)
            path = escalate(a.ticket, a.trigger, a.body_file)
    except Refused as r:
        print(r, file=sys.stderr)
        return 1
    print(f"wrote {path.parent.name}/{path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
