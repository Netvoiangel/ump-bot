from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from telegram import Update

from ..config import CACHE_DIR
from ..infra.otbivka import get_position_and_check
from ..infra.render_map import render_parks_with_vehicles
from ..services import auth
from ..utils.logging import log_print
from .vehicles import build_color_map_from_sections, deduplicate_numbers

_MAP_RENDER_SEM = asyncio.Semaphore(int(os.getenv("MAP_RENDER_CONCURRENCY", "2")))


async def render_map_with_numbers(
    logger,
    update: Update,
    depot_numbers: List[str],
    selected_park: Optional[str],
    sections: Optional[Dict[str, List[str]]] = None,
    token_path: Optional[str] = None,
    out_dir: str = "out",
    max_image_size: int = 10 * 1024 * 1024,
    tile_provider: str = "",
    tile_cache: str = CACHE_DIR,
    tile_user_agent: str = "",
    tile_referer: str = "",
    tile_apikey: str = "",
    tile_rate_tps: float = 3.0,
    zoom: int = 17,
) -> None:
    """Рендер карты для указанного списка ТС."""
    if not depot_numbers:
        await update.message.reply_text("❌ Не переданы номера ТС для построения карты.")
        return

    # Ограничение количества ТС
    if len(depot_numbers) > 50:
        depot_numbers = depot_numbers[:50]
        await update.message.reply_text(
            "⚠️ Обрабатываю только первые 50 ТС. Остальные обрезаны."
        )

    log_print(logger, f"render_map_with_numbers: {len(depot_numbers)} ТС, парк={selected_park}")

    if not token_path:
        await update.message.reply_text("❌ Нет токена UMP для запроса.")
        return

    await update.message.reply_text("🔄 Генерирую карту... Это может занять время.")

    color_map = build_color_map_from_sections(sections)
    log_print(logger, f"color_map создан: {len(color_map)} ТС с цветами")
    if color_map:
        log_print(logger, f"Примеры цветов: {list(color_map.items())[:3]}")
    if sections:
        log_print(logger, f"sections: {list(sections.keys())}")
        for cat, nums in sections.items():
            log_print(logger, f"  {cat}: {nums[:3]}... (всего {len(nums)})")

    try:
        sample_results = []
        for dep in depot_numbers[:5]:
            try:
                result = await asyncio.to_thread(get_position_and_check, dep, token_path=token_path)
                sample_results.append(result)
                log_print(
                    logger,
                    f"ТС {dep}: ok={result.get('ok')}, park={result.get('park_name')}, in_park={result.get('in_park')}",
                )
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    # пробуем обновить токен по сохранённым учётным данным
                    new_path = auth.refresh_session(update.effective_user.id)
                    if new_path:
                        token_path = new_path
                        try:
                            result = await asyncio.to_thread(get_position_and_check, dep, token_path=token_path)
                            sample_results.append(result)
                            continue
                        except Exception:
                            pass
                    await update.message.reply_text("❌ Сессия UMP истекла. Введите /login для повторной авторизации.")
                    return
                log_print(logger, f"HTTP error проверки ТС {dep}: {e}", "ERROR")
            except Exception as e:
                log_print(logger, f"Ошибка проверки ТС {dep}: {e}", "ERROR")

        # Ограничиваем параллельный рендер карт, чтобы не "забить" CPU/пулы потоков и не зависать на апдейтах.
        async with _MAP_RENDER_SEM:
            files = await asyncio.to_thread(
                render_parks_with_vehicles,
                depot_numbers=depot_numbers,
                out_dir=out_dir,
                size="1200x800",
                use_real_map=True,
                zoom=zoom,
                tile_provider=tile_provider,
                tile_cache=tile_cache,
                tile_user_agent=tile_user_agent,
                tile_referer=tile_referer,
                tile_apikey=tile_apikey,
                tile_rate_tps=tile_rate_tps,
                park_filter=selected_park,
                color_map=color_map,
                debug=True,
                auth_token_path=token_path,
            )

        if not files:
            debug_info = f"Обработано ТС: {len(depot_numbers)}\n"
            debug_info += f"Парк: {selected_park or 'все'}\n"
            if sample_results:
                debug_info += "\nПримеры:\n"
                for r in sample_results:
                    if r.get("ok"):
                        status = "✅ в парке" if r.get("in_park") else "❌ вне парка"
                        debug_info += f"  {r.get('depot_number')}: {status} ({r.get('park_name') or '—'})\n"
                    else:
                        debug_info += f"  {r.get('depot_number')}: ошибка {r.get('error')}\n"
            await update.message.reply_text(
                "❌ Нет ТС внутри парков для отображения.\n\n" + debug_info
            )
            return

        for file_path in files:
            try:
                file_size = os.path.getsize(file_path)
                if file_size > max_image_size:
                    await update.message.reply_text(
                        f"⚠️ Изображение слишком большое ({file_size // 1024 // 1024}MB)"
                    )
                    continue
                with open(file_path, "rb") as photo:
                    park_name = Path(file_path).stem.replace("park_", "")
                    caption = f"📍 Парк: {park_name}\n🚌 ТС: {len(depot_numbers)}"
                    await update.message.reply_photo(photo=photo, caption=caption)
            except Exception as e:
                log_print(logger, f"Ошибка отправки изображения {file_path}: {e}", "ERROR")
                await update.message.reply_text(f"❌ Ошибка отправки изображения: {e}")
    except FileNotFoundError as e:
        await update.message.reply_text(
            "❌ Токен UMP не найден. Введите /login и авторизуйтесь заново."
        )
    except Exception as e:
        log_print(logger, f"Error in render_map_with_numbers: {e}", "ERROR")
        import traceback
        log_print(logger, traceback.format_exc(), "ERROR")
        await update.message.reply_text(f"❌ Ошибка генерации карты: {e}")
