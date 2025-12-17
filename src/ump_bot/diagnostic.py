import re
import json
import base64
from typing import Dict, List, Optional, Any

import requests

from .otbivka import _auth_headers
from .config import UMP_BASE_URL, REQUEST_TIMEOUT, UMP_USER_ID

DEFAULT_INDICATORS = [
    "summary-state",
    "Navigation",
    "Online",
    "mnt",
    "bpts",
    "modem",
    "gps",
    "multimodem",
    "arch",
    "hdd",
    "msrv",
    "apc",
    "validator",
    "usb",
    "temperature-sensor",
    "dut",
    "accelerometer",
    "brd",
    "mbrd",
    "lastUpdate",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SESSION: Optional[requests.Session] = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _clean_html(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normalized = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    return _HTML_TAG_RE.sub("", normalized).strip()


def fetch_branch_diagnostics(
    branch_id: int,
    indicators: Optional[List[str]] = None,
    token: Optional[str] = None,
    token_path: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict:
    """
    Получает статусы оборудования для филиала (Branchs) из UMP.
    """
    uid = user_id or UMP_USER_ID
    if not uid:
        raise ValueError("Не задан user_id (нужен для запроса диагностики)")

    payload = {
        "RequestType": "GetVehicles",
        "Filters": {
            "Branchs": [branch_id],
            "Indicators": indicators or DEFAULT_INDICATORS,
            "Sort": {},
        },
        "Id": 3,
    }
    payload["Filters"]["user_id"] = int(uid)

    headers = _auth_headers(token=token, token_path=token_path)
    headers.update(
        {
            "Page-Id": "/vehicle-diagnostic",
            "Origin": UMP_BASE_URL,
            "Referer": f"{UMP_BASE_URL}/vehicle-diagnostic",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )

    r = _session().post(
        f"{UMP_BASE_URL}/db-api-query",
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or {}


def extract_user_id_from_token(token: str) -> Optional[int]:
    """Пытается вытащить userId из JWT токена без проверки подписи."""
    if not token or "." not in token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    # base64url padding
    rem = len(payload_b64) % 4
    if rem:
        payload_b64 += "=" * (4 - rem)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        data = json.loads(decoded.decode("utf-8"))
        uid = data.get("userId") or data.get("user_id") or data.get("user") or data.get("id")
        return int(uid) if uid is not None else None
    except Exception:
        return None


def _iter_items(data: Any):
    if isinstance(data, dict):
        return data.values()
    if isinstance(data, list):
        return data
    return []


def extract_red_issues(data: Any) -> List[Dict]:
    """
    Извлекает индикаторы со значением 'red' из ответа UMP (dict или list).
    """
    issues: List[Dict] = []
    for item in _iter_items(data):
        depot = item.get("DepotNumber")
        vehicle_id = item.get("VehicleId")
        indicators = item.get("Indicators") or {}
        if not isinstance(indicators, dict):
            continue
        for name, meta in indicators.items():
            if not isinstance(meta, dict):
                continue
            # summary-state — общий, его не выводим
            if str(name).strip().lower() == "summary-state":
                continue
            val = str(meta.get("Value")).lower()
            if val != "red":
                continue
            legend = _clean_html(meta.get("Legend", ""))
            issues.append(
                {
                    "depot_number": depot,
                    "indicator": name,
                    "vehicle_id": vehicle_id,
                    "legend": legend,
                }
            )
    return issues


def fetch_indicator_details(
    vehicle_id: int,
    indicators: List[str],
    token: Optional[str] = None,
    token_path: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict:
    uid = user_id or UMP_USER_ID
    if not uid:
        raise ValueError("Не задан user_id (нужен для деталей диагностики)")
    headers = _auth_headers(token=token, token_path=token_path)
    headers.update(
        {
            "Page-Id": "/vehicle-diagnostic",
            "Origin": UMP_BASE_URL,
            "Referer": f"{UMP_BASE_URL}/vehicle-diagnostic",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    payload = {
        "RequestType": "GetIndicatorsDetails",
        "Filters": {
            "user_id": int(uid),
            "Vehicles": [vehicle_id],
            "Indicators": indicators,
            "Service_Mode": False,
        },
        "Id": 1,
    }
    r = requests.post(
        f"{UMP_BASE_URL}/db-api-query",
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or {}


def _all_off_or_grey(entries: List[Dict]) -> bool:
    if not entries:
        return False
    seen = 0
    off = 0
    for e in entries:
        seen += 1
        val = str(e.get("Value", "")).lower()
        status = str(e.get("Status", "")).lower()
        if val == "red":
            return False
        if val == "grey" or "выключ" in status:
            off += 1
    return seen > 0 and off == seen


def is_indicator_suppressed(detail_item: Dict) -> bool:
    """
    Возвращает True, если все устройства в индикаторе выключены/grey (значит это не авария).
    """
    if not isinstance(detail_item, dict):
        return False
    values = detail_item.get("Value")
    if isinstance(values, list):
        return _all_off_or_grey(values)
    return False


def filter_issues_with_details(
    issues: List[Dict],
    token_path: str,
    user_id: int,
) -> List[Dict]:
    """
    Для каждого issue запрашивает детализированный статус.
    Если все устройства индикатора выключены/grey — исключает issue.
    """
    result: List[Dict] = []
    by_vehicle: Dict[int, List[Dict]] = {}
    for iss in issues:
        vid = iss.get("vehicle_id")
        if vid is None:
            result.append(iss)
            continue
        by_vehicle.setdefault(int(vid), []).append(iss)

    for vid, items in by_vehicle.items():
        indicators = list({i["indicator"] for i in items if i.get("indicator")})
        details = fetch_indicator_details(
            vehicle_id=vid,
            indicators=indicators,
            token_path=token_path,
            user_id=user_id,
        )
        vehicle_details = details.get(str(vid)) or details.get(vid) or {}
        for iss in items:
            ind = iss.get("indicator")
            det = vehicle_details.get(ind, {})
            if is_indicator_suppressed(det):
                continue
            result.append(iss)
    return result


def format_issues_compact(issues: List[Dict]) -> str:
    if not issues:
        return "✅ Красных индикаторов не обнаружено."
    lines = ["❗ Найдены ошибки оборудования:"]
    for item in issues:
        depot = item.get("depot_number") or "—"
        ind = item.get("indicator") or "—"
        legend = (item.get("legend") or "").split("\n")[0].strip()
        lines.append(f"{depot} {ind}: {legend}")
    return "\n".join(lines)


def format_issues_human(issues: List[Dict]) -> str:
    if not issues:
        return "✅ Красных индикаторов не обнаружено."
    lines = ["❗ Найдены ошибки оборудования:"]
    for item in issues:
        depot = item.get("depot_number") or "—"
        ind = item.get("indicator") or "—"
        legend = item.get("legend") or ""
        lines.append(f"• ТС {depot}: {ind} — {legend}")
    return "\n".join(lines)

