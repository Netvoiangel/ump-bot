# otbivka.py
import os, json, re, math, requests
from typing import Optional, List, Tuple, Dict
from ..domain.park import Park
from ..config import (
    UMP_BASE_URL,
    UMP_TOKEN_FILE,
    PARKS_FILE,
    UMP_TZ_OFFSET,
    REQUEST_TIMEOUT,
    CACHE_DIR,
    CACHE_TTL_SEC,
    ANTI_FLAP_GRACE_M,
)
try:
    from .login_token import login_and_save as _auto_login
except Exception:
    _auto_login = None

# ---------- UMP auth/requests ----------
_SESSION = None
def _load_token(token_override: Optional[str] = None, token_path: Optional[str] = None) -> str:
    """
    Загружает токен UMP.
    Если передан token_override — используется он, без чтения файла.
    Если указан token_path — читается файл по этому пути (без авто-логина из env).
    """
    import os
    from ..config import UMP_USER, UMP_PASS

    if token_override:
        tok = token_override.strip()
        if not tok:
            raise ValueError("Передан пустой токен UMP")
        return tok

    path = token_path or UMP_TOKEN_FILE

    # Проверяем существование файла
    if not os.path.exists(path):
        # Авто-логин разрешаем только для стандартного пути и когда заданы креды в env
        if _auto_login and not token_path and UMP_USER and UMP_PASS:
            try:
                _auto_login()
            except Exception as e:
                raise FileNotFoundError(f"Токен не найден и авторизация не удалась: {e}")
        else:
            raise FileNotFoundError(f"Токен не найден: {path}. Выполните авторизацию.")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except FileNotFoundError:
        raise
    except Exception as e:
        raise FileNotFoundError(f"Ошибка чтения токена: {e}")

    if not token:
        # Токен пустой - пытаемся обновить (только при стандартном пути и автологине)
        if _auto_login and not token_path and UMP_USER and UMP_PASS:
            _auto_login()
            with open(path, "r", encoding="utf-8") as f2:
                token = f2.read().strip()
        else:
            raise ValueError("Токен пустой и авторизация невозможна")
    return token

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION

def _auth_headers(token: Optional[str] = None, token_path: Optional[str] = None) -> Dict[str, str]:
    t = _load_token(token_override=token, token_path=token_path)
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "UMPProbe/1.3",
        "auth": t,
        "token": t,
        "X-Timezone-Offset": str(UMP_TZ_OFFSET),
        "Referer": f"{UMP_BASE_URL}/map",
    }

