# MCP server (`ast-tool`)

Exposes three tools that wrap the project CLI ([`cli.py`](../cli.py)):

| Tool | CLI | Writes |
|------|-----|--------|
| `ast_build` | `build <repo_root>` | Yes (SQLite under `.ast-tool/`) |
| `ast_analyze` | `analyze -t … -m impact\|refactor --repo-root …` | No |
| `ast_refactor` | `refactor …` with `--dry-run` (default) or `--apply` | Only if `apply_changes=true` |

`ast_refactor` defaults to **`--dry-run`** (preview only). Set MCP argument `apply_changes` to **`true`** only after explicit human approval — it skips the CLI confirmation prompt.

## Install

From the repo root (use the same interpreter as your MCP client, often a venv):

```bash
pip install -r requirements.txt
```

## Run locally (stdio)

The MCP SDK starts a stdio transport when you run:

```bash
python -m mcp_server.main
```

Run this command with **working directory = repository root**, or set `AST_TOOL_CLI` (see below).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AST_TOOL_CLI` | Absolute path to `cli.py` (optional; defaults to sibling of `mcp_server/`) |
| `AST_TOOL_PYTHON` | Python to run `cli.py` (optional; defaults to `sys.executable`) |
| `AST_TOOL_ROOT` | Comma-separated allowed absolute path prefixes for `repo_root` (optional sandbox) |
| `AST_TOOL_TIMEOUT_SEC` | Subprocess timeout seconds (default: `900`) |

## Cursor (example)

In Cursor MCP settings, add a server definition similar to:

```json
{
  "mcpServers": {
    "ast-tool": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "mcp_server.main"],
      "cwd": "/absolute/path/to/this/repo",
      "env": {
        "AST_TOOL_CLI": "/absolute/path/to/this/repo/cli.py"
      }
    }
  }
}
```

Adapt keys/layout to match your Cursor MCP config format/version.

## Claude Code / Claude Desktop

Use the same `command`, `args`, `cwd`, and `env` pattern as above in that product’s MCP server configuration UI or JSON — refer to Anthropic docs for exact schema.

## After `apply_changes=true`

Reminder text is appended by the MCP tool response; equivalently:

```bash
python cli.py build <repo_root>
```
