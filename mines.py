import telebot
from telebot import types
import random
import json
import time
import threading
import logging
import hashlib
from contextlib import contextmanager

# Добавляем импорт модуля referrals
import referrals  # ИМПОРТ ДЛЯ РЕФЕРАЛЬНЫХ БОНУСОВ

# Импорт функций из модуля лидеров
try:
    from leaders import add_game_to_history
except ImportError:
    # Функция-заглушка, если модуль лидеров не найден
    def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="mines"):
        logging.warning(f"Модуль лидеров не найден, игра не записана в историю: {user_id}")
        return False

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MinesGame:
    def __init__(self, user_id, mines_count, bet_amount, chat_id=None, message_id=None):
        self.user_id = user_id
        self.mines_count = mines_count
        self.bet_amount = bet_amount
        self.grid_size = 5
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.revealed = [[False for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.mines_positions = []
        self.multiplier = 1.0
        self.previous_multiplier = 1.0
        self.opened_cells = 0
        self.game_active = True  # Флаг активности игры
        self.session_token = generate_session_token(user_id, 'mines')
        self.place_mines()
        self.last_action_time = time.time()  # Время последнего действия
        self.action_lock = threading.Lock()  # Лок для защиты от конкурентных действий
        self.created_time = time.time()  # Время создания игры
        self.chat_id = chat_id  # ID чата с игрой
        self.message_id = message_id  # ID сообщения с игрой

    def place_mines(self):
        positions = [(i, j) for i in range(self.grid_size) for j in range(self.grid_size)]
        self.mines_positions = random.sample(positions, self.mines_count)

    def get_multiplier_for_opened_cells(self, opened_safe_cells):
        # Множители для каждого количества мин (количество безопасных ячеек = 25 - mines_count)
        multipliers = {
            2: [1.10, 1.22, 1.36, 1.52, 1.71, 1.93, 2.19, 2.50, 2.87, 3.32, 3.87, 4.55, 5.39, 6.45, 7.80, 9.55, 11.85, 14.95, 19.25, 25.25, 33.75, 55.75, 83.25],
            3: [1.15, 1.33, 1.55, 1.82, 2.15, 2.56, 3.07, 3.72, 4.55, 5.62, 7.02, 8.87, 11.35, 14.70, 25.30, 36.70, 49.80, 79.10, 99.80, 137.50, 195.00, 415.00],
            4: [1.20, 1.44, 1.73, 2.07, 2.49, 3.00, 3.62, 4.38, 5.32, 6.50, 7.98, 9.85, 14.20, 19.20, 27.10, 35.20, 43.80, 59.50, 85.20, 235.80, 678.80],
            5: [1.25, 1.56, 1.95, 2.44, 3.05, 3.81, 4.77, 5.98, 7.50, 9.42, 11.85, 19.95, 28.90, 39.95, 55.40, 79.70, 123.40, 163.20, 281.10, 1004.00],
            6: [1.30, 1.69, 2.20, 3.86, 5.71, 8.83, 11.28, 16.17, 27.62, 46.81, 78.95, 135.34, 230.34, 339.44, 551.27, 966.65, 2386.65, 5112.64, 10046.43],
            7: [1.35, 1.82, 2.46, 3.82, 5.48, 8.05, 15.16, 26.02, 67.88, 120.08, 227.11, 536.60, 1049.41, 3366.70, 7090.05, 15121.57, 26004.12, 40021.56],
            8: [1.40, 2.16, 3.34, 4.84, 7.38, 12.53, 25.54, 74.76, 200.66, 528.93, 1740.50, 5756.70, 17979.38, 39911.13, 135655.58, 245617.82, 589204.94],
            9: [1.45, 2.90, 4.05, 7.42, 13.41, 23.29, 45.47, 145.53, 298.32, 741.06, 1959.54, 4786.33, 10125.18, 36181.51, 56263.19, 145381.62],
            10: [1.60, 3.10, 5.38, 8.06, 18.59, 38.39, 89.08, 295.62, 738.43, 2557.65, 9886.47, 29129.71, 75194.56, 126291.84, 353837.76],
            11: [1.80, 4.20, 7.10, 19.55, 60.49, 345.78, 1526.84, 5642.95, 12768.72, 45109.95, 156175.92, 287931.47, 478750.35, 778420.56],
            12: [1.85, 4.39, 8.91, 26.35, 84.20, 424.14, 2341.03, 9769.76, 21118.59, 86201.60, 256342.72, 647582.62, 2467990.46],
            13: [1.90, 5.24, 10.83, 35.50, 125.90, 834.02, 5661.23, 21110.22, 67198.39, 249357.10, 797642.78, 2671157.00],
            14: [2.10, 6.61, 15.86, 53.03, 284.76, 1447.04, 23889.38, 118769.82, 354622.66, 975613.05, 2771164.80],
            15: [2.30, 7.00, 23.00, 75.00, 432.00, 2634.00, 55128.00, 274256.00, 536512.00, 1000024.00],
            16: [2.70, 8.41, 31.26, 125.45, 340.84, 2685.77, 18860.12, 36378.25, 246794.33],
            17: [3.30, 13.84, 56.65, 230.43, 501.54, 1138.39, 12496.46, 146548.81],
            18: [3.70, 18.29, 77.17, 270.98, 1640.36, 14800.03, 35340.47],
            19: [4.70, 23.76, 136.82, 433.18, 2579.63, 19861.11],
            20: [6.50, 36.25, 215.63, 1239.06, 9787.66],
            21: [7.60, 45.76, 1317.58, 4500.70],
            22: [8.70, 177.29, 1999.68],
            23: [10.80, 287.84],
            24: [25.90]
        }

        if self.mines_count in multipliers:
            multipliers_list = multipliers[self.mines_count]
            if opened_safe_cells <= len(multipliers_list):
                return multipliers_list[opened_safe_cells - 1]
            else:
                return multipliers_list[-1]
        return 1.0

    def reveal_cell(self, x, y):
        if not (0 <= x < self.grid_size and 0 <= y < self.grid_size):
            return False

        if self.revealed[x][y]:
            return True

        self.revealed[x][y] = True

        self.previous_multiplier = self.multiplier

        if (x, y) in self.mines_positions:
            self.game_active = False  # Игра завершается при попадании на мину
            return False

        self.opened_cells += 1
        self.multiplier = self.get_multiplier_for_opened_cells(self.opened_cells)

        return True

    def get_next_multiplier(self):
        next_opened = self.opened_cells + 1
        return self.get_multiplier_for_opened_cells(next_opened)

# Глобальный лок для доступа к файлу users_data.json
users_data_lock = threading.Lock()

def load_users_data():
    """Загружает данные пользователей"""
    try:
        with users_data_lock:
            with open('users_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
        return {}

def save_users_data(data):
    try:
        with users_data_lock:
            with open('users_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def generate_session_token(user_id, game_type):
    """Генерирует уникальный токен для сессии игры"""
    timestamp = str(time.time())
    data = f"{user_id}_{game_type}_{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

# Потокобезопасные словари
active_games = {}
user_temp_data = {}
last_click_time = {}
mines_lock = threading.Lock()
# Словарь для отслеживания обработки действий (защита от дублирования)
processing_actions = {}
processing_lock = threading.Lock()

# Минимальная и максимальная ставка
MIN_BET = 25  # Минимальная ставка 25 рублей
MAX_BET = float('inf')  # Максимальная ставка не ограничена

# Таймаут неактивной игры (5 минут)
GAME_TIMEOUT = 300  # 300 секунд = 5 минут

def cleanup_inactive_games():
    """Очистка неактивных игр и возврат ставок"""
    current_time = time.time()
    games_to_remove = []
    
    with mines_lock:
        for user_id, game in list(active_games.items()):
            # Проверяем, если игра существует более 5 минут без действий
            if current_time - game.created_time > GAME_TIMEOUT:
                logging.info(f"Удаление неактивной игры пользователя {user_id}, созданной {current_time - game.created_time:.1f} секунд назад")
                games_to_remove.append((user_id, game))
    
    # Обрабатываем удаление игр вне лока
    for user_id, game in games_to_remove:
        try:
            # Возвращаем ставку
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Возвращена ставка {game.bet_amount} пользователю {user_id} за неактивную игру")
            
            # Удаляем сообщение с игрой из чата
            if game.chat_id and game.message_id:
                try:
                    # Сначала обновляем сообщение с информацией о возврате
                    timeout_message = f"""
<blockquote expandable>╔══════════════════════╗
   ⏰ <b>ИГРА ЗАКРЫТА</b> ⏰
╚══════════════════════╝</blockquote>

<blockquote>
<b>⏱️ Игра была автоматически закрыта</b>
<b>📝 Причина:</b> 5 минут бездействия

<b>💰 Результат:</b>
├ 💸 Ставка: <b>{game.bet_amount}₽</b>
├ 🔄 Возвращено: <b>{game.bet_amount}₽</b>
└ 📊 Открыто ячеек: <b>{game.opened_cells}</b>
</blockquote>

<i>Ваша ставка возвращена на баланс! ✅</i>
"""
                    bot.edit_message_text(
                        timeout_message,
                        game.chat_id,
                        game.message_id,
                        parse_mode='HTML'
                    )
                    time.sleep(3)  # Даем время пользователю прочитать
                except Exception as e:
                    if "message is not modified" not in str(e) and "message to edit not found" not in str(e):
                        logging.error(f"Ошибка при редактировании сообщения игры {user_id}: {e}")
            
            # Удаляем игру из активных игр
            with mines_lock:
                if user_id in active_games and active_games[user_id].session_token == game.session_token:
                    del active_games[user_id]
            
            # Удаляем временные данные
            with mines_lock:
                if user_id in user_temp_data:
                    del user_temp_data[user_id]
            
            # Очищаем историю кликов
            with mines_lock:
                if user_id in last_click_time:
                    del last_click_time[user_id]
            
            # Очищаем обработку действий
            with processing_lock:
                # Удаляем все действия этого пользователя
                keys_to_remove = [k for k in processing_actions.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions[k]
                    
        except Exception as e:
            logging.error(f"Ошибка при удалении неактивной игры пользователя {user_id}: {e}")

def start_cleanup_thread():
    """Запускает поток для периодической очистки неактивных игр"""
    def cleanup_worker():
        while True:
            try:
                cleanup_inactive_games()
                time.sleep(60)  # Проверка каждую минуту
            except Exception as e:
                logging.error(f"Ошибка в cleanup_worker: {e}")
                time.sleep(60)
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    return thread

def rate_limit_mines(user_id):
    """Проверка ограничения по времени между нажатиями (0.3 секунды)"""
    current_time = time.time()
    with mines_lock:
        if user_id in last_click_time:
            if current_time - last_click_time[user_id] < 0.3:  # УВЕЛИЧЕНО ДО 0.3
                return False
        # ВАЖНОЕ ИЗМЕНЕНИЕ: Обновляем время только если не было ограничения
        last_click_time[user_id] = current_time
    return True

def is_action_processing(user_id, action_key=""):
    """Проверяет, обрабатывается ли уже действие пользователя"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        if key in processing_actions:
            # Если действие обрабатывалось менее 0.3 секунды назад
            if time.time() - processing_actions[key] < 0.3:  # УВЕЛИЧЕНО ДО 0.3
                return True
            else:
                # Удаляем старые записи
                del processing_actions[key]
        return False

def mark_action_processing(user_id, action_key=""):
    """Отмечает начало обработки действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        processing_actions[key] = time.time()

def clear_action_processing(user_id, action_key=""):
    """Очищает отметку о обработке действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        if key in processing_actions:
            del processing_actions[key]

def get_bet_selection_keyboard():
    """Клавиатура выбора ставки с новыми значениями"""
    markup = types.InlineKeyboardMarkup(row_width=5)
    bets = ["25", "50", "125", "250", "500"]  # Новые значения ставок
    buttons = [types.InlineKeyboardButton(f"{bet}₽", callback_data=f"mine_bet_{bet}") for bet in bets]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="mine_custom_bet"))
    return markup

def get_mines_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=5)
    mines_counts = ["2", "5", "10", "15", "18"]
    buttons = [types.InlineKeyboardButton(f"{count}", callback_data=f"mine_count_{count}") for count in mines_counts]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="mine_custom_count"))
    return markup

def get_game_keyboard(game, game_over=False):
    markup = types.InlineKeyboardMarkup(row_width=5)

    buttons = []
    for i in range(game.grid_size):
        row_buttons = []
        for j in range(game.grid_size):
            if game_over:
                if (i, j) in game.mines_positions:
                    if game.revealed[i][j]:
                        emoji = "❌"
                    else:
                        emoji = "💣"
                elif game.revealed[i][j]:
                    emoji = "🟩"
                else:
                    emoji = "◾️"
                callback_data = "mine_ignore"
            else:
                if game.revealed[i][j]:
                    if (i, j) in game.mines_positions:
                        emoji = "❌"
                    else:
                        emoji = "🟩"
                    callback_data = "mine_ignore"
                else:
                    emoji = "◽️"
                    callback_data = f"mine_cell_{i}_{j}"

            button = types.InlineKeyboardButton(
                emoji,
                callback_data=callback_data
            )
            row_buttons.append(button)
        buttons.append(row_buttons)

    for row in buttons:
        markup.row(*row)

    if not game_over and game.opened_cells > 0:
        markup.row(types.InlineKeyboardButton(
            f"💰 ЗАБРАТЬ {round(game.bet_amount * game.multiplier, 2)}₽",
            callback_data="mine_cashout"
        ))

    return markup

def format_game_info(game):
    """Форматирует информацию об игре в красивый вид"""
    next_mult = game.get_next_multiplier()
    
    # Рассчитываем время жизни игры
    game_lifetime = time.time() - game.created_time
    minutes = int(game_lifetime // 60)
    seconds = int(game_lifetime % 60)
    
    # Время до автоудаления
    time_left = GAME_TIMEOUT - game_lifetime
    if time_left > 0:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        time_info = f"{minutes} мин {seconds} сек (автоудаление через {minutes_left}:{seconds_left:02d})"
    else:
        time_info = f"{minutes} мин {seconds} сек (ожидание удаления)"

    game_info = f"""
<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
<b>🎯 Конфигурация:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 💣Мины: <b>{game.mines_count}</b>
└ 💹Открыто: <b>{game.opened_cells}</b> ячеек

<b>📊 Множители:</b>
├ ⬅️ Прошлый: <b>x{game.previous_multiplier:.2f}</b>
├ ✅ Текущий: <b>x{game.multiplier:.2f}</b>
└ ➡️ Следующий: <b>x{next_mult:.2f}</b>

<b>⏰ Время игры:</b>
└ {time_info}
</blockquote>

<i>Выберите безопасную ячейку! Игра будет закрыта через 5 минут бездействия.</i>
"""
    return game_info

def format_game_result(game, win_amount, is_win=False):
    """Форматирует результат игры"""
    if is_win:
        return f"""
<blockquote expandable>╔══════════════════════╗
   🎉 <b>ПОБЕДА!</b> 🎉
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 🍀Выигрыш: <b>{round(win_amount, 2)}₽</b>
└ 📌Множитель: <b>x{game.multiplier:.2f}</b>

<b>📊 Статистика:</b>
├ Открыто ячеек: <b>{game.opened_cells}</b>
└ Всего мин💣: <b>{game.mines_count}</b>
</blockquote>

<i>Отличная игра! Поздравляем с победой! 🥳</i>
"""
    else:
        return f"""
<blockquote expandable>╔══════════════════════╗
   💥 <b>ПОРАЖЕНИЕ</b> 💥
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 📉Потеряно: <b>{game.bet_amount}₽</b>
└ 📌Множитель: <b>x{game.multiplier:.2f}</b>

<b>📊 Статистика:</b>
├ Открыто ячеек: <b>{game.opened_cells}</b>
└ Попал на мину: <b>💣</b>
</blockquote>

<i>Не повезло в этот раз! Попробуйте еще! 💪</i>
"""

# Создаем бота глобально для доступа из функций
bot = None

def cancel_user_game(user_id, notify_user=True):
    """Принудительно отменяет игру пользователя и возвращает ставку"""
    try:
        with mines_lock:
            if user_id not in active_games:
                return False
            
            game = active_games[user_id]
            
            # Возвращаем ставку
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Принудительно возвращена ставка {game.bet_amount} пользователю {user_id}")
            
            # Обновляем сообщение в чате
            if notify_user and game.chat_id and game.message_id:
                try:
                    cancel_message = f"""
<blockquote expandable>╔══════════════════════╗
   🚫 <b>ИГРА ОТМЕНЕНА</b> 🚫
╚══════════════════════╝</blockquote>

<blockquote>
<b>⏱️ Игра была отменена</b>

<b>💰 Результат:</b>
├ 💸 Ставка: <b>{game.bet_amount}₽</b>
├ 🔄 Возвращено: <b>{game.bet_amount}₽</b>
└ 📊 Открыто ячеек: <b>{game.opened_cells}</b>
</blockquote>

<i>Ваша ставка возвращена на баланс! ✅</i>
"""
                    bot.edit_message_text(
                        cancel_message,
                        game.chat_id,
                        game.message_id,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    if "message is not modified" not in str(e) and "message to edit not found" not in str(e):
                        logging.error(f"Ошибка при редактировании сообщения отмены {user_id}: {e}")
                        # Если не удалось отредактировать, отправляем новое сообщение
                        try:
                            bot.send_message(game.chat_id, cancel_message, parse_mode='HTML')
                        except:
                            pass
            
            # Удаляем игру
            del active_games[user_id]
            
            # Очищаем связанные данные
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            
            if user_id in last_click_time:
                del last_click_time[user_id]
            
            # Очищаем обработку действий
            with processing_lock:
                keys_to_remove = [k for k in processing_actions.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions[k]
            
            return True
            
    except Exception as e:
        logging.error(f"Ошибка при отмене игры пользователя {user_id}: {e}")
        return False

def start_mines_game_from_command(user_id, mines_count, bet_amount, message=None, chat_id=None, message_id=None):
    """Функция для запуска игры через команду"""
    try:
        # Проверяем ограничение по времени
        if not rate_limit_mines(user_id):
            if message:
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
            return False

        # Проверяем активную игру пользователя
        with mines_lock:
            if user_id in active_games:
                # Если есть старая неактивная игра - отменяем ее
                game = active_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    # Автоматически отменяем старую игру
                    cancel_user_game(user_id)
                else:
                    if message:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return False

        # Проверяем количество мин
        if mines_count < 2 or mines_count > 24:
            if message:
                bot.send_message(message.chat.id, "❌ Количество мин должно быть от 2 до 24!")
            return False

        # Проверяем ставку
        if bet_amount < MIN_BET:
            if message:
                bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET}₽")
            return False

        users_data = load_users_data()
        
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)

        balance = users_data[user_id].get('balance', 0)
        if bet_amount > balance:
            if message:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
            return False

        # Создаем игру
        if message:
            game = MinesGame(user_id, mines_count, bet_amount, chat_id=message.chat.id)
        elif chat_id:
            game = MinesGame(user_id, mines_count, bet_amount, chat_id=chat_id, message_id=message_id)
        else:
            game = MinesGame(user_id, mines_count, bet_amount)

        with mines_lock:
            active_games[user_id] = game

        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)

        if message:
            sent_message = bot.send_message(
                message.chat.id,
                format_game_info(game),
                parse_mode='HTML',
                reply_markup=get_game_keyboard(game)
            )
            # Сохраняем ID сообщения
            game.message_id = sent_message.message_id
        elif chat_id and message_id:
            try:
                bot.edit_message_text(
                    format_game_info(game),
                    chat_id,
                    message_id,
                    parse_mode='HTML',
                    reply_markup=get_game_keyboard(game)
                )
                game.message_id = message_id
            except Exception as e:
                if "message is not modified" not in str(e):
                    logging.error(f"Ошибка edit_message_text при запуске игры: {e}")
                    # Если не удалось отредактировать, отправляем новое сообщение
                    sent_message = bot.send_message(
                        chat_id,
                        format_game_info(game),
                        parse_mode='HTML',
                        reply_markup=get_game_keyboard(game)
                    )
                    game.message_id = sent_message.message_id
        elif chat_id:
            sent_message = bot.send_message(
                chat_id,
                format_game_info(game),
                parse_mode='HTML',
                reply_markup=get_game_keyboard(game)
            )
            game.message_id = sent_message.message_id
        
        return True
    except Exception as e:
        logging.error(f"Ошибка в start_mines_game_from_command: {e}")
        if message:
            bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске игры!")
        return False

def parse_mines_command(text):
    """Парсит команду /мины или /mines и возвращает (количество_мин, сумма_ставки)"""
    try:
        # Убираем команду и разделяем аргументы
        parts = text.strip().split()
        
        if len(parts) < 3:
            return None, None
        
        # Проверяем оба варианта команд
        if parts[0].lower() not in ['/мины', '/mines', 'мины', 'mines']:
            return None, None
        
        # Пытаемся получить количество мин и ставку
        mines_count = None
        bet_amount = None
        
        # Пробуем разные варианты парсинга
        for i in range(1, len(parts)):
            if not mines_count:
                try:
                    # Пробуем конвертировать в число
                    mines_count = int(parts[i])
                    if not (2 <= mines_count <= 24):
                        mines_count = None
                except:
                    pass
            
            if mines_count and i + 1 < len(parts):
                try:
                    bet_amount = float(parts[i + 1])
                    if bet_amount < MIN_BET:
                        bet_amount = None
                    break
                except:
                    pass
        
        return mines_count, bet_amount
    except Exception as e:
        logging.error(f"Ошибка при парсинге команды: {e}")
        return None, None

def register_mines_handlers(bot_instance):
    global bot
    bot = bot_instance
    
    # Запускаем поток очистки
    start_cleanup_thread()

    # Обработчик команды /мины или /mines
    @bot.message_handler(func=lambda message: message.text and 
                        (message.text.lower().startswith('/мины') or 
                         message.text.lower().startswith('/mines') or
                         message.text.lower().startswith('мины ') or
                         message.text.lower().startswith('mines ')))
    def mines_command_handler(message):
        user_id = str(message.from_user.id)
        
        # Парсим команду
        mines_count, bet_amount = parse_mines_command(message.text)
        
        if mines_count is None or bet_amount is None:
            # Если не удалось распарсить, показываем справку
            help_text = """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
<b>📖 Как играть:</b>
• Напишите <code>/мины 10 100</code> чтобы начать игру с 10 минами и ставкой 100₽
• Или используйте меню для настройки игры

<b>🎯 Правила:</b>
• Открывайте безопасные ячейки без мин
• Каждая открытая ячейка увеличивает множитель
• Заберите выигрыш в любой момент
• Если наступите на мину - проигрываете ставку

<b>⚙️ Параметры:</b>
• Мины: от 2 до 24
• Минимальная ставка: 25₽
• Игра автоматически закрывается через 5 минут бездействия (ставка возвращается)
</blockquote>"""
            bot.send_message(message.chat.id, help_text, parse_mode='HTML')
            return
        
        # Запускаем игру с полученными параметрами
        start_mines_game_from_command(user_id, mines_count, bet_amount, message=message)

    def process_custom_bet(message):
        try:
            user_id = str(message.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit_mines(user_id):
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
                return

            bet_amount = float(message.text)

            if bet_amount < MIN_BET:
                bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET}₽")
                return

            if bet_amount > MAX_BET:
                bot.send_message(message.chat.id, f"❌ Максимальная ставка: {MAX_BET}₽")
                return

            users_data = load_users_data()
            
            if user_id not in users_data:
                users_data[user_id] = {'balance': 0}

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            with mines_lock:
                user_temp_data[user_id] = {'bet_amount': bet_amount}

            bot.send_message(
                message.chat.id,
                """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (2-24):
</blockquote>""",
                parse_mode='HTML',
                reply_markup=get_mines_selection_keyboard()
            )
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректную сумму!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_bet: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    def process_custom_mines(message):
        try:
            user_id = str(message.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit_mines(user_id):
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
                return

            mines_count = int(message.text)
            if not 2 <= mines_count <= 24:
                bot.send_message(message.chat.id, "❌ Введите число от 2 до 24!")
                return

            users_data = load_users_data()

            # Проверяем активную игру пользователя
            with mines_lock:
                if user_id in active_games:
                    # Проверяем, не устарела ли игра
                    game = active_games[user_id]
                    current_time = time.time()
                    if current_time - game.created_time > GAME_TIMEOUT:
                        # Автоматически отменяем старую игру
                        cancel_user_game(user_id)
                    else:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                        return

                if user_id not in user_temp_data or 'bet_amount' not in user_temp_data[user_id]:
                    bot.send_message(message.chat.id, "❌ Ошибка данных! Начните заново.")
                    return

                bet_amount = user_temp_data[user_id]['bet_amount']

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            # Запускаем игру через универсальную функцию
            success = start_mines_game_from_command(
                user_id=user_id,
                mines_count=mines_count,
                bet_amount=bet_amount,
                message=message
            )

            if success:
                with mines_lock:
                    if user_id in user_temp_data:
                        del user_temp_data[user_id]

        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректное число!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_mines: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    @bot.message_handler(func=lambda message: message.text in ["💣 Мины", "мины", "Mines"])
    def mines_start_internal(message):
        user_id = str(message.from_user.id)

        # Проверяем ограничение по времени
        if not rate_limit_mines(user_id):
            bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
            return

        # Проверяем активную игру пользователя
        with mines_lock:
            if user_id in active_games:
                # Проверяем, не устарела ли игра
                game = active_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    # Автоматически отменяем старую игру
                    cancel_user_game(user_id)
                else:
                    bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return

        users_data = load_users_data()

        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)

        balance = users_data[user_id].get('balance', 0)
        balance_rounded = round(balance, 2)

        bot.send_message(
            message.chat.id,
            f"""<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
            parse_mode='HTML',
            reply_markup=get_bet_selection_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('mine_'))
    def mines_callback_handler(call):
        try:
            user_id = str(call.from_user.id)

            # ВАЖНОЕ ИЗМЕНЕНИЕ: Проверяем ограничение по времени ВНУТРИ обработчика
            # для каждого типа кнопки отдельно
            
            # ЗАЩИТА ОТ ДУБЛИРОВАНИЯ ДЕЙСТВИЙ
            # Создаем уникальный ключ для этого действия
            action_key = ""
            if call.data.startswith("mine_cell_"):
                # Для кликов по клеткам используем координаты
                parts = call.data.split("_")
                x, y = int(parts[2]), int(parts[3])
                action_key = f"cell_{x}_{y}"
            elif call.data == "mine_cashout":
                action_key = "cashout"
            elif call.data.startswith("mine_bet_"):
                bet = call.data.split("_")[2]
                action_key = f"bet_{bet}"
            elif call.data.startswith("mine_count_"):
                count = call.data.split("_")[2]
                action_key = f"count_{count}"
            else:
                action_key = call.data

            # Проверяем, не обрабатывается ли уже это действие
            if is_action_processing(user_id, action_key):
                try:
                    bot.answer_callback_query(call.id, "⏳ Действие уже обрабатывается...", show_alert=False)
                except:
                    pass
                return

            # Отмечаем начало обработки
            mark_action_processing(user_id, action_key)

            if call.data.startswith("mine_bet_"):
                # Проверяем активную игру пользователя
                with mines_lock:
                    if user_id in active_games:
                        # Проверяем, не устарела ли игра
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            # Автоматически отменяем старую игру
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                bet_amount = float(call.data.split("_")[2])

                users_data = load_users_data()
                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                with mines_lock:
                    user_temp_data[user_id] = {'bet_amount': bet_amount}

                try:
                    bot.edit_message_text(
                        """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (2-24):
</blockquote>""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_mines_selection_keyboard()
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logging.error(f"Ошибка edit_message_text mine_bet: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            elif call.data.startswith("mine_count_"):
                # ИСПРАВЛЕНО: ВАЖНО - обработка выбора количества мин из меню
                mines_count = int(call.data.split("_")[2])

                # Проверяем активную игру пользователя
                with mines_lock:
                    if user_id in active_games:
                        # Проверяем, не устарела ли игра
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            # Автоматически отменяем старую игру
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                    if user_id not in user_temp_data or 'bet_amount' not in user_temp_data[user_id]:
                        try:
                            bot.answer_callback_query(call.id, "❌ Ошибка данных!")
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return

                    bet_amount = user_temp_data[user_id]['bet_amount']

                users_data = load_users_data()
                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                # Запускаем игру через универсальную функцию
                success = start_mines_game_from_command(
                    user_id=user_id,
                    mines_count=mines_count,
                    bet_amount=bet_amount,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )

                if success:
                    with mines_lock:
                        if user_id in user_temp_data:
                            del user_temp_data[user_id]

                clear_action_processing(user_id, action_key)
                return

            elif call.data == "mine_custom_bet":
                # Проверяем активную игру пользователя
                with mines_lock:
                    if user_id in active_games:
                        # Проверяем, не устарела ли игра
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            # Автоматически отменяем старую игру
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                try:
                    bot.send_message(
                        call.message.chat.id,
                        """<blockquote expandable>╔══════════════════════╗
   📝 <b>ВВОД СТАВКИ</b> 📝
╚══════════════════════╝</blockquote>

<blockquote>
Введите сумму ставки (мин. 25₽):
</blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения mine_custom_bet: {e}")
                    clear_action_processing(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_bet)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            elif call.data == "mine_custom_count":
                # Проверяем активную игру пользователя
                with mines_lock:
                    if user_id in active_games:
                        # Проверяем, не устарела ли игра
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            # Автоматически отменяем старую игру
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                try:
                    bot.send_message(
                        call.message.chat.id,
                        """<blockquote expandable>╔══════════════════════╗
   📝 <b>ВВОД КОЛИЧЕСТВА МИН</b> 📝
╚══════════════════════╝</blockquote>

<blockquote>
Введите количество мин (2-24):
</blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения mine_custom_count: {e}")
                    clear_action_processing(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_mines)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            # Проверяем наличие активной игры
            with mines_lock:
                if user_id not in active_games:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра не найдена")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                game = active_games[user_id]

            # Проверяем, активна ли еще игра
            if not game.game_active:
                try:
                    bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                except:
                    pass
                clear_action_processing(user_id, action_key)
                return

            if call.data.startswith("mine_cell_"):
                parts = call.data.split("_")
                x, y = int(parts[2]), int(parts[3])

                if game.revealed[x][y]:
                    try:
                        bot.answer_callback_query(call.id, "❌ Уже открыто!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                # Используем лок игры для защиты от конкурентного доступа
                with game.action_lock:
                    # Проверяем время последнего действия в игре
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.3:  # УВЕЛИЧЕНО ДО 0.3 секунды
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    success = game.reveal_cell(x, y)

                    if not success:
                        users_data = load_users_data()
                        users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
                        save_users_data(users_data)

                        # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
                        try:
                            add_game_to_history(
                                user_id=int(user_id),
                                bet_amount=game.bet_amount,
                                win_amount=0.0,
                                is_win=False,
                                game_type="mines"
                            )
                        except Exception as e:
                            logging.error(f"Ошибка записи проигрыша в историю: {e}")

                        # Удаляем игру из активных
                        with mines_lock:
                            if user_id in active_games:
                                del active_games[user_id]

                        try:
                            bot.edit_message_text(
                                format_game_result(game, 0, False),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_game_keyboard(game, game_over=True)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text mine_cell проигрыш: {e}")
                        finally:
                            clear_action_processing(user_id, action_key)
                        return
                    else:
                        try:
                            bot.edit_message_text(
                                format_game_info(game),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_game_keyboard(game)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text mine_cell успех: {e}")
                        finally:
                            clear_action_processing(user_id, action_key)
                        return

            elif call.data == "mine_cashout":
                # Используем лок игры для защиты от конкурентного доступа
                with game.action_lock:
                    # Проверяем время последнего действия в игре
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.3:  # УВЕЛИЧЕНО ДО 0.3 секунды
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    # Проверяем, что игра все еще активна
                    if not game.game_active:
                        try:
                            bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    # Помечаем игру как завершенную ПЕРЕД начислением
                    game.game_active = False
                    
                    win_amount = game.bet_amount * game.multiplier
                    
                    users_data = load_users_data()
                    users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + win_amount, 2)
                    save_users_data(users_data)

                    # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
                    try:
                        add_game_to_history(
                            user_id=int(user_id),
                            bet_amount=game.bet_amount,
                            win_amount=win_amount,
                            is_win=True,
                            game_type="mines"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка записи выигрыша в историю: {e}")

                    # ДОБАВЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС (6% от выигрыша) в отдельном потоке
                    threading.Thread(
                        target=lambda: referrals.add_referral_bonus(user_id, win_amount),
                        daemon=True
                    ).start()

                    # Удаляем игру из активных
                    with mines_lock:
                        if user_id in active_games:
                            del active_games[user_id]

                    try:
                        bot.edit_message_text(
                            format_game_result(game, win_amount, True),
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=get_game_keyboard(game, game_over=True)
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text mine_cashout: {e}")
                    finally:
                        clear_action_processing(user_id, action_key)
                    return

            elif call.data == "mine_ignore":
                # Игнорируем нажатия на уже открытые клетки
                try:
                    bot.answer_callback_query(call.id)
                except:
                    pass
                finally:
                    clear_action_processing(user_id, action_key)
                return

        except Exception as e:
            # Общая обработка ошибок
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                return
            elif "message is not modified" in str(e):
                # Это нормальная ситуация - игрок быстро нажимает
                pass
            else:
                logging.error(f"Ошибка в mines_callback_handler: {e}")
                try:
                    bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
                except:
                    pass
            # Всегда очищаем обработку
            clear_action_processing(user_id, action_key if 'action_key' in locals() else "")

# Публичная функция для запуска игры из main.py
def mines_start(message):
    """Функция для запуска игры Мины из внешних модулей"""
    user_id = str(message.from_user.id)

    # Проверяем ограничение по времени
    if not rate_limit_mines(user_id):
        bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
        return

    # Проверяем активную игру пользователя
    with mines_lock:
        if user_id in active_games:
            # Проверяем, не устарела ли игра
            game = active_games[user_id]
            current_time = time.time()
            if current_time - game.created_time > GAME_TIMEOUT:
                # Автоматически отменяем старую игру
                cancel_user_game(user_id)
            else:
                bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                return

    users_data = load_users_data()

    if user_id not in users_data:
        users_data[user_id] = {'balance': 0}
        save_users_data(users_data)

    balance = users_data[user_id].get('balance', 0)
    balance_rounded = round(balance, 2)

    bot.send_message(
        message.chat.id,
        f"""<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
        parse_mode='HTML',
        reply_markup=get_bet_selection_keyboard()
    )

# Экспортируем функцию для принудительной отмены игры
def cancel_game(user_id):
    """Внешняя функция для отмены игры пользователя"""
    return cancel_user_game(str(user_id))

# Экспортируем функцию для получения списка активных игр
def get_active_games():
    """Возвращает список активных игр (для админки)"""
    with mines_lock:
        return {user_id: {
            'bet_amount': game.bet_amount,
            'mines_count': game.mines_count,
            'opened_cells': game.opened_cells,
            'created_time': game.created_time,
            'last_action_time': game.last_action_time,
            'age_seconds': time.time() - game.created_time,
            'chat_id': game.chat_id,
            'message_id': game.message_id
        } for user_id, game in active_games.items()}