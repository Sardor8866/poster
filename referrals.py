import telebot
from telebot import types
import json
from datetime import datetime
import telebot.apihelper
import logging
import threading
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные блокировки для предотвращения race conditions
file_lock = threading.Lock()
withdrawal_locks = {}
processed_callbacks = set()
callback_lock = threading.Lock()

def load_users_data():
    try:
        with file_lock:
            with open('users_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл users_data.json не найден, создаем новый")
        return {}
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON, создаем новый файл")
        return {}

def save_users_data(data):
    try:
        with file_lock:
            with open('users_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")
        return False

def log_transaction(user_id, transaction_type, amount, details=""):
    """Логирование всех финансовых транзакций"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transaction_log = {
            'timestamp': timestamp,
            'user_id': user_id,
            'type': transaction_type,
            'amount': amount,
            'details': details
        }
        
        with file_lock:
            try:
                with open('transactions.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps(transaction_log, ensure_ascii=False) + '\n')
            except:
                pass
                
        logger.info(f"💳 Транзакция: {transaction_type} | Пользователь: {user_id} | Сумма: {amount}₽")
    except Exception as e:
        logger.error(f"Ошибка логирования транзакции: {e}")

def get_user_lock(user_id):
    """Получение блокировки для конкретного пользователя"""
    if user_id not in withdrawal_locks:
        withdrawal_locks[user_id] = threading.Lock()
    return withdrawal_locks[user_id]

def is_callback_processed(callback_id):
    """Проверка, был ли callback уже обработан"""
    with callback_lock:
        if callback_id in processed_callbacks:
            return True
        processed_callbacks.add(callback_id)
        # Ограничиваем размер множества
        if len(processed_callbacks) > 10000:
            processed_callbacks.clear()
        return False

def validate_amount(amount, min_amount=0, max_amount=1000000):
    """Валидация суммы"""
    try:
        amount = float(amount)
        if amount < min_amount or amount > max_amount:
            return None
        if amount != amount:  # проверка на NaN
            return None
        return round(amount, 2)
    except:
        return None

BOT_USERNAME = None
bot = None

def register_referrals_handlers(bot_instance):
    global bot, BOT_USERNAME
    bot = bot_instance

    try:
        bot_info = bot.get_me()
        BOT_USERNAME = bot_info.username
        logger.info(f"Получили username бота: @{BOT_USERNAME}")
    except Exception as e:
        logger.error(f"Ошибка получения username бота: {e}")
        BOT_USERNAME = "YOUR_BOT_USERNAME"

    @bot.callback_query_handler(func=lambda call: call.data == "referral_system")
    def show_referral_system(call):
        try:
            # Проверка на дублирование callback
            if is_callback_processed(call.id):
                return
                
            try:
                bot.answer_callback_query(call.id)
            except:
                pass

            user_id = str(call.from_user.id)
            users_data = load_users_data()

            if user_id not in users_data:
                bot.answer_callback_query(call.id, "❌ Сначала зарегистрируйтесь через /start")
                return

            user_info = users_data[user_id]
            referral_code = user_info.get('referral_code', user_id)
            referral_count = len(user_info.get('referrals', []))
            referral_bonus_balance = user_info.get('referral_bonus', 0)
            total_referral_income = user_info.get('total_referral_income', 0)

            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

            markup = types.InlineKeyboardMarkup(row_width=1)

            withdraw_text = "💸 Вывести на баланс"
            if referral_bonus_balance < 300:
                withdraw_text = f"💸 Вывести на баланс (нужно {300-referral_bonus_balance}₽)"

            markup.add(
                types.InlineKeyboardButton(withdraw_text, callback_data="withdraw_referral"),
                types.InlineKeyboardButton("📋 Мои рефералы", callback_data="my_referrals"),
                types.InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"Присоединяйся к игре! 🔥\n{referral_link}")
            )

            referral_text = f"""
<blockquote expandable>╔══════════════════════╗
   👥 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b> 👥
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 РЕФЕРАЛЬНЫЙ БАЛАНС:</b>
├ 💎 Доступно: <b>{referral_bonus_balance}₽</b>
├ 🎯 Всего рефералов: <b>{referral_count}</b>
├ 📊 Всего получено: <b>{total_referral_income}₽</b>
└ 🎯 Процент: <b>6%</b> от выигрышных ставок
</blockquote>

<blockquote>
<b>🔗 ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:</b>
<code>{referral_link}</code>
</blockquote>

<blockquote>
<b>🎯 УСЛОВИЯ ВЫВОДА:</b>
├ 💸 Минимальная сумма: <b>300₽</b>
├ ⚡ Вывод в любой момент
└ 🔄 На основной баланс
</blockquote>

<b>⚠️ Для вывода нажмите кнопку "💸 Вывести на баланс"</b>
"""

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=referral_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                elif "message is not modified" in str(e):
                    pass
                else:
                    raise e
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")

        except Exception as e:
            logger.error(f"Ошибка в show_referral_system: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "withdraw_referral")
    def withdraw_referral_bonus(call):
        try:
            # Проверка на дублирование callback
            if is_callback_processed(call.id):
                return
                
            try:
                bot.answer_callback_query(call.id)
            except:
                pass

            user_id = str(call.from_user.id)
            users_data = load_users_data()

            if user_id not in users_data:
                bot.answer_callback_query(call.id, "❌ Ошибка! Пользователь не найден")
                return

            user_info = users_data[user_id]
            referral_bonus = user_info.get('referral_bonus', 0)
            current_balance = user_info.get('balance', 0)

            if referral_bonus < 300:
                bot.answer_callback_query(
                    call.id,
                    f"❌ Минимальная сумма вывода 300₽\nУ вас: {referral_bonus}₽\nНе хватает: {300-referral_bonus}₽",
                    show_alert=True
                )
                return

            markup = types.InlineKeyboardMarkup(row_width=2)
            # ИСПРАВЛЕНИЕ: НЕ передаем сумму в callback_data
            markup.add(
                types.InlineKeyboardButton("✅ Да, вывести", callback_data="confirm_withdraw"),
                types.InlineKeyboardButton("❌ Отмена", callback_data="referral_system")
            )

            confirm_text = f"""
<blockquote expandable>╔══════════════════════╗
   💸 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b> 💸
╚══════════════════════╝</blockquote>

<blockquote>
<b>⚠️ Подтвердите вывод реферальных средств</b>
</blockquote>

<blockquote>
<b>📊 ДАННЫЕ О ВЫВОДЕ:</b>
├ 💰 Сумма к выводу: <b>{referral_bonus}₽</b>
├ 📤 На счет: <b>Основной баланс</b>
├ 💵 Текущий баланс: <b>{current_balance}₽</b>
└ 💵 После вывода: <b>{current_balance + referral_bonus}₽</b>
</blockquote>

<blockquote>
<b>📝 УСЛОВИЯ:</b>
├ ⚡ Вывод моментальный
├ 🔄 Без комиссии
└ ✅ Необратимая операция
</blockquote>

<b>Вы уверены, что хотите вывести {referral_bonus}₽ на основной баланс?</b>
"""

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=confirm_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                else:
                    raise e

        except Exception as e:
            logger.error(f"Ошибка в withdraw_referral_bonus: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "confirm_withdraw")
    def process_withdraw_confirmation(call):
        try:
            # Проверка на дублирование callback
            if is_callback_processed(call.id):
                logger.warning(f"⚠️ Повторный callback {call.id} от пользователя {call.from_user.id}")
                return
                
            try:
                bot.answer_callback_query(call.id)
            except:
                pass

            user_id = str(call.from_user.id)
            
            # ИСПРАВЛЕНИЕ: Используем блокировку для предотвращения race condition
            user_lock = get_user_lock(user_id)
            
            with user_lock:
                users_data = load_users_data()

                if user_id not in users_data:
                    bot.answer_callback_query(call.id, "❌ Ошибка! Пользователь не найден")
                    return

                # ИСПРАВЛЕНИЕ: Берем сумму из базы данных, а не из callback
                user_info = users_data[user_id]
                referral_bonus = user_info.get('referral_bonus', 0)
                
                # ИСПРАВЛЕНИЕ: Валидация суммы
                referral_bonus = validate_amount(referral_bonus, min_amount=300)
                if referral_bonus is None:
                    bot.answer_callback_query(call.id, "❌ Ошибка! Некорректная сумма")
                    logger.error(f"Попытка вывода некорректной суммы пользователем {user_id}")
                    return

                current_balance = user_info.get('balance', 0)

                # Двойная проверка минимальной суммы
                if referral_bonus < 300:
                    bot.answer_callback_query(
                        call.id,
                        f"❌ Недостаточно средств для вывода",
                        show_alert=True
                    )
                    return

                # Выполняем перевод
                users_data[user_id]['balance'] = round(current_balance + referral_bonus, 2)
                users_data[user_id]['referral_bonus'] = 0

                # Сохраняем изменения
                if not save_users_data(users_data):
                    bot.answer_callback_query(call.id, "❌ Ошибка сохранения данных")
                    logger.error(f"Ошибка сохранения при выводе для пользователя {user_id}")
                    return

                # Логируем транзакцию
                log_transaction(
                    user_id=user_id,
                    transaction_type="referral_withdrawal",
                    amount=referral_bonus,
                    details=f"Вывод с реферального баланса на основной баланс"
                )

            # Отправляем уведомление об успешном выводе
            success_text = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД ВЫПОЛНЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
<b>🎉 Поздравляем!</b>
Реферальные средства успешно переведены
на ваш основной баланс
</blockquote>

<blockquote>
<b>💰 ДАННЫЕ ОПЕРАЦИИ:</b>
├ 💸 Выведено: <b>{referral_bonus}₽</b>
├ 💵 Новый баланс: <b>{users_data[user_id]['balance']}₽</b>
├ 📊 Реферальный баланс: <b>0₽</b>
└ ⏰ Время: <b>{datetime.now().strftime("%H:%M:%S")}</b>
</blockquote>

<blockquote>
<b>🎯 ПРОДОЛЖАЙТЕ ПРИГЛАШАТЬ ДРУЗЕЙ!</b>
Чем больше рефералов - тем больше бонусов! 🚀
</blockquote>

<b>✨ Удачной игры!</b>
"""

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("👥 Реферальная система", callback_data="referral_system"),
                types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            )

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=success_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                else:
                    raise e

            logger.info(f"✅ Успешный вывод: пользователь {user_id}, сумма {referral_bonus}₽")

        except Exception as e:
            logger.error(f"Ошибка в process_withdraw_confirmation: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка при выводе средств")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data == "my_referrals")
    def show_my_referrals(call):
        try:
            # Проверка на дублирование callback
            if is_callback_processed(call.id):
                return
                
            try:
                bot.answer_callback_query(call.id)
            except:
                pass

            user_id = str(call.from_user.id)
            users_data = load_users_data()

            if user_id not in users_data:
                bot.answer_callback_query(call.id, "❌ Ошибка! Пользователь не найден")
                return

            user_info = users_data[user_id]
            referrals = user_info.get('referrals', [])
            referral_count = len(referrals)

            if referral_count == 0:
                referrals_text = """
<blockquote expandable>╔══════════════════════╗
   👥 <b>МОИ РЕФЕРАЛЫ</b> 👥
╚══════════════════════╝</blockquote>

<blockquote>
<b>😔 У вас пока нет рефералов</b>

<b>🎯 КАК ПРИГЛАСИТЬ:</b>
├ 📤 Поделитесь ссылкой с друзьями
├ 💰 Получайте 6% от их выигрышей
└ 🚀 Без ограничений по количеству!
</blockquote>

<blockquote>
<i>💡 Начните приглашать друзей прямо сейчас!</i>
</blockquote>
"""
            else:
                referrals_list = []
                for i, ref_id in enumerate(referrals[:10], 1):
                    if ref_id in users_data:
                        ref_data = users_data[ref_id]
                        ref_name = ref_data.get('first_name', 'Игрок')
                        ref_username = ref_data.get('username', '')
                        games_played = ref_data.get('games_played', 0)
                        
                        if ref_username:
                            ref_display = f"@{ref_username}"
                        else:
                            ref_display = ref_name
                        
                        referrals_list.append(f"├ {i}. {ref_display} ({games_played} игр)")

                if len(referrals) > 10:
                    referrals_list.append(f"└ ... и еще {len(referrals) - 10}")
                else:
                    if referrals_list:
                        referrals_list[-1] = referrals_list[-1].replace("├", "└")

                referrals_text = f"""
<blockquote expandable>╔══════════════════════╗
   👥 <b>МОИ РЕФЕРАЛЫ</b> 👥
╚══════════════════════╝</blockquote>

<blockquote>
<b>📊 СТАТИСТИКА:</b>
├ 👥 Всего рефералов: <b>{referral_count}</b>
├ 💰 Реферальный баланс: <b>{user_info.get('referral_bonus', 0)}₽</b>
└ 📈 Всего получено: <b>{user_info.get('total_referral_income', 0)}₽</b>
</blockquote>

<blockquote>
<b>👤 СПИСОК РЕФЕРАЛОВ:</b>
{chr(10).join(referrals_list)}
</blockquote>

<blockquote>
<i>🎯 Продолжайте приглашать друзей!</i>
</blockquote>
"""

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("◀️ Назад", callback_data="referral_system")
            )

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=referrals_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                elif "message is not modified" in str(e):
                    pass
                else:
                    raise e

        except Exception as e:
            logger.error(f"Ошибка в show_my_referrals: {e}")

