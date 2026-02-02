import telebot
from telebot import types
import json
import time
import threading
from datetime import datetime, timedelta
import logging
import html
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class LeadersModule:
    def __init__(self):
        self.users_data_lock = threading.Lock()
        self.game_history_lock = threading.Lock()
        self.transactions_lock = threading.Lock()
        
    def safe_file_operation(self, filename, mode='r', default=None, data=None):
        """Безопасная операция с файлами с проверкой пути"""
        try:
            # Защита от Path Traversal
            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, filename)
            
            # Проверяем, что файл находится в нужной директории
            if not os.path.commonpath([base_dir, os.path.dirname(file_path)]) == base_dir:
                logging.error(f"Попытка доступа к файлу вне рабочей директории: {filename}")
                return default
            
            if mode == 'r' and data is not None:
                raise ValueError("Режим 'r' не поддерживает запись данных")
                
            if mode == 'w' or mode == 'a':
                if data is None:
                    raise ValueError("Для записи данные обязательны")
                
                # Атомарная запись через временный файл
                temp_file = file_path + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(temp_file, file_path)
                return True
                
            elif mode == 'r':
                # Проверка размера файла (макс 50MB)
                if os.path.exists(file_path):
                    if os.path.getsize(file_path) > 50 * 1024 * 1024:
                        logging.error(f"Файл слишком большой: {filename}")
                        return default
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                return default
                
        except json.JSONDecodeError as e:
            logging.error(f"Ошибка парсинга JSON в файле {filename}: {e}")
            # Создаем backup поврежденного файла
            if os.path.exists(file_path):
                backup_path = file_path + '.backup_' + str(int(time.time()))
                os.rename(file_path, backup_path)
            return default
        except Exception as e:
            logging.error(f"Ошибка работы с файлом {filename}: {e}")
            return default

    def load_users_data(self):
        """Загружает данные пользователей"""
        try:
            with self.users_data_lock:
                return self.safe_file_operation('users_data.json', mode='r', default={})
        except Exception as e:
            logging.error(f"Ошибка загрузки данных: {e}")
            return {}

    def load_game_history(self):
        """Загружает историю игр"""
        try:
            with self.game_history_lock:
                return self.safe_file_operation('game_history.json', mode='r', default={})
        except Exception as e:
            logging.error(f"Ошибка загрузки истории игр: {e}")
            return {}

    def load_transactions(self):
        """Загружает историю транзакций"""
        try:
            with self.transactions_lock:
                return self.safe_file_operation('transactions.json', mode='r', default=[])
        except Exception as e:
            logging.error(f"Ошибка загрузки транзакций: {e}")
            return []

    def format_number(self, num):
        """Форматирует число с пробелами"""
        try:
            # Безопасное преобразование числа
            if isinstance(num, (int, float)):
                return f"{int(num):,}".replace(",", ".")
            elif isinstance(num, str):
                # Пробуем преобразовать строку в число
                num_float = float(num)
                return f"{int(num_float):,}".replace(",", ".")
            else:
                return "0"
        except (ValueError, TypeError):
            return "0"

    def validate_user_id(self, user_id):
        """Валидация ID пользователя"""
        try:
            user_id_int = int(user_id)
            # Telegram ID обычно положительные и не слишком большие
            if 0 < user_id_int < 10**12:  # Разумные ограничения
                return user_id_int
            else:
                logging.warning(f"Подозрительный user_id: {user_id}")
                return None
        except (ValueError, TypeError):
            logging.warning(f"Некорректный user_id: {user_id}")
            return None

    def validate_period(self, period):
        """Валидация периода"""
        valid_periods = ["today", "week", "month", "all"]
        return period if period in valid_periods else "all"

    def validate_metric(self, metric):
        """Валидация метрики"""
        valid_metrics = ["turnover", "wins", "deposits", "withdrawals"]
        return metric if metric in valid_metrics else "turnover"

    def get_time_period_filter(self, period):
        """Возвращает timestamp начала периода"""
        try:
            now = datetime.now()
            period = self.validate_period(period)
            
            if period == "today":
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                return int(start_of_day.timestamp())
            elif period == "week":
                start_of_week = now - timedelta(days=now.weekday())
                start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
                return int(start_of_week.timestamp())
            elif period == "month":
                start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return int(start_of_month.timestamp())
            else:  # "all"
                return 0
        except Exception as e:
            logging.error(f"Ошибка расчета периода {period}: {e}")
            return 0

    def calculate_user_statistics(self, user_id, period="all"):
        """Рассчитывает статистику пользователя за указанный период"""
        try:
            # Валидация user_id
            validated_user_id = self.validate_user_id(user_id)
            if validated_user_id is None:
                return {'turnover': 0, 'wins': 0, 'deposits': 0, 'withdrawals': 0, 'net_wins': 0}
            
            # Валидация периода
            period = self.validate_period(period)
            
            # Загружаем данные только если нужно
            time_filter = self.get_time_period_filter(period)
            
            turnover = 0.0
            wins = 0.0
            total_wins = 0.0
            deposits = 0.0
            withdrawals = 0.0
            
            # Оптимизированная загрузка истории игр
            game_history = self.load_game_history()
            user_games = game_history.get(str(validated_user_id), [])
            
            for game in user_games[-1000:]:  # Ограничиваем последними 1000 играми
                try:
                    game_time = game.get('timestamp', 0)
                    if game_time >= time_filter:
                        bet_amount = float(game.get('bet_amount', 0))
                        win_amount = float(game.get('win_amount', 0))
                        is_win = bool(game.get('is_win', False))
                        
                        # Защита от переполнения
                        turnover = min(turnover + bet_amount, 10**15)  # Макс 1 квадриллион
                        
                        if is_win and win_amount > 0:
                            wins = min(wins + win_amount, 10**15)
                            total_wins = min(total_wins + win_amount, 10**15)
                except (ValueError, TypeError):
                    continue
            
            # Оптимизированная обработка транзакций
            transactions = self.load_transactions()
            for transaction in transactions[-5000:]:  # Ограничиваем последними 5000 транзакций
                try:
                    trans_user_id = str(transaction.get('user_id', ''))
                    if trans_user_id == str(validated_user_id):
                        trans_time = transaction.get('timestamp', 0)
                        if trans_time >= time_filter:
                            amount = float(transaction.get('amount', 0))
                            trans_type = str(transaction.get('type', ''))
                            
                            if trans_type == 'deposit':
                                deposits = min(deposits + amount, 10**15)
                            elif trans_type == 'withdraw':
                                withdrawals = min(withdrawals + amount, 10**15)
                except (ValueError, TypeError):
                    continue
            
            return {
                'turnover': round(max(0, turnover), 2),
                'wins': round(max(0, total_wins), 2),
                'deposits': round(max(0, deposits), 2),
                'withdrawals': round(max(0, withdrawals), 2),
                'net_wins': round(max(0, wins), 2)
            }
        except Exception as e:
            logging.error(f"Ошибка расчета статистики для пользователя {user_id}: {e}")
            return {'turnover': 0, 'wins': 0, 'deposits': 0, 'withdrawals': 0, 'net_wins': 0}

    def get_top_users(self, period="all", metric="turnover", limit=50):
        """Получает топ пользователей по указанному показателю"""
        try:
            # Валидация параметров
            period = self.validate_period(period)
            metric = self.validate_metric(metric)
            limit = min(max(1, int(limit)), 100)  # Ограничиваем от 1 до 100
            
            users_data = self.load_users_data()
            if not users_data:
                return []
            
            top_users = []
            processed_count = 0
            max_users_to_process = 10000  # Защита от DoS
            
            for user_id_str, user_data in users_data.items():
                if processed_count >= max_users_to_process:
                    logging.warning(f"Ограничение обработки пользователей достигнуто: {max_users_to_process}")
                    break
                    
                try:
                    user_id = self.validate_user_id(user_id_str)
                    if user_id is None:
                        continue
                    
                    stats = self.calculate_user_statistics(user_id, period)
                    
                    # Безопасное получение username
                    username = str(user_data.get('username', ''))[:32]  # Ограничение длины
                    if not username:
                        username = str(user_data.get('first_name', f'Игрок {user_id_str[:6]}...'))[:32]
                    
                    # Экранирование HTML
                    username = html.escape(username)
                    
                    value = float(stats.get(metric, 0))
                    
                    top_users.append({
                        'user_id': user_id,
                        'username': username,
                        'stats': stats,
                        'value': value
                    })
                    
                    processed_count += 1
                    
                except Exception as e:
                    logging.error(f"Ошибка обработки пользователя {user_id_str}: {e}")
                    continue
            
            top_users.sort(key=lambda x: x['value'], reverse=True)
            return top_users[:limit]
            
        except Exception as e:
            logging.error(f"Ошибка получения топ пользователей: {e}")
            return []

    def format_leaderboard_message(self, top_users, period="all", metric="turnover"):
        """Форматирует красивое сообщение с таблицей лидеров"""
        try:
            # Валидация параметров
            period = self.validate_period(period)
            metric = self.validate_metric(metric)
            
            period_names = {
                "today": "СЕГОДНЯ",
                "week": "НЕДЕЛЯ",
                "month": "МЕСЯЦ",
                "all": "ВСЕ ВРЕМЯ"
            }
            period_name = period_names.get(period, "ВСЕ ВРЕМЯ")
            
            metric_names = {
                "turnover": "📊 ОБОРОТ",
                "wins": "💰 ВЫИГРЫШИ",
                "deposits": "💳 ДЕПОЗИТЫ",
                "withdrawals": "💸 ВЫВОДЫ"
            }
            metric_name = metric_names.get(metric, "📊 ОБОРОТ")
            
            place_emojis = {
                1: "🥇", 2: "🥈", 3: "🥉",
                4: "4️⃣", 5: "5️⃣", 6: "6️⃣",
                7: "7️⃣", 8: "8️⃣", 9: "9️⃣",
                10: "🔟"
            }
            
            message = f"""<blockquote expandable>╔══════════════════════════════╗
   🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b> 🏆
╚══════════════════════════════╝</blockquote>

<blockquote>
📅 <b>Период:</b> {period_name}
{metric_name}
</blockquote>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🔥 ТОП-10 ИГРОКОВ 🔥</b>

"""
            
            for i, user in enumerate(top_users[:10], 1):
                place_emoji = place_emojis.get(i, f"{i}.")
                username = user['username']
                
                # Уже экранировано в get_top_users, но на всякий случай
                username = html.escape(str(username))
                
                # Ограничение длины для отображения
                if len(username) > 12:
                    username = username[:12] + "..."
                
                value = float(user.get('value', 0))
                value_str = f"{self.format_number(value)} ₽"
                
                if value > 0:
                    message += f"{place_emoji} <code>{username:<15}</code> <b>{value_str}</b>\n"
                else:
                    message += f"{place_emoji} <code>{username:<15}</code> 0 ₽\n"
            
            message += """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<code>Используйте кнопки ниже для навигации</code>
"""
            
            return message
        except Exception as e:
            logging.error(f"Ошибка форматирования таблицы лидеров: {e}")
            return "❌ Произошла ошибка при формировании таблицы лидеров."

    def format_user_stats_message(self, user_id, period="all"):
        """Форматирует сообщение со статистикой пользователя"""
        try:
            # Валидация user_id
            validated_user_id = self.validate_user_id(user_id)
            if validated_user_id is None:
                return "❌ Некорректный ID пользователя."
            
            # Валидация периода
            period = self.validate_period(period)
            
            users_data = self.load_users_data()
            user_data = users_data.get(str(validated_user_id), {})
            
            # Безопасное получение username
            username = str(user_data.get('username', ''))[:32]
            if not username:
                username = str(user_data.get('first_name', f'Игрок {str(validated_user_id)[:6]}...'))[:32]
            
            # Экранирование HTML
            username = html.escape(username)
            
            stats = self.calculate_user_statistics(validated_user_id, period)
            
            period_names = {
                "today": "СЕГОДНЯ",
                "week": "НЕДЕЛЯ",
                "month": "МЕСЯЦ",
                "all": "ВСЁ ВРЕМЯ"
            }
            period_name = period_names.get(period, "ВСЁ ВРЕМЯ")
            
            turnover = self.format_number(stats['turnover'])
            wins = self.format_number(stats['wins'])
            deposits = self.format_number(stats['deposits'])
            withdrawals = self.format_number(stats['withdrawals'])
            
            # Безопасный расчет профита
            profit = float(stats['wins']) - float(stats['withdrawals'])
            if profit >= 0:
                profit_str = f"+{self.format_number(profit)} ₽"
                profit_emoji = "📈"
            else:
                profit_str = f"-{self.format_number(abs(profit))} ₽"
                profit_emoji = "📉"
            
            message = f"""<blockquote expandable>╔══════════════════════════════╗
   📊 <b>ВАША СТАТИСТИКА</b> 📊
╚══════════════════════════════╝</blockquote>

<blockquote>
👤 <b>Игрок:</b> @{username}
📅 <b>Период:</b> {period_name}
</blockquote>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📈 ОСНОВНЫЕ ПОКАЗАТЕЛИ</b>

📊 <b>Оборот:</b> <code>{turnover} ₽</code>
💰 <b>Выигрыши:</b> <code>{wins} ₽</code>
💳 <b>Депозиты:</b> <code>{deposits} ₽</code>
💸 <b>Выводы:</b> <code>{withdrawals} ₽</code>
{profit_emoji} <b>Профит:</b> <code>{profit_str}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<code>Статистика обновляется в реальном времени</code>
"""
            
            return message
        except Exception as e:
            logging.error(f"Ошибка форматирования статистики пользователя {user_id}: {e}")
            return "❌ Произошла ошибка при формировании статистики."

    def get_leaderboard_keyboard(self, current_period="all", current_metric="turnover"):
        """Клавиатура для таблицы лидеров"""
        markup = types.InlineKeyboardMarkup(row_width=4)
        
        # Валидация параметров
        current_period = self.validate_period(current_period)
        current_metric = self.validate_metric(current_metric)
        
        periods = [
            ("🕐 Сегодня", "today"),
            ("📆 Неделя", "week"),
            ("🗓️ Месяц", "month"),
            ("⏳ Все время", "all")
        ]
        
        period_buttons = []
        for text, period in periods:
            if period == current_period:
                display_text = f"✅ {text[2:]}"
            else:
                display_text = text
            
            # Валидация callback_data
            callback_data = f"leaders_period_{period}_{current_metric}"
            if len(callback_data) > 64:  # Ограничение Telegram
                callback_data = f"lp_{period[:2]}_{current_metric[:3]}"
            
            period_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=callback_data
            ))
        
        markup.row(*period_buttons)
        
        categories = [
            ("📊 Оборот", "turnover"),
            ("💰 Выигрыши", "wins"),
            ("💳 Депозиты", "deposits"),
            ("💸 Выводы", "withdrawals")
        ]
        
        category_buttons = []
        for text, metric in categories:
            if metric == current_metric:
                display_text = f"✅ {text[2:]}"
            else:
                display_text = text
            
            # Валидация callback_data
            callback_data = f"leaders_metric_{metric}_{current_period}"
            if len(callback_data) > 64:
                callback_data = f"lm_{metric[:3]}_{current_period[:2]}"
            
            category_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=callback_data
            ))
        
        markup.row(*category_buttons)
        
        # Кнопка статистики
        callback_stats = f"leaders_mystats_{current_period}"
        if len(callback_stats) > 64:
            callback_stats = f"lmystats_{current_period[:2]}"
        
        markup.row(types.InlineKeyboardButton(
            "📈 Моя статистика",
            callback_data=callback_stats
        ))
        
        return markup

    def get_stats_period_keyboard(self, current_period="all"):
        """Клавиатура для выбора периода статистики"""
        markup = types.InlineKeyboardMarkup(row_width=4)
        
        # Валидация периода
        current_period = self.validate_period(current_period)
        
        periods = [
            ("🕐 Сегодня", "today"),
            ("📆 Неделя", "week"),
            ("🗓️ Месяц", "month"),
            ("⏳ Все время", "all")
        ]
        
        period_buttons = []
        for text, period in periods:
            if period == current_period:
                display_text = f"✅ {text[2:]}"
            else:
                display_text = text
            
            # Валидация callback_data
            callback_data = f"stats_period_{period}"
            if len(callback_data) > 64:
                callback_data = f"sp_{period[:2]}"
            
            period_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=callback_data
            ))
        
        markup.row(*period_buttons)
        
        markup.row(types.InlineKeyboardButton(
            "← Назад к лидерам",
            callback_data="leaders_back"
        ))
        
        return markup

