#!/usr/bin/env python3
"""
Lightweight analyzer benchmark + gates.

Usage:
  python scripts/benchmark_analyzer.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer import parse_file
from core.graph_store import GraphStore


PATTERN_CASES = [
    ("simple_direct", "def a():\n  b()\ndef b():\n  pass\n", {("a", "b", "direct")}),
    ("alias_assignment", "def b():\n  pass\ndef a():\n  fn=b\n  fn()\n", {("a", "b", "alias")}),
    ("import_attr", "import p.m as m\ndef run():\n  m.login()\n", {("run", "login", "direct")}),
    ("self_method", "class C:\n  def a(self):\n    self.b()\n  def b(self):\n    pass\n", {("a", "b", "direct")}),
    ("super_method", "class P:\n  def b(self): pass\nclass C(P):\n  def a(self):\n    super().b()\n", {("a", "b", "direct")}),
    ("async_call", "async def a():\n  b()\ndef b():\n  pass\n", {("a", "b", "direct")}),
]


def edge_set(edges):
    return {(e["source_name"], e["target_name"], e["edge_type"]) for e in edges}


def run_pattern_benchmark() -> tuple[int, int]:
    passed = 0
    for _, code, expected in PATTERN_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name
        _, edges = parse_file(temp_path)
        got = edge_set(edges)
        if expected.issubset(got):
            passed += 1
    return passed, len(PATTERN_CASES)


def run_resolution_benchmark() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.py").write_text("def login():\n  pass\ndef checkout():\n  login()\n", encoding="utf-8")
        (root / "b.py").write_text("def login():\n  pass\ndef run():\n  login()\n", encoding="utf-8")

        store = GraphStore(str(root))
        for fp in (root / "a.py", root / "b.py"):
            nodes, edges = parse_file(str(fp))
            fid = store.upsert_file(str(fp), "x")
            node_id_map = {}
            for n in nodes:
                nid = store.upsert_node(
                    fid,
                    n["name"],
                    n["start_line"],
                    n["end_line"],
                    n["start_byte"],
                    n["end_byte"],
                    qualified_name=n.get("qualified_name"),
                    kind=n.get("kind"),
                    container=n.get("container"),
                    module_path=n.get("module_path"),
                )
                node_id_map[n.get("qualified_name") or n["name"]] = nid
            for e in edges:
                src_id = node_id_map.get(e.get("source_qualified_name") or e["source_name"])
                if src_id:
                    store.upsert_edge(
                        src_id,
                        e["target_name"],
                        e["edge_type"],
                        target_qualname=e.get("target_qualname"),
                        target_module_hint=e.get("target_module_hint"),
                        target_container_hint=e.get("target_container_hint"),
                    )
        store.commit()
        store.resolve_edges()
        diag = store.query_resolution_diagnostics()
        store.close()
        return diag


def main() -> int:
    pattern_passed, pattern_total = run_pattern_benchmark()
    pattern_rate = pattern_passed / pattern_total if pattern_total else 0.0

    diag = run_resolution_benchmark()
    resolved_rate = (
        diag["resolved_edges"] / diag["total_edges"] if diag["total_edges"] else 0.0
    )

    print("Analyzer benchmark summary")
    print(f"- pattern_pass_rate: {pattern_passed}/{pattern_total} ({pattern_rate:.2%})")
    print(
        f"- edge_resolved_rate: {diag['resolved_edges']}/{diag['total_edges']} ({resolved_rate:.2%})"
    )
    print(f"- confidence_buckets: {diag['resolution_confidence']}")

    # Pass/fail gates (tunable)
    gates = [
        ("pattern_pass_rate >= 80%", pattern_rate >= 0.80),
        ("edge_resolved_rate >= 80%", resolved_rate >= 0.80),
    ]
    failed = [name for name, ok in gates if not ok]
    if failed:
        print("FAILED gates:")
        for f in failed:
            print(f"  - {f}")
        return 1
    print("All benchmark gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