def add_referral_bonus(user_id, win_amount):
    """
    Начисляет реферальный бонус рефереру при выигрыше реферала.
    user_id - ID пользователя, который выиграл
    win_amount - сумма выигрыша
    """
    try:
        # ИСПРАВЛЕНИЕ: Валидация суммы выигрыша
        win_amount = validate_amount(win_amount, min_amount=0.01)
        if win_amount is None:
            logger.error(f"Некорректная сумма выигрыша: {win_amount}")
            return

        users_data = load_users_data()

        if user_id not in users_data:
            logger.warning(f"Пользователь {user_id} не найден для начисления реферального бонуса")
            return

        referrer_id = users_data[user_id].get('referrer_id')
        
        if not referrer_id:
            return

        if referrer_id not in users_data:
            logger.warning(f"Реферер {referrer_id} не найден в базе данных")
            return

        # ИСПРАВЛЕНИЕ: Используем блокировку для рефера
        referrer_lock = get_user_lock(referrer_id)
        
        with referrer_lock:
            # Перезагружаем данные внутри блокировки
            users_data = load_users_data()
            
            if referrer_id not in users_data:
                return

            bonus = round(win_amount * 0.06, 2)
            
            # ИСПРАВЛЕНИЕ: Валидация бонуса
            bonus = validate_amount(bonus, min_amount=0)
            if bonus is None or bonus == 0:
                return

            current_bonus = users_data[referrer_id].get('referral_bonus', 0)
            users_data[referrer_id]['referral_bonus'] = round(current_bonus + bonus, 2)

            current_income = users_data[referrer_id].get('total_referral_income', 0)
            users_data[referrer_id]['total_referral_income'] = round(current_income + bonus, 2)

            save_users_data(users_data)

            # Логируем транзакцию
            log_transaction(
                user_id=referrer_id,
                transaction_type="referral_bonus",
                amount=bonus,
                details=f"Бонус от реферала {user_id}, выигрыш: {win_amount}₽"
            )

        logger.info(f"🎯 Реферальный бонус: {user_id} -> {referrer_id}")
        logger.info(f"💰 Сумма выигрыша: {win_amount}₽")
        logger.info(f"🎯 Бонус (6%): {bonus}₽")
        logger.info(f"💰 Новый реферальный баланс {referrer_id}: {users_data[referrer_id]['referral_bonus']}₽")
        logger.info(f"📊 Всего получено {referrer_id}: {users_data[referrer_id]['total_referral_income']}₽")

    except Exception as e:
        logger.error(f"Ошибка при начислении реферального бонуса: {e}")

