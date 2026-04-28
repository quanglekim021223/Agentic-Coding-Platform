import os
import sqlite3
from typing import Dict, List, Optional

DB_DIR = ".ast-tool"
DB_FILENAME = "graph.db"


def _get_db_path(repo_root: str) -> str:
    db_dir = os.path.join(repo_root, DB_DIR)
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, DB_FILENAME)


class GraphStore:
    def __init__(self, repo_root: str):
        self.repo_root = os.path.abspath(repo_root)
        self.db_path = _get_db_path(self.repo_root)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id      INTEGER PRIMARY KEY,
                path    TEXT UNIQUE NOT NULL,
                sha256  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nodes (
                id          INTEGER PRIMARY KEY,
                file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                start_line  INTEGER NOT NULL,
                end_line    INTEGER NOT NULL,
                start_byte  INTEGER NOT NULL,
                end_byte    INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                id                INTEGER PRIMARY KEY,
                source_node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                target_name       TEXT NOT NULL,
                resolved_node_id  INTEGER REFERENCES nodes(id),
                edge_type         TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_name   ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(resolved_node_id);
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def is_file_unchanged(self, filepath: str, sha256: str) -> bool:
        row = self.conn.execute(
            "SELECT sha256 FROM files WHERE path = ?", (filepath,)
        ).fetchone()
        return row is not None and row["sha256"] == sha256

    def upsert_file(self, filepath: str, sha256: str) -> int:
        """Insert or replace a file record and wipe its stale nodes."""
        existing = self.conn.execute(
            "SELECT id FROM files WHERE path = ?", (filepath,)
        ).fetchone()

        if existing:
            file_id = existing["id"]
            self.conn.execute("DELETE FROM nodes WHERE file_id = ?", (file_id,))
            self.conn.execute(
                "UPDATE files SET sha256 = ? WHERE id = ?", (sha256, file_id)
            )
        else:
            cur = self.conn.execute(
                "INSERT INTO files (path, sha256) VALUES (?, ?)", (filepath, sha256)
            )
            file_id = cur.lastrowid

        return file_id

    def upsert_node(
        self,
        file_id: int,
        name: str,
        start_line: int,
        end_line: int,
        start_byte: int,
        end_byte: int,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO nodes
               (file_id, name, start_line, end_line, start_byte, end_byte)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (file_id, name, start_line, end_line, start_byte, end_byte),
        )
        return cur.lastrowid

    def upsert_edge(self, source_node_id: int, target_name: str, edge_type: str):
        self.conn.execute(
            """INSERT INTO edges (source_node_id, target_name, edge_type)
               VALUES (?, ?, ?)""",
            (source_node_id, target_name, edge_type),
        )

    def commit(self):
        self.conn.commit()

    # ------------------------------------------------------------------
    # Cross-file resolution
    # ------------------------------------------------------------------

    def resolve_edges(self):
        """
        For every unresolved edge, look up target_name in the nodes table.
        Prefer the first match (same-file calls will usually be the only match).
        """
        unresolved = self.conn.execute(
            "SELECT id, target_name FROM edges WHERE resolved_node_id IS NULL"
        ).fetchall()

        for edge in unresolved:
            match = self.conn.execute(
                "SELECT id FROM nodes WHERE name = ? LIMIT 1",
                (edge["target_name"],),
            ).fetchone()
            if match:
                self.conn.execute(
                    "UPDATE edges SET resolved_node_id = ? WHERE id = ?",
                    (match["id"], edge["id"]),
                )

        self.conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_blast_radius(self, target_func_name: str) -> Optional[Dict]:
        """
        Find the target function and compute its blast radius.
        Returns a dict with target + high_risk / alias_risk / medium_risk lists,
        each entry carrying full file+line location data.
        Returns None if target function is not found in the graph.
        """
        target_row = self.conn.execute(
            """SELECT n.id, n.name, n.start_line, n.end_line, n.start_byte, n.end_byte,
                      f.path AS filepath
               FROM nodes n
               JOIN files f ON n.file_id = f.id
               WHERE n.name = ?
               LIMIT 1""",
            (target_func_name,),
        ).fetchone()

        if not target_row:
            return None

        target_id = target_row["id"]

        high_risk_rows = self.conn.execute(
            """SELECT DISTINCT n.id, n.name, n.start_line, n.end_line,
                               n.start_byte, n.end_byte, f.path AS filepath
               FROM edges e
               JOIN nodes n ON e.source_node_id = n.id
               JOIN files f ON n.file_id = f.id
               WHERE e.resolved_node_id = ? AND e.edge_type = 'direct'""",
            (target_id,),
        ).fetchall()

        alias_risk_rows = self.conn.execute(
            """SELECT DISTINCT n.id, n.name, n.start_line, n.end_line,
                               n.start_byte, n.end_byte, f.path AS filepath
               FROM edges e
               JOIN nodes n ON e.source_node_id = n.id
               JOIN files f ON n.file_id = f.id
               WHERE e.resolved_node_id = ? AND e.edge_type = 'alias'""",
            (target_id,),
        ).fetchall()

        high_risk_ids = {r["id"] for r in high_risk_rows}
        alias_risk_ids = {r["id"] for r in alias_risk_rows}

        medium_risk_rows = []
        if high_risk_ids:
            placeholders = ",".join("?" * len(high_risk_ids))
            candidates = self.conn.execute(
                f"""SELECT DISTINCT n.id, n.name, n.start_line, n.end_line,
                                   n.start_byte, n.end_byte, f.path AS filepath
                    FROM edges e
                    JOIN nodes n ON e.source_node_id = n.id
                    JOIN files f ON n.file_id = f.id
                    WHERE e.resolved_node_id IN ({placeholders})""",
                list(high_risk_ids),
            ).fetchall()
            for row in candidates:
                if (
                    row["id"] != target_id
                    and row["id"] not in high_risk_ids
                    and row["id"] not in alias_risk_ids
                ):
                    medium_risk_rows.append(row)

        def _to_dict(row, risk: str) -> Dict:
            return {
                "id": row["id"],
                "name": row["name"],
                "file": row["filepath"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "start_byte": row["start_byte"],
                "end_byte": row["end_byte"],
                "risk": risk,
            }

        return {
            "target": {
                "id": target_row["id"],
                "name": target_row["name"],
                "file": target_row["filepath"],
                "start_line": target_row["start_line"],
                "end_line": target_row["end_line"],
                "start_byte": target_row["start_byte"],
                "end_byte": target_row["end_byte"],
            },
            "high_risk": sorted(
                [_to_dict(r, "high") for r in high_risk_rows], key=lambda x: x["name"]
            ),
            "alias_risk": sorted(
                [_to_dict(r, "alias") for r in alias_risk_rows], key=lambda x: x["name"]
            ),
            "medium_risk": sorted(
                [_to_dict(r, "medium") for r in medium_risk_rows], key=lambda x: x["name"]
            ),
        }

    def stats(self) -> Dict:
        files = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        nodes = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        resolved = self.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE resolved_node_id IS NOT NULL"
        ).fetchone()[0]
        return {
            "files": files,
            "nodes": nodes,
            "edges": edges,
            "resolved_edges": resolved,
        }

    def close(self):
        self.conn.close()
