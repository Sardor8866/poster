import telebot
from telebot import types
import random
import json
import time
import threading
import logging
import hashlib
import os

import referrals

try:
    from leaders import add_game_to_history
except ImportError:
    def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="tower"):
        logging.warning(f"Модуль лидеров не найден, игра не записана в историю: {user_id}")
        return False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TowerGame:
    def __init__(self, user_id, mines_count, bet_amount, chat_id=None, message_id=None):
        # Валидация входных данных для безопасности
        if not isinstance(user_id, (str, int)):
            raise ValueError("Invalid user_id type")
        if not isinstance(mines_count, int) or mines_count < 1 or mines_count > 4:
            raise ValueError("Invalid mines_count: must be between 1 and 4")
        if not isinstance(bet_amount, (int, float)) or bet_amount <= 0:
            raise ValueError("Invalid bet_amount: must be positive")
        
        self.user_id = str(user_id)
        self.mines_count = int(mines_count)
        self.bet_amount = float(bet_amount)
        self.floor = 0
        self.game_active = True
        self.session_token = self.generate_session_token(user_id, 'tower')
        self.multipliers = {
            1: [1.2, 1.6, 2.3, 4.7],
            2: [1.5, 2.4, 6.0, 24.0],
            3: [1.8, 4.2, 16.0, 120.0],
            4: [2.4, 7.0, 42.0, 400.0],
            5: [3.2, 12.5, 90.0, 1600.0],
            6: [3.9, 20.0, 160.0, 3000.0]
        }
        self.mine_floors = {}
        self.selected_cells = {}
        self.last_action_time = time.time()
        self.action_lock = threading.Lock()
        self.created_time = time.time()
        self.chat_id = chat_id
        self.message_id = message_id
        self.generate_mines()

    def generate_session_token(self, user_id, game_type):
        """Генерирует уникальный токен для сессии игры"""
        timestamp = str(time.time())
        random_component = str(random.randint(100000, 999999))
        data = f"{user_id}_{game_type}_{timestamp}_{random_component}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def generate_mines(self):
        for floor in range(1, 7):
            available_cells = list(range(5))
            random.shuffle(available_cells)
            self.mine_floors[floor] = available_cells[:self.mines_count]

    def climb_floor(self, selected_cell):
        # Валидация входных данных
        if not isinstance(selected_cell, int) or selected_cell < 0 or selected_cell >= 5:
            raise ValueError("Invalid selected_cell")
        
        self.floor += 1
        current_floor = self.floor

        if current_floor in self.mine_floors and selected_cell in self.mine_floors[current_floor]:
            self.game_active = False
            return False
        return True

    def add_selected_cell(self, floor, cell):
        # Валидация входных данных
        if not isinstance(floor, int) or floor < 1 or floor > 6:
            raise ValueError("Invalid floor")
        if not isinstance(cell, int) or cell < 0 or cell >= 5:
            raise ValueError("Invalid cell")
        
        if floor not in self.selected_cells:
            self.selected_cells[floor] = []
        if cell not in self.selected_cells[floor]:
            self.selected_cells[floor].append(cell)

    def get_current_multiplier(self):
        if self.floor == 0:
            return 1.0
        mine_index = self.mines_count - 1
        if self.floor in self.multipliers and mine_index < len(self.multipliers[self.floor]):
            return self.multipliers[self.floor][mine_index]
        return 1.0

    def get_next_multiplier(self):
        next_floor = self.floor + 1
        if next_floor > 6:
            next_floor = 6
        mine_index = self.mines_count - 1
        if next_floor in self.multipliers and mine_index < len(self.multipliers[next_floor]):
            return self.multipliers[next_floor][mine_index]
        return 1.0

users_data_lock = threading.Lock()

# Константы для безопасной работы с файлами
DATA_FILE = 'users_data.json'
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB максимальный размер файла

def load_users_data():
    """Загружает данные пользователей"""
    try:
        # Проверка размера файла для безопасности
        if os.path.exists(DATA_FILE):
            file_size = os.path.getsize(DATA_FILE)
            if file_size > MAX_FILE_SIZE:
                logging.error(f"Файл данных слишком большой: {file_size} байт")
                return {}
        
        with users_data_lock:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Валидация структуры данных
                if not isinstance(data, dict):
                    logging.error("Неверная структура данных")
                    return {}
                return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON: {e}")
        return {}
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
        return {}

