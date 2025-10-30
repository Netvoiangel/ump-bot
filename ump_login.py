import os, json
import requests
from http.cookiejar import MozillaCookieJar

BASE_URL   = os.getenv("UMP_BASE_URL", "http://ump.piteravto.ru").rstrip("/")
USERNAME   = os.getenv("UMP_USER", "")
PASSWORD   = os.getenv("UMP_PASS", "")
COOKIES_FP = os.getenv("UMP_COOKIES", "ump_cookies.txt")
TOKEN_FP   = os.getenv("UMP_TOKEN_FILE", "ump_token.txt")

def save_token(token: str | None):
    if token:
        with open(TOKEN_FP, "w", encoding="utf-8") as f:
            f.write(token.strip())

def load_token() -> str | None:
    try:
        with open(TOKEN_FP, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None

def make_session():
    s = requests.Session()
    # Подвязываем файл-куки (формат Netscape, совместим с curl)
    s.cookies = MozillaCookieJar(COOKIES_FP)
    try:
        s.cookies.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        pass
    s.headers.update({
        "User-Agent": "UMPClient/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
        "X-Timezone-Offset": "180",
    })
    return s

def login_and_get_cookies(session: requests.Session, username: str, password: str) -> str | None:
    url = f"{BASE_URL}/api/v1/auth/login"
    payload = {"username": username, "password": password}
    r = session.post(url, json=payload, timeout=30)
    r.raise_for_status()

    # 1) сохраняем куки
    session.cookies.save(ignore_discard=True, ignore_expires=True)

    # 2) пытаемся достать JWT (если сервер его возвращает)
    token = None
    # из JSON
    try:
        data = r.json()
        # На практике ключи бывают разными: token / auth / accessToken / data.token
        token = (
            data.get("token") or data.get("auth") or data.get("accessToken")
            or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("token")
        )
    except Exception:
        pass
    # из заголовков (как в вашем трафике)
    token = token or r.headers.get("token") or r.headers.get("auth")

    save_token(token)
    return token

def vehicles_by_number(session: requests.Session, number: str) -> dict:
    url = f"{BASE_URL}/api/v1/map/vehicles"
    params = {"number": str(number)}
    headers = {}
    token = load_token()
    if token:
        headers["auth"] = token
        headers["token"] = token

    r = session.post(url, params=params, json={}, headers=headers, timeout=30)
    # если внезапно 401 — попробуем принудительный релогин (один раз)
    if r.status_code in (401, 403):
        if USERNAME and PASSWORD:
            login_and_get_cookies(session, USERNAME, PASSWORD)
            if load_token():
                headers["auth"] = load_token()
                headers["token"] = load_token()
            r = session.post(url, params=params, json={}, headers=headers, timeout=30)
    r.raise_for_status()

    data = r.json()
    # Нормализация под «ожидаемый» вид
    items = data if isinstance(data, list) else data.get("items") or data.get("data") or [data]
    first = items[0] if items else {}
    lat = first.get("lat") or first.get("latitude") or first.get("y")
    lon = first.get("lon") or first.get("longitude") or first.get("x")
    return {
        "raw": data,
        "ts": (first.get("number") or first.get("name") or first.get("id")),
        "lat": lat, "lon": lon,
        "time": first.get("timestamp") or first.get("time") or first.get("updatedAt"),
        "ok": lat is not None and lon is not None
    }

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        raise SystemExit("Set UMP_USER and UMP_PASS env vars first")

    s = make_session()
    # 1) Логин
    token = login_and_get_cookies(s, USERNAME, PASSWORD)
    print("Login OK. Token found:", bool(token))
    print("Cookies saved to:", COOKIES_FP)

    # 2) Проверка одной машины
    probe_number = os.getenv("UMP_PROBE", "15294")
    res = vehicles_by_number(s, probe_number)
    print(json.dumps(res, ensure_ascii=False, indent=2))
