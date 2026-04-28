from demo_app.checkout import checkout


def submit_order(email: str, password: str) -> str:
    return checkout(email, password)
