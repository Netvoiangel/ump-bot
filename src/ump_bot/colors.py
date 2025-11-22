"""Модуль для определения цветов категорий задач"""

from typing import Dict, List, Tuple, Optional


def get_category_color(category: str) -> Tuple[str, str]:
    """
    Определяет цвет точки по названию категории задачи.
    
    Цвета:
    - Проверка ГК: желтый (#ffd43b, #fab005)
    - Заявки Redmine: синий (#4dabf7, #339af0)
    - Текущие задачи: оранжевый (#ff922b, #fd7e14)
    - Перенос камеры: фиолетовый (#9775fa, #845ef7)
    - Остальные: красный (#fa5252, #c92a2a)
    
    Args:
        category: Название категории (например, "Заявки Redmine:")
        
    Returns:
        Кортеж (fill_color, outline_color) в формате HEX
    """
    cat_lower = (category or "").lower().strip()
    cat_clean = cat_lower.rstrip(":")

    # Проверка ГК (любые маршруты) - желтый
    if "проверка гк" in cat_clean or cat_clean.startswith("проверка гк"):
        return "#ffd43b", "#fab005"
    
    # Заявки Redmine - синий
    if ("заявки redmine" in cat_clean
            or cat_clean.startswith("заявки redmine")
            or ("redmine" in cat_clean and "заявк" in cat_clean)):
        return "#4dabf7", "#339af0"
    
    # Текущие задачи - оранжевый
    if "текущие задачи" in cat_clean or cat_clean.startswith("текущие задачи"):
        return "#ff922b", "#fd7e14"
    
    # Перенос камеры - фиолетовый
    if ("перенос камеры" in cat_clean
            or cat_clean.startswith("перенос камеры")
            or ("камера" in cat_clean and "перенос" in cat_clean)):
        return "#9775fa", "#845ef7"
    
    # Остальные - красный (дефолт)
    return "#fa5252", "#c92a2a"


def build_color_map_from_sections(sections: Optional[Dict[str, List[str]]]) -> Dict[str, Tuple[str, str]]:
    """
    Создает карту цветов для номеров ТС на основе секций с категориями.
    
    Args:
        sections: Словарь {category: [depot_numbers...]} или None
        
    Returns:
        Словарь {depot_number: (fill_color, outline_color)}
    """
    color_map: Dict[str, Tuple[str, str]] = {}
    if not sections:
        return color_map
    
    for category, numbers in sections.items():
        fill, outline = get_category_color(category)
        for num in numbers:
            color_map[str(num)] = (fill, outline)
    
    return color_map

