from typing import Optional, Tuple, TypedDict, Any


class VehicleStatus(TypedDict, total=False):
    vehicle_id: Optional[int]
    depot_number: str
    lat: Optional[float]
    lon: Optional[float]
    time: Any
    park_name: Optional[str]
    in_park: Optional[bool]
    ok: Optional[bool]
    error: Optional[str]
