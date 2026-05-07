"""
MCP stdio server: three tools mapping to `cli.py` build / analyze / refactor.

Run from the repository root:
  python -m mcp_server.main
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from mcp_server.runner import (
    ensure_cli_exists,
    normalize_repo_root,
    repo_root_error_message,
    resolve_cli_path,
    run_cli,
)

mcp = FastMCP("ast-tool")


def _format_failure(proc_label: str, proc) -> str:
    parts = [
        proc_label,
        f"exit_code: {proc.returncode}",
    ]
    if proc.stdout:
        parts.append("--- stdout ---\n" + proc.stdout.rstrip())
    if proc.stderr:
        parts.append("--- stderr ---\n" + proc.stderr.rstrip())
    return "\n\n".join(parts)


@mcp.tool()
def ast_build(repo_root: str) -> str:
    """
    Incrementally rebuild the SQLite call graph (.ast-tool/graph.db) from Python sources.

    Use after cloning or large code changes so analyze/refactor sees up-to-date nodes/edges.
    Writes only under repo_root (.ast-tool/). Safe to run repeatedly.
    """
    root = normalize_repo_root(repo_root)
    err = repo_root_error_message(root)
    if err:
        raise ToolError(err)
    if not root.is_dir():
        raise ToolError(f"repo_root is not a directory: {root}")

    proc = run_cli(["build", str(root)], cwd=root)
    if proc.returncode != 0:
        raise ToolError(_format_failure("ast_build failed", proc))

    msg = proc.stdout.strip() or "(no stdout)"
    if proc.stderr.strip():
        msg += "\n\n--- stderr ---\n" + proc.stderr.strip()
    return msg


@mcp.tool()
def ast_analyze(
    repo_root: str,
    target: str,
    mode: str = "impact",
) -> str:
    """
    Read-only: blast-radius style context for `target` function from the existing graph.

    mode:
      impact   — locations + blast list, no inline source snippets
      refactor — includes source excerpts for downstream editing tools

    Requires a prior successful ast_build on this repo_root.
    """
    if mode not in ("impact", "refactor"):
        raise ToolError("mode must be 'impact' or 'refactor'")

    root = normalize_repo_root(repo_root)
    err = repo_root_error_message(root)
    if err:
        raise ToolError(err)
    if not root.is_dir():
        raise ToolError(f"repo_root is not a directory: {root}")

    proc = run_cli(
        [
            "analyze",
            "-t",
            target,
            "-m",
            mode,
            "--repo-root",
            str(root),
        ],
        cwd=root,
    )
    if proc.returncode != 0:
        raise ToolError(_format_failure("ast_analyze failed", proc))

    text = proc.stdout.strip()
    if not text:
        raise ToolError("ast_analyze produced empty stdout")

    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        raise ToolError(
            _format_failure(
                "ast_analyze stdout was not valid JSON (unexpected CLI output)",
                proc,
            )
        )


@mcp.tool()
def ast_refactor(
    repo_root: str,
    target: str,
    model: str = "ollama/qwen2.5-coder:7b",
    apply_changes: bool = False,
) -> str:
    """
    Run Aider-driven refactor constrained by blast radius and data_contracts.json.

    When apply_changes is false (default for automation): CLI runs with --dry-run only
    (preview, no writes). When true: runs preview then applies without prompting.

    Applying changes modifies source files — only set apply_changes when the user explicitly
    approved. After successful apply, run ast_build again to refresh the graph.
    Requires aider, Ollama, and configured models locally.
    """
    root = normalize_repo_root(repo_root)
    err = repo_root_error_message(root)
    if err:
        raise ToolError(err)
    if not root.is_dir():
        raise ToolError(f"repo_root is not a directory: {root}")

    args = ["refactor", "-t", target, "--repo-root", str(root), "--model", model]
    if apply_changes:
        args.append("--apply")
    else:
        args.append("--dry-run")

    proc = run_cli(args, cwd=root)
    if proc.returncode != 0:
        raise ToolError(_format_failure("ast_refactor failed", proc))

    out = proc.stdout.strip() or "(no stdout)"
    if proc.stderr.strip():
        out += "\n\n--- stderr ---\n" + proc.stderr.strip()
    if apply_changes:
        out += (
            "\n\nNext: run ast_build with the same repo_root to refresh the graph "
            "(e.g. after source edits)."
        )
    return out


def main() -> None:
    ensure_cli_exists(resolve_cli_path())
    mcp.run()


if __name__ == "__main__":
    main()
