import os
import telebot
import schedule
import time
import threading
from datetime import datetime
from flask import Flask

# ========== КОНФИГ ==========
TOKEN = "8367850036:AAFlwAwCeCMG1fC8e1kT1pUuFCZtC1Zis4A"

# 🔥 ЗАМЕНИ ЭТО НА РЕАЛЬНЫЙ КАНАЛ:
# Вариант 1: Для публичного канала с @
# CHANNEL = "@weywewr"  # Пример: @daily_posts_bot

# Вариант 2: Для приватного канала с ID
CHANNEL = "-1003530391096"  # Пример: -1001234567890

POST_INTERVAL = 4  # минуты между постами
PORT = 10000
# ============================

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== ОТПРАВКА ПОСТА ==========
def send_post():
    try:
        now = datetime.now().strftime("%H:%M:%S")
        message = f"✅ Бот работает!\nВремя: {now}"
        
        bot.send_message(CHANNEL, message)
        print(f"[{now}] Пост отправлен")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ========== ШЕДУЛЕР ==========
def run_scheduler():
    schedule.every(POST_INTERVAL).minutes.do(send_post)
    print(f"🔄 Посты каждые {POST_INTERVAL} мин")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========== FLASK ЭНДПОИНТЫ ==========
@app.route('/')
def home():
    return "🤖 Бот-постер активен!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/send_test')
def send_test():
    """Принудительная отправка"""
    send_post()
    return "Тестовый пост отправлен!"

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🚀 Запуск бота...")
    
    # Запускаем шедулер
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Первый пост
    send_post()
    
    # Запускаем Flask
    print(f"🌐 Сервер запущен")
    app.run(host='0.0.0.0', port=PORT, debug=False)
