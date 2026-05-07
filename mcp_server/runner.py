"""
Subprocess bridge to project root `cli.py`.

Environment:
  AST_TOOL_CLI      Absolute path to cli.py (default: <repo>/cli.py next to this package)
  AST_TOOL_PYTHON   Python interpreter (default: sys.executable)
  AST_TOOL_ROOT     Comma-separated absolute path prefixes allowed for repo_root (optional)
  AST_TOOL_TIMEOUT_SEC  Subprocess timeout seconds (default: 900)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_cli_path() -> Path:
    env = os.environ.get("AST_TOOL_CLI", "").strip()
    if env:
        return Path(env).resolve()
    return _package_root() / "cli.py"


def resolve_python() -> str:
    return os.environ.get("AST_TOOL_PYTHON", "").strip() or sys.executable


def timeout_seconds() -> Optional[int]:
    raw = os.environ.get("AST_TOOL_TIMEOUT_SEC", "").strip()
    if not raw:
        return 900
    try:
        return max(1, int(raw))
    except ValueError:
        return 900


def normalize_repo_root(repo_root: str) -> Path:
    p = Path(repo_root).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve(strict=False)


def repo_root_error_message(repo: Path) -> Optional[str]:
    """
    If AST_TOOL_ROOT is set, repo must be equal to or under one of the prefixes.
    Otherwise return None (allowed).
    """
    raw = os.environ.get("AST_TOOL_ROOT", "").strip()
    if not raw:
        return None
    prefixes: List[Path] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            prefixes.append(Path(part).expanduser().resolve(strict=False))
    if not prefixes:
        return None
    try:
        repo_res = repo.resolve(strict=True)
    except OSError:
        return f"repo_root is not a valid directory: {repo}"
    for prefix in prefixes:
        try:
            repo_res.relative_to(prefix)
            return None
        except ValueError:
            continue
    return (
        f"repo_root {repo_res} is not under any AST_TOOL_ROOT prefix: "
        + ", ".join(str(p) for p in prefixes)
    )


def ensure_cli_exists(cli: Path) -> None:
    if not cli.is_file():
        raise FileNotFoundError(f"AST tool cli not found: {cli}")


def run_cli(cli_args: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cli = resolve_cli_path()
    ensure_cli_exists(cli)
    py = resolve_python()
    cmd = [py, str(cli), *cli_args]
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds(),
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Timed out after {timeout_seconds()}s running: {' '.join(cmd)}"
        ) from e