def _as_list(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ("items","data","result"):
            v = data.get(k)
            if isinstance(v, list): return v
            if isinstance(v, dict) and isinstance(v.get("items"), list): return v["items"]
        return [data]
    return []

WKT_POINT_RE = re.compile(r'^POINT\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)$')
def parse_wkt_point(s: str) -> Optional[Tuple[float,float]]:
    if not isinstance(s, str): return None
    m = WKT_POINT_RE.match(s.strip())
    if not m: return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return (lat, lon)  # возвращаем (lat, lon)

def get_vehicle_id_by_depot_number(
    depot_number: str,
    token: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Optional[int]:
    url = f"{UMP_BASE_URL}/api/v1/map/vehicles"
    s = _get_session()
    for attempt in range(2):
        try:
            r = s.post(
                url,
                params={"number": str(depot_number)},
                json={},
                headers=_auth_headers(token=token, token_path=token_path),
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            break
        except requests.HTTPError as e:
            if (
                e.response is not None
                and e.response.status_code == 401
                and _auto_login
                and attempt == 0
                and token is None
                and token_path is None
            ):
                _auto_login()
                continue
            raise
    items = _as_list(r.json())
    for it in items:
        dep = it.get("depotNumber") or it.get("depot_number") or it.get("number")
        vid = it.get("vehicle_id") or it.get("id") or it.get("vehicleId")
        if str(dep) == str(depot_number) and vid is not None:
            return int(vid)
    if items:
        vid = items[0].get("vehicle_id") or items[0].get("id") or items[0].get("vehicleId")
        if vid is not None:
            return int(vid)
    return None

def fetch_online_by_vehicle_id(
    vehicle_id: int,
    token: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Dict:
    url = f"{UMP_BASE_URL}/api/v1/map/online/{vehicle_id}"
    s = _get_session()
    last_exc = None
    for attempt in range(3):
        try:
            r = s.get(
                url,
                headers=_auth_headers(token=token, token_path=token_path),
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = (
                r.json()
                if "application/json" in r.headers.get("Content-Type", "")
                else {}
            )
            break
        except Exception as e:
            last_exc = e
            # если 401 — один раз пробуем перелогиниться
            if (
                isinstance(e, requests.HTTPError)
                and e.response is not None
                and e.response.status_code == 401
                and _auto_login
                and attempt < 2
                and token is None
                and token_path is None
            ):
                _auto_login()
                continue
            if attempt < 2:
                import time as _t
                _t.sleep(0.3 * (2 ** attempt))
                continue
            raise
    center = data.get("center")
    lat = lon = None
    if isinstance(center, str):
        pair = parse_wkt_point(center)
        if pair: lat, lon = pair
    tstamp = data.get("time") or data.get("timestamp") or data.get("updatedAt")
    depot = data.get("depotNumber") or data.get("depot_number")
    return {
        "vehicle_id": vehicle_id,
        "depot_number": depot,
        "lat": lat, "lon": lon,
        "time": tstamp,
        "raw": data
    }

# ---------- File cache ----------
def _cache_path_for(vehicle_id: int) -> str:
    return os.path.join(CACHE_DIR, f"online_{vehicle_id}.json")

def _load_cached_position(vehicle_id: int) -> Optional[Dict]:
    try:
        path = _cache_path_for(vehicle_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        import time
        if (time.time() - data.get("ts", 0)) > CACHE_TTL_SEC:
            return None
        return data
    except Exception:
        return None

def _save_cached_position(vehicle_id: int, lat: float, lon: float, in_park: bool, park_name: Optional[str], raw_time) -> None:
    try:
        import time
        path = _cache_path_for(vehicle_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "ts": time.time(),
                "vehicle_id": vehicle_id,
                "lat": lat,
                "lon": lon,
                "in_park": in_park,
                "park_name": park_name,
                "time": raw_time,
            }, f, ensure_ascii=False)
    except Exception:
        pass

# ---------- Geometry / Geofencing ----------
def load_parks(path=PARKS_FILE) -> List[Park]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    parks = cfg.get("parks") or []
    out = []
    for p in parks:
        poly = p.get("polygon") or []
        if len(poly) >= 2 and poly[0] == poly[-1]:
            poly = poly[:-1]
        out.append({
            "name": p.get("name","park"),
            "polygon": [(float(x), float(y)) for x, y in poly],  # (lon, lat)
            "tolerance_m": float(p.get("tolerance_m", 0.0))
        })
    return out

def meters_per_degree(lat_deg: float) -> Tuple[float,float]:
    lat_m = 111_132.0
    lon_m = 111_320.0 * math.cos(math.radians(lat_deg))
    return lat_m, lon_m

def point_in_polygon(lon: float, lat: float, polygon: List[Tuple[float,float]]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3: return False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i+1) % n]
        cond = ((y1 > lat) != (y2 > lat)) and (lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1)
        if cond:
            inside = not inside
    return inside

def point_in_polygon_with_tolerance(lon: float, lat: float, polygon: List[Tuple[float,float]], tol_m: float) -> bool:
    if point_in_polygon(lon, lat, polygon):
        return True
    if tol_m <= 0:
        return False
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    lat_m, lon_m = meters_per_degree(lat)
    eps_lon = tol_m / max(lon_m, 1e-9)
    eps_lat = tol_m / lat_m
    in_bbox = (min(lons)-eps_lon <= lon <= max(lons)+eps_lon) and (min(lats)-eps_lat <= lat <= max(lats)+eps_lat)
    if not in_bbox:
        return False
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i+1) % len(polygon)]
        dx = x2 - x1; dy = y2 - y1
        if dx == dy == 0: 
            continue
        t = max(0.0, min(1.0, ((lon - x1)*dx + (lat - y1)*dy) / (dx*dx + dy*dy)))
        proj_x = x1 + t*dx; proj_y = y1 + t*dy
        d_lon = (lon - proj_x) * lon_m
        d_lat = (lat - proj_y) * lat_m
        dist_m = (d_lon*d_lon + d_lat*d_lat)**0.5
        if dist_m <= tol_m:
            return True
    return False

def distance_to_polygon_m(lon: float, lat: float, polygon: List[Tuple[float,float]]) -> float:
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    lat_m, lon_m = meters_per_degree(lat)
    best = float("inf")
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i+1) % len(polygon)]
        dx = x2 - x1; dy = y2 - y1
        if dx == dy == 0:
            continue
        t = max(0.0, min(1.0, ((lon - x1)*dx + (lat - y1)*dy) / (dx*dx + dy*dy)))
        proj_x = x1 + t*dx; proj_y = y1 + t*dy
        d_lon = (lon - proj_x) * lon_m
        d_lat = (lat - proj_y) * lat_m
        dist_m = (d_lon*d_lon + d_lat*d_lat)**0.5
        if dist_m < best:
            best = dist_m
    if point_in_polygon(lon, lat, polygon):
        return 0.0
    return best

def locate_park(lon: float, lat: float, parks: List[Dict]) -> Optional[str]:
    for p in parks:
        if point_in_polygon_with_tolerance(lon, lat, p["polygon"], p["tolerance_m"]):
            return p["name"]
    return None

