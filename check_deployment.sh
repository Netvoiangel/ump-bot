#!/bin/bash
# Скрипт для проверки деплоя на сервере

echo "=== Проверка версии кода ==="
echo "1. Проверка, что /map без аргументов выдает ошибку (не читает файл)"
echo "2. Проверка логов на наличие color_map"
echo ""
echo "После обновления кода на сервере:"
echo "1. Перезапусти бота: docker-compose restart или systemctl restart ump-bot"
echo "2. Проверь логи: docker-compose logs -f или journalctl -u ump-bot -f"
echo "3. Отправь текст с категориями в бота и проверь логи на наличие:"
echo "   - 'color_map создан: X ТС с цветами'"
echo "   - 'Примеры цветов: ...'"
echo "   - '[DEBUG] color_map передан: X ТС'"
echo ""
echo "Если в логах нет этих сообщений - код не обновлен!"

