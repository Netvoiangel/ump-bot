# otbivka.py
import os, json, re, math, requests
from typing import Optional, List, Tuple, Dict
from config import (
    UMP_BASE_URL, UMP_TOKEN_FILE, PARKS_FILE, UMP_TZ_OFFSET, REQUEST_TIMEOUT
)

# ---------- UMP auth/requests ----------
def _load_token() -> str:
    with open(UMP_TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def _auth_headers() -> Dict[str, str]:
    t = _load_token()
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

def get_vehicle_id_by_depot_number(depot_number: str) -> Optional[int]:
    url = f"{UMP_BASE_URL}/api/v1/map/vehicles"
    r = requests.post(url, params={"number": str(depot_number)}, json={}, headers=_auth_headers(), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
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

def fetch_online_by_vehicle_id(vehicle_id: int) -> Dict:
    url = f"{UMP_BASE_URL}/api/v1/map/online/{vehicle_id}"
    r = requests.get(url, headers=_auth_headers(), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json() if "application/json" in r.headers.get("Content-Type","") else {}
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

# ---------- Geometry / Geofencing ----------
def load_parks(path=PARKS_FILE) -> List[Dict]:
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

def locate_park(lon: float, lat: float, parks: List[Dict]) -> Optional[str]:
    for p in parks:
        if point_in_polygon_with_tolerance(lon, lat, p["polygon"], p["tolerance_m"]):
            return p["name"]
    return None

# ---------- Orchestrator ----------
def get_position_and_check(depot_number: str) -> Dict:
    vid = get_vehicle_id_by_depot_number(depot_number)
    if vid is None:
        return {"ok": False, "depot_number": depot_number, "error": "vehicle_id_not_found"}
    pos = fetch_online_by_vehicle_id(vid)
    lat, lon = pos["lat"], pos["lon"]
    if lat is None or lon is None:
        return {"ok": False, "depot_number": depot_number, "vehicle_id": vid, "error": "no_coords", "raw": pos["raw"]}
    parks = load_parks(PARKS_FILE)
    park_name = locate_ark = locate_park(lon, lat, parks) if parks else None
    return {
        "ok": True,
        "depot_number": str(depot_number),
        "vehicle_id": vid,
        "lat": lat, "lon": lon,
        "time": pos.get("time"),
        "in_park": park_name is not None,
        "park_name": park_name
    }

if __name__ == "__main__":
    import sys
    depot = sys.argv[1] if len(sys.argv) > 1 else "6268"
    try:
        out = get_position_and_check(depot)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except requests.HTTPError as e:
        print("HTTP error:", e.response.status_code, e.response.text[:400])
    except Exception as e:
        print("Error:", e)
