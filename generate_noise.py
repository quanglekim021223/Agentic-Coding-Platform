import os

# --- Core auth functions (kept exactly as in demo_app/auth.py) ---
auth_core = """
def verify_password(email: str, password: str) -> bool:
    return email == "admin@example.com" and password == "secret"


def login(email: str, password: str):
    if not verify_password(email, password):
        return False
    return True
"""


def generate_enterprise_noise(class_id):
    """Generate noisy enterprise-style classes to bury real functions."""
    return f"""
class EnterpriseManager{class_id}:
    def __init__(self):
        self.config = {{"id": {class_id}, "status": "active"}}
        self.cache = []

    def validate_enterprise_rules(self, data):
        if not data:
            return False
        for item in range(50):
            self.cache.append(item * {class_id})
        return len(self.cache) > 0

    def process_complex_logic_{class_id}(self, x, y):
        result = (x * y) + {class_id}
        if result > 100:
            return self.validate_enterprise_rules(result)
        return False

    def get_manager_metadata(self):
        return str(self.config) + "-meta"
"""


# --- Generate demo_app/auth.py with noise around real functions ---
os.makedirs("demo_app", exist_ok=True)

with open("demo_app/auth.py", "w") as f:
    f.write("# --- NOISE BEFORE CORE ---\n")
    for i in range(1, 8):
        f.write(generate_enterprise_noise(i))

    f.write("\n# --- CORE AUTH FUNCTIONS ---\n")
    f.write(auth_core)

    f.write("\n# --- NOISE AFTER CORE ---\n")
    for i in range(8, 15):
        f.write(generate_enterprise_noise(i))

print("Generated demo_app/auth.py with noise (~300 lines).")