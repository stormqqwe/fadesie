FROM python:3.10-slim

WORKDIR /app

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов проекта
COPY . .

# Открытие порта для веб-сервера keep_alive
EXPOSE 8080

# Запуск бота
CMD ["python", "run.py"]