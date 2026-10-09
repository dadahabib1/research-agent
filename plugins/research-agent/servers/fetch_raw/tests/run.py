# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp==2.3.0",
#     "anyio==4.15.1",
#     "httpx==0.28.1",
#     "httpcore==1.0.9",
#     "truststore==0.10.4",
#     "beautifulsoup4==4.15.0",
#     "html5lib==1.1",
#     "markdownify==1.2.3",
#     "pdfplumber==0.11.10",
#     "pdfminer.six==20260107",
#     "pytest==9.1.1",
#     "reportlab==5.0.1",
# ]
# ///
"""Run the tests: `uv run --script tests/run.py` (unit) or `uv run --script tests/run.py -m live` (live)."""

import sys
from pathlib import Path

import pytest

here = Path(__file__).resolve().parent
sys.exit(pytest.main([str(here), "-p", "no:cacheprovider", "-rs", *sys.argv[1:]]))
