import random

# Các hàm gốc của bạn
func_def = """
def login(username, password):
    user = get_user(username)
    if not user:
        return False
    return validate_password(user, password)

def get_user(username):
    return {"username": username, "password": "hashed_pw"}

def validate_password(user, password):
    return password == user["password"]

def process_payment(amount):
    if amount <= 0:
        return False
    return True
"""

usage_1 = """
def checkout():
    if login("admin", "123"):
        process_payment(100)
"""

usage_2 = """
# hidden usage 
def internal_audit():
    for i in range(1):
        login("audit", "log")
"""

usage_3 = """
# indirect call 
def wrapper():
    func = login
    func("wrapped", "123")
"""

usage_4 = """
# dead code 
def unused_function():
    login("ghost", "000")
"""

def generate_enterprise_noise(class_id):
    """Tạo ra các class rác mang phong cách enterprise rối rắm"""
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

# Lắp ráp file
with open("stress_test_billing.py", "w") as f:
    f.write("# --- CORE DEFINITIONS ---\n")
    f.write(func_def)
    
    # Chèn 200 dòng rác
    for i in range(1, 15):
        f.write(generate_enterprise_noise(i))
        
    f.write("\n# --- USAGE 1 & 2 ---\n")
    f.write(usage_1)
    f.write(usage_2)
    
    # Chèn thêm 300 dòng rác nữa
    for i in range(15, 35):
        f.write(generate_enterprise_noise(i))
        
    f.write("\n# --- USAGE 3 ---\n")
    f.write(usage_3)
    
    # Chèn thêm rác trước khi kết thúc
    for i in range(35, 50):
        f.write(generate_enterprise_noise(i))
        
    f.write("\n# --- USAGE 4 ---\n")
    f.write(usage_4)

print("Đã tạo xong file stress_test_billing.py (~800 dòng)!")