leaders_module = LeadersModule()

bot = None

def validate_callback_data(callback_data):
    """Валидация callback_data"""
    if not callback_data or len(callback_data) > 128:
        return False
    
    # Разрешенные префиксы
    allowed_prefixes = ['leaders_', 'stats_', 'lp_', 'lm_', 'lmystats_', 'sp_']
    
    if not any(callback_data.startswith(prefix) for prefix in allowed_prefixes):
        return False
    
    # Проверка на инъекции
    forbidden_chars = [';', '&', '|', '`', '$', '(', ')', '{', '}']
    for char in forbidden_chars:
        if char in callback_data:
            return False
    
    return True

def register_leaders_handlers(bot_instance):
    global bot
    bot = bot_instance
    
    @bot.message_handler(func=lambda message: message.text and 
                        any(cmd.lower() in message.text.lower() for cmd in 
                            ['/лидеры', '/топ', '/leaders', '/top', 'топ', 'Топ', 'ТОП']))
    def leaders_command_handler(message):
        try:
            # Логирование запроса
            user_id = message.from_user.id
            username = message.from_user.username or "без username"
            logging.info(f"Таблица лидеров запрошена: user_id={user_id}, username={username}")
            
            top_users = leaders_module.get_top_users(period="all", metric="turnover", limit=10)
            leaderboard_message = leaders_module.format_leaderboard_message(
                top_users,
                period="all",
                metric="turnover"
            )
            
            bot.send_message(
                message.chat.id,
                leaderboard_message,
                parse_mode='HTML',
                reply_markup=leaders_module.get_leaderboard_keyboard(
                    current_period="all",
                    current_metric="turnover"
                )
            )
            
        except Exception as e:
            logging.error(f"Ошибка в leaders_command_handler: {e}")
            try:
                bot.send_message(
                    message.chat.id,
                    "❌ Произошла ошибка при загрузке таблицы лидеров.",
                    parse_mode='HTML'
                )
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith('leaders_'))
    def leaders_callback_handler(call):
        try:
            # Валидация callback_data
            if not validate_callback_data(call.data):
                logging.warning(f"Некорректный callback_data: {call.data} от user_id={call.from_user.id}")
                bot.answer_callback_query(call.id, "❌ Некорректный запрос")
                return
            
            user_id = call.from_user.id
            username = call.from_user.username or "без username"
            logging.info(f"Callback лидеры: user_id={user_id}, username={username}, data={call.data}")
            
            data_parts = call.data.split('_')
            
            if len(data_parts) < 2:
                bot.answer_callback_query(call.id, "❌ Некорректные данные")
                return
            
            action = data_parts[1]
            
            if action == "period":
                if len(data_parts) >= 4:
                    period = data_parts[2]
                    metric = data_parts[3]
                    
                    # Валидация параметров
                    period = leaders_module.validate_period(period)
                    metric = leaders_module.validate_metric(metric)
                    
                    top_users = leaders_module.get_top_users(period=period, metric=metric, limit=10)
                    leaderboard_message = leaders_module.format_leaderboard_message(
                        top_users,
                        period=period,
                        metric=metric
                    )
                    
                    try:
                        bot.edit_message_text(
                            leaderboard_message,
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=leaders_module.get_leaderboard_keyboard(
                                current_period=period,
                                current_metric=metric
                            )
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text leaders_period: {e}")
                            bot.answer_callback_query(call.id, "❌ Ошибка обновления")
            
            elif action == "metric":
                if len(data_parts) >= 4:
                    metric = data_parts[2]
                    period = data_parts[3]
                    
                    # Валидация параметров
                    metric = leaders_module.validate_metric(metric)
                    period = leaders_module.validate_period(period)
                    
                    top_users = leaders_module.get_top_users(period=period, metric=metric, limit=10)
                    leaderboard_message = leaders_module.format_leaderboard_message(
                        top_users,
                        period=period,
                        metric=metric
                    )
                    
                    try:
                        bot.edit_message_text(
                            leaderboard_message,
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=leaders_module.get_leaderboard_keyboard(
                                current_period=period,
                                current_metric=metric
                            )
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text leaders_metric: {e}")
                            bot.answer_callback_query(call.id, "❌ Ошибка обновления")
            
            elif action == "mystats":
                if len(data_parts) >= 3:
                    period = data_parts[2]
                    
                    # Валидация периода
                    period = leaders_module.validate_period(period)
                    
                    stats_message = leaders_module.format_user_stats_message(user_id, period=period)
                    
                    try:
                        bot.edit_message_text(
                            stats_message,
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=leaders_module.get_stats_period_keyboard(current_period=period)
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text leaders_mystats: {e}")
                            bot.answer_callback_query(call.id, "❌ Ошибка обновления")
            
            elif action == "back":
                top_users = leaders_module.get_top_users(period="all", metric="turnover", limit=10)
                leaderboard_message = leaders_module.format_leaderboard_message(
                    top_users,
                    period="all",
                    metric="turnover"
                )
                
                try:
                    bot.edit_message_text(
                        leaderboard_message,
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=leaders_module.get_leaderboard_keyboard(
                            current_period="all",
                            current_metric="turnover"
                        )
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logging.error(f"Ошибка edit_message_text leaders_back: {e}")
                        bot.answer_callback_query(call.id, "❌ Ошибка обновления")
            
            bot.answer_callback_query(call.id)
            
        except Exception as e:
            logging.error(f"Ошибка в leaders_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith('stats_'))
    def stats_callback_handler(call):
        try:
            # Валидация callback_data
            if not validate_callback_data(call.data):
                logging.warning(f"Некорректный callback_data: {call.data} от user_id={call.from_user.id}")
                bot.answer_callback_query(call.id, "❌ Некорректный запрос")
                return
            
            user_id = call.from_user.id
            data_parts = call.data.split('_')
            
            if len(data_parts) < 2:
                bot.answer_callback_query(call.id, "❌ Некорректные данные")
                return
            
            action = data_parts[1]
            
            if action == "period":
                if len(data_parts) >= 3:
                    period = data_parts[2]
                    
                    # Валидация периода
                    period = leaders_module.validate_period(period)
                    
                    stats_message = leaders_module.format_user_stats_message(user_id, period=period)
                    
                    try:
                        bot.edit_message_text(
                            stats_message,
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=leaders_module.get_stats_period_keyboard(current_period=period)
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text stats_period: {e}")
                            bot.answer_callback_query(call.id, "❌ Ошибка обновления")
            
            bot.answer_callback_query(call.id)
            
        except Exception as e:
            logging.error(f"Ошибка в stats_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
            except:
                pass

def leaders_start(message):
    """Функция для запуска таблицы лидеров из внешних модулей"""
    try:
        user_id = message.from_user.id
        logging.info(f"leaders_start вызвана: user_id={user_id}")
        
        top_users = leaders_module.get_top_users(period="all", metric="turnover", limit=10)
        leaderboard_message = leaders_module.format_leaderboard_message(
            top_users,
            period="all",
            metric="turnover"
        )
        
        bot.send_message(
            message.chat.id,
            leaderboard_message,
            parse_mode='HTML',
            reply_markup=leaders_module.get_leaderboard_keyboard(
                current_period="all",
                current_metric="turnover"
            )
        )
    except Exception as e:
        logging.error(f"Ошибка в leaders_start: {e}")
        try:
            bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при загрузке таблицы лидеров.",
                parse_mode='HTML'
            )
        except:
            pass

def update_game_history(user_id, game_data):
    """Обновляет историю игр для статистики"""
    try:
        # Валидация user_id
        validated_user_id = leaders_module.validate_user_id(user_id)
        if validated_user_id is None:
            return False
        
        # Валидация game_data
        if not isinstance(game_data, dict):
            return False
        
        # Обязательные поля
        required_fields = ['bet_amount', 'win_amount', 'is_win', 'game_type']
        for field in required_fields:
            if field not in game_data:
                return False
        
        # Добавляем timestamp
        game_data['timestamp'] = int(time.time())
        
        # Безопасная операция
        with leaders_module.game_history_lock:
            game_history = leaders_module.load_game_history()
            
            user_key = str(validated_user_id)
            if user_key not in game_history:
                game_history[user_key] = []
            
            # Ограничиваем историю
            game_history[user_key].append(game_data)
            if len(game_history[user_key]) > 1000:
                game_history[user_key] = game_history[user_key][-1000:]
            
            # Сохраняем через безопасную операцию
            return leaders_module.safe_file_operation(
                'game_history.json', 
                mode='w', 
                data=game_history
            )
            
    except Exception as e:
        logging.error(f"Ошибка обновления истории игр для пользователя {user_id}: {e}")
        return False

def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="mines"):
    """Добавляет игру в историю"""
    try:
        # Валидация сумм
        bet_amount_float = float(bet_amount)
        win_amount_float = float(win_amount)
        
        # Проверка на разумные значения
        if bet_amount_float < 0 or bet_amount_float > 1000000:  # Макс 1 млн
            return False
        
        if win_amount_float < 0 or win_amount_float > 10000000:  # Макс 10 млн
            return False
        
        game_data = {
            'game_type': str(game_type)[:50],  # Ограничение длины
            'bet_amount': bet_amount_float,
            'win_amount': win_amount_float,
            'is_win': bool(is_win),
            'timestamp': int(time.time())
        }
        return update_game_history(user_id, game_data)
    except (ValueError, TypeError):
        return False

def get_user_stats(user_id, period="all"):
    """Получает статистику пользователя (публичная функция)"""
    try:
        return leaders_module.calculate_user_statistics(user_id, period)
    except Exception as e:
        logging.error(f"Ошибка в get_user_stats: {e}")
        return {'turnover': 0, 'wins': 0, 'deposits': 0, 'withdrawals': 0, 'net_wins': 0}

def get_leaderboard(period="all", metric="turnover", limit=10):
    """Получает топ пользователей (публичная функция)"""
    try:
        return leaders_module.get_top_users(period, metric, limit)
    except Exception as e:
        logging.error(f"Ошибка в get_leaderboard: {e}")
        return []

__all__ = [
    'register_leaders_handlers',
    'leaders_start',
    'add_game_to_history',
    'get_user_stats',
    'get_leaderboard'
]
