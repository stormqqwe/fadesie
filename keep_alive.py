from flask import Flask
from threading import Thread
import logging
import time
import requests
import os

app = Flask('')

# Отключаем стандартные логи Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def home():
    return "Бот работает!"

def run():
    app.run(host='0.0.0.0', port=8080)

def ping_server():
    """Функция для периодического пинга сервера каждые 15 секунд"""
    # Получаем URL сервера из переменной окружения или используем localhost по умолчанию
    server_url = os.getenv('SERVER_URL', 'http://localhost:8080')
    
    while True:
        try:
            # Отправляем GET-запрос на сервер
            response = requests.get(server_url)
            print(f"Пинг отправлен, статус: {response.status_code}")
        except Exception as e:
            print(f"Ошибка при отправке пинга: {e}")
        
        # Ждем 15 секунд перед следующим пингом
        time.sleep(15)

def keep_alive():
    # Запускаем веб-сервер в отдельном потоке
    server_thread = Thread(target=run)
    server_thread.daemon = True  # Поток будет автоматически завершен при завершении основного потока
    server_thread.start()
    
    # Запускаем пинг в отдельном потоке
    ping_thread = Thread(target=ping_server)
    ping_thread.daemon = True  # Поток будет автоматически завершен при завершении основного потока
    ping_thread.start()
