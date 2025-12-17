from typing import TypedDict, Optional, List


class Park(TypedDict, total=False):
    name: str
    id: Optional[int]
    lat: float
    lon: float
    radius: float
    polygon: List[List[float]]  # [[lon, lat], ...]
