# render_map.py
import os, re, json, math, io, time
from typing import List, Tuple, Dict, Optional
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from otbivka import load_parks, batch_get_positions


def _normalize_token(tok: str) -> str:
    return tok.strip()


def _parse_sections_from_lines(lines: List[str]) -> Dict[str, List[str]]:
    """Парсит секции из списка строк"""
    from otbivka import is_valid_depot_number

    result: Dict[str, List[str]] = {}
    current_category = "default"

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        is_valid_number = is_valid_depot_number(line)
        has_colon = ":" in line
        has_no_digits = not any(c.isdigit() for c in line)
        is_header = (not is_valid_number) and (has_colon or has_no_digits)

        if is_header:
            current_category = line.rstrip(":").strip() or "default"
            result.setdefault(current_category, [])
        else:
            if is_valid_number:
                result.setdefault(current_category, [])
                if line not in result[current_category]:
                    result[current_category].append(line)
    return result


def parse_vehicles_file_with_sections(file_path: str) -> Dict[str, List[str]]:
    """
    Парсит vehicles.txt с секциями (заголовки) и возвращает словарь:
    { "category_name": [depot_numbers...], ... }
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return _parse_sections_from_lines(lines)
    except Exception as e:
        import traceback
        import sys
        print(f"Ошибка парсинга vehicles.txt: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return {}


def parse_sections_from_text(text: str) -> Dict[str, List[str]]:
    """Парсит секции из произвольного текста"""
    lines = text.splitlines()
    return _parse_sections_from_lines(lines)


def _parse_size(s: str) -> Tuple[int, int]:
    m = re.match(r"^(\d+)[xX](\d+)$", s.strip())
    if not m:
        return (1200, 800)
    return (int(m.group(1)), int(m.group(2)))


def _lonlat_bbox(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _project(lon: float, lat: float, bbox: Tuple[float, float, float, float], size: Tuple[int, int], pad: int) -> Tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    w, h = size
    w2 = max(maxx - minx, 1e-12)
    h2 = max(maxy - miny, 1e-12)
    sx = (w - 2 * pad) / w2
    sy = (h - 2 * pad) / h2
    # равномерное масштабирование, чтобы сохранить пропорции
    s = min(sx, sy)
    ox = pad + (w - 2 * pad - s * w2) / 2.0
    oy = pad + (h - 2 * pad - s * h2) / 2.0
    x = int(ox + (lon - minx) * s)
    # y растет вниз — инвертируем lat по bbox
    y = int(oy + (maxy - lat) * s)
    return (x, y)


# ---- Web Mercator helpers ----
def _lonlat_to_mercator_xy(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    siny = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0
    y = 0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)
    scale = 256 * (2 ** zoom)
    return x * scale, y * scale

def _tile_xy_ranges(bbox: Tuple[float, float, float, float], zoom: int, pad_px: int = 64) -> Tuple[int, int, int, int]:
    minlon, minlat, maxlon, maxlat = bbox
    x1, y2 = _lonlat_to_mercator_xy(minlon, minlat, zoom)
    x2, y1 = _lonlat_to_mercator_xy(maxlon, maxlat, zoom)
    minx = int((min(x1, x2) - pad_px) // 256)
    maxx = int((max(x1, x2) + pad_px) // 256)
    miny = int((min(y1, y2) - pad_px) // 256)
    maxy = int((max(y1, y2) + pad_px) // 256)
    return minx, miny, maxx, maxy

def _fetch_tile(session: requests.Session, provider: str, z: int, x: int, y: int, cache_dir: str) -> Image.Image:
    _ensure_dir(cache_dir)
    local = os.path.join(cache_dir, f"{provider.replace('://','_').replace('/','_')}_{z}_{x}_{y}.png")
    if os.path.exists(local):
        try:
            return Image.open(local)
        except Exception:
            pass
    url = provider.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content))
    try:
        img.save(local)
    except Exception:
        pass
    return img

def _stitch_tiles(bbox: Tuple[float,float,float,float], zoom: int, provider: str, cache_dir: str, headers: Dict[str,str], tiles_per_sec: float, debug: bool=False) -> Tuple[Image.Image, Tuple[int,int,int,int]]:
    minx, miny, maxx, maxy = _tile_xy_ranges(bbox, zoom)
    w = (maxx - minx + 1) * 256
    h = (maxy - miny + 1) * 256
    base = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    sess = requests.Session()
    if headers:
        sess.headers.update(headers)
    last_ts = 0.0
    min_interval = 1.0 / max(tiles_per_sec, 0.1)
    fetched = 0
    for tx in range(minx, maxx + 1):
        for ty in range(miny, maxy + 1):
            try:
                # мягкий rate limit
                now = time.monotonic()
                sleep_for = last_ts + min_interval - now
                if sleep_for > 0:
                    time.sleep(sleep_for)
                tile = _fetch_tile(sess, provider, zoom, tx, ty, cache_dir)
                pos = ((tx - minx) * 256, (ty - miny) * 256)
                if tile.mode == "RGBA":
                    base.paste(tile, pos, tile)
                else:
                    base.paste(tile.convert("RGBA"), pos)
                last_ts = time.monotonic()
                fetched += 1
            except Exception:
                # оставим серую заглушку
                if debug:
                    try:
                        url_dbg = provider.replace("{z}", str(zoom)).replace("{x}", str(tx)).replace("{y}", str(ty))
                        print("tile_fetch_failed:", url_dbg)
                    except Exception:
                        pass
    if debug:
        print(f"tiles_fetched={fetched}, grid_size={(maxx-minx+1)}x{(maxy-miny+1)}")
    return base.convert("RGB"), (minx, miny, maxx, maxy)

def _project_on_tileimg(lon: float, lat: float, zoom: int, tile_range: Tuple[int,int,int,int]) -> Tuple[int,int]:
    px, py = _lonlat_to_mercator_xy(lon, lat, zoom)
    minx, miny, _, _ = tile_range
    return int(px - minx * 256), int(py - miny * 256)


def _ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def render_parks_with_vehicles(
    depot_numbers: List[str],
    out_dir: str = "out",
    size: str = "1200x800",
    use_real_map: bool = True,
    zoom: int = 17,
    tile_provider: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    tile_cache: str = ".tile_cache",
    tile_user_agent: str = "UMPBot/1.0 (+contact: set UA via --ua)",
    tile_referer: str = "",
    tile_apikey: str = "",
    tile_rate_tps: float = 5.0,
    background: str = "#ffffff",
    fill_color: str = "#f1f3f5",
    outline_color: str = "#495057",
    vehicle_fill: str = "#fa5252",
    vehicle_outline: str = "#c92a2a",
    text_color: str = "#212529",
    point_radius: int = 6,
    font_path: str = "",
    debug: bool = False,
    park_filter: Optional[str] = None,
    color_map: Optional[Dict[str, Tuple[str, str]]] = None,
) -> List[str]:
    # загрузим .env для поддержки MAPTILER_API_KEY, MAP_USER_AGENT, MAP_REFERER
    try:
        load_dotenv()
    except Exception:
        pass
    parks = load_parks()
    # ключ: park_name -> park dict
    park_by_name: Dict[str, Dict] = {p["name"]: p for p in parks}

    results = batch_get_positions(depot_numbers)
    if debug:
        try:
            print(json.dumps({"debug_results": results}, ensure_ascii=False)[:800])
        except Exception:
            pass
    # сгруппировать ТС, которые в парке
    in_park_by_name: Dict[str, List[Dict]] = {}
    for r in results:
        if r.get("ok") and r.get("in_park") and r.get("park_name"):
            in_park_by_name.setdefault(r["park_name"], []).append(r)
        elif debug:
            try:
                print("skip_item:", r)
            except Exception:
                pass

    out_files: List[str] = []
    _ensure_dir(out_dir)

    # загрузим шрифт, если указан; иначе fallback на default
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, size=16)
        except Exception:
            font = None

    width, height = _parse_size(size)
    pad = max(int(min(width, height) * 0.05), 30)

    if debug:
        print("parks_found:", list(in_park_by_name.keys()))

    for park_name, vehicles in in_park_by_name.items():
        # фильтр по имени парка, если указан
        if park_filter and park_name != park_filter:
            if debug:
                print(f"skipping_park (filter={park_filter}):", park_name)
            continue
        park = park_by_name.get(park_name)
        if not park:
            if debug:
                print("park_not_in_config:", park_name)
            continue
        polygon = park["polygon"]  # list[(lon,lat)]
        bbox = _lonlat_bbox(polygon)

        # фон: либо реальные тайлы, либо однотонный
        if use_real_map:
            provider_url = tile_provider
            # подхватываем ключ/UA/Referer из окружения, если не переданы явно
            env_key = os.getenv("MAPTILER_API_KEY", "")
            env_ua = os.getenv("MAP_USER_AGENT", "")
            env_ref = os.getenv("MAP_REFERER", "")
            if not tile_apikey:
                tile_apikey = env_key
            if not tile_user_agent and env_ua:
                tile_user_agent = env_ua
            if not tile_referer and env_ref:
                tile_referer = env_ref
            if "{apikey}" in provider_url:
                provider_url = provider_url.replace("{apikey}", tile_apikey)
            headers = {}
            if tile_user_agent:
                headers["User-Agent"] = tile_user_agent
            if tile_referer:
                headers["Referer"] = tile_referer
            tile_img, tile_range = _stitch_tiles(bbox, zoom, provider_url, tile_cache, headers, tile_rate_tps, debug)
            if debug and tile_img.getbbox() is None:
                print("tile_canvas_empty: fallback to simple background")
            img = tile_img.resize((width, height), Image.LANCZOS)
            draw = ImageDraw.Draw(img)
            # обведем полигон легкой линией сверху карты для ориентира
            poly_xy = []
            scale_x = width / float(tile_img.width)
            scale_y = height / float(tile_img.height)
            for (x, y) in polygon:
                px, py = _project_on_tileimg(x, y, zoom, tile_range)
                # масштаб до итогового размера
                sx = int(px * scale_x)
                sy = int(py * scale_y)
                poly_xy.append((sx, sy))
            if len(poly_xy) >= 3:
                draw.line(poly_xy + [poly_xy[0]], fill=outline_color, width=2)
        else:
            img = Image.new("RGB", (width, height), background)
            draw = ImageDraw.Draw(img)
            poly_xy = [_project(x, y, bbox, (width, height), pad) for (x, y) in polygon]
            if len(poly_xy) >= 3:
                draw.polygon(poly_xy, fill=fill_color, outline=outline_color)

        # заголовок с полупрозрачным фоном
        title_text = f"Парк: {park_name}"
        _draw_label_box(draw, (10, 10), title_text, text_color, font)

        # ТС
        for v in vehicles:
            lon = v.get("lon")
            lat = v.get("lat")
            dep = str(v.get("depot_number"))
            if lon is None or lat is None:
                continue
            if use_real_map:
                px, py = _project_on_tileimg(lon, lat, zoom, tile_range)
                cx = int(px * scale_x)
                cy = int(py * scale_y)
            else:
                cx, cy = _project(lon, lat, bbox, (width, height), pad)
            r = point_radius
            # Определяем цвет точки на основе color_map
            fill_col = vehicle_fill
            outline_col = vehicle_outline
            if color_map and dep in color_map:
                fill_col, outline_col = color_map[dep]
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill_col, outline=outline_col)
            # подпись с фоновой коробкой
            tx, ty = cx + r + 6, cy - r - 14
            _draw_label_box(draw, (tx, ty), dep, text_color, font)

        safe_name = re.sub(r"[^0-9A-Za-zА-Яа-я_\-]+", "_", park_name)
        out_path = os.path.join(out_dir, f"park_{safe_name}.png")
        img.save(out_path)
        out_files.append(out_path)

    return out_files


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        return draw.textsize(text, font=font)

def _draw_label_box(draw: ImageDraw.ImageDraw, pos: Tuple[int,int], text: str, text_color: str, font: ImageFont.ImageFont):
    x, y = pos
    if not font:
        font = ImageFont.load_default()
    w, h = _measure_text(draw, text, font)
    pad = 4
    bg = (255, 255, 255, 220)
    outline = (0, 0, 0, 255)
    # прямоугольник фона
    draw.rectangle((x - pad, y - pad, x + w + pad, y + h + pad), fill=bg, outline=outline)
    draw.text((x, y), text, fill=text_color, font=font)


def _parse_args(argv: List[str]) -> Dict:
    out = {
        "depots": [],
        "out_dir": "out",
        "size": "1200x800",
        "font": "",
        "zoom": 17,
        "provider": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "cache": ".tile_cache",
        "ua": "",
        "referer": "",
        "apikey": "",
        "tps": 5.0,
        "debug": False,
        "park": "",
    }
    i = 0
    buf: List[str] = []
    file_path = None
    while i < len(argv):
        a = argv[i]
        if a == "--file" and i + 1 < len(argv):
            file_path = argv[i + 1]
            i += 2
            continue
        if a.startswith("--out="):
            out["out_dir"] = a.split("=", 1)[1]
        elif a == "--out" and i + 1 < len(argv):
            out["out_dir"] = argv[i + 1]; i += 1
        elif a.startswith("--size="):
            out["size"] = a.split("=", 1)[1]
        elif a == "--size" and i + 1 < len(argv):
            out["size"] = argv[i + 1]; i += 1
        elif a.startswith("--zoom="):
            out["zoom"] = int(a.split("=", 1)[1])
        elif a == "--zoom" and i + 1 < len(argv):
            out["zoom"] = int(argv[i + 1]); i += 1
        elif a.startswith("--provider="):
            out["provider"] = a.split("=", 1)[1]
        elif a == "--provider" and i + 1 < len(argv):
            out["provider"] = argv[i + 1]; i += 1
        elif a.startswith("--cache="):
            out["cache"] = a.split("=", 1)[1]
        elif a == "--cache" and i + 1 < len(argv):
            out["cache"] = argv[i + 1]; i += 1
        elif a.startswith("--ua="):
            out["ua"] = a.split("=", 1)[1]
        elif a == "--ua" and i + 1 < len(argv):
            out["ua"] = argv[i + 1]; i += 1
        elif a.startswith("--referer="):
            out["referer"] = a.split("=", 1)[1]
        elif a == "--referer" and i + 1 < len(argv):
            out["referer"] = argv[i + 1]; i += 1
        elif a.startswith("--apikey="):
            out["apikey"] = a.split("=", 1)[1]
        elif a == "--apikey" and i + 1 < len(argv):
            out["apikey"] = argv[i + 1]; i += 1
        elif a.startswith("--tps="):
            out["tps"] = float(a.split("=", 1)[1])
        elif a == "--tps" and i + 1 < len(argv):
            out["tps"] = float(argv[i + 1]); i += 1
        elif a.startswith("--font="):
            out["font"] = a.split("=", 1)[1]
        elif a == "--font" and i + 1 < len(argv):
            out["font"] = argv[i + 1]; i += 1
        elif a == "--debug":
            out["debug"] = True
        elif a.startswith("--park="):
            out["park"] = a.split("=", 1)[1]
        elif a == "--park" and i + 1 < len(argv):
            out["park"] = argv[i + 1]; i += 1
        else:
            buf.append(a)
        i += 1

    # загрузим .env и подставим значения окружения как дефолты
    try:
        load_dotenv()
    except Exception:
        pass

    # Только если пользователь не указал явный провайдер — используем из окружения/по умолчанию
    env_provider = os.getenv("MAP_PROVIDER") or os.getenv("MAP_PROVIDER_URL")
    env_zoom = os.getenv("MAP_ZOOM")
    env_tps = os.getenv("MAP_TPS")
    env_cache = os.getenv("MAP_CACHE_DIR")
    env_out = os.getenv("MAP_OUT_DIR")
    env_size = os.getenv("MAP_SIZE")
    env_font = os.getenv("MAP_FONT")
    env_ua = os.getenv("MAP_USER_AGENT")
    env_ref = os.getenv("MAP_REFERER")
    env_key = os.getenv("MAPTILER_API_KEY")
    env_park = os.getenv("MAP_PARK")

    # приоритет: CLI > .env > дефолт
    if out["provider"] == "https://tile.openstreetmap.org/{z}/{x}/{y}.png":
        if env_provider:
            out["provider"] = env_provider
        elif env_key:
            out["provider"] = "https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={apikey}"
    if out["zoom"] == 17 and env_zoom:
        try: out["zoom"] = int(env_zoom)
        except Exception: pass
    if out["tps"] == 5.0 and env_tps:
        try: out["tps"] = float(env_tps)
        except Exception: pass
    if out["cache"] == ".tile_cache" and env_cache:
        out["cache"] = env_cache
    if out["out_dir"] == "out" and env_out:
        out["out_dir"] = env_out
    if out["size"] == "1200x800" and env_size:
        out["size"] = env_size
    if out["font"] == "" and env_font:
        out["font"] = env_font
    if out["ua"] == "" and env_ua:
        out["ua"] = env_ua
    if out["referer"] == "" and env_ref:
        out["referer"] = env_ref
    if out["apikey"] == "" and env_key:
        out["apikey"] = env_key
    if out["park"] == "" and env_park:
        out["park"] = env_park

    color_map: Optional[Dict[str, Tuple[str, str]]] = None
    
    def get_category_color(category: str) -> Tuple[str, str]:
        """Определяет цвет точки по категории задачи"""
        category_lower = category.lower().strip()
        category_clean = category_lower.rstrip(":")
        
        # Проверка ГК (любые маршруты) - желтый
        # Проверяем точное совпадение или начало строки
        if "проверка гк" in category_clean or category_clean.startswith("проверка гк"):
            return "#ffd43b", "#fab005"  # желтый, темно-желтый
        
        # Заявки Redmine - синий
        # Точная проверка: "заявки redmine" или содержит "redmine" (но не как часть другого слова)
        elif ("заявки redmine" in category_clean or 
              category_clean.startswith("заявки redmine") or
              (category_clean.find("redmine") >= 0 and "заявки" in category_clean)):
            return "#4dabf7", "#339af0"  # синий, темно-синий
        
        # Текущие задачи - оранжевый
        # Точная проверка: "текущие задачи" (с двоеточием или без)
        elif ("текущие задачи" in category_clean or 
              category_clean.startswith("текущие задачи")):
            return "#ff922b", "#fd7e14"  # оранжевый, темно-оранжевый
        
        # Перенос камеры - фиолетовый
        # Проверяем "перенос камеры" или просто "камера" (но не как часть другого слова)
        elif ("перенос камеры" in category_clean or
              category_clean.startswith("перенос камеры") or
              (category_clean.find("камера") >= 0 and "перенос" in category_clean)):
            return "#9775fa", "#845ef7"  # фиолетовый, темно-фиолетовый
        
        # Остальные - красный (дефолт)
        else:
            return "#fa5252", "#c92a2a"  # красный, темно-красный
    
    if file_path:
        try:
            # Парсим файл с секциями для создания color_map
            sections = parse_vehicles_file_with_sections(file_path)
            if sections:
                color_map = {}
                # Определяем цвета по категориям
                for category, depot_list in sections.items():
                    fill_color_special, outline_color_special = get_category_color(category)
                    for depot_num in depot_list:
                        color_map[depot_num] = (fill_color_special, outline_color_special)
                
                # Собираем все номера ТС из всех секций
                with open(file_path, "r", encoding="utf-8") as f:
                    buf.append(f.read())
            else:
                # Если не удалось распарсить секции, читаем как обычно
                with open(file_path, "r", encoding="utf-8") as f:
                    buf.append(f.read())
        except Exception as e:
            print("Не удалось прочитать файл:", e)

    raw = "\n".join(buf)
    depots: List[str] = []
    seen = set()
    for part in re.split(r"[\s,;]+", raw):
        t = _normalize_token(part)
        if not t:
            continue
        if not t.isdigit():
            continue
        if t in seen:
            continue
        depots.append(t); seen.add(t)

    out["depots"] = depots
    out["color_map"] = color_map
    return out


if __name__ == "__main__":
    import sys
    args = _parse_args(sys.argv[1:])
    files = render_parks_with_vehicles(
        depot_numbers=args["depots"],
        out_dir=args["out_dir"],
        size=args["size"],
        use_real_map=True,
        zoom=args["zoom"],
        tile_provider=args["provider"],
        tile_cache=args["cache"],
        tile_user_agent=args["ua"],
        tile_referer=args["referer"],
        tile_apikey=args["apikey"],
        tile_rate_tps=args["tps"],
        font_path=args["font"],
        debug=args["debug"],
        park_filter=args["park"] if args["park"] else None,
        color_map=args.get("color_map"),
    )
    if not files:
        print("Нет ТС внутри парков — изображение не создано.")
    else:
        print(json.dumps({"generated": files}, ensure_ascii=False, indent=2))


