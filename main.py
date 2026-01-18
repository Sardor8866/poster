import os
import telebot
import schedule
import time
import threading
import random
from datetime import datetime
from flask import Flask

# ========== КОНФИГ ==========
TOKEN = os.getenv('8367850036:AAFlwAwCeCMG1fC8e1kT1pUuFCZtC1Zis4A') or "8367850036:AAFlwAwCeCMG1fC8e1kT1pUuFCZtC1Zis4A"
CHANNEL = "@hweywewr"  # ЗАМЕНИ НА СВОЙ КАНАЛ!
POST_INTERVAL = 4  # минуты (4 для надежности)
PORT = int(os.environ.get('PORT', 10000))
# ============================

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== СТАТИСТИКА ==========
class BotStats:
    def __init__(self):
        self.start_time = time.time()
        self.post_count = 0
        
    def add_post(self):
        self.post_count += 1
        
    def get_uptime(self):
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        return f"{hours}ч {minutes}м"

stats = BotStats()

# ========== 10 ВИДОВ ПОСТОВ ==========
POST_TYPES = [
    lambda: f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y')}\n"
            f"📊 Постов: {stats.post_count}",
    
    lambda: "💪 Мотивация:\n«Ковчег построил любитель, профессионалы построили Титаник.»",
    
    lambda: random.choice([
        "🤓 Факт: Мёд никогда не портится.",
        "🧠 Факт: Мозг активнее ночью, чем днём.",
        "🐧 Факт: Пингвины прыгают до 2 метров.",
    ]),
    
    lambda: random.choice([
        "🤔 Вопрос: Какая ваша полезная привычка?",
        "💭 Вопрос: Что сделали бы при 48-часовом дне?",
    ]),
    
    lambda: random.choice([
        "📖 «Не откладывай на завтра...» — Марк Твен",
        "✨ «Будущее принадлежит мечтателям.»",
    ]),
    
    lambda: random.choice([
        "🌿 Совет: Выпейте воды после пробуждения.",
        "💻 Совет: Перерывы каждые 45 минут.",
    ]),
    
    lambda: {
        12: "❄️ Зима! Тепло одевайтесь.",
        1: "❄️ Зима! Тепло одевайтесь.", 
        2: "❄️ Зима! Тепло одевайтесь.",
        3: "🌸 Весна! Природа просыпается.",
        4: "🌸 Весна! Природа просыпается.",
        5: "🌸 Весна! Природа просыпается.",
        6: "☀️ Лето! Время путешествий.",
        7: "☀️ Лето! Время путешествий.",
        8: "☀️ Лето! Время путешествий.",
        9: "🍁 Осень! Яркие краски.",
        10: "🍁 Осень! Яркие краски.",
        11: "🍁 Осень! Яркие краски.",
    }.get(datetime.now().month, "📆 Хорошего дня!"),
    
    lambda: f"🤖 Статистика:\n"
            f"✅ Работает: {stats.get_uptime()}\n"
            f"📨 Постов: {stats.post_count}\n"
            f"🔄 Интервал: {POST_INTERVAL} мин\n"
            f"⚡ Статус: Активен 24/7",
    
    lambda: random.choice([
        "😂 Почему программисты не любят природу?\nСлишком много багов.",
        "🤣 Как программиста на пляже?\nСенд-кодер.",
    ]),
    
    lambda: random.choice([
        "🔗 Полезное: GitHub, Docker, VS Code",
        "🎓 Курсы: Coursera, edX, Stepik",
    ])
]

# ========== ОТПРАВКА ПОСТА ==========
def send_post_to_channel():
    """Отправляет случайный пост в канал"""
    try:
        # Выбираем случайный тип
        post_generator = random.choice(POST_TYPES)
        message = post_generator()
        
        # Добавляем время
        current_time = datetime.now().strftime("%H:%M")
        message += f"\n\n⏰ {current_time}"
        
        # Отправляем
        bot.send_message(CHANNEL, message)
        
        # Обновляем статистику
        stats.add_post()
        
        # Логируем
        print(f"[{current_time}] Пост #{stats.post_count} отправлен")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        
        # Fallback сообщение
        try:
            bot.send_message(CHANNEL, f"✅ Бот активен: {datetime.now().strftime('%H:%M')}")
            stats.add_post()
        except:
            pass

# ========== ШЕДУЛЕР ==========
def run_scheduler():
    """Запускает планировщик постов"""
    schedule.every(POST_INTERVAL).minutes.do(send_post_to_channel)
    print(f"🔄 Шедулер: пост каждые {POST_INTERVAL} мин")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========== TELEGRAM КОМАНДЫ (polling) ==========
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 Бот-постер работает 24/7!")

@bot.message_handler(commands=['status'])
def send_status(message):
    bot.reply_to(message, 
        f"📊 Статус:\n"
        f"✅ Работает: {stats.get_uptime()}\n"
        f"📨 Постов: {stats.post_count}\n"
        f"🔄 Интервал: {POST_INTERVAL} мин"
    )

@bot.message_handler(commands=['test'])
def test_post(message):
    send_post_to_channel()
    bot.reply_to(message, "✅ Тестовый пост отправлен!")

# ========== ЗАПУСК POLLING В ОТДЕЛЬНОМ ПОТОКЕ ==========
def run_polling():
    """Запускает polling в отдельном потоке"""
    print("🔄 Запуск Telegram polling...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            print(f"⚠️ Ошибка polling: {e}")
            time.sleep(5)

# ========== FLASK ЭНДПОИНТЫ ==========
@app.route('/')
def home():
    return f"""
    <h1>🤖 Бот-постер для Telegram</h1>
    <p>Работает 24/7, постит каждые {POST_INTERVAL} минут</p>
    <p>Отправлено постов: {stats.post_count}</p>
    <p>Uptime: {stats.get_uptime()}</p>
    """

@app.route('/health')
def health():
    return "OK", 200

@app.route('/stats')
def get_stats():
    return {
        "status": "running",
        "posts_sent": stats.post_count,
        "uptime": stats.get_uptime(),
        "next_post_in": schedule.idle_seconds()
    }

@app.route('/send_now')
def send_now():
    """Принудительная отправка поста"""
    send_post_to_channel()
    return "✅ Пост отправлен!"

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🚀 Запуск бота-постера...")
    
    # 1. Запускаем шедулер постов
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("✅ Шедулер запущен")
    
    # 2. Запускаем Telegram polling
    polling_thread = threading.Thread(target=run_polling, daemon=True)
    polling_thread.start()
    print("✅ Telegram polling запущен")
    
    # 3. Первый пост
    send_post_to_channel()
    print("✅ Первый пост отправлен")
    
    # 4. Запускаем Flask
    print(f"🌐 Flask запущен на порту {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
