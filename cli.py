import argparse
import json
import os
import sys

import pyperclip

from core.context_builder import build_prompt_context
from core.compiler import generate_prompt


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

    print(f"Analyzing '{args.target}' (mode: {args.mode.upper()})...")

    try:
        context = build_prompt_context(repo_root, args.target, args.mode)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        print("\n=== DEBUG CONTEXT ===")
        print(json.dumps(context, indent=2))
        print("=====================\n")

    template_map = {"impact": "impact_analysis", "refactor": "safe_refactor"}
    template_name = template_map[args.mode]

    print("Compiling prompt via Jinja2...")
    try:
        final_prompt = generate_prompt(template_name, context)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n--- PREVIEW PROMPT ---\n")
    print(final_prompt[:1000])
    if len(final_prompt) > 1000:
        print("\n... (truncated)")

    print("\n--- EDIT TARGETS ---")
    for f in context.get("edit_targets", []):
        print(f"  {f}")

    try:
        pyperclip.copy(final_prompt)
        print("\n" + "=" * 50)
        print("Prompt copied to clipboard.")
        print("Open Claude / ChatGPT / OpenCode and paste.")
        print("=" * 50 + "\n")
    except pyperclip.PyperclipException:
        print("\nCould not copy to clipboard. Full prompt:\n")
        print(final_prompt)


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
        "analyze", help="Query the graph and generate a prompt."
    )
    p_analyze.add_argument(
        "-t", "--target", required=True, help="Target function name to analyze."
    )
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
        "--debug", action="store_true", help="Print full context JSON."
    )

    args = parser.parse_args()

    if args.command == "build":
        cmd_build(args)
    elif args.command == "analyze":
        cmd_analyze(args)


if __name__ == "__main__":
    main()
