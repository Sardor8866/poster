from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
from datetime import datetime
import logging
import time
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Защита от быстрых нажатий
user_last_click = {}
click_cooldown = 2  # 2 секунды между нажатиями

def check_click_cooldown(user_id, action_type="button"):
    """Проверяет задержку между нажатиями"""
    current_time = time.time()
    key = f"{user_id}_{action_type}"
    
    if key in user_last_click:
        elapsed = current_time - user_last_click[key]
        if elapsed < click_cooldown:
            wait_time = click_cooldown - int(elapsed)
            return False, f"⏳ Не так быстро! Подождите {wait_time} сек."
    
    user_last_click[key] = current_time
    return True, ""

def load_users_data():
    try:
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
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")
        return False

BOT_USERNAME = None
bot: Bot = None
dp: Dispatcher = None

def register_referrals_handlers(dp_instance: Dispatcher, bot_instance: Bot):
    global bot, dp, BOT_USERNAME
    bot = bot_instance
    dp = dp_instance

    async def get_bot_username():
        try:
            bot_info = await bot.get_me()
            return bot_info.username
        except Exception as e:
            logger.error(f"Ошибка получения username бота: {e}")
            return "YOUR_BOT_USERNAME"

    @dp.callback_query(F.data == "referral_system")
    async def show_referral_system(call: CallbackQuery):
        try:
            user_id = str(call.from_user.id)
            
            # Защита от быстрых нажатий
            allowed, message = check_click_cooldown(user_id)
            if not allowed:
                try:
                    await call.answer(message)
                except:
                    pass
                return
            
            try:
                await call.answer()
            except:
                pass

            users_data = load_users_data()

            if user_id not in users_data:
                await call.answer("❌ Сначала зарегистрируйтесь через /start")
                return

            user_info = users_data[user_id]
            referral_code = user_info.get('referral_code', user_id)
            referral_count = len(user_info.get('referrals', []))
            referral_bonus_balance = user_info.get('referral_bonus', 0)
            total_referral_income = user_info.get('total_referral_income', 0)

            global BOT_USERNAME
            if not BOT_USERNAME:
                BOT_USERNAME = await get_bot_username()

            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

            withdraw_text = "💸 Вывести на баланс"
            if referral_bonus_balance < 300:
                withdraw_text = f"💸 Вывести на баланс (нужно {300-referral_bonus_balance}₽)"

            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=withdraw_text, callback_data="withdraw_referral")],
                [InlineKeyboardButton(text="📋 Мои рефералы", callback_data="my_referrals")],
                [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"Присоединяйся к игре! 🔥\n{referral_link}")]
            ])

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
                await call.message.edit_text(
                    text=referral_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except Exception as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                elif "message is not modified" in str(e):
                    pass
                else:
                    logger.error(f"Ошибка редактирования сообщения: {e}")

        except Exception as e:
            logger.error(f"Ошибка в show_referral_system: {e}")

    @dp.callback_query(F.data == "withdraw_referral")
    async def withdraw_referral_bonus(call: CallbackQuery):
        try:
            user_id = str(call.from_user.id)
            
            # Защита от быстрых нажатий
            allowed, message = check_click_cooldown(user_id)
            if not allowed:
                try:
                    await call.answer(message)
                except:
                    pass
                return
            
            try:
                await call.answer()
            except:
                pass

            users_data = load_users_data()

            if user_id not in users_data:
                await call.answer("❌ Ошибка! Пользователь не найден")
                return

            user_info = users_data[user_id]
            referral_bonus = user_info.get('referral_bonus', 0)
            current_balance = user_info.get('balance', 0)

            if referral_bonus < 300:
                await call.answer(
                    f"❌ Минимальная сумма вывода 300₽\nУ вас: {referral_bonus}₽\nНе хватает: {300-referral_bonus}₽",
                    show_alert=True
                )
                return

            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, вывести", callback_data=f"confirm_withdraw_{referral_bonus}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="referral_system")
                ]
            ])

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
                await call.message.edit_text(
                    text=confirm_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except Exception as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                else:
                    logger.error(f"Ошибка редактирования сообщения: {e}")

        except Exception as e:
            logger.error(f"Ошибка в withdraw_referral_bonus: {e}")

    @dp.callback_query(F.data.startswith("confirm_withdraw_"))
    async def process_withdraw_confirmation(call: CallbackQuery):
        try:
            user_id = str(call.from_user.id)
            
            # Защита от быстрых нажатий с проверкой на повторные запросы
            allowed, message = check_click_cooldown(user_id, "withdraw_action")
            if not allowed:
                try:
                    await call.answer(message)
                except:
                    pass
                return
            
            try:
                await call.answer()
            except:
                pass

            users_data = load_users_data()

            if user_id not in users_data:
                await call.answer("❌ Ошибка! Пользователь не найден")
                return

            withdraw_amount_str = call.data.split("_")[2]
            try:
                withdraw_amount = float(withdraw_amount_str)
            except:
                withdraw_amount = 0

            user_info = users_data[user_id]
            referral_bonus = user_info.get('referral_bonus', 0)

            # Проверка на изменение суммы (двойной клик)
            if withdraw_amount != referral_bonus:
                await call.answer(
                    "❌ Ошибка! Сумма изменилась. Обновите страницу",
                    show_alert=True
                )
                return

            if referral_bonus < 300:
                await call.answer(
                    f"❌ Минимальная сумма вывода 300₽",
                    show_alert=True
                )
                return

            # Проверка что операция еще не была выполнена
            if referral_bonus == 0:
                await call.answer(
                    "❌ Операция уже была выполнена",
                    show_alert=True
                )
                return

            old_referral_balance = referral_bonus
            old_main_balance = user_info.get('balance', 0)

            users_data[user_id]['balance'] = round(old_main_balance + referral_bonus, 2)
            users_data[user_id]['referral_bonus'] = 0

            if 'withdrawal_history' not in users_data[user_id]:
                users_data[user_id]['withdrawal_history'] = []

            withdrawal_record = {
                'type': 'referral',
                'amount': referral_bonus,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'from': 'referral_bonus',
                'to': 'main_balance'
            }
            users_data[user_id]['withdrawal_history'].append(withdrawal_record)

            save_users_data(users_data)

            new_balance = users_data[user_id]['balance']

            success_text = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД УСПЕШНО ВЫПОЛНЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
<b>🎉 Средства успешно переведены!</b>
</blockquote>

<blockquote>
<b>📊 ДЕТАЛИ ОПЕРАЦИИ:</b>
├ 💰 Выведенная сумма: <b>{old_referral_balance}₽</b>
├ 📤 Откуда: <b>Реферальный баланс</b>
├ 📥 Куда: <b>Основной баланс</b>
├ 💵 Было на основном: <b>{old_main_balance}₽</b>
└ 💵 Стало на основном: <b>{new_balance}₽</b>
</blockquote>

<blockquote>
<b>⚡ СТАТУС:</b> <b>Завершено успешно</b>
<b>📅 ДАТА:</b> <b>{datetime.now().strftime("%d.%m.%Y %H:%M")}</b>
<b>🆔 ID ОПЕРАЦИИ:</b> <b>REF-{user_id[:6]}-{datetime.now().strftime('%H%M%S')}</b>
</blockquote>

<b>✅ Теперь вы можете использовать {old_referral_balance}₽ для ставок!</b>
"""

            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 В рефералы", callback_data="referral_system")]
            ])

            try:
                await call.message.edit_text(
                    text=success_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except Exception as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                else:
                    logger.error(f"Ошибка редактирования сообщения: {e}")

            await call.answer(
                f"✅ Успешно! {old_referral_balance}₽ переведены на основной баланс",
                show_alert=True
            )

            logger.info(f"Вывод реферальных средств: {user_id}")
            logger.info(f"💰 Сумма: {old_referral_balance}₽")
            logger.info(f"📊 Баланс до: {old_main_balance}₽, после: {new_balance}₽")

        except Exception as e:
            logger.error(f"Ошибка в process_withdraw_confirmation: {e}")
            await call.answer(
                "❌ Произошла ошибка при выводе",
                show_alert=True
            )

    @dp.callback_query(F.data == "my_referrals")
    async def show_my_referrals(call: CallbackQuery):
        try:
            user_id = str(call.from_user.id)
            
            # Защита от быстрых нажатий
            allowed, message = check_click_cooldown(user_id)
            if not allowed:
                try:
                    await call.answer(message)
                except:
                    pass
                return
            
            try:
                await call.answer()
            except:
                pass

            users_data = load_users_data()

            if user_id not in users_data:
                await call.answer("❌ Сначала зарегистрируйтесь через /start")
                return

            user_info = users_data[user_id]
            referrals_list = user_info.get('referrals', [])
            referral_bonus = user_info.get('referral_bonus', 0)
            total_referral_income = user_info.get('total_referral_income', 0)

            if not referrals_list:
                no_ref_text = f"""
<blockquote expandable>╔══════════════════════╗
   📋 <b>МОИ РЕФЕРАЛЫ</b> 📋
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Реферальный баланс:</b> <b>{referral_bonus}₽</b>
<b>📊 Всего получено:</b> <b>{total_referral_income}₽</b>
</blockquote>

<blockquote>
😔 <b>У вас пока нет рефералов</b>
</blockquote>
"""

                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👥 К рефералам", callback_data="referral_system")]
                ])

                try:
                    await call.message.edit_text(
                        text=no_ref_text,
                        parse_mode='HTML',
                        reply_markup=markup
                    )
                except Exception as e:
                    if "query is too old" in str(e) or "query ID is invalid" in str(e):
                        return
                    else:
                        logger.error(f"Ошибка редактирования сообщения: {e}")
                return

            active_count = 0

            referrals_details = ""
            for i, ref_id in enumerate(referrals_list[:50], 1):
                if ref_id in users_data:
                    ref_info = users_data[ref_id]
                    ref_name = ref_info.get('first_name', f'Игрок {ref_id[:4]}')
                    ref_username = f"@{ref_info.get('username', '')}" if ref_info.get('username') else ref_name
                    ref_won_games = ref_info.get('games_won', 0)

                    is_active = ref_won_games > 0
                    if is_active:
                        active_count += 1

                    status_emoji = "✅" if is_active else "⏳"
                    referrals_details += f"{i}. {status_emoji} {ref_username}\n"

            stats_text = f"""
<blockquote expandable>╔══════════════════════╗
   📋 <b>МОИ РЕФЕРАЛЫ</b> 📋
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 РЕФЕРАЛЬНЫЙ БАЛАНС:</b> <b>{referral_bonus}₽</b>
<b>📊 ВСЕГО ПОЛУЧЕНО:</b> <b>{total_referral_income}₽</b>
</blockquote>

<blockquote>
<b>📊 СТАТИСТИКА:</b>
├ 👥 Всего рефералов: <b>{len(referrals_list)}</b>
├ ✅ Активных: <b>{active_count}</b>
└ 🎯 Процент: <b>6%</b> от выигрышей
</blockquote>

<blockquote>
<b>📝 СПИСОК РЕФЕРАЛОВ:</b>
{referrals_details if referrals_details else "Список пуст"}
</blockquote>
"""

            buttons = []
            if referral_bonus >= 300:
                buttons.append([InlineKeyboardButton(text="💸 Вывести на баланс", callback_data="withdraw_referral")])
            buttons.append([InlineKeyboardButton(text="👥 К рефералам", callback_data="referral_system")])

            markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            try:
                await call.message.edit_text(
                    text=stats_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except Exception as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    return
                elif "Can't find end tag" in str(e):
                    simple_text = f"📋 Ваши рефералы: {len(referrals_list)}\n💰 Реферальный баланс: {referral_bonus}₽\n📊 Всего получено: {total_referral_income}₽"
                    await call.message.edit_text(
                        text=simple_text,
                        reply_markup=markup
                    )
                else:
                    logger.error(f"Ошибка редактирования сообщения: {e}")
            except Exception as e:
                logger.error(f"Ошибка в show_my_referrals: {e}")

        except Exception as e:
            logger.error(f"Ошибка в show_my_referrals: {e}")

    print("✅ Referrals handlers registered")

def add_referral_bonus(user_id, win_amount):
    """
    Начисляет 6% от выигрыша реферала его рефереру
    """
    try:
        users_data = load_users_data()

        if user_id not in users_data:
            logger.error(f"Пользователь {user_id} не найден")
            return

        referrer_id = users_data[user_id].get('referrer_id')
        if not referrer_id:
            logger.error(f"У пользователя {user_id} нет реферера")
            return

        if referrer_id not in users_data:
            logger.error(f"Реферер {referrer_id} не найден")
            return

        bonus = round(win_amount * 0.06, 2)

        current_bonus = users_data[referrer_id].get('referral_bonus', 0)
        users_data[referrer_id]['referral_bonus'] = round(current_bonus + bonus, 2)

        current_income = users_data[referrer_id].get('total_referral_income', 0)
        users_data[referrer_id]['total_referral_income'] = round(current_income + bonus, 2)

        save_users_data(users_data)

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

async def send_referral_welcome_message(chat_id, referrer_data):
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
        
        await bot.send_message(
            chat_id,
            welcome_text,
            parse_mode='HTML'
        )
        logger.info(f"Отправлено приветственное реферальное сообщение для чата {chat_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки реферального приветствия: {e}")

async def send_referral_notification_to_referrer(referrer_id, new_user_id):
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
        
        await bot.send_message(
            referrer_id,
            notification_text,
            parse_mode='HTML'
        )
        
        users_data[referrer_id]['referral_notifications_sent'].append(new_user_id)
        save_users_data(users_data)
        
        logger.info(f"Отправлено уведомление рефереру {referrer_id} о новом реферале {new_user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления рефереру: {e}")
