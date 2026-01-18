import os
import telebot
import schedule
import time
import threading
from datetime import datetime
import random
from flask import Flask, request

# ========== КОНФИГ ==========
TOKEN = "8367850036:AAFlwAwCeCMG1fC8e1kT1pUuFCZtC1Zis4A"
CHANNEL = "-1003530391096"  # WEYWE
PORT = int(os.environ.get('PORT', 10000))
# ============================

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== АВТОПОСТИНГ ==========
post_count = 0
MESSAGES = [
    "✅ Бот работает! {time}",
    "🤖 Активен 24/7! {time}",
    "⚡ Работаем! {time}",
    "📊 Онлайн! {time}"
]

def send_scheduled_post():
    """Пост по расписанию"""
    global post_count
    try:
        now = datetime.now().strftime("%H:%M:%S")
        msg = random.choice(MESSAGES).format(time=now)
        bot.send_message(CHANNEL, msg)
        post_count += 1
        print(f"[{now}] Автопост #{post_count}")
    except Exception as e:
        print(f"❌ Ошибка автопоста: {e}")

# ========== WEBHOOK ЭНДПОИНТЫ ==========
@app.route('/')
def home():
    return f"🤖 Бот работает. Постов: {post_count}"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/send_test')
def send_test():
    """Ручная отправка поста"""
    send_scheduled_post()
    return f"✅ Тестовый пост отправлен! Всего: {post_count}"

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Основной endpoint для Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    return '', 200

# ========== TELEGRAM КОМАНДЫ ==========
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 Бот-постер работает 24/7 с вебхуком!")

@bot.message_handler(commands=['status'])
def send_status(message):
    bot.reply_to(message, f"📊 Статус:\nПостов отправлено: {post_count}")

@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.reply_to(message, f"Вы сказали: {message.text}")

# ========== ШЕДУЛЕР ==========
def run_scheduler():
    """Запускает планировщик постов"""
    schedule.every(10).minutes.do(send_scheduled_post)  # 10 минут
    print("🔄 Шедулер запущен: пост каждые 10 мин")
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🚀 Запуск бота с вебхуком...")
    
    # Запускаем шедулер
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Устанавливаем вебхук
    try:
        # Получаем URL Render автоматически
        render_url = os.environ.get('RENDER_EXTERNAL_URL')
        if not render_url:
            # Если не на Render, используем вручную
            render_url = "https://poster-2-124n.onrender.com"
        
        webhook_url = f"{render_url}/webhook"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"✅ Вебхук установлен: {webhook_url}")
        
    except Exception as e:
        print(f"⚠️ Ошибка вебхука: {e}")
    
    # Первый пост
    send_scheduled_post()
    
    # Запускаем Flask
    print(f"🌐 Сервер запущен на порту {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
