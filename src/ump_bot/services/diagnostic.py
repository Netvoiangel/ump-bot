from __future__ import annotations

from typing import Optional

from ..config import UMP_BRANCH_MAP
from ..diagnostic import (
    fetch_branch_diagnostics,
    extract_red_issues,
    format_issues_compact,
    extract_user_id_from_token,
    filter_issues_with_details,
    is_indicator_suppressed,
)

__all__ = [
    "fetch_branch_diagnostics",
    "extract_red_issues",
    "format_issues_compact",
    "extract_user_id_from_token",
    "filter_issues_with_details",
    "is_indicator_suppressed",
    "_resolve_branch_id",
    "_known_branches_text",
]


def _resolve_branch_id(branch_name: str) -> Optional[int]:
    if not branch_name:
        return None
    name_norm = branch_name.strip().lower()
    for k, v in (UMP_BRANCH_MAP or {}).items():
        try:
            if k.strip().lower() == name_norm:
                return int(v)
        except Exception:
            continue
    return None


def _known_branches_text() -> str:
    if not UMP_BRANCH_MAP:
        return "Настройте переменную UMP_BRANCH_MAP, например: {\"Екатерининский\":1382}"
    keys = ", ".join(UMP_BRANCH_MAP.keys())
    return f"Доступные филиалы: {keys}"
