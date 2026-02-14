from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import json
import random
import string
from datetime import datetime

def load_users_data():
    try:
        with open('users_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users_data(data):
    with open('users_data.json', 'w') as f:
        json.dump(data, f, indent=2)

def load_withdraw_requests():
    try:
        with open('withdraw_requests.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_withdraw_requests(data):
    with open('withdraw_requests.json', 'w') as f:
        json.dump(data, f)

ADMIN_IDS = [8118184388, 8115654734]

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_give_balance = State()
    waiting_for_set_balance = State()
    waiting_for_remove_balance = State()
    waiting_for_user_stats = State()
    waiting_for_broadcast = State()

def register_admin_handlers(dp: Dispatcher):
    """Регистрирует только админ-обработчики"""

    def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS

    @dp.message(Command('admin'))
    async def admin_panel(message: Message):
        user_id = message.from_user.id
        if not is_admin(user_id):
            await message.answer("❌ У вас нет прав доступа к админ-панели.")
            return

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_give_balance"),
                InlineKeyboardButton(text="⚡ Задать баланс", callback_data="admin_set_balance")
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_user_stats"),
                InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_all_users")
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
                InlineKeyboardButton(text="📋 Управление выводами", callback_data="admin_withdrawals")
            ],
            [
                InlineKeyboardButton(text="➖ Снять баланс", callback_data="admin_remove_balance")
            ]
        ])

        await message.answer(
            """🛠️ <b>АДМИН-ПАНЕЛЬ</b>

<blockquote>Выберите нужный раздел для управления ботом</blockquote>""",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith('admin_'))
    async def handle_admin_buttons(call: CallbackQuery, state: FSMContext):
        user_id = call.from_user.id
        if not is_admin(user_id):
            await call.answer("❌ Нет прав доступа!")
            return

        if call.data == "admin_give_balance":
            await call.message.edit_text(
                """💰 <b>ВЫДАЧА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 100</code> - выдать 100₽ пользователю с ID 123456789</blockquote>""",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_give_balance)

        elif call.data == "admin_set_balance":
            await call.message.edit_text(
                """⚡ <b>УСТАНОВКА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 200</code> - установить баланс 200₽ пользователю с ID 123456789</blockquote>""",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_set_balance)

        elif call.data == "admin_remove_balance":
            await call.message.edit_text(
                """➖ <b>СНЯТИЕ БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 50</code> - снять 50₽ у пользователя с ID 123456789</blockquote>""",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_remove_balance)

        elif call.data == "admin_user_stats":
            await call.message.edit_text(
                """📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>Введите ID пользователя:</blockquote>""",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_user_stats)

        elif call.data == "admin_all_users":
            await show_all_users(call.message)

        elif call.data == "admin_broadcast":
            await call.message.edit_text(
                """📢 <b>РАССЫЛКА СООБЩЕНИЙ</b>

<blockquote>Введите сообщение для рассылки всем пользователям:</blockquote>""",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_broadcast)

        elif call.data == "admin_withdrawals":
            await show_withdrawals_menu(call.message)

        await call.answer()

    @dp.message(AdminStates.waiting_for_give_balance)
    async def process_give_balance(message: Message, state: FSMContext):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                await state.clear()
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
                await state.clear()
                return

            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = current_balance + amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            await message.answer(
                f"""✅ <b>БАЛАНС ВЫДАН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💰 <b>Выдано:</b> {amount}₽
💳 <b>Новый баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                parse_mode="HTML"
            )

            try:
                await message.bot.send_message(
                    user_id,
                    f"""🎉 <b>Вам начислены средства!</b>

<blockquote>💰 <b>Сумма:</b> {amount}₽
💳 <b>Текущий баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                    parse_mode="HTML"
                )
            except:
                pass

        except ValueError:
            await message.answer("❌ Неверная сумма. Введите число.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
        finally:
            await state.clear()

    @dp.message(AdminStates.waiting_for_set_balance)
    async def process_set_balance(message: Message, state: FSMContext):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                await state.clear()
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
                await state.clear()
                return

            users_data[user_id]['balance'] = amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            await message.answer(
                f"""⚡ <b>БАЛАНС УСТАНОВЛЕН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💳 <b>Новый баланс:</b> {amount}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError:
            await message.answer("❌ Неверная сумма. Введите число.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
        finally:
            await state.clear()

    @dp.message(AdminStates.waiting_for_remove_balance)
    async def process_remove_balance(message: Message, state: FSMContext):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                await state.clear()
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
                await state.clear()
                return

            current_balance = users_data[user_id].get('balance', 0)
            if current_balance < amount:
                await message.answer(f"❌ Недостаточно средств. У пользователя только {current_balance}₽")
                await state.clear()
                return

            users_data[user_id]['balance'] = current_balance - amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            await message.answer(
                f"""➖ <b>БАЛАНС СНЯТ</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💰 <b>Снято:</b> {amount}₽
💳 <b>Новый баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError:
            await message.answer("❌ Неверная сумма. Введите число.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
        finally:
            await state.clear()

    @dp.message(AdminStates.waiting_for_user_stats)
    async def process_user_stats(message: Message, state: FSMContext):
        user_id = message.text
        users_data = load_users_data()

        if user_id not in users_data:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
            await state.clear()
            return

        user_data = users_data[user_id]
        username = user_data.get('username', 'Неизвестно')
        balance = user_data.get('balance', 0)
        level = user_data.get('level', 1)
        first_seen = user_data.get('first_seen', 'Неизвестно')

        await message.answer(
            f"""📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>👤 <b>Username:</b> @{username}
🆔 <b>ID:</b> {user_id}
💰 <b>Баланс:</b> {balance}₽
🏅 <b>Уровень:</b> {level}
📅 <b>Первый вход:</b> {first_seen}</blockquote>""",
            parse_mode="HTML"
        )
        await state.clear()

    @dp.message(AdminStates.waiting_for_broadcast)
    async def process_broadcast(message: Message, state: FSMContext):
        broadcast_text = message.text
        users_data = load_users_data()

        await message.answer(
            f"""📢 <b>НАЧАЛО РАССЫЛКИ</b>

<blockquote>📝 <b>Сообщение:</b>
{broadcast_text}

👥 <b>Получателей:</b> {len(users_data)}
⏳ <b>Начинаем отправку...</b></blockquote>""",
            parse_mode="HTML"
        )

        success_count = 0
        fail_count = 0

        for user_id, user_data in users_data.items():
            try:
                await message.bot.send_message(
                    user_id,
                    f"""📢 <b>ОБЪЯВЛЕНИЕ ОТ АДМИНИСТРАЦИИ</b>

<blockquote>{broadcast_text}</blockquote>""",
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                fail_count += 1

        await message.answer(
            f"""✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>

<blockquote>📊 <b>Статистика:</b>
✅ Успешно: {success_count}
❌ Не доставлено: {fail_count}
👥 Всего получателей: {len(users_data)}</blockquote>""",
            parse_mode="HTML"
        )
        await state.clear()

    async def show_withdrawals_menu(message: Message):
        requests = load_withdraw_requests()

        if not requests:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])

            await message.answer(
                """📋 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

<blockquote>❌ Нет активных заявок на вывод</blockquote>""",
                reply_markup=markup,
                parse_mode="HTML"
            )
            return

        buttons = []
        for i, req in enumerate(requests[:10], 1):
            user_id = req.get('user_id', 'Неизвестно')
            amount = req.get('amount', 0)
            req_id = req.get('id', i)
            
            buttons.append([InlineKeyboardButton(
                text=f"#{req_id} | {amount}₽",
                callback_data=f"withdraw_view_{req_id}"
            )])

        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            """📋 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

<blockquote>Выберите заявку для просмотра:</blockquote>""",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith('withdraw_view_'))
    async def view_withdraw_request(call: CallbackQuery):
        try:
            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            req = None
            for r in requests:
                if r.get('id') == req_id:
                    req = r
                    break

            if not req:
                await call.answer("❌ Заявка не найдена!")
                return

            user_id = req.get('user_id')
            amount = req.get('amount', 0)
            method = req.get('method', 'Неизвестно')
            data = req.get('data', 'Не указано')
            status = req.get('status', 'pending')
            created_at = req.get('created_at', 'Неизвестно')

            status_text = {
                'pending': '⏳ Ожидает',
                'approved': '✅ Одобрено',
                'rejected': '❌ Отклонено'
            }.get(status, status)

            buttons = []
            if status == 'pending':
                buttons.append([
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"withdraw_approve_{req_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"withdraw_reject_{req_id}")
                ])
            
            buttons.append([InlineKeyboardButton(text="⬅️ Назад к заявкам", callback_data="admin_withdrawals")])
            
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            await call.message.edit_text(
                f"""📋 <b>ЗАЯВКА НА ВЫВОД #{req_id}</b>

<blockquote>👤 <b>Пользователь:</b> ID {user_id}
💰 <b>Сумма:</b> {amount}₽
📋 <b>Метод:</b> {method}
📝 <b>Реквизиты:</b> {data}
📅 <b>Дата:</b> {created_at}
📊 <b>Статус:</b> {status_text}</blockquote>""",
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)}")

    @dp.callback_query(F.data.startswith('withdraw_approve_'))
    async def approve_withdraw_request(call: CallbackQuery):
        try:
            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            for i, req in enumerate(requests):
                if req.get('id') == req_id:
                    req['status'] = 'approved'

                    user_id = req.get('user_id')
                    users_data = load_users_data()

                    if user_id in users_data:
                        current_balance = users_data[user_id].get('balance', 0)
                        amount = req.get('amount', 0)

                        if current_balance >= amount:
                            users_data[user_id]['balance'] = current_balance - amount
                            save_users_data(users_data)

                    try:
                        await call.message.bot.send_message(
                            user_id,
                            f"""✅ <b>ЗАЯВКА НА ВЫВОД ОДОБРЕНА</b>

<blockquote>💰 <b>Сумма:</b> {amount}₽
📋 <b>Метод:</b> {req.get('method', 'Неизвестно')}
📝 <b>Реквизиты:</b> {req.get('data', 'Не указано')}
📅 <b>Дата обработки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}</blockquote>

💸 <i>Средства будут переведены в течение 24 часов</i>""",
                            parse_mode="HTML"
                        )
                    except:
                        pass

                    break

            save_withdraw_requests(requests)
            await call.answer("✅ Заявка одобрена!")
            await view_withdraw_request(call)

        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)}")

    @dp.callback_query(F.data.startswith('withdraw_reject_'))
    async def reject_withdraw_request(call: CallbackQuery):
        try:
            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            for i, req in enumerate(requests):
                if req.get('id') == req_id:
                    req['status'] = 'rejected'

                    user_id = req.get('user_id')
                    try:
                        await call.message.bot.send_message(
                            user_id,
                            """❌ <b>ЗАЯВКА НА ВЫВОД ОТКЛОНЕНА</b>

<blockquote>Ваша заявка на вывод была отклонена администратором.</blockquote>

📞 <i>По вопросам обращайтесь в поддержку</i>""",
                            parse_mode="HTML"
                        )
                    except:
                        pass

                    break

            save_withdraw_requests(requests)
            await call.answer("❌ Заявка отклонена!")
            await view_withdraw_request(call)

        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)}")

    @dp.callback_query(F.data == "admin_back")
    async def handle_back_button(call: CallbackQuery):
        await admin_panel(call.message)
        await call.answer()

    async def show_all_users(message: Message):
        users_data = load_users_data()

        if not users_data:
            await message.answer("❌ Нет зарегистрированных пользователей.")
            return

        total_balance = sum(user_data.get('balance', 0) for user_data in users_data.values())
        total_users = len(users_data)

        stats_text = f"""👥 <b>ОБЩАЯ СТАТИСТИКА</b>

<blockquote>📊 <b>Всего пользователей:</b> {total_users}
💰 <b>Общий баланс:</b> {total_balance}₽</blockquote>

<b>📈 ПОСЛЕДНИЕ 10 ПОЛЬЗОВАТЕЛЕЙ:</b>
"""

        recent_users = list(users_data.items())[-10:]

        for i, (uid, user_data) in enumerate(recent_users, 1):
            username = user_data.get('username', 'Неизвестно')
            balance = user_data.get('balance', 0)
            stats_text += f"<blockquote>{i}. @{username} - {balance}₽ (ID: {uid})</blockquote>\n"

        await message.answer(stats_text, parse_mode="HTML")

    print("✅ Админ-команды зарегистрированы!")
