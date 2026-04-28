from demo_app.auth import login


def checkout(email: str, password: str) -> str:
    is_logged_in = login(email, password)
    if not is_logged_in:
        return "DENIED"
    return "PAID"
