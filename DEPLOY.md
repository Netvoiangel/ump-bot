# Инструкция по деплою Telegram бота

## Подготовка

### 1. Создание бота в Telegram

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям для создания бота
4. Сохраните полученный токен

### 2. Настройка .env

Создайте файл `.env` на сервере со следующим содержимым:

```bash
# UMP доступы
UMP_BASE_URL=http://ump.piteravto.ru
UMP_USER=ваш_логин
UMP_PASS=ваш_пароль

# Токены и файлы
UMP_TOKEN_FILE=var/ump_token.txt
UMP_COOKIES=var/ump_cookies.txt
PARKS_FILE=src/ump_bot/data/parks.json
VEHICLES_FILE=src/ump_bot/data/vehicles.sample.txt

# Telegram Bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=123456789,987654321
# Оставьте пустым для открытого доступа

# MapTiler
MAPTILER_API_KEY=ваш_ключ_maptiler
MAP_PROVIDER=https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={apikey}
MAP_ZOOM=17
MAP_TPS=3
MAP_CACHE_DIR=var/tile_cache
MAP_OUT_DIR=out
MAP_SIZE=1200x800
MAP_USER_AGENT=UMPBot/1.0 (+contact: you@example.com)

# Оптимизация для слабого сервера
MAX_IMAGE_SIZE_MB=10
CACHE_TTL=120
```

## Вариант 1: Деплой через Docker (рекомендуется)

### Установка Docker и Docker Compose

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
```

### Запуск

```bash
# Клонируйте репозиторий
git clone <your-repo-url>
cd ump_bot

# Создайте .env файл (см. выше)

# Соберите и запустите
docker-compose up -d --build

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

## Вариант 2: Деплой через systemd (без Docker)

### Установка зависимостей

```bash
# Установите Python 3.11+
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Создайте директорию
sudo mkdir -p /opt/ump_bot
sudo chown $USER:$USER /opt/ump_bot

# Клонируйте репозиторий
cd /opt/ump_bot
git clone <your-repo-url> .

# Создайте виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env файл
nano .env  # заполните по образцу выше

# Создайте необходимые директории
mkdir -p .secrets/cache out .tile_cache
```

### Настройка systemd

```bash
# Скопируйте service файл
sudo cp ump-bot.service /etc/systemd/system/

# Отредактируйте пути в файле (если нужно)
sudo nano /etc/systemd/system/ump-bot.service

# Обновите systemd
sudo systemctl daemon-reload

# Запустите сервис
sudo systemctl enable ump-bot
sudo systemctl start ump-bot

# Проверьте статус
sudo systemctl status ump-bot

# Просмотр логов
sudo journalctl -u ump-bot -f
```

## Первый запуск

### Авторизация в UMP

```bash
# Если используете Docker
docker-compose exec ump-bot python login_token.py

# Если используете systemd
cd /opt/ump_bot
source venv/bin/activate
python login_token.py
```

## Команды бота

- `/start` - Начать работу
- `/help` - Справка
- `/parks` - Выбрать парк (кнопки)
- `/map` - Показать карту с ТС из файла `VEHICLES_FILE`
- `/map 6177 6848` - Карта для конкретных ТС
- `/status 6569` - Статус конкретного ТС

## Оптимизация для слабого сервера

### Уже реализовано:

1. **Ограничение ресурсов**:
   - Docker: лимит 2 CPU, 1GB RAM
   - systemd: CPUQuota=200%, MemoryLimit=1G

2. **Оптимизация рендеринга**:
   - Размер изображения: 1200x800 (можно уменьшить)
   - Zoom: 17 (можно снизить до 16)
   - TPS: 3 (скорость загрузки тайлов)
   - Максимальный размер изображения: 10MB

3. **Кэширование**:
   - Тайлы карт кэшируются в `.tile_cache`
   - Позиции ТС кэшируются в `.secrets/cache`

### Дополнительные настройки:

В `.env` можно изменить:
```bash
MAP_ZOOM=16          # Меньше детализация = быстрее
MAP_SIZE=800x600    # Меньше размер = быстрее
MAP_TPS=2           # Медленнее загрузка тайлов
MAX_IMAGE_SIZE_MB=5  # Меньше размер изображений
```

## Мониторинг

### Docker

```bash
# Статус
docker-compose ps

# Логи
docker-compose logs -f --tail=100

# Использование ресурсов
docker stats ump-telegram-bot
```

### systemd

```bash
# Статус
sudo systemctl status ump-bot

# Логи
sudo journalctl -u ump-bot -f --lines=100

# Использование ресурсов
top -p $(pgrep -f bot.py)
```

## Обновление

### Docker

```bash
cd /path/to/ump_bot
git pull
docker-compose up -d --build
```

### systemd

```bash
cd /opt/ump_bot
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ump-bot
```

## Устранение неполадок

### Бот не отвечает

1. Проверьте токен в `.env`
2. Проверьте логи: `docker-compose logs` или `journalctl -u ump-bot`
3. Проверьте доступ к интернету

### Ошибка авторизации UMP

```bash
# Перелогиньтесь
python login_token.py
```

### Нехватка памяти

1. Уменьшите `MAP_SIZE` в `.env`
2. Уменьшите `MAP_ZOOM`
3. Очистите кэш: `rm -rf .tile_cache/*`

### Медленная работа

1. Уменьшите количество ТС в `VEHICLES_FILE` (по умолчанию `src/ump_bot/data/vehicles.sample.txt`)
2. Используйте фильтр по парку: `/parks` → выберите парк
3. Снизьте `MAP_ZOOM` до 16

## Безопасность

1. **Ограничение доступа**: Укажите `TELEGRAM_ALLOWED_USERS` в `.env`
2. **Секреты**: Не коммитьте `.env` и `.secrets/`
3. **Firewall**: Закройте все порты кроме SSH (22)

## Поддержка

При возникновении проблем проверьте логи и убедитесь, что:
- Все переменные в `.env` заполнены
- Токен UMP актуален (запустите `login_token.py`)
- Файлы `PARKS_FILE` и `VEHICLES_FILE` существуют (дефолт: `src/ump_bot/data/parks.json`, `src/ump_bot/data/vehicles.sample.txt`)
- Достаточно места на диске для кэша

