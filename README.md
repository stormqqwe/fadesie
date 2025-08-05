# Fadesie Discord Bot

## Запуск с использованием Docker

### Предварительные требования

- Установленный Docker
- Установленный Docker Compose

### Шаги для запуска

1. Убедитесь, что файл `.env` содержит необходимые переменные окружения:
   ```
   TOKEN=ваш_токен_discord_бота
   MONGODB_URI=ваш_uri_mongodb
   MONGODB_DB=имя_базы_данных
   ```

2. Запустите бота с помощью Docker Compose:
   ```bash
   docker-compose up -d
   ```

3. Для просмотра логов:
   ```bash
   docker-compose logs -f
   ```

4. Для остановки бота:
   ```bash
   docker-compose down
   ```

## Запуск без Docker

1. Установите Python 3.10

2. Установите зависимости:
   ```bash
   pip install discord.py python-dotenv motor dnspython
   ```

3. Запустите бота:
   ```bash
   python run.py
   ```