def save_users_data(data):
    try:
        # Валидация данных перед сохранением
        if not isinstance(data, dict):
            logging.error("Попытка сохранить некорректные данные")
            return False
        
        with users_data_lock:
            # Создание временного файла для атомарной записи
            temp_file = f"{DATA_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Атомарная замена файла
            os.replace(temp_file, DATA_FILE)
            return True
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")
        # Удаление временного файла в случае ошибки
        try:
            if os.path.exists(f"{DATA_FILE}.tmp"):
                os.remove(f"{DATA_FILE}.tmp")
        except:
            pass
        return False

active_tower_games = {}
user_temp_data_tower = {}
last_click_time_tower = {}
tower_lock = threading.RLock()  # Используем RLock для рекурсивных блокировок
processing_actions_tower = {}
processing_lock_tower = threading.Lock()

MIN_BET = 25
MAX_BET = 1000000  # Установлен разумный максимум вместо infinity

GAME_TIMEOUT = 300

def cleanup_inactive_tower_games():
    """Очистка неактивных игр и возврат ставок"""
    current_time = time.time()
    games_to_remove = []
    
    # Быстро собираем игры для удаления
    with tower_lock:
        for user_id, game in list(active_tower_games.items()):
            if current_time - game.created_time > GAME_TIMEOUT:
                games_to_remove.append((user_id, game.session_token, game))
    
    # Обрабатываем удаление вне основной блокировки
    for user_id, session_token, game in games_to_remove:
        try:
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Возвращена ставка {game.bet_amount} пользователю {user_id} за неактивную игру Башня")
            
            if game.chat_id and game.message_id:
                try:
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
└ 📊 Достигнут этаж: <b>{game.floor}/6</b>
</blockquote>

<i>Ваша ставка возвращена на баланс! ✅</i>
"""
                    bot.edit_message_text(
                        timeout_message,
                        game.chat_id,
                        game.message_id,
                        parse_mode='HTML'
                    )
                    time.sleep(2)
                except Exception as e:
                    if "message is not modified" not in str(e) and "message to edit not found" not in str(e):
                        logging.error(f"Ошибка при редактировании сообщения игры Башня {user_id}: {e}")
            
            # Удаляем игру только если она всё ещё существует с тем же токеном
            with tower_lock:
                if user_id in active_tower_games and active_tower_games[user_id].session_token == session_token:
                    del active_tower_games[user_id]
            
            # Очищаем временные данные
            with tower_lock:
                if user_id in user_temp_data_tower:
                    del user_temp_data_tower[user_id]
            
            with tower_lock:
                if user_id in last_click_time_tower:
                    del last_click_time_tower[user_id]
            
            # Очищаем обработку действий
            with processing_lock_tower:
                keys_to_remove = [k for k in processing_actions_tower.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions_tower[k]
                    
        except Exception as e:
            logging.error(f"Ошибка при удалении неактивной игры Башня пользователя {user_id}: {e}")

def start_cleanup_tower_thread():
    """Запускает поток для периодической очистки неактивных игр"""
    def cleanup_worker():
        while True:
            try:
                cleanup_inactive_tower_games()
                time.sleep(60)
            except Exception as e:
                logging.error(f"Ошибка в cleanup_worker (Башня): {e}")
                time.sleep(60)
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    logging.info("Поток очистки неактивных игр Башня запущен")

def rate_limit_tower(user_id):
    """Проверка ограничения по времени между нажатиями (0.4 секунды)"""
    current_time = time.time()
    with tower_lock:
        if user_id in last_click_time_tower:
            if current_time - last_click_time_tower[user_id] < 0.4:
                return False
        last_click_time_tower[user_id] = current_time
    return True

def is_action_processing_tower(user_id, action_key=""):
    """Проверяет, обрабатывается ли уже действие пользователя"""
    key = f"{user_id}_{action_key}"
    with processing_lock_tower:
        if key in processing_actions_tower:
            if time.time() - processing_actions_tower[key] < 0.4:
                return True
            else:
                del processing_actions_tower[key]
        return False

def mark_action_processing_tower(user_id, action_key=""):
    """Отмечает начало обработки действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock_tower:
        processing_actions_tower[key] = time.time()

