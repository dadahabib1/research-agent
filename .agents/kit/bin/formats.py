"""The role formats' check (contract C9 section 1 rule 5) and the message reader rule (C9 section 3).

    python -I .agents/kit/bin/formats.py check <file or folder> ...   # one line per problem, exit 1
    python -I .agents/kit/bin/formats.py unread <inbox> <read_through or none>

`check` reads every `*.md` under a folder (skipping C4 rule 3's `*.tmp-*` and C7's raw review files under
`reviews/<review id>/`) and prints
`<file>: <problem>: <detail>` for each problem, where the problem is one of `front-matter` (not flat
`key: value` lines between `---` lines, C9 rule 1), `missing-field`, `bad-value` (an unknown format, a
version other than 1, or a message kind or state role C9 does not list), `headline` (80 characters or
more, C9 rule 3), `id` (an event's id that is not its file name, C9 rule 2), `missing-section`,
`section-order` and `end-line` (a message whose last line is not `<!-- end -->`, C9 section 3).

`unread` prints the inbox's complete messages after `read_through`, one per line, then
`read_through: <name>`: the newest name up to which every message is complete. It never passes a message
still being written, so one that sorts earlier but finishes later is listed next time; the messages after
it are listed again too, so a reader acts on a message once by its name.

The formats' one copy is `.agents/kit/templates/` (C9 rule 5); the table below is what this check needs
of them, and `tests/test_formats.py` checks the templates pass it. Standard library only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

END = "<!-- end -->"
HEADLINE_LIMIT = 80  # a headline is under 80 characters (C9 rule 3)
KEY = re.compile(r"([a-z][a-z0-9_]*):(?: (.*))?")
SECTION = re.compile(r"## (.+?)\s*")
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")

# Per format: the fields beyond `format` and `version`, the `## ` sections in order (a trailing `?` marks
# one that may be left out), whether it is an event (`id` is its file name) and whether it is a message
# (the end line). `by` names the field whose value adds fields and sections (`values`); a value not listed
# is a bad value. `c9` marks C9's formats, each of which has a template.
STATE = ("role", "session", "launch_id", "headline", "stage", "waiting_on", "read_through", "handoff_read",
         "steer_ack", "updated_at")
FORMATS: dict[str, dict] = {
    "brief": {"c9": True, "fields": ("headline", "ticket", "issue", "spec", "decisions", "files", "base",
                                     "base_commit", "stacked_on", "lower_base_commit", "effort", "effort_reason",
                                     "effort_lowered_from", "written_at"),
              "sections": ("Issue", "Spec", "Prior art", "Files", "Stacking?", "Stop and ask"),
              "when": {"Stacking": "stacked_on"}},  # required when that field is not none (C9 section 2)
    "message": {"c9": True, "message": True,
                "fields": ("from", "to", "kind", "ticket", "headline", "reply_to", "written_at"), "by": "kind",
                "values": {"ready": {"fields": ("head", "branch", "base_commit", "round", "effort"),
                                     "sections": ("Acceptance", "Evidence", "Red first", "Prior art", "Cuts", "Open")},
                           "blocked": {"sections": ("Missing", "Tried", "Options")},
                           "escalate": {}, "question": {}, "answer": {}, "handoff": {}, "takeover": {},
                           "pr-open": {}, "wake": {}}},
    "escalation": {"c9": True, "event": True,
                   "fields": ("id", "ticket", "trigger", "headline", "by", "review", "round", "head", "verdict",
                              "holds", "answers", "written_at"),
                   "sections": ("The choice", "Findings", "Options", "Recommendation")},
    "answer": {"c9": True, "fields": ("escalation", "answer", "headline", "quote", "answered_at")},
    "handoff": {"c9": True, "event": True,
                "fields": ("id", "session", "launch_id", "role", "ticket", "headline", "reason", "context_percent",
                           "branch", "head", "written_at"),
                "sections": ("Done", "In progress", "Next", "Open questions", "Unanswered messages", "Dropped",
                             "Files touched", "Tried and failed", "Decisions", "Check")},
    "state": {"c9": True, "fields": STATE, "by": "role",
              "values": {"builder": {"fields": ("ticket", "round", "branch", "head", "base_commit"),
                                     "sections": ("Notes",)},
                         "orchestrator": {"fields": ("merges_since_start",),
                                          "sections": ("Tickets", "Waiting sessions reported", "Notes")}}},
    "tasks": {"c9": True, "fields": ("headline", "usage", "updated_at"),
              "sections": ("Needs you", "Working", "In review", "Ready to merge", "Done", "Notices")},
    "probe": {"c9": True, "event": True,
              "fields": ("id", "ticket|topic", "trigger", "headline", "sample", "asked_by", "written_at"),
              "sections": ("Question", "1. Real-use path", "2. Evidence", "3. Cost against harm", "4. Repeats",
                           "Candidate fixes", "Smallest fix")},
    # C9 section 9: the orchestrator's steer file (the guard reads `id` and `action`; issue #107).
    "steer": {"c9": True, "fields": ("id", "action", "headline", "written_at"), "by": "action",
              "values": {"nudge": {}, "halt": {}, "none": {}}},
    # C6 section 7's notices share the folder; notices.py writes them, so they are checked for shape only.
    "notice": {"event": True, "fields": ("id", "kind")},
    "notice-sent": {"fields": ("id", "sent_at")},
}


def front_matter(text: str) -> tuple[dict, str, list[str]]:
    """The front matter's fields, the body after it, and its `front-matter` problems (C9 rule 1)."""
    lines = text.removeprefix("﻿").replace("\r\n", "\n").split("\n")
    if lines[0] != "---":
        return {}, text, ["front-matter: the first line is not ---"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text, ["front-matter: no closing --- line"]
    fields, found = {}, []
    for number, line in enumerate(lines[1:end], 2):
        match = KEY.fullmatch(line)
        if not line.strip():
            continue
        if line[0].isspace() or line.lstrip().startswith("- "):
            found.append(f"front-matter: line {number} is nested; values are flat, one line each")
        elif not match:
            found.append(f"front-matter: line {number} is not key: value")
        elif not (match.group(2) or "").strip():
            found.append(f"front-matter: {match.group(1)} has no value (write none when empty; values do not nest)")
        elif match.group(2).lstrip()[:1] in ("[", "{"):
            found.append(f"front-matter: {match.group(1)} is a nested value; a list is comma-separated")
        elif match.group(1) in fields:
            found.append(f"front-matter: {match.group(1)} appears twice")
        else:
            fields[match.group(1)] = match.group(2).strip()
    return fields, "\n".join(lines[end + 1:]), found


def sections(body: str) -> list[str]:
    """The `## ` headings outside fenced code blocks, in order. A fence closes only on the same character
    at least as long as its opening, with nothing after it (CommonMark), so a `~~~` line of pasted output
    inside a backtick block stays output."""
    out, fence = [], None
    for line in body.split("\n"):
        match = FENCE.fullmatch(line)
        if fence is None and match:
            fence = match.group(1)
        elif fence and match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                and not match.group(2).strip():
            fence = None
        elif fence is None and (heading := SECTION.fullmatch(line)):
            out.append(heading.group(1))
    return out


def problems(text: str, name: str) -> list[str]:
    """`<problem>: <detail>` for each problem in one file's text; `name` is its file name (an event's id)."""
    fields, body, found = front_matter(text)
    if found and not fields:
        return found
    spec = FORMATS.get(fields.get("format", ""))
    if spec is None:
        return found + ["missing-field: format" if "format" not in fields else
                        f"bad-value: format {fields['format']} is not one of {', '.join(FORMATS)}"]
    if fields.get("version") != "1":
        found.append("missing-field: version" if "version" not in fields else
                     f"bad-value: version {fields['version']}; this check reads version 1")
    need, order = list(spec.get("fields", ())), list(spec.get("sections", ()))
    if "by" in spec and spec["by"] in fields:
        value = fields[spec["by"]]
        if value in spec["values"]:
            need += spec["values"][value].get("fields", ())
            order += spec["values"][value].get("sections", ())
        else:
            found.append(f"bad-value: {spec['by']} {value} is not one of {', '.join(spec['values'])}")
    for title, field in spec.get("when", {}).items():
        if fields.get(field, "none") != "none":
            order = [title if w == f"{title}?" else w for w in order]
    for field in need:
        if not any(f in fields for f in field.split("|")):
            found.append(f"missing-field: {field.replace('|', ' or ')}")
    if len(fields.get("headline", "")) >= HEADLINE_LIMIT:
        found.append(f"headline: {len(fields['headline'])} characters; a headline is under {HEADLINE_LIMIT}")
    if spec.get("event") and "id" in fields and fields["id"] != Path(name).stem:
        found.append(f"id: {fields['id']} is not the file name {Path(name).stem}")
    found += order_problems(sections(body), order)
    if spec.get("message") and text.rstrip().rsplit("\n", 1)[-1] != END:
        found.append(f"end-line: the last line is not {END}; the message is still being written, or broken")
    return found


def order_problems(present: list[str], order: list[str]) -> list[str]:
    """Each required section missing, and each one out of order. Other headings may sit anywhere, and a
    title may repeat (an issue quoted verbatim in a brief has its own headings): each section is matched
    at its first heading after the previous section's, so a file whose sections are in order always
    passes, wherever the repeats sit."""
    found, at, previous = [], 0, None
    for wanted in order:
        title, optional = wanted.removesuffix("?"), wanted.endswith("?")
        if title in present[at:]:
            at = present.index(title, at) + 1
            previous = title
        elif title in present and not optional:  # an optional title found only earlier is quoted text
            found.append(f"section-order: ## {title} comes before ## {previous}; the order is "
                         + ", ".join(w.removesuffix("?") for w in order))
        elif not optional:
            found.append(f"missing-section: ## {title}")
    return found


def files(path: Path) -> list[Path]:
    """A folder's Markdown files, less the review script's raw ones: C7's `reviews/<review id>/` holds the rendered
    prompt, the canary's output and the triager's input, none of them a format (issue #107)."""
    if path.is_dir():
        return sorted(p for p in path.rglob("*.md") if ".tmp-" not in p.name and p.is_file()
                      and not _review_raw(path, p.relative_to(path).parts))
    return [path]


def _review_raw(root: Path, parts: tuple[str, ...]) -> bool:
    """`reviews/<review id>/...` under a coordination folder, or `<review id>/...` when the folder checked is
    `reviews/` itself (an inbox of a project named `review-...` is never skipped; PR #108 review r1)."""
    return (len(parts) > 2 and parts[0] == "reviews") or (root.name == "reviews" and len(parts) > 1)


def check(paths: list[Path]) -> tuple[int, list[str]]:
    """The files checked and one `<file>: <problem>: <detail>` line per problem; a folder's files are
    named relative to it."""
    count, lines = 0, []
    for root in paths:
        for path in files(root):
            count += 1
            shown = path.relative_to(root).as_posix() if root.is_dir() else str(path)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                lines.append(f"{shown}: unreadable: {e}")
                continue
            lines += [f"{shown}: {p}" for p in problems(text, path.name)]
    return count, lines


def complete(path: Path) -> bool:
    """C9 section 3: a message is read only when its front matter parses and its last line is the end
    line; any other is still being written, or broken."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fields, _, found = front_matter(text)
    return bool(fields) and not found and text.rstrip().rsplit("\n", 1)[-1] == END


def readable(inbox: Path, read_through: str) -> tuple[list[str], str]:
    """The complete messages after `read_through`, oldest first, and the new `read_through`: the newest
    name up to which every message is complete. It never passes an incomplete one."""
    names = sorted(p.name for p in Path(inbox).glob("*.md") if ".tmp-" not in p.name)
    after = [n for n in names if read_through == "none" or n > read_through]
    done = [n for n in after if complete(Path(inbox) / n)]
    newest = read_through
    for name in after:
        if name not in done:
            break
        newest = name
    return done, newest


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["check"] and len(argv) > 1:
        missing = [a for a in argv[1:] if not Path(a).exists()]
        if missing:
            print(f"no such file or folder: {', '.join(missing)}", file=sys.stderr)
            return 2
        count, lines = check([Path(a) for a in argv[1:]])
        print("\n".join(lines) if lines else f"{count} files checked, no problems")
        return 1 if lines else 0
    if argv[:1] == ["unread"] and len(argv) == 3:
        done, newest = readable(Path(argv[1]), argv[2])
        print("\n".join(done + [f"read_through: {newest}"]))
        return 0
    print("\n".join(__doc__.strip().splitlines()[2:4]), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
