import re


def build_call_graph(file_path):
    graph = {}

    with open(file_path, "r") as f:
        lines = f.readlines()

    current_function = None

    for line in lines:
        # detect function definition
        match = re.match(r"def (\w+)\(", line)
        if match:
            current_function = match.group(1)
            graph[current_function] = set()
            continue  # tránh self-loop

        # detect function calls
        call_match = re.findall(r"(\w+)\(", line)
        if call_match and current_function:
            for func in call_match:
                # filter basic noise
                if func not in ["if", "elif", "for", "while", "range", "print"]:
                    graph[current_function].add(func)

    # convert set -> list
    return {k: list(v) for k, v in graph.items()}


def find_callers(graph, target):
    callers = []

    for func, calls in graph.items():
        if target in calls:
            callers.append(func)

    return callers


if __name__ == "__main__":
    graph = build_call_graph("stress_test_billing.py")

    print("=== CALL GRAPH ===")
    for k, v in graph.items():
        print(f"{k} -> {v}")

    print("\n=== CALLERS OF login ===")
    print(find_callers(graph, "login"))