def clear_action_processing_tower(user_id, action_key=""):
    """Очищает отметку о обработке действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock_tower:
        if key in processing_actions_tower:
            del processing_actions_tower[key]

def get_bet_selection_keyboard_tower():
    """Клавиатура выбора ставки для башни"""
    markup = types.InlineKeyboardMarkup(row_width=5)
    bets = ["25", "50", "125", "250", "500"]
    buttons = [types.InlineKeyboardButton(f"{bet_value}₽", callback_data=f"tower_bet_{bet_value}") for bet_value in bets]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="tower_custom_bet"))
    return markup

def get_mines_selection_keyboard_tower():
    markup = types.InlineKeyboardMarkup(row_width=4)
    mines_counts = ["1", "2", "3", "4"]
    buttons = [types.InlineKeyboardButton(f"{count}", callback_data=f"tower_mines_{count}") for count in mines_counts]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="tower_custom_mines"))
    return markup

def get_tower_keyboard(game, show_all=False, show_current_mines=False):
    markup = types.InlineKeyboardMarkup(row_width=6)

    for floor_num in range(6, 0, -1):
        row_buttons = []

        mine_index = game.mines_count - 1
        multiplier = game.multipliers[floor_num][mine_index]
        if multiplier < 10:
            mult_text = f"x{multiplier:.2f}"
        elif multiplier < 100:
            mult_text = f"x{multiplier:.1f}"
        else:
            mult_text = f"x{multiplier:.0f}"

        mult_button = types.InlineKeyboardButton(f"{mult_text}", callback_data="tower_ignore")
        row_buttons.append(mult_button)

        for cell in range(5):
            if show_all:
                if floor_num in game.mine_floors and cell in game.mine_floors[floor_num]:
                    emoji = "💣"
                elif floor_num in game.selected_cells and cell in game.selected_cells[floor_num]:
                    emoji = "💎"
                else:
                    emoji = "◾"
                callback_data = "tower_ignore"

            elif show_current_mines and floor_num == game.floor:
                if cell in game.mine_floors.get(floor_num, []):
                    emoji = "💣"
                elif cell in game.selected_cells.get(floor_num, []):
                    emoji = "💎"
                else:
                    emoji = "◾"
                callback_data = "tower_ignore"

            else:
                if floor_num == game.floor + 1:
                    emoji = "☁️"
                    callback_data = f"tower_climb_{floor_num}_{cell}"
                elif floor_num <= game.floor:
                    if floor_num in game.mine_floors and cell in game.mine_floors[floor_num]:
                        emoji = "💣"
                    elif floor_num in game.selected_cells and cell in game.selected_cells[floor_num]:
                        emoji = "💎"
                    else:
                        emoji = "◾"
                    callback_data = "tower_ignore"
                else:
                    emoji = "◾"
                    callback_data = "tower_ignore"

            row_buttons.append(types.InlineKeyboardButton(emoji, callback_data=callback_data))

        markup.row(*row_buttons)

    if (not show_all and game.floor > 0 and game.game_active) or show_current_mines:
        current_mult = game.get_current_multiplier()
        markup.row(types.InlineKeyboardButton(
            f"💰 ЗАБРАТЬ {round(game.bet_amount * current_mult, 2)}₽",
            callback_data="tower_cashout"
        ))

    return markup

def format_tower_info(game):
    """Форматирует информацию об игре в красивый вид"""
    # Санитизация данных для предотвращения HTML injection
    bet_amount = round(float(game.bet_amount), 2)
    floor = int(game.floor)
    mines_count = int(game.mines_count)
    current_mult = round(float(game.get_current_multiplier()), 2)
    next_mult = round(float(game.get_next_multiplier()), 2)
    
    game_lifetime = time.time() - game.created_time
    minutes = int(game_lifetime // 60)
    seconds = int(game_lifetime % 60)
    
    time_left = GAME_TIMEOUT - game_lifetime
    if time_left > 0:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        time_info = f"{minutes} мин {seconds} сек (автоудаление через {minutes_left}:{seconds_left:02d})"
    else:
        time_info = f"{minutes} мин {seconds} сек (ожидание удаления)"

    tower_info = f"""
<blockquote expandable>╔══════════════════════╗
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
<b>🎯 Конфигурация:</b>
├ 💸Ставка: <b>{bet_amount}₽</b>
├ 💣Мин на этаж: <b>{mines_count}</b>
└ 📌Этаж: <b>{floor}/6</b>