def process_referral_join(new_user_id, referral_code, user_data=None):
    """
    Обрабатывает присоединение по реферальной ссылке.
    user_data - данные нового пользователя (опционально)
    ВОЗВРАЩАЕТ: {'success': True/False, 'message': 'причина', 'referrer_data': {...}}
    """
    try:
        # ИСПРАВЛЕНИЕ: Блокировка для предотвращения дублирования
        with file_lock:
            users_data = load_users_data()
            
            if referral_code not in users_data:
                return {
                    'success': False,
                    'message': 'Реферер не найден',
                    'referrer_data': None
                }
            
            if new_user_id == referral_code:
                return {
                    'success': False,
                    'message': 'Нельзя пригласить самого себя',
                    'referrer_data': None
                }
            
            is_new_user = new_user_id not in users_data
            
            if not is_new_user:
                logger.info(f"⚠️ Пользователь {new_user_id} уже существует, не добавляем в рефералы")
                return {
                    'success': False,
                    'message': 'Пользователь уже зарегистрирован',
                    'referrer_data': None
                }
            
            if user_data is None:
                user_data = {
                    'referrer_id': referral_code,
                    'first_name': f'Игрок{new_user_id[-4:]}',
                    'username': '',
                    'balance': 0.0,
                    'referral_bonus': 0.0,
                    'total_referral_income': 0.0,
                    'referrals': [],
                    'games_played': 0,
                    'games_won': 0,
                    'registration_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'referral_code': new_user_id
                }
            
            user_data['referrer_id'] = referral_code
            
            users_data[new_user_id] = user_data
            
            if 'referrals' not in users_data[referral_code]:
                users_data[referral_code]['referrals'] = []
            
            if new_user_id not in users_data[referral_code]['referrals']:
                users_data[referral_code]['referrals'].append(new_user_id)
            
            save_success = save_users_data(users_data)
            
            if not save_success:
                return {
                    'success': False,
                    'message': 'Ошибка сохранения данных',
                    'referrer_data': None
                }
            
            # Логируем событие
            log_transaction(
                user_id=new_user_id,
                transaction_type="referral_registration",
                amount=0,
                details=f"Зарегистрирован по реферальной ссылке {referral_code}"
            )
            
            referrer_name = users_data[referral_code].get('first_name', 'Ваш друг')
            referrer_username = users_data[referral_code].get('username', '')
            
            logger.info(f"Новый реферал зарегистрирован: {new_user_id} приглашен пользователем {referral_code}")
            logger.info(f"📊 Рефералов у {referral_code}: {len(users_data[referral_code]['referrals'])}")
            logger.info(f"📝 Данные пользователя {new_user_id} созданы успешно")
            
            return {
                'success': True,
                'message': 'Реферал успешно зарегистрирован',
                'referrer_data': {
                    'referrer_id': referral_code,
                    'referrer_name': referrer_name,
                    'referrer_username': referrer_username
                }
            }
        
    except Exception as e:
        logger.error(f"Ошибка обработки реферала: {e}")
        return {
            'success': False,
            'message': f'Ошибка: {str(e)}',
            'referrer_data': None
        }

