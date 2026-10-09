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
# ]
# ///
"""MCP stdio server: one read-only tool, fetch_raw. Launched by the plugin's .mcp.json with
`uv run --script`; dependencies are pinned above and locked in server.py.lock."""

from __future__ import annotations

import os
import sys
from typing import Literal

sys.dont_write_bytecode = True  # write nothing into the plugin folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anyio  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from fetchraw import __version__  # noqa: E402
from fetchraw.tool import fetch_page  # noqa: E402

DESCRIPTION = """Fetch one URL and return its text without summarising: the page itself, not a model's paraphrase.

Returns a header block, then `--- content ---` and the text:
- status: OK | BLOCKED | ERROR, with the HTTP code; a `reason:` line when not OK.
- final_url, content_type, fetched_at (UTC), sha256 of the body bytes, route, bytes, total_chars, next_offset, warnings.

HTML becomes markdown of the whole visible page (nav, footer and footnotes kept); tables keep every cell,
empty ones included; superscripts are written ^[x] and subscripts _[x]; links are [text](absolute url).
PDFs come back as text per page with `--- page N ---` markers. JSON, XML, CSV and plain text come back as is.

Paging: read long documents in pages by calling again with offset=next_offset until next_offset is none.
BLOCKED means a bot wall, captcha, login or JavaScript-only page: there is no content; log it as a dead end.
route: auto (direct, then Firecrawl if the page is blocked and FIRECRAWL_API_KEY is set), direct, firecrawl."""

server = MCPServer(name="fetch-raw", version=__version__)


@server.tool(
    name="fetch_raw",
    description=DESCRIPTION,
    annotations=ToolAnnotations(title="Raw page fetch", readOnlyHint=True, destructiveHint=False,
                                idempotentHint=True, openWorldHint=True),
    meta={"anthropic/maxResultSizeChars": 110_000},
    structured_output=False,
)
async def fetch_raw(url: str, offset: int = 0, max_chars: int = 40000,
                    route: Literal["auto", "direct", "firecrawl"] = "auto") -> str:
    return await anyio.to_thread.run_sync(fetch_page, url, offset, max_chars, route, os.environ)


if __name__ == "__main__":
    server.run("stdio")
