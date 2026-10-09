"""The MCP wiring: start server.py over stdio with the SDK's client, list the tool, call it."""

import re
import sys

import anyio
from conftest import SERVER_DIR

from fetchraw import __version__


def _session_run(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_DIR / "server.py")],
                                   env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})

    async def main():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                return await fn(session, init)

    return anyio.run(main)


def test_tool_listed_with_schema_and_meta():
    async def fn(session, init):
        tools = (await session.list_tools()).tools
        return init, tools

    init, tools = _session_run(fn)
    assert init.server_info.name == "fetch-raw" and init.server_info.version == __version__
    assert [t.name for t in tools] == ["fetch_raw"]
    t = tools[0]
    props = t.input_schema["properties"]
    assert set(props) == {"url", "offset", "max_chars", "route"}
    assert t.input_schema["required"] == ["url"]
    assert props["route"]["enum"] == ["auto", "direct", "firecrawl"]
    assert props["max_chars"]["default"] == 40000 and props["offset"]["default"] == 0
    assert t.meta["anthropic/maxResultSizeChars"] == 110_000
    assert t.annotations.read_only_hint is True


def test_call_refuses_a_private_address_without_network():
    async def fn(session, init):
        r = await session.call_tool("fetch_raw", {"url": "http://127.0.0.1:9/"})
        return r

    r = _session_run(fn)
    text = r.content[0].text
    assert text.startswith("status: ERROR") and "non-public address" in text


def test_versions_agree_with_plugin_manifest():
    import json

    plugin = json.loads((SERVER_DIR.parents[1] / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == __version__


def test_runner_pins_match_server_pins():
    def pins(path):
        head = path.read_text(encoding="utf-8").split("# ///", 2)[1]
        return set(re.findall(r'"([A-Za-z0-9_.-]+==[^"]+)"', head))

    assert pins(SERVER_DIR / "server.py") <= pins(SERVER_DIR / "tests" / "run.py")
