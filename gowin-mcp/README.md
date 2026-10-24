# Gowin MCP 0.5.1

Dependency-free Python stdio MCP server for the Windows Gowin EDA toolchain.
See the [repository README](../README.md) for configuration, all 11 tools,
the persistent-build workflow, evidence semantics and limitations.

Runtime: Python 3.10+, no pip packages. Set absolute `GOWIN_HOME` and explicit
semicolon-separated `GOWIN_ALLOWED_ROOTS` in the MCP client's environment.
Version 0.5.1 removes machine-specific default directories from 0.5.0;
existing installations must now configure both variables.

Run the complete test suite from the repository root:

```powershell
python -m unittest discover -s gowin-mcp/tests -v
```

The server uses newline-delimited JSON-RPC over stdin/stdout. Tool-result JSON
is ASCII escaped on this boundary so Unicode evidence does not break Windows
MCP proxies. JSON decoding restores Unicode. No HTTP listener is started.

Production builds require a separately installed, licensed Gowin EDA. Tests
use fake processes and synthetic reports. The server intentionally provides
no hardware programming or arbitrary command-execution endpoint.
