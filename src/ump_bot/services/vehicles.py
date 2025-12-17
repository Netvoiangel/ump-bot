from __future__ import annotations

from typing import Dict, List, Tuple

from ..colors import build_color_map_from_sections
from ..parsing import parse_sections_from_text, deduplicate_numbers, is_valid_depot_number

__all__ = [
    "parse_sections_from_text",
    "deduplicate_numbers",
    "is_valid_depot_number",
    "build_color_map_from_sections",
    "build_color_map",
]


def build_color_map(sections: Dict[str, List[str]]) -> Dict[str, Tuple[str, str]]:
    """Alias для единообразия."""
    return build_color_map_from_sections(sections)