def send_referral_welcome_message(chat_id, referrer_data):
    """
    Отправляет красивое сообщение о приглашении по реферальной ссылке
    ТОЛЬКО ДЛЯ НОВЫХ РЕФЕРАЛОВ
    """
    try:
        global bot
        if bot is None:
            return
        
        referrer_name = referrer_data.get('referrer_name', 'Ваш друг')
        referrer_username = referrer_data.get('referrer_username', '')
        
        if referrer_username:
            referrer_mention = f"@{referrer_username}"
        else:
            referrer_mention = referrer_name
            
        welcome_text = f"""
<blockquote expandable>╔══════════════════════╗
   🎉 <b>РЕФЕРАЛЬНОЕ ПРИГЛАШЕНИЕ</b> 🎉
╚══════════════════════╝</blockquote>

<blockquote>
✨ <b>Поздравляем!</b> Вы присоединились к проекту
по приглашению <b>{referrer_mention}</b>
</blockquote>

<blockquote>
<b>🎯 ВАШИ БОНУСЫ:</b>
├ ✅ Реферальная система активирована
├ 🔥 Теперь вы в команде {referrer_name}
├ 💫 Ваши выигрыши приносят бонусы рефереру
└ 🚀 Удачной игры и больших побед!
</blockquote>

<blockquote>
<b>📊 КАК ЭТО РАБОТАЕТ:</b>
Ваш реферер получает <b>6%</b> от ваших
выигрышных ставок на свой реферальный баланс
</blockquote>

<blockquote>
<i>🔥 Добро пожаловать в команду!
Удачной игры и больших выигрышей! 💰</i>
</blockquote>
"""
        
        bot.send_message(
            chat_id,
            welcome_text,
            parse_mode='HTML'
        )
        logger.info(f"Отправлено приветственное реферальное сообщение для чата {chat_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки реферального приветствия: {e}")

