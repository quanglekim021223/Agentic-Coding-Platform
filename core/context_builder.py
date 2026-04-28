import json
import os
from typing import Dict, List, Optional

from .graph_store import GraphStore


def _extract_source(node_info: Dict) -> str:
    """Read exact source bytes for a located node using its byte offsets."""
    try:
        with open(node_info["file"], "rb") as f:
            code = f.read()
        return code[node_info["start_byte"]:node_info["end_byte"]].decode("utf-8")
    except Exception:
        return ""


def build_prompt_context(repo_root: str, target_func: str, mode: str = "impact") -> Dict:
    """
    Query the pre-built graph and produce a location-aware context dict.

    repo_root must contain a .ast-tool/graph.db built by `cli.py build`.
    mode: 'impact' | 'refactor'
    """
    store = GraphStore(repo_root)
    blast = store.query_blast_radius(target_func)
    store.close()

    if blast is None:
        raise ValueError(
            f"Function '{target_func}' not found in graph. "
            f"Run `python cli.py build` first."
        )

    # Load data contracts
    contract = {"before": "Unknown", "after": "Unknown"}
    contract_path = os.path.join(repo_root, "data_contracts.json")
    if os.path.exists(contract_path):
        with open(contract_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if target_func in data:
                    contract = data[target_func]
            except json.JSONDecodeError:
                pass

    target_info = blast["target"]
    all_risk_nodes: List[Dict] = (
        blast["high_risk"] + blast["alias_risk"] + blast["medium_risk"]
    )

    # Attach source code for refactor/debug modes
    target_source = ""
    if mode in ("refactor", "debug"):
        target_source = _extract_source(target_info)

    blast_radius = []
    for node in all_risk_nodes:
        entry = dict(node)
        if mode in ("refactor", "debug"):
            entry["source"] = _extract_source(node)
        blast_radius.append(entry)

    # Files that need editing: target + all high_risk callers
    edit_targets = sorted(set(
        [target_info["file"]]
        + [n["file"] for n in blast["high_risk"]]
        + [n["file"] for n in blast["alias_risk"]]
    ))

    # Legacy callers dict — keeps Jinja2 templates working unchanged
    callers = {
        "high_risk":  sorted(n["name"] for n in blast["high_risk"]),
        "alias_risk": sorted(n["name"] for n in blast["alias_risk"]),
        "medium_risk": sorted(n["name"] for n in blast["medium_risk"]),
        "low_risk": [],
    }

    # source_codes dict for Jinja2 templates
    source_codes: Dict[str, str] = {}
    if mode in ("refactor", "debug"):
        source_codes[target_func] = target_source
        for node in all_risk_nodes:
            source_codes[node["name"]] = node.get("source", "")

    return {
        # New located fields for OpenCode
        "target": {
            "name": target_info["name"],
            "file": target_info["file"],
            "start_line": target_info["start_line"],
            "end_line": target_info["end_line"],
            "source": target_source,
        },
        "blast_radius": blast_radius,
        "edit_targets": edit_targets,
        "data_contract": contract,
        # Legacy fields — Jinja2 templates remain unchanged
        "target_function": target_func,
        "callers": callers,
        "source_codes": source_codes,
    }
