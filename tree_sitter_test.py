import tree_sitter_python as tspy
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspy.language())
parser = Parser()
parser.language = PY_LANGUAGE

def build_graph_with_treesitter(filepath):
    with open(filepath, "rb") as f:
        code = f.read()
    
    tree = parser.parse(code)
    graph = {}
    
    # 🔥 The Symbol Table (Lưu trữ alias)
    alias_map = {}

    def walk_tree(node, current_func=None):
        # 1. BẮT ĐỊNH NGHĨA HÀM
        if node.type == 'function_definition':
            name_node = node.child_by_field_name('name')
            if name_node:
                current_func = code[name_node.start_byte:name_node.end_byte].decode('utf-8')
                if current_func not in graph:
                    graph[current_func] = set()

        # 2. BẮT PHÉP GÁN (ALIAS TRACKING)
        elif node.type == 'assignment':
            left = node.child_by_field_name('left')
            right = node.child_by_field_name('right')

            # Nếu cả 2 vế đều là biến/tên hàm (ví dụ: func = login)
            if left and right and left.type == 'identifier' and right.type == 'identifier':
                alias = code[left.start_byte:left.end_byte].decode('utf-8')
                target = code[right.start_byte:right.end_byte].decode('utf-8')
                alias_map[alias] = target # Lưu vào bộ nhớ

        # 3. BẮT LỜI GỌI HÀM
        elif node.type == 'call' and current_func:
            func_node = node.child_by_field_name('function')
            if func_node and func_node.type == 'identifier':
                called_func = code[func_node.start_byte:func_node.end_byte].decode('utf-8')
                
                # 🔥 RESOLVE ALIAS Ở ĐÂY
                if called_func in alias_map:
                    called_func = alias_map[called_func]

                # Bỏ qua các hàm built-in
                if called_func not in ["if", "elif", "for", "while", "range", "print", "len", "str", "append"]:
                    graph[current_func].add(called_func)

        # 4. Duyệt đệ quy các con
        for child in node.children:
            walk_tree(child, current_func)

    walk_tree(tree.root_node)
    return {k: list(v) for k, v in graph.items()}

def find_callers(graph, target):
    return [func for func, calls in graph.items() if target in calls]

def visualize_graph(graph, output_filename="knowledge_graph.html"):
    try:
        from pyvis.network import Network
    except ImportError:
        print("Vui lòng cài đặt thư viện: pip install pyvis networkx")
        return
        
    # Khởi tạo đồ thị pyvis
    net = Network(height="800px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.barnes_hut(gravity=-3000, spring_length=250) # Tinh chỉnh để các node đỡ bay văng quá xa
    
    # Thêm Node (Hàm) và Edge (Lời gọi)
    for source, targets in graph.items():
        # Node gốc (caller) - Nền xám đậm tối, viền neon cyan. Màu này giúp nổi chữ trắng cực rõ.
        net.add_node(source, label=source, title=source, shape="box", 
                     color={"background": "#1e2124", "border": "#00ffcc", "highlight": {"background": "#0a6c6c", "border": "#ffffff"}}, 
                     font={"size": 20, "face": "monospace", "color": "white"})
        for target in targets:
            # Node đích (callee) - Nền đen ngả hồng tối, viền hồng neon
            net.add_node(target, label=target, title=target, shape="box", 
                         color={"background": "#2a1b24", "border": "#ff0055", "highlight": {"background": "#880e4f", "border": "#ffffff"}}, 
                         font={"size": 20, "face": "monospace", "color": "white"})
            # Thêm mũi tên 'arrows="to"' để thấy rõ flow gọi hàm
            net.add_edge(source, target, color="#aaaaaa", arrows="to")
            
    net.show(output_filename, notebook=False)

if __name__ == "__main__":
    graph = build_graph_with_treesitter("stress_test_billing.py")
    callers = find_callers(graph, "login")
    print(f"=== TẤT CẢ CÁC HÀM GỌI 'login' ===")
    print(callers)

    # Dựng Knowledge Graph
    visualize_graph(graph)