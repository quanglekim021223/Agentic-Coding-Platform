import re
import tree_sitter_python as tspy
from tree_sitter import Language, Parser
from typing import Dict, List, Tuple
import os

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

    # Keyed by qualified_name when possible, fallback to name.
    nodes: Dict[str, Dict] = {} # Stores every function, method, or class it discovers in the file
    edges: List[Dict] = [] #Tracks the actual "call" (connections) between function
    assignment_alias_map: Dict[str, str] = {} # Local variables aliasing (e.g., "x = self.y")
    import_alias_map: Dict[str, str] = {} # Imports aliasing (e.g., "import os as _os")
    from_import_alias_map: Dict[str, str] = {} # From imports aliasing (e.g., "from os import path as _path")

    BUILTINS = set(dir(__builtins__))
    module_path = os.path.splitext(filepath)[0].replace(os.sep, ".")

    # Exactly extract the actual readble text (source code) from an AST Node.
    # Example: _split_dotted("api.auth.login") returns ["api", "auth", "login"].
    def _text(n) -> str:
        return code[n.start_byte:n.end_byte].decode("utf-8")

    # Helper to split dotted names into parts (e.g. "api.auth.login" -> ["api", "auth", "login"]).
    def _split_dotted(text: str) -> List[str]:
        return [p.strip() for p in text.split(".") if p.strip()]

    #  Constructs the Fully Qualified Name (FQN) of a function to guarantee it is 100% unique across the entire project
    def _build_qualified_name(name: str, class_stack: List[str]) -> str:
        if class_stack:
            return f"{module_path}.{'.'.join(class_stack)}.{name}"
        return f"{module_path}.{name}"

    # Look at a function call in the code and try to guess exactly where that function originated from.
    def _get_root_object(node) -> str:
        """
        Walk an attribute chain to find the root identifier.
        Handles chained calls like self.handler.process() where
        obj_node is itself an attribute node.
        """
        while node is not None and node.type == "attribute":
            node = node.child_by_field_name("object")
        return _text(node) if node else ""

    def _extract_call_target(func_node) -> Dict[str, str]:
        """
        Return target hints:
          - target_name: simple callable name
          - target_qualname: fully-qualified when resolvable
          - target_module_hint: dotted module path hint
          - target_container_hint: class/container hint for self/super calls
          - resolution_confidence: 'high' or 'medium' (medium = local may shadow import)
        """
        result = {
            "target_name": "",
            "target_qualname": "",
            "target_module_hint": "",
            "target_container_hint": "",
            "resolution_confidence": "high",
        }
        if func_node is None:
            return result

        # foo()
        if func_node.type == "identifier":
            called = _text(func_node)
            result["target_name"] = called
            if called in from_import_alias_map:
                fq = from_import_alias_map[called]
                result["target_qualname"] = fq
                parts = _split_dotted(fq)
                if len(parts) > 1:
                    result["target_module_hint"] = ".".join(parts[:-1])
                # FIX 3: local function may shadow the import alias — flag ambiguity
                result["resolution_confidence"] = "medium"
            return result

        # module_or_obj.func()
        if func_node.type == "attribute":
            attr_node = func_node.child_by_field_name("attribute")
            obj_node = func_node.child_by_field_name("object")
            if attr_node:
                result["target_name"] = _text(attr_node)
            if obj_node:
                obj_text = _text(obj_node)
                # imported module alias: import demo_app.auth as auth_mod; auth_mod.login()
                if obj_text in import_alias_map:
                    result["target_module_hint"] = import_alias_map[obj_text]
                    if result["target_name"]:
                        result["target_qualname"] = (
                            f"{result['target_module_hint']}.{result['target_name']}"
                        )
                # FIX 1 & 2: Handle super() with any args, and chained self.x.y() calls
                else:
                    # FIX 1: Check super() by node type, not text (handles super(ClassName, self))
                    if obj_node.type == "call":
                        call_func = obj_node.child_by_field_name("function")
                        if call_func and _text(call_func) == "super":
                            result["target_container_hint"] = "super"
                        # else: some other call expression, fall through to weak hint
                    else:
                        # FIX 2: Walk the full attribute chain to find root object
                        # Handles self.handler.process() where obj_node is an attribute node
                        root = _get_root_object(obj_node)
                        if root == "self":
                            result["target_container_hint"] = "self"
                        elif root == "super":
                            result["target_container_hint"] = "super"
                        else:
                            # FIX 4: Only store as hint if it looks like a valid identifier/dotted path
                            # Prevents arbitrary expressions (e.g. function call results) from
                            # polluting the resolver with misleading module hints
                            if re.match(r'^[a-zA-Z_][\w.]*$', obj_text):
                                result["target_module_hint"] = obj_text
            return result

        return result

    def _parse_import_statement(node):
        """
        Supports:
          import demo_app.auth
          import demo_app.auth as auth_mod
        """
        text = _text(node).replace("import ", "", 1).strip()
        parts = [p.strip() for p in text.split(",") if p.strip()]
        for p in parts:
            if " as " in p:
                mod, alias = [x.strip() for x in p.split(" as ", 1)]
                import_alias_map[alias] = mod
            else:
                # import demo_app.auth => alias demo_app (python semantics)
                top = p.split(".")[0]
                import_alias_map[top] = p

    def _parse_import_from_statement(node):
        """
        Supports:
          from demo_app.auth import login
          from demo_app.auth import login as auth_login
        """
        text = _text(node).strip()
        if not text.startswith("from ") or " import " not in text:
            return
        module = text.split(" import ", 1)[0].replace("from ", "", 1).strip()
        imported_part = text.split(" import ", 1)[1].strip()
        imported_names = [p.strip() for p in imported_part.split(",") if p.strip()]
        for name in imported_names:
            if " as " in name:
                original, alias = [x.strip() for x in name.split(" as ", 1)]
                from_import_alias_map[alias] = f"{module}.{original}"
            else:
                from_import_alias_map[name] = f"{module}.{name}"

    def walk_tree(node, current_func=None, current_class_stack=None):
        if current_class_stack is None:
            current_class_stack = []

        # IMPORTS (used later for deterministic edge resolution)
        if node.type == "import_statement":
            _parse_import_statement(node)
        elif node.type == "import_from_statement":
            _parse_import_from_statement(node)

        # CLASS DEF — update class context stack
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                current_class_stack = current_class_stack + [_text(name_node)]

        # FUNCTION/ASYNC FUNCTION DEF — capture location and metadata
        if node.type in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name('name')
            if name_node:
                func_name = _text(name_node)
                qualified_name = _build_qualified_name(func_name, current_class_stack)
                node_key = qualified_name or func_name
                kind = "async_function" if node.type == "async_function_definition" else (
                    "method" if current_class_stack else "function"
                )
                if node_key not in nodes:
                    nodes[node_key] = {
                        "name": func_name,
                        "qualified_name": qualified_name,
                        "kind": kind,
                        "container": current_class_stack[-1] if current_class_stack else "",
                        "module_path": module_path,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "start_byte": node.start_byte,
                        "end_byte": node.end_byte,
                    }
                current_func = {
                    "name": func_name,
                    "qualified_name": qualified_name,
                    "container": current_class_stack[-1] if current_class_stack else "",
                }

        # ALIAS — same tracking logic as before
        elif node.type == 'assignment':
            left = node.child_by_field_name('left')
            right = node.child_by_field_name('right')
            if left and right and left.type == 'identifier' and right.type == 'identifier':
                alias = _text(left)
                target = _text(right)
                assignment_alias_map[alias] = target

        # FUNCTION CALL — same classification logic as before
        elif node.type == 'call' and current_func:
            func_node = node.child_by_field_name('function')
            target = _extract_call_target(func_node)
            called_func = target["target_name"]
            if not called_func:
                # unknown callable shape, still traverse children
                pass
            elif called_func in assignment_alias_map:
                real_func = assignment_alias_map[called_func]
                if real_func not in BUILTINS:
                    edges.append({
                        "source_name": current_func["name"],
                        "source_qualified_name": current_func["qualified_name"],
                        "target_name": real_func,
                        "target_qualname": "",
                        "target_module_hint": "",
                        "target_container_hint": "",
                        "edge_type": "alias",
                    })
            else:
                if called_func not in BUILTINS:
                    edges.append({
                        "source_name": current_func["name"],
                        "source_qualified_name": current_func["qualified_name"],
                        "target_name": called_func,
                        "target_qualname": target["target_qualname"],
                        "target_module_hint": target["target_module_hint"],
                        "target_container_hint": target["target_container_hint"],
                        "edge_type": "direct",
                    })

        for child in node.children:
            walk_tree(child, current_func, current_class_stack)

    walk_tree(tree.root_node)
    return list(nodes.values()), edges