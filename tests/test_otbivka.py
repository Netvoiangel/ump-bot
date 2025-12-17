"""Тесты для функций из otbivka.py"""

import pytest

from src.ump_bot import otbivka


@pytest.fixture(autouse=True)
def no_auto_login(monkeypatch):
    """Отключаем авто-логин, чтобы тесты не лезли в сеть."""
    monkeypatch.setattr(otbivka, "_auto_login", None)


def test_load_token_reads_existing_file(monkeypatch, tmp_path):
    """_load_token должен возвращать содержимое файла токена."""
    token_file = tmp_path / "token.txt"
    token_file.write_text("abc123", encoding="utf-8")

    # Перенаправляем путь к токену на временный файл
    monkeypatch.setattr(otbivka, "UMP_TOKEN_FILE", str(token_file))

    token = otbivka._load_token()

    assert token == "abc123"


def test_load_token_raises_when_not_exists(monkeypatch, tmp_path):
    """Если файл отсутствует и авто-логин недоступен, ожидаем FileNotFoundError."""
    missing_file = tmp_path / "missing.txt"
    monkeypatch.setattr(otbivka, "UMP_TOKEN_FILE", str(missing_file))

    with pytest.raises(FileNotFoundError):
        otbivka._load_token()
"""Тесты для otbivka._load_token"""

from pathlib import Path

import pytest

from src.ump_bot import otbivka
from src.ump_bot import config


@pytest.fixture(autouse=True)
def reset_autologin(monkeypatch):
    """Отключаем автологин, чтобы тесты не ходили в сеть"""
    monkeypatch.setattr(otbivka, "_auto_login", None, raising=False)


def test_load_token_reads_file(tmp_path, monkeypatch):
    """Проверяет, что _load_token возвращает содержимое файла"""
    token_path = tmp_path / "ump_token.txt"
    token_path.write_text("abc123\n", encoding="utf-8")

    monkeypatch.setattr(otbivka, "UMP_TOKEN_FILE", str(token_path))
    monkeypatch.setattr(config, "UMP_USER", None, raising=False)
    monkeypatch.setattr(config, "UMP_PASS", None, raising=False)

    assert otbivka._load_token() == "abc123"


def test_load_token_missing_file_raises(tmp_path, monkeypatch):
    """Если токен не найден и нет автологина, должно быть FileNotFoundError"""
    missing_path = tmp_path / "no_token.txt"
    monkeypatch.setattr(otbivka, "UMP_TOKEN_FILE", str(missing_path))
    monkeypatch.setattr(config, "UMP_USER", None, raising=False)
    monkeypatch.setattr(config, "UMP_PASS", None, raising=False)

    with pytest.raises(FileNotFoundError):
        otbivka._load_token()

