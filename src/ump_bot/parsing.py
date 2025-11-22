"""Модуль для парсинга текста с задачами и валидации номеров ТС"""

from typing import Dict, List


def is_valid_depot_number(s: str) -> bool:
    """
    Проверяет, является ли строка валидным номером ТС.
    
    Валидные номера: 3-6 цифр (например: 656, 6563, 10268, 15153)
    
    Args:
        s: Строка для проверки
        
    Returns:
        True если номер валиден, False иначе
    """
    s = s.strip()
    if not s.isdigit():
        return False
    return 3 <= len(s) <= 6


def parse_sections_from_text(text: str) -> Dict[str, List[str]]:
    """
    Парсит текст с задачами и возвращает словарь категорий и номеров ТС.
    
    Формат текста:
        Заявки Redmine:
        6683
        6174
        
        Текущие задачи:
        6700
        6504
    
    Args:
        text: Текст с задачами
        
    Returns:
        Словарь {category: [depot_numbers...]}
    """
    lines = text.splitlines()
    return _parse_sections_from_lines(lines)


def _parse_sections_from_lines(lines: List[str]) -> Dict[str, List[str]]:
    """Парсит секции из списка строк"""
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


def deduplicate_numbers(numbers: List[str]) -> List[str]:
    """
    Удаляет дубликаты из списка номеров ТС, сохраняя порядок.
    
    Args:
        numbers: Список номеров ТС
        
    Returns:
        Список уникальных номеров в исходном порядке
    """
    seen = set()
    result = []
    for num in numbers:
        normalized = num.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result