<b>📊 Множители:</b>
├ ⬅️ Прошлый: <b>x{current_mult:.2f}</b>
├ ✅ Текущий: <b>x{current_mult:.2f}</b>
└ ➡️ Следующий: <b>x{next_mult:.2f}</b>

<b>⏰ Время игры:</b>
└ {time_info}
</blockquote>

<i>Выберите безопасную ячейку на этаже {floor + 1}! Игра будет закрыта через 5 минут бездействия.</i>
"""
    return tower_info

def format_tower_result(game, win_amount, is_win=False):
    """Форматирует результат игры"""
    # Санитизация данных
    bet_amount = round(float(game.bet_amount), 2)
    floor = int(game.floor)
    mines_count = int(game.mines_count)
    current_mult = round(float(game.get_current_multiplier()), 2)
    
    if is_win:
        win_amount = round(float(win_amount), 2)
        return f"""
<blockquote expandable>╔══════════════════════╗
   🎉 <b>ПОБЕДА!</b> 🎉
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{bet_amount}₽</b>
├ 🍀Выигрыш: <b>{win_amount}₽</b>
└ 📌Множитель: <b>x{current_mult:.2f}</b>

<b>📊 Статистика:</b>
├ 💹Достигнут этаж: <b>{floor}/6</b>
└ 💣Мин на этаж: <b>{mines_count}</b>
</blockquote>

<i>Вы успешно прошли башню! Поздравляем! 🏰</i>
"""
    else:
        return f"""
<blockquote expandable>╔══════════════════════╗
   💣 <b>ПОРАЖЕНИЕ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{bet_amount}₽</b>
├ 📉Потеряно: <b>{bet_amount}₽</b>
└ 📌Множитель: <b>x{current_mult:.2f}</b>

<b>📊 Статистика:</b>
├ ❌Попали на мину на этаже: <b>{floor}/6</b>
└ 💣Мин на этаж: <b>{mines_count}</b>
</blockquote>

