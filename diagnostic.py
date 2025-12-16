import re
from typing import Dict, List, Optional

import requests

from otbivka import _auth_headers
from config import UMP_BASE_URL, REQUEST_TIMEOUT

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
    payload = {
        "RequestType": "GetVehicles",
        "Filters": {
            "Branchs": [branch_id],
            "Indicators": indicators or DEFAULT_INDICATORS,
            "Sort": {},
        },
        "Id": 3,
    }
    if user_id is not None:
        payload["Filters"]["user_id"] = user_id

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


def extract_red_issues(data: Dict) -> List[Dict]:
    """
    Извлекает индикаторы со значением 'red' из ответа UMP.
    """
    issues: List[Dict] = []
    if not isinstance(data, dict):
        return issues

    for item in data.values():
        depot = item.get("DepotNumber")
        indicators = item.get("Indicators") or {}
        if not isinstance(indicators, dict):
            continue
        for name, meta in indicators.items():
            if not isinstance(meta, dict):
                continue
            if str(meta.get("Value")).lower() != "red":
                continue
            legend = _clean_html(meta.get("Legend", ""))
            issues.append(
                {
                    "depot_number": depot,
                    "indicator": name,
                    "legend": legend,
                }
            )
    return issues


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

