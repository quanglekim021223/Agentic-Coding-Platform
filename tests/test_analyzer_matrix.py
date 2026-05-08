import os
import tempfile
import unittest
from pathlib import Path

from core.analyzer import parse_file
from core.graph_store import GraphStore


def _edge_set(edges):
    return {
        (
            e.get("source_name", ""),
            e.get("target_name", ""),
            e.get("edge_type", ""),
        )
        for e in edges
    }


class AnalyzerPatternTests(unittest.TestCase):
    def _write_temp(self, code: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        Path(path).write_text(code, encoding="utf-8")
        return path

    def test_pattern_matrix(self):
        # ~20 patterns covering function/method/async/import/attribute behaviors.
        cases = [
            ("simple_direct", "def a():\n  b()\ndef b():\n  return 1\n", {("a", "b", "direct")}),
            ("alias_assignment", "def b():\n  return 1\ndef a():\n  fn = b\n  fn()\n", {("a", "b", "alias")}),
            ("async_definition", "async def a():\n  b()\ndef b():\n  return 1\n", {("a", "b", "direct")}),
            ("from_import", "from x.y import login\ndef run():\n  login()\n", {("run", "login", "direct")}),
            ("from_import_alias", "from x.y import login as l\ndef run():\n  l()\n", {("run", "l", "direct")}),
            ("import_alias_attribute", "import pkg.mod as m\ndef run():\n  m.login()\n", {("run", "login", "direct")}),
            ("self_method", "class C:\n  def a(self):\n    self.b()\n  def b(self):\n    return 1\n", {("a", "b", "direct")}),
            ("super_method", "class P:\n  def b(self):\n    pass\nclass C(P):\n  def a(self):\n    super().b()\n", {("a", "b", "direct")}),
            ("builtin_filtered", "def a():\n  print('x')\n", set()),
            ("two_calls", "def a():\n  b(); c()\ndef b():\n  pass\ndef c():\n  pass\n", {("a", "b", "direct"), ("a", "c", "direct")}),
            ("class_method_extract", "class A:\n  def run(self):\n    return 1\n", set()),
            ("mixed_async_class", "class A:\n  async def run(self):\n    helper()\ndef helper():\n  pass\n", {("run", "helper", "direct")}),
            ("import_multi", "import x.y as y, a.b as b\ndef run():\n  y.f(); b.g()\n", {("run", "f", "direct"), ("run", "g", "direct")}),
            ("from_import_multi", "from m.n import f, g\ndef run():\n  f(); g()\n", {("run", "f", "direct"), ("run", "g", "direct")}),
            ("attribute_unknown_obj", "def run(obj):\n  obj.process()\n", {("run", "process", "direct")}),
            ("alias_chain_local", "def t():\n  pass\ndef run():\n  a=t\n  b=a\n  b()\n", {("run", "a", "alias")}),
            ("decorated_fn", "@dec\ndef run():\n  helper()\ndef helper():\n  pass\n", {("run", "helper", "direct")}),
            ("nested_class_method", "class A:\n  class B:\n    def run(self):\n      helper()\ndef helper():\n  pass\n", {("run", "helper", "direct")}),
            ("relative_from_import", "from .auth import login\ndef run():\n  login()\n", {("run", "login", "direct")}),
            ("method_calls_method", "class S:\n  def a(self):\n    self.b()\n  def b(self):\n    self.c()\n  def c(self):\n    pass\n", {("a", "b", "direct"), ("b", "c", "direct")}),
        ]

        for name, code, expected_subset in cases:
            with self.subTest(name=name):
                path = self._write_temp(code)
                nodes, edges = parse_file(path)
                self.assertTrue(len(nodes) >= 1, f"{name}: expected at least one node")
                got = _edge_set(edges)
                self.assertTrue(
                    expected_subset.issubset(got),
                    f"{name}: expected subset {expected_subset}, got {got}",
                )
                for n in nodes:
                    self.assertIn("qualified_name", n)
                    self.assertIn("kind", n)
                    self.assertIn("container", n)
                    self.assertIn("module_path", n)


class ResolverQualityTests(unittest.TestCase):
    def _mk_repo(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "a.py").write_text(
            "def login():\n  return True\n\ndef checkout():\n  login()\n",
            encoding="utf-8",
        )
        (root / "b.py").write_text(
            "def login():\n  return False\n\ndef run():\n  login()\n",
            encoding="utf-8",
        )
        return tmp, root

    def test_same_file_resolution_preferred(self):
        tmp, root = self._mk_repo()
        try:
            store = GraphStore(str(root))
            for file in ("a.py", "b.py"):
                path = str(root / file)
                nodes, edges = parse_file(path)
                fid = store.upsert_file(path, "x")
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
                    src = e.get("source_qualified_name") or e["source_name"]
                    src_id = node_id_map.get(src)
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
            self.assertGreaterEqual(diag["resolved_edges"], 2)
            self.assertIn("high", diag["resolution_confidence"])
            store.close()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
