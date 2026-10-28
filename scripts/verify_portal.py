"""Repeatable HTTP checks for the MДК.05.03 practical assignments.

Usage: python scripts/verify_portal.py ../mdk09-01-samoylov-2026/portal
The application runs against a temporary SQLite database, not the user's data.
"""

import importlib.util
import gc
import json
import sys
import tempfile
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_portal.py PATH_TO_PORTAL")
    portal = Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("conference_portal", portal / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)

    with tempfile.TemporaryDirectory(prefix="mdk05-test-") as temp:
        app.DB = Path(temp) / "test.db"
        app.init_db()
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        checks = []

        def request(method, path, fields=None, cookie=None):
            body = urlencode(fields).encode() if fields is not None else None
            headers = {"Accept": "text/html"}
            if body is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            if cookie:
                headers["Cookie"] = cookie
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            result = {
                "status": response.status,
                "reason": response.reason,
                "headers": dict(response.getheaders()),
                "body": response.read().decode("utf-8", "replace"),
            }
            conn.close()
            return result

        def check(name, expected, response):
            checks.append({"name": name, "expected_status": expected, "actual_status": response["status"], "passed": response["status"] == expected})

        check("Главная страница", 200, request("GET", "/"))
        registration = {"login": "student01", "email": "student01@example.test", "phone": "+79990000000", "password": "ValidPass123"}
        check("Корректная регистрация", 303, request("POST", "/register", registration))
        check("Короткий логин", 400, request("POST", "/register", {**registration, "login": "ab", "email": "short@example.test"}))
        check("Короткий пароль", 400, request("POST", "/register", {**registration, "login": "shortpass", "email": "shortpass@example.test", "password": "1234567"}))
        check("Дублирующийся логин", 400, request("POST", "/register", {**registration, "email": "another@example.test"}))
        invalid_email = request("POST", "/register", {**registration, "login": "bademail", "email": "bad@"})
        check("Некорректная почта bad@", 400, invalid_email)
        wrong_login = request("POST", "/login", {"login": "student01", "password": "WrongPass123"})
        check("Неверный пароль", 401, wrong_login)
        good_login = request("POST", "/login", {"login": "student01", "password": "ValidPass123"})
        check("Корректный вход", 303, good_login)
        cookie = good_login["headers"].get("Set-Cookie", "").split(";", 1)[0]
        check("Личный кабинет после входа", 200, request("GET", "/dashboard", cookie=cookie))

        # The sample request/response is the evidence for practical assignment 2.
        exchange = {
            "request": {
                "method": "POST",
                "path": "/login",
                "headers": {"Accept": "text/html", "Content-Type": "application/x-www-form-urlencoded"},
                "body": "login=student01&password=WrongPass123",
            },
            "response": {
                "status": wrong_login["status"],
                "reason": wrong_login["reason"],
                "headers": {k: v for k, v in wrong_login["headers"].items() if k.lower() in ("content-type", "content-length", "x-content-type-options", "referrer-policy")},
                "body_excerpt": wrong_login["body"].split("<main id=\"main\">", 1)[-1].split("</main>", 1)[0][:500],
            },
        }
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        del server, thread
        gc.collect()

    output = {"system_under_test": "Lipson07/mdk09-01-samoylov-2026, portal/app.py", "scope": "isolated local SQLite test database", "checks": checks, "http_exchange": exchange}
    target = Path(__file__).resolve().parents[1] / "evidence" / "verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{sum(c['passed'] for c in checks)}/{len(checks)} checks passed; evidence: {target}")
    for item in checks:
        if not item["passed"]:
            print(f"DEFECT: {item['name']}: expected {item['expected_status']}, actual {item['actual_status']}")


if __name__ == "__main__":
    main()
