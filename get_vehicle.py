import os, json, requests, re
from typing import Optional

BASE_URL = os.getenv("UMP_BASE_URL", "http://ump.piteravto.ru").rstrip("/")
TOKEN_FP = os.getenv("UMP_TOKEN_FILE", "ump_token.txt")

def _load_token() -> str:
    with open(TOKEN_FP, "r", encoding="utf-8") as f:
        return f.read().strip()

def _auth_headers():
    t = _load_token()
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "UMPProbe/1.2",
        "auth": t,
        "token": t,
        "X-Timezone-Offset": "180",
        "Referer": f"{BASE_URL}/map",
    }

def _as_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items","data","result"):
            v = data.get(k)
            if isinstance(v, list): return v
            if isinstance(v, dict) and isinstance(v.get("items"), list): return v["items"]
        return [data]
    return []

WKT_POINT_RE = re.compile(r'^POINT\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)$')

def parse_wkt_point(s: str) -> Optional[tuple[float,float]]:
    if not isinstance(s, str): return None
    m = WKT_POINT_RE.match(s.strip())
    if not m: return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon  # вернём (lat, lon)

def get_vehicle_id_by_depot_number(depot_number: str) -> Optional[int]:
    url = f"{BASE_URL}/api/v1/map/vehicles"
    r = requests.post(url, params={"number": str(depot_number)}, json={}, headers=_auth_headers(), timeout=20)
    r.raise_for_status()
    items = _as_list(r.json())
    # ищем точное совпадение depotNumber/depot_number
    for it in items:
        dep = it.get("depotNumber") or it.get("depot_number") or it.get("number")
        vid = it.get("vehicle_id") or it.get("id") or it.get("vehicleId")
        if str(dep) == str(depot_number) and vid is not None:
            return int(vid)
    # если ничего — возьмём первый id (на всякий)
    if items:
        vid = items[0].get("vehicle_id") or items[0].get("id") or items[0].get("vehicleId")
        if vid is not None:
            return int(vid)
    return None

def get_online_by_vehicle_id(vehicle_id: int) -> dict:
    # ВАЖНО: именно /api/v1/map/online/{id}, не ?q=
    url = f"{BASE_URL}/api/v1/map/online/{vehicle_id}"
    r = requests.get(url, headers=_auth_headers(), timeout=20)
    r.raise_for_status()
    data = r.json() if "application/json" in r.headers.get("Content-Type","") else {}
    # По вашему примеру поля плоские: { id, depotNumber, center: "POINT(lon lat)", time, ... }
    center = data.get("center") or data.get("geometry") or data.get("position")
    lat = lon = None
    if isinstance(center, str):
        xy = parse_wkt_point(center)  # (lat, lon)
        if xy:
            lat, lon = xy
    elif isinstance(center, dict):
        # запасной вариант, если бы center был объектом
        lat = center.get("lat") or center.get("latitude") or center.get("y")
        lon = center.get("lon") or center.get("lng") or center.get("longitude") or center.get("x")
    # timestamp
    tstamp = data.get("time") or data.get("timestamp") or data.get("updatedAt")
    # номер ТС, если есть
    depot = data.get("depotNumber") or data.get("depot_number")
    return {
        "ok": (lat is not None and lon is not None),
        "vehicle_id": vehicle_id,
        "depot_number": depot,
        "lat": lat, "lon": lon,
        "time": tstamp,
        "raw": data
    }

def get_position_by_depot_number(depot_number: str) -> dict:
    vid = get_vehicle_id_by_depot_number(depot_number)
    if vid is None:
        return {"ok": False, "depot_number": depot_number, "error": "vehicle_id_not_found"}
    res = get_online_by_vehicle_id(vid)
    # если с сервера пришёл depotNumber, отлично; иначе добавим наш:
    res.setdefault("depot_number", depot_number)
    return res

if __name__ == "__main__":
    import sys
    depot = sys.argv[1] if len(sys.argv) > 1 else "6268"
    try:
        out = get_position_by_depot_number(depot)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except requests.HTTPError as e:
        print("HTTP error:", e.response.status_code, e.response.text[:400])
    except Exception as e:
        print("Error:", e)
