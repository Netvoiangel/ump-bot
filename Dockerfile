FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей (минимальные для Pillow)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание необходимых директорий
RUN mkdir -p .secrets/cache out .tile_cache

# Переменные окружения (переопределяются через docker-compose или -e)
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "telegram_bot.py"]

