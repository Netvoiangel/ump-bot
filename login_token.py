# login_token.py
import json, requests
from http.cookiejar import MozillaCookieJar
from config import UMP_BASE_URL, UMP_USER, UMP_PASS, UMP_COOKIES_FILE, UMP_TOKEN_FILE, REQUEST_TIMEOUT

def login_and_save():
    if not UMP_USER or not UMP_PASS:
        raise SystemExit("Set UMP_USER and UMP_PASS in .env to use auto-login")

    s = requests.Session()
    s.cookies = MozillaCookieJar(UMP_COOKIES_FILE)
    s.headers.update({
        "User-Agent": "UMPClient/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": UMP_BASE_URL,
        "Referer": f"{UMP_BASE_URL}/",
    })
    r = s.post(f"{UMP_BASE_URL}/api/v1/auth/login",
               json={"username": UMP_USER, "password": UMP_PASS},
               timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    s.cookies.save(ignore_discard=True, ignore_expires=True)

    token = None
    try:
        data = r.json()
        token = data.get("token") or data.get("auth") or data.get("accessToken")
        if not token and isinstance(data.get("data"), dict):
            token = data["data"].get("token")
    except Exception:
        pass
    token = token or r.headers.get("token") or r.headers.get("auth")
    if not token:
        raise RuntimeError("Login ok but no token in response")

    with open(UMP_TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token.strip())

    print("Login OK. Token saved to", UMP_TOKEN_FILE, "Cookies ->", UMP_COOKIES_FILE)

if __name__ == "__main__":
    login_and_save()
