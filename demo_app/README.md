## demo_app

This package is a minimal multi-file test fixture for the AST graph tool.

- `auth.login` is the target function.
- `checkout.checkout` calls `login` directly.
- `audit.run_audit` calls `login` through alias (`auth_handler = login`).
- `api.submit_order` calls `checkout` and should appear as indirect impact.
