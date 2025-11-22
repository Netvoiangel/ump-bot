"""Тесты для модуля parsing"""

import pytest
from src.ump_bot.parsing import (
    is_valid_depot_number,
    parse_sections_from_text,
    deduplicate_numbers,
)


class TestIsValidDepotNumber:
    """Тесты для валидации номеров ТС"""
    
    def test_valid_3_digit(self):
        """3-значные номера валидны"""
        assert is_valid_depot_number("656") is True
        assert is_valid_depot_number("123") is True
    
    def test_valid_4_digit(self):
        """4-значные номера валидны"""
        assert is_valid_depot_number("6563") is True
        assert is_valid_depot_number("6174") is True
    
    def test_valid_5_digit(self):
        """5-значные номера валидны"""
        assert is_valid_depot_number("15153") is True
        assert is_valid_depot_number("10268") is True
    
    def test_valid_6_digit(self):
        """6-значные номера валидны"""
        assert is_valid_depot_number("123456") is True
    
    def test_invalid_2_digit(self):
        """2-значные номера невалидны"""
        assert is_valid_depot_number("12") is False
        assert is_valid_depot_number("99") is False
    
    def test_invalid_7_digit(self):
        """7-значные номера невалидны"""
        assert is_valid_depot_number("1234567") is False
    
    def test_invalid_non_digit(self):
        """Нецифровые строки невалидны"""
        assert is_valid_depot_number("abc") is False
        assert is_valid_depot_number("12a") is False
        assert is_valid_depot_number("") is False
    
    def test_whitespace_handling(self):
        """Пробелы обрезаются"""
        assert is_valid_depot_number("  6563  ") is True
        assert is_valid_depot_number(" 123 ") is True


class TestParseSectionsFromText:
    """Тесты для парсинга текста с задачами"""
    
    def test_simple_single_category(self):
        """Простой текст с одной категорией"""
        text = """Заявки Redmine:
6683
6174"""
        result = parse_sections_from_text(text)
        assert "Заявки Redmine" in result
        assert "6683" in result["Заявки Redmine"]
        assert "6174" in result["Заявки Redmine"]
    
    def test_multiple_categories(self):
        """Текст с несколькими категориями"""
        text = """Заявки Redmine:
6683

Текущие задачи:
6719
6306"""
        result = parse_sections_from_text(text)
        assert "Заявки Redmine" in result
        assert "Текущие задачи" in result
        assert "6683" in result["Заявки Redmine"]
        assert "6719" in result["Текущие задачи"]
        assert "6306" in result["Текущие задачи"]
    
    def test_category_with_colon(self):
        """Категория с двоеточием"""
        text = """Заявки Redmine:
6683"""
        result = parse_sections_from_text(text)
        assert "Заявки Redmine" in result
    
    def test_category_without_colon(self):
        """Категория без двоеточия"""
        text = """Текущие задачи
6719"""
        result = parse_sections_from_text(text)
        assert "Текущие задачи" in result
        assert "6719" in result["Текущие задачи"]
    
    def test_empty_lines_ignored(self):
        """Пустые строки игнорируются"""
        text = """Заявки Redmine:

6683

6174"""
        result = parse_sections_from_text(text)
        assert "6683" in result["Заявки Redmine"]
        assert "6174" in result["Заявки Redmine"]
    
    def test_default_category(self):
        """Номера без категории попадают в default"""
        text = """6683
6174"""
        result = parse_sections_from_text(text)
        assert "default" in result
        assert "6683" in result["default"]
        assert "6174" in result["default"]
    
    def test_duplicate_numbers_removed(self):
        """Дубликаты номеров удаляются"""
        text = """Заявки Redmine:
6683
6683
6174"""
        result = parse_sections_from_text(text)
        assert result["Заявки Redmine"].count("6683") == 1
        assert "6174" in result["Заявки Redmine"]
    
    def test_invalid_numbers_ignored(self):
        """Невалидные номера игнорируются"""
        text = """Заявки Redmine:
6683
12
1234567
abc"""
        result = parse_sections_from_text(text)
        assert "6683" in result["Заявки Redmine"]
        assert "12" not in result["Заявки Redmine"]
        assert "1234567" not in result["Заявки Redmine"]
        assert "abc" not in result["Заявки Redmine"]
    
    def test_real_world_example(self):
        """Реальный пример из использования"""
        text = """Заявки Redmine:
6683

Текущие задачи:
6719
6306
6514
6683
6753
6810

Перенос камеры front:
6690
6684

Проверка ГК, маршрут 55, 58:
6635
6124"""
        result = parse_sections_from_text(text)
        assert len(result["Заявки Redmine"]) == 1
        assert len(result["Текущие задачи"]) == 6
        assert len(result["Перенос камеры front"]) == 2
        assert len(result["Проверка ГК, маршрут 55, 58"]) == 2


class TestDeduplicateNumbers:
    """Тесты для удаления дубликатов"""
    
    def test_no_duplicates(self):
        """Список без дубликатов остается без изменений"""
        numbers = ["6683", "6719", "6306"]
        result = deduplicate_numbers(numbers)
        assert result == numbers
    
    def test_with_duplicates(self):
        """Дубликаты удаляются"""
        numbers = ["6683", "6719", "6683", "6306", "6719"]
        result = deduplicate_numbers(numbers)
        assert len(result) == 3
        assert "6683" in result
        assert "6719" in result
        assert "6306" in result
    
    def test_preserves_order(self):
        """Порядок сохраняется"""
        numbers = ["6683", "6719", "6306", "6683"]
        result = deduplicate_numbers(numbers)
        assert result == ["6683", "6719", "6306"]
    
    def test_whitespace_handling(self):
        """Пробелы обрезаются"""
        numbers = [" 6683 ", "6719", "  6306  "]
        result = deduplicate_numbers(numbers)
        assert result == ["6683", "6719", "6306"]
    
    def test_empty_list(self):
        """Пустой список возвращается как есть"""
        assert deduplicate_numbers([]) == []
    
    def test_empty_strings_ignored(self):
        """Пустые строки игнорируются"""
        numbers = ["6683", "", "6719", "  ", "6306"]
        result = deduplicate_numbers(numbers)
        assert result == ["6683", "6719", "6306"]

