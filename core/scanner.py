import os
import subprocess
import hashlib
from pathlib import Path
from typing import List, Tuple

_SKIP_DIRS = {".venv", "venv", "__pycache__", "node_modules", ".git", ".ast-tool"}


def _sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def scan_repo(repo_root: str) -> List[Tuple[str, str]]:
    """
    Discover all .py files under repo_root.
    Uses git ls-files if in a git repo, falls back to recursive glob.
    Returns list of (absolute_filepath, sha256_hash).
    """
    repo_root = os.path.abspath(repo_root)
    results = []

    try:
        output = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()

        if output:
            for rel_path in output.splitlines():
                if not rel_path.endswith(".py"):
                    continue
                abs_path = os.path.join(repo_root, rel_path)
                if os.path.isfile(abs_path):
                    results.append((abs_path, _sha256(abs_path)))
            return results
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    for path in Path(repo_root).rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        abs_path = str(path.resolve())
        results.append((abs_path, _sha256(abs_path)))

    return results
