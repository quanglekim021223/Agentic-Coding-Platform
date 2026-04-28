import os
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, StrictUndefined

_env = None

def get_env():
    global _env
    if _env is None:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        templates_dir = os.path.join(root_dir, 'templates')
        _env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined
        )
    return _env

def generate_prompt(template_name, context_dict):
    """
    Nhận Context Dictionary và render ra chuỗi String thông qua Jinja2 template.
    Lớp này đóng vai trò như View Engine trong mô hình MVC.
    """
    env = get_env()
    
    try:
        # Tự động thêm đuôi .j2 nếu người dùng quên gõ
        if not template_name.endswith('.j2'):
            template_name += '.j2'
            
        # Load file template
        template = env.get_template(template_name)
        
        # 3. Đổ dữ liệu (Context) vào Template và kết xuất ra text
        rendered_prompt = template.render(**context_dict)
        return rendered_prompt
        
    except TemplateNotFound:
        templates_dir = env.loader.searchpath[0]
        raise RuntimeError(f"Template '{template_name}' not found in {templates_dir}")
    except Exception as e:
        raise RuntimeError(f"Jinja2 render error: {str(e)}")

# --- ĐOẠN TEST NHANH ---
if __name__ == "__main__":
    # Tạo một Context Dictionary giả lập (giống output của context_builder)
    mock_context = {
        "target_function": "login",
        "data_contract": {
            "before": "bool",
            "after": "dict {'status': 'success/fail', 'user_id': int}"
        },
        "callers": {
            "direct": ["checkout", "wrapper"],
            "indirect": ["internal_audit"],
            "alias": []
        },
        "source_codes": {}
    }
    
    print("=== ĐANG TEST BIÊN DỊCH PROMPT: IMPACT ANALYSIS ===")
    prompt_result = generate_prompt("impact_analysis", mock_context)
    print(prompt_result)