<i>Попали на мину! Попробуйте еще раз! 💪</i>
"""

bot = None

def cancel_tower_user_game(user_id, notify_user=True):
    """Принудительно отменяет игру пользователя и возвращает ставку"""
    try:
        with tower_lock:
            if user_id not in active_tower_games:
                return False
            
            game = active_tower_games[user_id]
            
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Принудительно возвращена ставка {game.bet_amount} пользователю {user_id} за игру Башня")
            
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
└ 📊 Достигнут этаж: <b>{game.floor}/6</b>
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
                        logging.error(f"Ошибка при редактировании сообщения отмены Башня {user_id}: {e}")
                        try:
                            bot.send_message(game.chat_id, cancel_message, parse_mode='HTML')
                        except:
                            pass
            
            del active_tower_games[user_id]
            
            if user_id in user_temp_data_tower:
                del user_temp_data_tower[user_id]
            
            if user_id in last_click_time_tower:
                del last_click_time_tower[user_id]
            
            with processing_lock_tower:
                keys_to_remove = [k for k in processing_actions_tower.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions_tower[k]
            
            return True
            
    except Exception as e:
        logging.error(f"Ошибка при отмене игры Башня пользователя {user_id}: {e}")
        return False

def start_tower_game_from_command(user_id, mines_count, bet_amount, message=None, chat_id=None, message_id=None):
    """Функция для запуска игры через команду"""
    try:
        if not rate_limit_tower(user_id):
            if message:
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
            return False

        with tower_lock:
            if user_id in active_tower_games:
                game = active_tower_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    cancel_tower_user_game(user_id)
                else:
                    if message:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return False

        if mines_count < 1 or mines_count > 4:
            if message:
                bot.send_message(message.chat.id, "❌ Количество мин должно быть от 1 до 4!")
            return False

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

        if message:
            game = TowerGame(user_id, mines_count, bet_amount, chat_id=message.chat.id)
        elif chat_id:
            game = TowerGame(user_id, mines_count, bet_amount, chat_id=chat_id, message_id=message_id)
        else:
            game = TowerGame(user_id, mines_count, bet_amount)

        with tower_lock:
            active_tower_games[user_id] = game

        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)

        if message:
            sent_message = bot.send_message(
                message.chat.id,
                format_tower_info(game),
                parse_mode='HTML',
                reply_markup=get_tower_keyboard(game)
            )
            game.message_id = sent_message.message_id
        elif chat_id and message_id:
            try:
                bot.edit_message_text(
                    format_tower_info(game),
                    chat_id,
                    message_id,
                    parse_mode='HTML',
                    reply_markup=get_tower_keyboard(game)
                )
                game.message_id = message_id
            except Exception as e:
                if "message is not modified" not in str(e):
                    logging.error(f"Ошибка edit_message_text при запуске игры Башня: {e}")
                    sent_message = bot.send_message(
                        chat_id,
                        format_tower_info(game),
                        parse_mode='HTML',
                        reply_markup=get_tower_keyboard(game)
                    )
                    game.message_id = sent_message.message_id
        elif chat_id:
            sent_message = bot.send_message(
                chat_id,
                format_tower_info(game),
                parse_mode='HTML',
                reply_markup=get_tower_keyboard(game)
            )
            game.message_id = sent_message.message_id
        
        return True
    except Exception as e:
        logging.error(f"Ошибка в start_tower_game_from_command: {e}")
        if message:
            bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске игры!")
        return False

def parse_tower_command(text):
    """Парсит команду /башня или /tower и возвращает (количество_мин, сумма_ставки)"""
    try:
        parts = text.strip().split()
        
        if len(parts) < 3:
            return None, None
        
        command_lower = parts[0].lower()
        valid_commands = ['/башня', '/tower', 'башня', 'tower', '/лесенка', 'лесенка', '/лестница', 'лестница']
        
        if command_lower not in valid_commands:
            return None, None
        
        mines_count = None
        bet_amount = None
        
        for i in range(1, len(parts)):
            if not mines_count:
                try:
                    mines_count = int(parts[i])
                    if not (1 <= mines_count <= 4):
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

def register_tower_handlers(bot_instance):
    global bot
    bot = bot_instance
    
    start_cleanup_tower_thread()

    @bot.message_handler(func=lambda message: message.text and 
                        any(message.text.lower().startswith(cmd + ' ') or 
                            message.text.lower() == cmd for cmd in 
                            ['/башня', '/tower', 'башня', 'tower', 
                             '/лесенка', 'лесенка', '/лестница', 'лестница']))
    def tower_command_handler(message):
        user_id = str(message.from_user.id)
        
        mines_count, bet_amount = parse_tower_command(message.text)
        
        if mines_count is None or bet_amount is None:
            help_text = """<blockquote expandable>╔══════════════════════╗
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
<b>📖 Как играть:</b>
• Напишите <code>/башня 2 100</code> чтобы начать игру с 2 минами и ставкой 100₽
• Или используйте меню для настройки игры

<b>🎯 Правила:</b>
• Поднимайтесь по этажам башни (6 этажей)
• На каждом этаже выбирайте безопасную ячейку
• Избегайте мин - если выберете ячейку с миной, проиграете
• Каждый успешный этаж увеличивает множитель
• Заберите выигрыш в любой момент

