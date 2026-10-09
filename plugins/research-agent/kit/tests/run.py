# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pytest==9.1.1",
# ]
# ///
"""Run the drift tool's tests: `uv run --script kit/tests/run.py`."""

import sys
from pathlib import Path

import pytest

here = Path(__file__).resolve().parent
sys.exit(pytest.main([str(here), "-p", "no:cacheprovider", "-rs", *sys.argv[1:]]))
