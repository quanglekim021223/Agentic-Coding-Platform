from demo_app.auth import login


def run_audit(email: str, password: str) -> str:
    auth_handler = login
    ok = auth_handler(email, password)
    if ok:
        return "AUDIT_OK"
    return "AUDIT_FAIL"
