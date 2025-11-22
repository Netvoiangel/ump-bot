"""Тесты для модуля colors"""

import pytest
from src.ump_bot.colors import get_category_color, build_color_map_from_sections


class TestGetCategoryColor:
    """Тесты для определения цветов категорий"""
    
    def test_proverka_gk(self):
        """Проверка ГК - желтый"""
        fill, outline = get_category_color("Проверка ГК")
        assert fill == "#ffd43b"
        assert outline == "#fab005"
        
        fill2, outline2 = get_category_color("Проверка ГК, маршрут 55, 58:")
        assert fill2 == "#ffd43b"
        assert outline2 == "#fab005"
    
    def test_zayavki_redmine(self):
        """Заявки Redmine - синий"""
        fill, outline = get_category_color("Заявки Redmine")
        assert fill == "#4dabf7"
        assert outline == "#339af0"
        
        fill2, outline2 = get_category_color("Заявки Redmine:")
        assert fill2 == "#4dabf7"
        assert outline2 == "#339af0"
    
    def test_tekushchie_zadachi(self):
        """Текущие задачи - оранжевый"""
        fill, outline = get_category_color("Текущие задачи")
        assert fill == "#ff922b"
        assert outline == "#fd7e14"
        
        fill2, outline2 = get_category_color("Текущие задачи:")
        assert fill2 == "#ff922b"
        assert outline2 == "#fd7e14"
    
    def test_perenos_kamery(self):
        """Перенос камеры - фиолетовый"""
        fill, outline = get_category_color("Перенос камеры front")
        assert fill == "#9775fa"
        assert outline == "#845ef7"
        
        fill2, outline2 = get_category_color("Перенос камеры front:")
        assert fill2 == "#9775fa"
        assert outline2 == "#845ef7"
    
    def test_default_red(self):
        """Остальные категории - красный (дефолт)"""
        fill, outline = get_category_color("Какая-то другая задача")
        assert fill == "#fa5252"
        assert outline == "#c92a2a"
        
        fill2, outline2 = get_category_color("default")
        assert fill2 == "#fa5252"
        assert outline2 == "#c92a2a"
    
    def test_case_insensitive(self):
        """Регистр не важен"""
        fill1, outline1 = get_category_color("Заявки Redmine")
        fill2, outline2 = get_category_color("заявки redmine")
        fill3, outline3 = get_category_color("ЗАЯВКИ REDMINE")
        
        assert fill1 == fill2 == fill3 == "#4dabf7"
        assert outline1 == outline2 == outline3 == "#339af0"
    
    def test_whitespace_handling(self):
        """Пробелы обрезаются"""
        fill1, outline1 = get_category_color("  Заявки Redmine  ")
        fill2, outline2 = get_category_color("Заявки Redmine")
        
        assert fill1 == fill2 == "#4dabf7"
        assert outline1 == outline2 == "#339af0"
    
    def test_empty_string(self):
        """Пустая строка - дефолт (красный)"""
        fill, outline = get_category_color("")
        assert fill == "#fa5252"
        assert outline == "#c92a2a"
    
    def test_none(self):
        """None - дефолт (красный)"""
        fill, outline = get_category_color(None)
        assert fill == "#fa5252"
        assert outline == "#c92a2a"


class TestBuildColorMapFromSections:
    """Тесты для создания карты цветов"""
    
    def test_simple_sections(self):
        """Простая карта цветов"""
        sections = {
            "Заявки Redmine": ["6683", "6174"],
            "Текущие задачи": ["6719", "6306"]
        }
        color_map = build_color_map_from_sections(sections)
        
        assert "6683" in color_map
        assert "6174" in color_map
        assert "6719" in color_map
        assert "6306" in color_map
        
        # Проверяем цвета
        fill1, outline1 = color_map["6683"]
        assert fill1 == "#4dabf7"  # синий для Redmine
        assert outline1 == "#339af0"
        
        fill2, outline2 = color_map["6719"]
        assert fill2 == "#ff922b"  # оранжевый для Текущих задач
        assert outline2 == "#fd7e14"
    
    def test_empty_sections(self):
        """Пустые секции - пустая карта"""
        assert build_color_map_from_sections({}) == {}
    
    def test_none_sections(self):
        """None - пустая карта"""
        assert build_color_map_from_sections(None) == {}
    
    def test_multiple_categories_same_color(self):
        """Несколько категорий одного цвета"""
        sections = {
            "Проверка ГК, маршрут 55": ["6635", "6124"],
            "Проверка ГК, маршрут 58": ["6226", "6129"]
        }
        color_map = build_color_map_from_sections(sections)
        
        # Все должны быть желтыми
        for num in ["6635", "6124", "6226", "6129"]:
            fill, outline = color_map[num]
            assert fill == "#ffd43b"
            assert outline == "#fab005"
    
    def test_duplicate_numbers_different_categories(self):
        """Один номер в разных категориях - берется последний цвет"""
        sections = {
            "Заявки Redmine": ["6683"],
            "Текущие задачи": ["6683"]
        }
        color_map = build_color_map_from_sections(sections)
        
        # Должен быть оранжевый (последняя категория)
        fill, outline = color_map["6683"]
        assert fill == "#ff922b"
        assert outline == "#fd7e14"
    
    def test_string_numbers_converted(self):
        """Номера как строки конвертируются"""
        sections = {
            "Заявки Redmine": [6683, 6174]  # числа, не строки
        }
        color_map = build_color_map_from_sections(sections)
        
        assert "6683" in color_map
        assert "6174" in color_map