# ---------- Orchestrator ----------
def get_position_and_check(
    depot_number: str,
    token: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Dict:
    vid = get_vehicle_id_by_depot_number(depot_number, token=token, token_path=token_path)
    if vid is None:
        return {"ok": False, "depot_number": depot_number, "error": "vehicle_id_not_found"}
    try:
        pos = fetch_online_by_vehicle_id(vid, token=token, token_path=token_path)
    except Exception as e:
        cached = _load_cached_position(vid)
        if cached:
            return {
                "ok": True,
                "depot_number": str(depot_number),
                "vehicle_id": vid,
                "lat": cached.get("lat"), "lon": cached.get("lon"),
                "time": cached.get("time"),
                "in_park": bool(cached.get("in_park")),
                "park_name": cached.get("park_name")
            }
        raise
    lat, lon = pos["lat"], pos["lon"]
    if lat is None or lon is None:
        cached = _load_cached_position(vid)
        if cached:
            return {
                "ok": True,
                "depot_number": str(depot_number),
                "vehicle_id": vid,
                "lat": cached.get("lat"), "lon": cached.get("lon"),
                "time": cached.get("time"),
                "in_park": bool(cached.get("in_park")),
                "park_name": cached.get("park_name")
            }
        return {"ok": False, "depot_number": depot_number, "vehicle_id": vid, "error": "no_coords", "raw": pos["raw"]}
    parks = load_parks(PARKS_FILE)
    park_name = locate_park(lon, lat, parks) if parks else None

    # анти-флап возле границы
    if not park_name and parks and ANTI_FLAP_GRACE_M > 0:
        try:
            for p in parks:
                d = distance_to_polygon_m(lon, lat, p["polygon"])
                if d <= ANTI_FLAP_GRACE_M:
                    park_name = p["name"]
                    break
        except Exception:
            pass

    _save_cached_position(vid, lat, lon, park_name is not None, park_name, pos.get("time"))
    return {
        "ok": True,
        "depot_number": str(depot_number),
        "vehicle_id": vid,
        "lat": lat, "lon": lon,
        "time": pos.get("time"),
        "in_park": park_name is not None,
        "park_name": park_name
    }

def _normalize_token(tok: str) -> str:
    return tok.strip()

def is_valid_depot_number(s: str) -> bool:
    s = _normalize_token(s)
    if not s.isdigit():
        return False
    # допускаем 3-6 цифр: 656, 6563, 10268, 15153 и т.п.
    return 3 <= len(s) <= 6

def parse_depots_from_args(args: List[str]) -> Tuple[List[str], List[Dict]]:
    """
    Возвращает (валидные_депо, список_ошибок_invalid).
    Поддерживает перечисление через пробелы/запятые/новые строки и --file path.
    Дубликаты удаляются, порядок первого появления сохраняется.
    """
    valid: List[str] = []
    invalid: List[Dict] = []
    seen = set()

    # поддержка флага --file <path>
    file_path = None
    i = 0
    while i < len(args):
        if args[i] == "--file" and i + 1 < len(args):
            file_path = args[i+1]
            i += 2
        else:
            i += 1

    tokens: List[str] = []
    # собрать токены из args без --file секции
    i = 0
    while i < len(args):
        if args[i] == "--file":
            i += 2
            continue
        tokens.append(args[i])
        i += 1

    # если указан файл — добавить его строки
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            tokens.append(file_content)
        except Exception as e:
            invalid.append({"ok": False, "error": "file_read_error", "detail": str(e)})

    # распарсить все токены: разделители — пробел/запятая/перевод строки/точка с запятой
    raw = "\n".join(tokens)
    for part in re.split(r"[\s,;]+", raw):
        t = _normalize_token(part)
        if not t:
            continue
        if t in seen:
            continue
        if is_valid_depot_number(t):
            valid.append(t)
            seen.add(t)
        else:
            invalid.append({"ok": False, "depot_number": t, "error": "invalid_depot_number"})

    return valid, invalid

def batch_get_positions(
    depot_numbers: List[str],
    token: Optional[str] = None,
    token_path: Optional[str] = None,
) -> List[Dict]:
    results: List[Dict] = []
    for dep in depot_numbers:
        try:
            results.append(get_position_and_check(dep, token=token, token_path=token_path))
        except requests.HTTPError as e:
            results.append({
                "ok": False,
                "depot_number": str(dep),
                "error": "http_error",
                "status": getattr(e.response, "status_code", None),
                "detail": (getattr(e.response, "text", "") or "")[:400],
            })
        except Exception as e:
            results.append({
                "ok": False,
                "depot_number": str(dep),
                "error": "exception",
                "detail": str(e),
            })
    return results

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    # обратная совместимость: один аргумент — как раньше
    if len(args) == 1 and args[0] and args[0] != "--file":
        depot = args[0]
    try:
        out = get_position_and_check(depot)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except requests.HTTPError as e:
        print("HTTP error:", e.response.status_code, e.response.text[:400])
    except Exception as e:
        print("Error:", e)
        raise SystemExit(0)

    # пакетный режим
    valids, invalids = parse_depots_from_args(args)
    batch = batch_get_positions(valids) if valids else []
    out = []
    if invalids:
        out.extend(invalids)
    if batch:
        out.extend(batch)
    print(json.dumps(out, ensure_ascii=False, indent=2))