<b>⚙️ Параметры:</b>
• Мин на этаж: от 1 до 4
• Этажей: 6
• Минимальная ставка: 25₽
• Игра автоматически закрывается через 5 минут бездействия (ставка возвращается)
</blockquote>"""
            bot.send_message(message.chat.id, help_text, parse_mode='HTML')
            return
        
        start_tower_game_from_command(user_id, mines_count, bet_amount, message=message)

    def process_custom_bet(message):
        try:
            user_id = str(message.from_user.id)

            if not rate_limit_tower(user_id):
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
                return

            with tower_lock:
                if user_id in active_tower_games:
                    game = active_tower_games[user_id]
                    current_time = time.time()
                    if current_time - game.created_time > GAME_TIMEOUT:
                        cancel_tower_user_game(user_id)
                    else:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                        return

            # Валидация и очистка ввода
            bet_text = message.text.strip()
            
            # Удаление валюты и пробелов
            bet_text = bet_text.replace('₽', '').replace(' ', '').replace(',', '.')
            
            bet_amount = float(bet_text)
            
            if bet_amount < MIN_BET:
                bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET}₽")
                return

            if bet_amount > MAX_BET:
                bot.send_message(message.chat.id, f"❌ Максимальная ставка: {MAX_BET}₽")
                return
            
            bet_amount = round(bet_amount, 2)

            users_data = load_users_data()

            if user_id not in users_data:
                users_data[user_id] = {'balance': 0}

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            with tower_lock:
                user_temp_data_tower[user_id] = {'bet_amount': bet_amount}

            bot.send_message(
                message.chat.id,
                """<blockquote expandable>╔══════════════════════╗
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (1-4):
</blockquote>""",
                parse_mode='HTML',
                reply_markup=get_mines_selection_keyboard_tower()
            )
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректную сумму!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_bet: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    def process_custom_mines_tower(message):
        try:
            user_id = str(message.from_user.id)

            mines_count = int(message.text)
            if not 1 <= mines_count <= 4:
                bot.send_message(message.chat.id, "❌ Введите число от 1 до 4!")
                return

            users_data = load_users_data()

            with tower_lock:
                if user_id in active_tower_games:
                    game = active_tower_games[user_id]
                    current_time = time.time()
                    if current_time - game.created_time > GAME_TIMEOUT:
                        cancel_tower_user_game(user_id)
                    else:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                        return

                if user_id not in user_temp_data_tower or 'bet_amount' not in user_temp_data_tower[user_id]:
                    bot.send_message(message.chat.id, "❌ Ошибка данных! Начните заново.")
                    return

                bet_amount = user_temp_data_tower[user_id]['bet_amount']

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            success = start_tower_game_from_command(
                user_id=user_id,
                mines_count=mines_count,
                bet_amount=bet_amount,
                message=message
            )

            if success:
                with tower_lock:
                    if user_id in user_temp_data_tower:
                        del user_temp_data_tower[user_id]

        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректное число!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_mines_tower: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    @bot.message_handler(func=lambda message: message.text in ["🏰 Башня", "башня", "Tower", "tower", "Лесенка", "лесенка", "Лестница", "лестница", "Ленсенька", "лесенька"])
    def tower_start_internal(message):
        user_id = str(message.from_user.id)

        if not rate_limit_tower(user_id):
            bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
            return

        with tower_lock:
            if user_id in active_tower_games:
                game = active_tower_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    cancel_tower_user_game(user_id)
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
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
            parse_mode='HTML',
            reply_markup=get_bet_selection_keyboard_tower()
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('tower_'))
    def tower_callback_handler(call):
        try:
            user_id = str(call.from_user.id)

            # Валидация callback_data для предотвращения injection
            if not call.data or len(call.data) > 100:
                logging.warning(f"Подозрительный callback_data от {user_id}")
                return
            
            allowed_prefixes = ['tower_bet_', 'tower_custom_bet', 'tower_mines_', 'tower_custom_mines',
                              'tower_climb_', 'tower_cashout', 'tower_ignore']
            
            if not any(call.data.startswith(prefix) or call.data == prefix.rstrip('_') for prefix in allowed_prefixes):
                logging.warning(f"Неизвестный callback: {call.data} от {user_id}")
                return

            action_key = ""
            if call.data.startswith("tower_climb_"):
                parts = call.data.split('_')
                if len(parts) != 4:
                    logging.warning(f"Некорректный формат tower_climb от {user_id}")
                    return
                try:
                    floor_num = int(parts[2])
                    cell_num = int(parts[3])
                    # Валидация диапазонов
                    if not (1 <= floor_num <= 6) or not (0 <= cell_num < 5):
                        logging.warning(f"Некорректные параметры tower_climb от {user_id}")
                        return
                    action_key = f"climb_{floor_num}_{cell_num}"
                except (ValueError, IndexError):
                    logging.warning(f"Ошибка парсинга tower_climb от {user_id}")
                    return
            elif call.data == "tower_cashout":
                action_key = "cashout"
            elif call.data.startswith("tower_bet_"):
                bet = call.data.split("_")[2]
                action_key = f"bet_{bet}"
            elif call.data.startswith("tower_mines_"):
                count = call.data.split("_")[2]
                action_key = f"dragons_{count}"
            else:
                action_key = call.data

            if is_action_processing_tower(user_id, action_key):
                try:
                    bot.answer_callback_query(call.id, "⏳ Действие уже обрабатывается...", show_alert=False)
                except:
                    pass
                return

            mark_action_processing_tower(user_id, action_key)

            users_data = load_users_data()

            if call.data.startswith("tower_bet_"):
                # Валидация суммы ставки
                try:
                    bet_str = call.data.split("_")[2]
                    bet_amount = float(bet_str)
                    
                    if bet_amount < MIN_BET or bet_amount > MAX_BET:
                        try:
                            bot.answer_callback_query(
                                call.id, 
                                f"❌ Ставка должна быть от {MIN_BET}₽ до {MAX_BET}₽",
                                show_alert=True
                            )
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return
                except (ValueError, IndexError):
                    try:
                        bot.answer_callback_query(call.id, "❌ Некорректная сумма ставки", show_alert=True)
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return
                
                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_tower_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing_tower(user_id, action_key)
                            return

                bet_amount = float(call.data.split("_")[2])

                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                with tower_lock:
                    user_temp_data_tower[user_id] = {'bet_amount': bet_amount}

                try:
                    bot.edit_message_text(
                        """<blockquote expandable>╔══════════════════════╗
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (1-4):
</blockquote>""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_mines_selection_keyboard_tower()
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logging.error(f"Ошибка edit_message_text tower_bet: {e}")
                finally:
                    clear_action_processing_tower(user_id, action_key)
                return

            elif call.data.startswith("tower_mines_"):
                # Валидация количества мин
                try:
                    mines_str = call.data.split("_")[2]
                    mines_count = int(mines_str)
                    
                    if mines_count < 1 or mines_count > 4:
                        try:
                            bot.answer_callback_query(call.id, "❌ Количество мин должно быть от 1 до 4", show_alert=True)
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return
                except (ValueError, IndexError):
                    try:
                        bot.answer_callback_query(call.id, "❌ Некорректное количество мин", show_alert=True)
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_tower_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing_tower(user_id, action_key)
                            return

                    if user_id not in user_temp_data_tower or 'bet_amount' not in user_temp_data_tower[user_id]:
                        try:
                            bot.answer_callback_query(call.id, "❌ Ошибка данных!")
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return

                    bet_amount = user_temp_data_tower[user_id]['bet_amount']

                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                success = start_tower_game_from_command(
                    user_id=user_id,
                    mines_count=mines_count,
                    bet_amount=bet_amount,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )

                if success:
                    with tower_lock:
                        if user_id in user_temp_data_tower:
                            del user_temp_data_tower[user_id]

                clear_action_processing_tower(user_id, action_key)
                return

            elif call.data == "tower_custom_bet":
                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_tower_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing_tower(user_id, action_key)
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
                    logging.error(f"Ошибка отправки сообщения tower_custom_bet: {e}")
                    clear_action_processing_tower(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_bet)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing_tower(user_id, action_key)
                return

            elif call.data == "tower_custom_mines":
                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_tower_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing_tower(user_id, action_key)
                            return

                try:
                    bot.send_message(
                        call.message.chat.id,
                        """<blockquote expandable>╔══════════════════════╗
   📝 <b>ВВОД КОЛИЧЕСТВА ДРАКОНОВ</b> 📝
╚══════════════════════╝</blockquote>

<blockquote>
Введите количество мин (1-4):
</blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения tower_custom_mines: {e}")
                    clear_action_processing_tower(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_mines_tower)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing_tower(user_id, action_key)
                return

            elif call.data.startswith("tower_climb_"):
                # Получаем игру без долгой блокировки
                game = None
                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]

                if not game:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра не найдена")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                if not game.game_active:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                # Используем уже провалидированные значения из начала функции
                parts = call.data.split('_')
                floor_num = int(parts[2])
                cell_num = int(parts[3])

                # Быстрая проверка времени
                with game.action_lock:
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.4:
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    # Обработка с try-except для валидационных ошибок
                    try:
                        game.add_selected_cell(floor_num, cell_num)
                    except ValueError as e:
                        logging.error(f"Ошибка валидации в add_selected_cell: {e}")
                        try:
                            bot.answer_callback_query(call.id, "❌ Ошибка обработки хода", show_alert=True)
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return

                    try:
                        success = game.climb_floor(cell_num)
                    except ValueError as e:
                        logging.error(f"Ошибка валидации в climb_floor: {e}")
                        try:
                            bot.answer_callback_query(call.id, "❌ Ошибка обработки хода", show_alert=True)
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return

                    if not success:
                        users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
                        save_users_data(users_data)

                        try:
                            add_game_to_history(
                                user_id=int(user_id),
                                bet_amount=game.bet_amount,
                                win_amount=0.0,
                                is_win=False,
                                game_type="tower"
                            )
                        except Exception as e:
                            logging.error(f"Ошибка записи проигрыша в историю: {e}")

                        with tower_lock:
                            if user_id in active_tower_games and active_tower_games[user_id].session_token == game.session_token:
                                del active_tower_games[user_id]

                        try:
                            bot.edit_message_text(
                                format_tower_result(game, 0, False),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_tower_keyboard(game, show_all=True)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text tower_climb поражение: {e}")
                        finally:
                            clear_action_processing_tower(user_id, action_key)
                        return
                    else:
                        try:
                            bot.edit_message_text(
                                format_tower_info(game),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_tower_keyboard(game, show_current_mines=True)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text tower_climb успех: {e}")
                        finally:
                            clear_action_processing_tower(user_id, action_key)
                        return

            elif call.data == "tower_cashout":
                # Получаем игру без долгой блокировки
                game = None
                with tower_lock:
                    if user_id in active_tower_games:
                        game = active_tower_games[user_id]

                if not game:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра не найдена")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                if not game.game_active:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                    except:
                        pass
                    clear_action_processing_tower(user_id, action_key)
                    return

                with game.action_lock:
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.4:
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing_tower(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    game.game_active = False
                    
                    win_amount = game.bet_amount * game.get_current_multiplier()
                    users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + win_amount, 2)
                    save_users_data(users_data)
                    
                    # Уведомляем пользователя
                    try:
                        bot.answer_callback_query(call.id, f"✅ Выигрыш {round(win_amount, 2)}₽ зачислен!")
                    except:
                        pass

                    try:
                        add_game_to_history(
                            user_id=int(user_id),
                            bet_amount=game.bet_amount,
                            win_amount=win_amount,
                            is_win=True,
                            game_type="tower"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка записи выигрыша в историю: {e}")

                    threading.Thread(
                        target=lambda: referrals.add_referral_bonus(user_id, win_amount),
                        daemon=True
                    ).start()

                    # Сначала обновляем клавиатуру
                    try:
                        bot.edit_message_text(
                            format_tower_result(game, win_amount, True),
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=get_tower_keyboard(game, show_all=True)
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text tower_cashout: {e}")

                    # Потом удаляем игру
                    with tower_lock:
                        if user_id in active_tower_games and active_tower_games[user_id].session_token == game.session_token:
                            del active_tower_games[user_id]
                    
                    clear_action_processing_tower(user_id, action_key)
                    return

            elif call.data == "tower_ignore":
                try:
                    bot.answer_callback_query(call.id)
                except:
                    pass
                finally:
                    clear_action_processing_tower(user_id, action_key)
                return

        except Exception as e:
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                return
            elif "message is not modified" in str(e):
                pass
            else:
                logging.error(f"Ошибка в tower_callback_handler: {e}")
                try:
                    bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
                except:
                    pass
            clear_action_processing_tower(user_id, action_key if 'action_key' in locals() else "")

def tower_start(message):
    """Функция для запуска игры Башня из внешних модулей"""
    user_id = str(message.from_user.id)

    if not rate_limit_tower(user_id):
        bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
        return

    with tower_lock:
        if user_id in active_tower_games:
            game = active_tower_games[user_id]
            current_time = time.time()
            if current_time - game.created_time > GAME_TIMEOUT:
                cancel_tower_user_game(user_id)
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
   🏰 <b>ИГРА БАШНЯ</b> 🏰
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
        parse_mode='HTML',
        reply_markup=get_bet_selection_keyboard_tower()
    )

def cancel_tower_game(user_id):
    """Внешняя функция для отмены игры пользователя"""
    return cancel_tower_user_game(str(user_id))

def get_active_tower_games():
    """Возвращает список активных игр (для админки)"""
    with tower_lock:
        return {user_id: {
            'bet_amount': game.bet_amount,
            'mines_count': game.mines_count,
            'floor': game.floor,
            'created_time': game.created_time,
            'last_action_time': game.last_action_time,
            'age_seconds': time.time() - game.created_time,
            'chat_id': game.chat_id,
            'message_id': game.message_id
        } for user_id, game in active_tower_games.items()}
