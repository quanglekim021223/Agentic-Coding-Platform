import argparse
import json
import os
import subprocess
import sys

from core.context_builder import build_opencode_context

DEFAULT_MODEL = "ollama/qwen2.5-coder:7b"


# ---------------------------------------------------------------------------
# BUILD command
# ---------------------------------------------------------------------------

def cmd_build(args):
    from core.scanner import scan_repo
    from core.analyzer import parse_file
    from core.graph_store import GraphStore

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"Error: '{repo_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning Python files in '{repo_root}'...")
    files = scan_repo(repo_root)
    print(f"Found {len(files)} Python file(s).")

    store = GraphStore(repo_root)
    parsed = 0
    skipped = 0

    for filepath, sha256 in files:
        if store.is_file_unchanged(filepath, sha256):
            skipped += 1
            continue

        try:
            nodes, edges = parse_file(filepath)
        except Exception as e:
            print(f"  Warning: could not parse {filepath}: {e}", file=sys.stderr)
            continue

        file_id = store.upsert_file(filepath, sha256)

        node_id_map = {}
        for node in nodes:
            nid = store.upsert_node(
                file_id,
                node["name"],
                node["start_line"],
                node["end_line"],
                node["start_byte"],
                node["end_byte"],
            )
            node_id_map[node["name"]] = nid

        for edge in edges:
            source_id = node_id_map.get(edge["source_name"])
            if source_id is not None:
                store.upsert_edge(source_id, edge["target_name"], edge["edge_type"])

        store.commit()
        parsed += 1

    print(f"Parsed {parsed} file(s), skipped {skipped} unchanged.")
    print("Resolving cross-file edges...")
    store.resolve_edges()

    stats = store.stats()
    store.close()

    print(
        f"Graph built: {stats['files']} files, "
        f"{stats['nodes']} functions, "
        f"{stats['edges']} edges "
        f"({stats['resolved_edges']} resolved)."
    )
    print(f"Graph stored at: {os.path.join(repo_root, '.ast-tool', 'graph.db')}")


# ---------------------------------------------------------------------------
# ANALYZE command
# ---------------------------------------------------------------------------

def cmd_analyze(args):
    repo_root = os.path.abspath(args.repo_root)

    print(f"Analyzing '{args.target}' for OpenCode (mode: {args.mode.upper()})...")

    try:
        context = build_opencode_context(repo_root, args.target, args.mode)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2, ensure_ascii=False)
        print(f"Structured OpenCode context written to: {args.output}")
    else:
        print(json.dumps(context, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# REFACTOR command
# ---------------------------------------------------------------------------

def _build_aider_instruction(context: dict) -> str:
    target = context["target"]
    contract = context["data_contract"]
    blast = context["blast_radius"]

    high = [n["name"] for n in blast if n["risk"] == "high"]
    alias = [n["name"] for n in blast if n["risk"] == "alias"]
    medium = [n["name"] for n in blast if n["risk"] == "medium"]

    lines = [
        f"Refactor the function `{target['name']}` to comply with a new data contract.",
        "",
        "DATA CONTRACT CHANGE:",
        f"  - Before: {contract['before']}",
        f"  - After:  {contract['after']}",
        "",
        "BLAST RADIUS (functions that call this function and must be updated):",
    ]
    if high:
        lines.append(f"  - Direct callers (HIGH risk): {', '.join(high)}")
    if alias:
        lines.append(f"  - Alias callers (HIGH risk):  {', '.join(alias)}")
    if medium:
        lines.append(f"  - Indirect callers (MEDIUM):  {', '.join(medium)}")

    lines += [
        "",
        "RULES:",
        "  1. Update `" + target['name'] + "` to match the new contract exactly.",
        "  2. Update ALL direct and alias callers to handle the new return format.",
        "  3. Do NOT modify any function outside the blast radius.",
        "  4. Preserve existing business logic and formatting where possible.",
    ]

    return "\n".join(lines)


def _run_aider(model: str, files: list, instruction: str, dry_run: bool, repo_root: str):
    flags = [
        sys.executable, "-m", "aider",
        "--model", model,
        "--no-git",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--message", instruction,
    ] + files

    if dry_run:
        flags.append("--dry-run")
    else:
        flags.append("--yes")

    subprocess.run(flags, text=True, cwd=repo_root)


def cmd_refactor(args):
    repo_root = os.path.abspath(args.repo_root)
    model = args.model

    print(f"Analyzing blast radius for '{args.target}'...")
    try:
        context = build_opencode_context(repo_root, args.target, mode="refactor")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    edit_targets = context["edit_targets"]
    instruction = _build_aider_instruction(context)

    print(f"\nModel       : {model}")
    print(f"Target func : {context['target']['name']} @ {context['target']['file']} (lines {context['target']['start_line']}-{context['target']['end_line']})")
    print(f"\nFiles to edit ({len(edit_targets)}):")
    for f in edit_targets:
        print(f"  {f}")
    print(f"\nInstruction:\n{'-' * 50}\n{instruction}\n{'-' * 50}")

    print("\n--- DRY RUN: Previewing proposed changes ---")
    _run_aider(model, edit_targets, instruction, dry_run=True, repo_root=repo_root)

    confirm = input("\nApply these changes? (y/n): ").strip().lower()
    if confirm != "y":
        print("Aborted. No files were changed.")
        return

    print("\n--- Applying changes ---")
    _run_aider(model, edit_targets, instruction, dry_run=False, repo_root=repo_root)
    print("\nDone. Rebuild the graph to reflect changes:")
    print("  python cli.py build .")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AST Prompt Compiler: Deterministic context for LLM-assisted editing."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- build ---
    p_build = sub.add_parser("build", help="Scan repo and build the AST graph.")
    p_build.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Root directory of the project (default: current directory)",
    )

    # --- analyze ---
    p_analyze = sub.add_parser(
        "analyze", help="Query the graph and output structured OpenCode context JSON."
    )
    p_analyze.add_argument(
        "-t", "--target", required=True, help="Target function name to analyze."
    )
    """
    impact mode
    Returns: file + line locations only
    No source code attached
    Use when: you want to know what is affected (read-only analysis)

    refactor mode
    Returns: same as impact + full source code of each function
    Use when: you want to pass code to OpenCode/Ollama to actually edit
    """
    p_analyze.add_argument(
        "-m", "--mode",
        choices=["impact", "refactor"],
        required=True,
        help="Strategy mode.",
    )
    p_analyze.add_argument(
        "--repo-root",
        default=".",
        dest="repo_root",
        help="Project root containing .ast-tool/graph.db (default: current directory).",
    )
    p_analyze.add_argument(
        "--output",
        help="Optional JSON output path. If omitted, prints JSON to stdout.",
    )

    # --- refactor ---
    p_refactor = sub.add_parser(
        "refactor",
        help="Analyze blast radius and apply AI-driven refactor via Aider + Ollama.",
    )
    p_refactor.add_argument(
        "-t", "--target", required=True, help="Target function name to refactor."
    )
    p_refactor.add_argument(
        "--repo-root",
        default=".",
        dest="repo_root",
        help="Project root containing .ast-tool/graph.db (default: current directory).",
    )
    p_refactor.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL}).",
    )

    args = parser.parse_args()

    if args.command == "build":
        cmd_build(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "refactor":
        cmd_refactor(args)


if __name__ == "__main__":
    main()
