import tree_sitter_python as tspy
from tree_sitter import Language, Parser
from typing import Dict, List, Tuple

PY_LANGUAGE = Language(tspy.language())


def get_parser():
    parser = Parser()
    parser.language = PY_LANGUAGE
    return parser


def parse_file(filepath: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse a single Python file using Tree-Sitter.

    start_byte, end_byte: The byte offsets of the node in the file. (Useful for exact slicing/rewrite: code[start_byte:end_byte] => exact function source.)
    source_name: the caller function name (where the call happens)
    Example: in checkout.py, if login() calls checkout(), then checkout() is the source_name and login() is the target_name.
    target_name: the called function name (what is being called)
    Same example: target_name = "login"

    Returns:
        nodes: list of dicts with keys
               {name, start_line, end_line, start_byte, end_byte}
        edges: list of dicts with keys
               {source_name, target_name, edge_type}
               edge_type is 'direct' or 'alias'
    """
    with open(filepath, "rb") as f:
        code = f.read()

    parser = get_parser()
    tree = parser.parse(code)

    # Keyed by name to deduplicate nested defs — first occurrence wins
    nodes: Dict[str, Dict] = {}
    edges: List[Dict] = []
    alias_map: Dict[str, str] = {}

    BUILTINS = set(dir(__builtins__))

    def walk_tree(node, current_func=None):
        # FUNCTION DEF — capture location from the AST node
        if node.type == 'function_definition':
            name_node = node.child_by_field_name('name')
            if name_node:
                func_name = code[name_node.start_byte:name_node.end_byte].decode('utf-8')
                if func_name not in nodes:
                    nodes[func_name] = {
                        "name": func_name,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "start_byte": node.start_byte,
                        "end_byte": node.end_byte,
                    }
                current_func = func_name

        # ALIAS — same tracking logic as before
        elif node.type == 'assignment':
            left = node.child_by_field_name('left')
            right = node.child_by_field_name('right')
            if left and right and left.type == 'identifier' and right.type == 'identifier':
                alias = code[left.start_byte:left.end_byte].decode('utf-8')
                target = code[right.start_byte:right.end_byte].decode('utf-8')
                alias_map[alias] = target

        # FUNCTION CALL — same classification logic as before
        elif node.type == 'call' and current_func:
            func_node = node.child_by_field_name('function')
            if func_node and func_node.type == 'identifier':
                called_func = code[func_node.start_byte:func_node.end_byte].decode('utf-8')
                if called_func in alias_map:
                    real_func = alias_map[called_func]
                    if real_func not in BUILTINS:
                        edges.append({
                            "source_name": current_func,
                            "target_name": real_func,
                            "edge_type": "alias",
                        })
                else:
                    if called_func not in BUILTINS:
                        edges.append({
                            "source_name": current_func,
                            "target_name": called_func,
                            "edge_type": "direct",
                        })

        for child in node.children:
            walk_tree(child, current_func)

    walk_tree(tree.root_node)
    return list(nodes.values()), edges