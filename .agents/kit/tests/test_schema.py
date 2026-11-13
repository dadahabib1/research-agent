"""The schema is well formed (V12, C3). Shipped, so a project that changes its schema (a kit file it may
customise, C2) checks it in the kit tests its control-code PR runs (decision 100), instead of every
session checking it on every run.

`schema_problems` below is kitconfig.py's V12 check as it was before it left the runtime (PR #18),
moved unchanged, so nothing it caught is lost.
"""

import re
import sys
import tomllib
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent  # .agents/kit
sys.path.insert(0, str(KIT / "bin"))  # C1 section 2: imports by __file__ under -I

import kitconfig  # noqa: E402
from kitconfig import FILES, SCHEMA_FILE, SCHEMA_VERSION, Problem, value_problems  # noqa: E402

TYPES = {"string", "integer", "float", "boolean", "string-list", "path", "path-list", "glob-list"}
SPEC_FIELDS = ("file", "type", "labels", "doc", "added_in")
FIXED_LISTS = ("control_paths", "labels", "efforts", "claude_models", "codex_models")
NUMBER_TYPES, STRING_TYPES = {"integer", "float"}, {"string", "path"}


def schema_problems(schema: dict) -> list[Problem]:
    """V12, and the schema's version line (C2 section 7)."""
    out = []

    def bad(key, message, valid):
        out.append(Problem(SCHEMA_FILE, key, message, valid))

    version = schema.get("version")
    if schema.get("format") != "config-schema" or not isinstance(version, int):
        bad("", "missing or wrong format/version line", 'format = "config-schema", version = 1')
        return out
    if version > SCHEMA_VERSION:
        bad("", f"version {version} is newer than this validator reads ({SCHEMA_VERSION})",
            f"a kit release whose kitconfig.py reads version {version}")
        return out
    fixed = schema.get("fixed", {})
    if isinstance(fixed, dict):
        for name in FIXED_LISTS:  # V5 and the labels need these; a missing one would switch a rule off
            if not (isinstance(fixed.get(name), list) and all(isinstance(v, str) for v in fixed[name])):
                bad("", f"fixed.{name} is missing or not a list of strings", f"fixed.{name} = [...]")
        if out:
            return out
    labels = set(fixed["labels"]) if isinstance(fixed, dict) else set()
    keys = schema.get("key")
    if not isinstance(keys, dict) or not isinstance(fixed, dict):
        bad("", "[key] and [fixed] must be tables", "the schema's [key] and [fixed] tables")
        return out
    for key, spec in keys.items():
        before = len(out)
        if not isinstance(spec, dict):
            bad(key, "is not a table", f"a table with {', '.join(SPEC_FIELDS)}")
            continue
        missing = [f for f in SPEC_FIELDS if f not in spec]
        if missing:
            bad(key, f"missing {', '.join(missing)}", f"every key has {', '.join(SPEC_FIELDS)}")
            continue
        if not isinstance(spec["file"], str) or spec["file"] not in FILES:
            bad(key, f"file {spec['file']!r} is not project or local", 'file = "project" or "local"')
        type_ok = isinstance(spec["type"], str) and spec["type"] in TYPES
        if not type_ok:
            bad(key, f"type {spec['type']!r} is unknown", f"one of {sorted(TYPES)}")
        tags = spec["labels"]
        if not (isinstance(tags, list) and tags and all(isinstance(t, str) for t in tags) and set(tags) <= labels):
            bad(key, f"labels {tags!r} are not a list from fixed.labels", f"a list from {sorted(labels)}")
        if "choices" in spec and not (isinstance(spec["choices"], str) and isinstance(fixed.get(spec["choices"]), list)):
            bad(key, f"choices {spec['choices']!r} names no list in [fixed]", "the name of a list in [fixed]")
        if "allowed" in spec and not isinstance(spec["allowed"], list):
            bad(key, f"allowed {spec['allowed']!r} is not a list", "a list of values")
        for bound in ("min", "max"):
            if bound in spec and (isinstance(spec[bound], bool) or not isinstance(spec[bound], (int, float))):
                bad(key, f"{bound} {spec[bound]!r} is not a number", "a number")
            elif bound in spec and type_ok and spec["type"] not in NUMBER_TYPES:
                bad(key, f"{bound} on a {spec['type']} setting", f"{bound} only on {sorted(NUMBER_TYPES)}")
        if "pattern" in spec and type_ok and spec["type"] not in STRING_TYPES:
            bad(key, f"pattern on a {spec['type']} setting", f"pattern only on {sorted(STRING_TYPES)}")
        elif "pattern" in spec:
            try:
                re.compile(spec["pattern"])
            except (re.error, TypeError):
                bad(key, f"pattern {spec['pattern']!r} is not a regular expression", "a regular expression")
        if len(out) == before and "default" in spec:  # only a well-formed spec can judge its default
            for message, valid in value_problems(spec, spec["default"], fixed):
                bad(key, f"default {spec['default']!r}: {message}", valid)
    return out


def load_schema():
    with open(KIT / "config/schema.toml", "rb") as f:
        return tomllib.load(f)


class TestSchema(unittest.TestCase):
    def test_schema_is_well_formed(self):
        schema = load_schema()
        self.assertEqual([str(p) for p in schema_problems(schema)], [])
        for name in FIXED_LISTS:  # empty would pass the check above: control_paths = [] protects nothing
            with self.subTest(fixed=name):
                self.assertTrue(schema["fixed"][name])

    def test_a_constraint_written_as_a_string_is_caught(self):  # round 4: "codex, claude" accepts "code"
        schema = load_schema()
        schema["key"]["reviewer.engine"]["allowed"] = "codex, claude"
        self.assertTrue(any("reviewer.engine: allowed" in str(p) for p in schema_problems(schema)))

    def test_a_newer_schema_version_is_refused(self):  # the run-time check (C2 section 7)
        problems = kitconfig.schema_problems({"format": "config-schema", "version": SCHEMA_VERSION + 1})
        self.assertTrue(problems and "newer than this validator reads" in problems[0].message)


if __name__ == "__main__":
    unittest.main()
