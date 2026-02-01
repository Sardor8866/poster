import telebot
from telebot import types
import json
import time
import threading
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class LeadersModule:
    def __init__(self):
        self.users_data_lock = threading.Lock()
        
    def load_users_data(self):
        """Загружает данные пользователей"""
        try:
            with self.users_data_lock:
                with open('users_data.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logging.error(f"Ошибка загрузки данных: {e}")
            return {}

    def load_game_history(self):
        """Загружает историю игр"""
        try:
            with open('game_history.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logging.error(f"Ошибка загрузки истории игр: {e}")
            return {}

    def load_transactions(self):
        """Загружает историю транзакций"""
        try:
            with open('transactions.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            logging.error(f"Ошибка загрузки транзакций: {e}")
            return []

    def format_number(self, num):
        """Форматирует число с пробелами"""
        return f"{int(num):,}".replace(",", ".")

    def get_time_period_filter(self, period):
        """Возвращает timestamp начала периода"""
        now = datetime.now()
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
        elif period == "all":
            return 0
        else:
            return 0

    def calculate_user_statistics(self, user_id, period="all"):
        """Рассчитывает статистику пользователя за указанный период"""
        try:
            users_data = self.load_users_data()
            game_history = self.load_game_history()
            transactions = self.load_transactions()
            
            time_filter = self.get_time_period_filter(period)
            
            turnover = 0.0
            wins = 0.0
            total_wins = 0.0
            deposits = 0.0
            withdrawals = 0.0
            
            if str(user_id) in game_history:
                for game in game_history[str(user_id)]:
                    game_time = game.get('timestamp', 0)
                    if game_time >= time_filter:
                        bet_amount = game.get('bet_amount', 0)
                        win_amount = game.get('win_amount', 0)
                        is_win = game.get('is_win', False)
                        
                        turnover += bet_amount
                        
                        if is_win and win_amount > 0:
                            wins += win_amount
                            total_wins += win_amount
            
            for transaction in transactions:
                if str(transaction.get('user_id')) == str(user_id):
                    trans_time = transaction.get('timestamp', 0)
                    if trans_time >= time_filter:
                        amount = transaction.get('amount', 0)
                        trans_type = transaction.get('type', '')
                        
                        if trans_type == 'deposit':
                            deposits += amount
                        elif trans_type == 'withdraw':
                            withdrawals += amount
            
            return {
                'turnover': round(turnover, 2),
                'wins': round(total_wins, 2),
                'deposits': round(deposits, 2),
                'withdrawals': round(withdrawals, 2),
                'net_wins': round(wins, 2)
            }
        except Exception as e:
            logging.error(f"Ошибка расчета статистики для пользователя {user_id}: {e}")
            return {'turnover': 0, 'wins': 0, 'deposits': 0, 'withdrawals': 0, 'net_wins': 0}

    def get_top_users(self, period="all", metric="turnover", limit=50):
        """Получает топ пользователей по указанному показателю"""
        try:
            users_data = self.load_users_data()
            top_users = []
            
            for user_id_str, user_data in users_data.items():
                try:
                    user_id = int(user_id_str)
                    stats = self.calculate_user_statistics(user_id, period)
                    
                    username = user_data.get('username', '')
                    if not username:
                        username = user_data.get('first_name', f'Игрок {user_id_str[:6]}...')
                    
                    top_users.append({
                        'user_id': user_id,
                        'username': username,
                        'stats': stats,
                        'value': stats.get(metric, 0)
                    })
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
            
            message = f"""
<blockquote expandable>╔══════════════════════════════╗
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
                
                if len(username) > 12:
                    username = username[:12] + "..."
                
                value = user['value']
                
                value_str = f"{self.format_number(value)} ₽"
                
                if value > 0:
                    message += f"{place_emoji} <code>{username:<15}</code> <b>{value_str}</b>\n"
                else:
                    message += f"{place_emoji} <code>{username:<15}</code> 0 ₽\n"
            
            message += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<code>Используйте кнопки ниже для навигации</code>
"""
            
            return message
        except Exception as e:
            logging.error(f"Ошибка форматирования таблицы лидеров: {e}")
            return "❌ Произошла ошибка при формировании таблицы лидеров."

    def format_user_stats_message(self, user_id, period="all"):
        """Форматирует сообщение со статистикой пользователя"""
        try:
            users_data = self.load_users_data()
            
            user_data = users_data.get(str(user_id), {})
            username = user_data.get('username', '')
            if not username:
                username = user_data.get('first_name', f'Игрок {str(user_id)[:6]}...')
            
            stats = self.calculate_user_statistics(user_id, period)
            
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
            
            profit = stats['wins'] - stats['withdrawals']
            if profit >= 0:
                profit_str = f"+{self.format_number(profit)} ₽"
                profit_emoji = "📈"
            else:
                profit_str = f"-{self.format_number(abs(profit))} ₽"
                profit_emoji = "📉"
            
            message = f"""
<blockquote expandable>╔══════════════════════════════╗
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
            period_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=f"leaders_period_{period}_{current_metric}"
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
            category_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=f"leaders_metric_{metric}_{current_period}"
            ))
        
        markup.row(*category_buttons)
        
        markup.row(types.InlineKeyboardButton(
            "📈 Моя статистика",
            callback_data=f"leaders_mystats_{current_period}"
        ))
        
        return markup

    def get_stats_period_keyboard(self, current_period="all"):
        """Клавиатура для выбора периода статистики"""
        markup = types.InlineKeyboardMarkup(row_width=4)
        
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
            period_buttons.append(types.InlineKeyboardButton(
                display_text,
                callback_data=f"stats_period_{period}"
            ))
        
        markup.row(*period_buttons)
        
        markup.row(types.InlineKeyboardButton(
            "← Назад к лидерам",
            callback_data="leaders_back"
        ))
        
        return markup

leaders_module = LeadersModule()

bot = None

def register_leaders_handlers(bot_instance):
    global bot
    bot = bot_instance
    
    @bot.message_handler(func=lambda message: message.text and 
                        any(cmd.lower() in message.text.lower() for cmd in 
                            ['/лидеры', '/топ', '/leaders', '/top', 'топ', 'Топ', 'ТОП']))
    def leaders_command_handler(message):
        user_id = str(message.from_user.id)
        
        try:
            text = message.text.lower().strip()
            
            if '/топ' in text or 'топ' in text or '/top' in text or '/лидеры' in text or '/leaders' in text:
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
            bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при загрузке таблицы лидеров.",
                parse_mode='HTML'
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('leaders_'))
    def leaders_callback_handler(call):
        try:
            user_id = str(call.from_user.id)
            data_parts = call.data.split('_')
            
            if len(data_parts) < 2:
                return
            
            action = data_parts[1]
            
            if action == "period":
                if len(data_parts) >= 4:
                    period = data_parts[2]
                    metric = data_parts[3]
                    
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
                
            elif action == "metric":
                if len(data_parts) >= 4:
                    metric = data_parts[2]
                    period = data_parts[3]
                    
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
            
            elif action == "mystats":
                if len(data_parts) >= 3:
                    period = data_parts[2]
                    
                    stats_message = leaders_module.format_user_stats_message(int(user_id), period=period)
                    
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
            
        except Exception as e:
            logging.error(f"Ошибка в leaders_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith('stats_'))
    def stats_callback_handler(call):
        try:
            user_id = str(call.from_user.id)
            data_parts = call.data.split('_')
            
            if len(data_parts) < 2:
                return
            
            action = data_parts[1]
            
            if action == "period":
                if len(data_parts) >= 3:
                    period = data_parts[2]
                    
                    stats_message = leaders_module.format_user_stats_message(int(user_id), period=period)
                    
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
            
        except Exception as e:
            logging.error(f"Ошибка в stats_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
            except:
                pass

def leaders_start(message):
    """Функция для запуска таблицы лидеров из внешних модулей"""
    try:
        user_id = str(message.from_user.id)
        
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
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка при загрузке таблицы лидеров.",
            parse_mode='HTML'
        )

def update_game_history(user_id, game_data):
    """Обновляет историю игр для статистики"""
    try:
        game_history = leaders_module.load_game_history()
        
        if str(user_id) not in game_history:
            game_history[str(user_id)] = []
        
        game_data['timestamp'] = int(time.time())
        
        game_history[str(user_id)].append(game_data)
        if len(game_history[str(user_id)]) > 1000:
            game_history[str(user_id)] = game_history[str(user_id)][-1000:]
        
        with open('game_history.json', 'w', encoding='utf-8') as f:
            json.dump(game_history, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        logging.error(f"Ошибка обновления истории игр для пользователя {user_id}: {e}")
        return False

def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="mines"):
    """Добавляет игру в историю"""
    game_data = {
        'game_type': game_type,
        'bet_amount': float(bet_amount),
        'win_amount': float(win_amount),
        'is_win': is_win,
        'timestamp': int(time.time())
    }
    return update_game_history(user_id, game_data)

def get_user_stats(user_id, period="all"):
    """Получает статистику пользователя (публичная функция)"""
    return leaders_module.calculate_user_statistics(user_id, period)

def get_leaderboard(period="all", metric="turnover", limit=10):
    """Получает топ пользователей (публичная функция)"""
    return leaders_module.get_top_users(period, metric, limit)

__all__ = [
    'register_leaders_handlers',
    'leaders_start',
    'add_game_to_history',
    'get_user_stats',
    'get_leaderboard'
]
