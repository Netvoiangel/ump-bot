import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from docxtpl import DocxTemplate
from ..domain.warranty_act import WarrantyActData
from ..config import USER_META_DIR, DATA_DIR

EXECUTORS_FILE = Path(USER_META_DIR) / "executors.json"
ACT_TEMPLATE_PATH = DATA_DIR / "templates" / "act_template.docx"

def get_executor_name(user_id: int) -> Optional[str]:
    """Получает ФИО исполнителя по Telegram ID."""
    if not EXECUTORS_FILE.exists():
        return None
    try:
        with open(EXECUTORS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(str(user_id))
    except Exception:
        return None

def save_executor_name(user_id: int, name: str) -> None:
    """Сохраняет ФИО исполнителя для Telegram ID."""
    data = {}
    if EXECUTORS_FILE.exists():
        try:
            with open(EXECUTORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    
    data[str(user_id)] = name
    
    with open(EXECUTORS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_warranty_act(data: WarrantyActData) -> str:
    """
    Генерирует DOCX файл акта на основе шаблона.
    Возвращает путь к созданному файлу.
    """
    if not ACT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Шаблон акта не найден по пути: {ACT_TEMPLATE_PATH}")

    doc = DocxTemplate(ACT_TEMPLATE_PATH)
    
    # Форматируем данные для шаблона
    context = data.model_dump()
    context['act_date'] = data.act_date.strftime("%d.%m.%Y")
    context['start_date'] = data.start_date.strftime("%d.%m.%Y")
    context['end_date'] = data.end_date.strftime("%d.%m.%Y")
    
    # Обработка пустых опциональных полей
    if not context.get('old_sam_activation_no'):
        context['old_sam_activation_no'] = "-"
    if not context.get('new_sam_activation_no'):
        context['new_sam_activation_no'] = "-"

    doc.render(context)
    
    # Формируем имя файла: акт_заявка_<request_no>_ТС_<garage_no>_<date>.docx
    date_str = data.act_date.strftime("%d_%m_%Y")
    filename = f"акт_заявка_{data.request_no}_ТС_{data.garage_no}_{date_str}.docx"
    
    # Сохраняем во временную директорию (или CACHE_DIR)
    from ..config import CACHE_DIR
    output_path = Path(CACHE_DIR) / "acts"
    output_path.mkdir(parents=True, exist_ok=True)
    
    full_path = output_path / filename
    doc.save(full_path)
    
    return str(full_path)

def validate_date_str(date_str: str) -> Optional[datetime]:
    """Проверяет строку даты на корректность формата ДД.ММ.ГГГГ."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return None