def send_referral_notification_to_referrer(referrer_id, new_user_id):
    """
    Отправляет уведомление рефереру о новом реферале (ТОЛЬКО ОДИН РАЗ)
    """
    try:
        global bot
        if bot is None:
            return
        
        users_data = load_users_data()
        if referrer_id not in users_data:
            return
        
        if new_user_id in users_data:
            new_user_data = users_data[new_user_id]
            new_user_name = new_user_data.get('first_name', 'Новый игрок')
            new_user_username = f"@{new_user_data.get('username')}" if new_user_data.get('username') else new_user_name
        else:
            logger.error(f"Новый пользователь {new_user_id} не найден в базе данных")
            return
        
        if 'referral_notifications_sent' not in users_data[referrer_id]:
            users_data[referrer_id]['referral_notifications_sent'] = []
        
        if new_user_id in users_data[referrer_id]['referral_notifications_sent']:
            logger.info(f"⚠️ Уведомление для реферала {new_user_id} уже отправлялось рефереру {referrer_id}")
            return
        
        referral_count = len(users_data[referrer_id].get('referrals', []))
        referral_bonus = users_data[referrer_id].get('referral_bonus', 0)
        
        notification_text = f"""
<blockquote>╔══════════════════╗
   🎉 <b>НОВЫЙ РЕФЕРАЛ</b> 🎉
╚══════════════════╝</blockquote>

<b>👤 Реферал:</b> {new_user_username}
<b>🆔 ID:</b> <code>{new_user_id[-8:]}</code>

<b>📊 Ваша статистика:</b>
├ 👥 Всего: <b>{referral_count}</b>
└ 💰 Баланс: <b>{referral_bonus}₽</b>

<b>🎯 Бонус:</b> 6% от выигрышей
"""
        
        bot.send_message(
            referrer_id,
            notification_text,
            parse_mode='HTML'
        )
        
        users_data[referrer_id]['referral_notifications_sent'].append(new_user_id)
        save_users_data(users_data)
        
        logger.info(f"Отправлено уведомление рефереру {referrer_id} о новом реферале {new_user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления рефереру: {e}")
