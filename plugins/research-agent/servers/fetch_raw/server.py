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
`uv run --script`; dependencies are pinned above and locked in server.py.lock.

Start time (issue #61): Claude Code gives a server 30 s to connect unless MCP_TIMEOUT is set, and this
one took 14 to 36 s on a busy machine. Two things keep the handshake short. The libraries' bytecode is
cached in uv's environment, outside the plugin folder, so a start no longer recompiles them; this
package's own modules still write no bytecode, so nothing lands in the plugin folder. And the fetcher
(converter, network and PDF code) is imported on the first tool call, not at start."""

from __future__ import annotations

import os
import sys
from importlib.machinery import PathFinder, SourceFileLoader
from typing import Literal


class _NoBytecodeLoader(SourceFileLoader):
    """Loads a module from source without writing its bytecode."""

    def set_data(self, path, data, *, _mode=0o666):  # the loader writes bytecode only through this
        pass


class _PluginModules:
    """Finds the fetchraw package as usual and loads it with _NoBytecodeLoader: nothing is written
    into the plugin folder, while the libraries cache their bytecode in uv's environment."""

    @staticmethod
    def find_spec(name, path=None, target=None):
        if name != "fetchraw" and not name.startswith("fetchraw."):
            return None
        spec = PathFinder.find_spec(name, path, target)
        if spec is not None and type(spec.loader) is SourceFileLoader:
            spec.loader = _NoBytecodeLoader(spec.loader.name, spec.loader.path)
        return spec


sys.meta_path.insert(0, _PluginModules)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anyio  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from fetchraw import __version__  # noqa: E402

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
    return await anyio.to_thread.run_sync(fetch, url, offset, max_chars, route)


def fetch(url: str, offset: int, max_chars: int, route: str) -> str:
    """The tool's work, in a worker thread. The first call imports the fetcher; Python's import lock
    makes concurrent first calls wait for that one import."""
    from fetchraw.tool import fetch_page

    return fetch_page(url, offset, max_chars, route, os.environ)


if __name__ == "__main__":
    server.run("stdio")
