# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml==6.0.3",
#     "pytest==9.1.1",
# ]
# ///
"""Run the doctor's tests: `uv run --script tools/tests/run.py`."""

import sys
from pathlib import Path

import pytest

here = Path(__file__).resolve().parent
sys.exit(pytest.main([str(here), "-p", "no:cacheprovider", "-rs", *sys.argv[1:]]))
