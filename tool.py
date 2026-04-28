import re

with open("stress_test_billing.py", "r") as f:
    code = f.read()


def search_function(name):
    pattern = rf"def {name}\(.*?\):([\s\S]*?)(?=\ndef |\Z)"
    match = re.search(pattern, code)
    return match.group(0) if match else None


def search_usage(name):
    lines = code.split("\n")
    results = []

    for i, line in enumerate(lines):
        if f"{name}(" in line and not line.strip().startswith("def"):
            results.append({
                "line": i + 1,
                "code": line.strip()
            })

    return results


def get_function_source(name):
    return search_function(name)


if __name__ == "__main__":
    usages = search_usage("login")

    print("Found usages:")
    for u in usages:
        print(u)