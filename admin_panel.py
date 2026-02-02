import telebot
from telebot import types
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

ADMIN_IDS = [8118184388, 5046075976]

def register_admin_handlers(bot):
    """Регистрирует только админ-обработчики"""

    def is_admin(user_id):
        return user_id in ADMIN_IDS

    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        user_id = message.from_user.id
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "❌ У вас нет прав доступа к админ-панели.")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💰 Выдать баланс", callback_data="admin_give_balance"),
            types.InlineKeyboardButton("⚡ Задать баланс", callback_data="admin_set_balance"),
            types.InlineKeyboardButton("📊 Статистика", callback_data="admin_user_stats"),
            types.InlineKeyboardButton("👥 Все пользователи", callback_data="admin_all_users")
        )
        markup.add(
            types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("📋 Управление выводами", callback_data="admin_withdrawals"),
            types.InlineKeyboardButton("➖ Снять баланс", callback_data="admin_remove_balance")
        )

        bot.send_message(
            message.chat.id,
            """🛠️ <b>АДМИН-ПАНЕЛЬ</b>

<blockquote>Выберите нужный раздел для управления ботом</blockquote>""",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def handle_admin_buttons(call):
        user_id = call.from_user.id
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет прав доступа!")
            return

        if call.data == "admin_give_balance":
            bot.edit_message_text(
                """💰 <b>ВЫДАЧА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 100</code> - выдать 100₽ пользователю с ID 123456789</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_give_balance)

        elif call.data == "admin_set_balance":
            bot.edit_message_text(
                """⚡ <b>УСТАНОВКА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 200</code> - установить баланс 200₽ пользователю с ID 123456789</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_set_balance)

        elif call.data == "admin_user_stats":
            bot.edit_message_text(
                """📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>Введите ID пользователя:</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_user_stats)

        elif call.data == "admin_all_users":
            show_all_users(call.message)

        elif call.data == "admin_broadcast":
            bot.edit_message_text(
                """📢 <b>РАССЫЛКА СООБЩЕНИЙ</b>

<blockquote>Введите сообщение для рассылки всем пользователям:</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_broadcast)

        elif call.data == "admin_withdrawals":
            show_withdrawals_menu(call.message)

        elif call.data == "admin_remove_balance":
            bot.edit_message_text(
                """➖ <b>СНЯТИЕ БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 50</code> - снять 50₽ у пользователя с ID 123456789</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_remove_balance)

        bot.answer_callback_query(call.id)

    def show_withdrawals_menu(message):
        requests = load_withdraw_requests()

        if not requests:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))

            bot.send_message(
                message.chat.id,
                """📋 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

<blockquote>❌ Нет активных заявок на вывод</blockquote>""",
                reply_markup=markup,
                parse_mode="HTML"
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=2)

        for i, req in enumerate(requests[:10], 1):
            user_id = req.get('user_id', 'Неизвестно')
            amount = req.get('amount', 0)
            req_id = req.get('id', i)

            markup.add(
                types.InlineKeyboardButton(
                    f"#{req_id} | {amount}₽",
                    callback_data=f"withdraw_view_{req_id}"
                )
            )

        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))

        bot.send_message(
            message.chat.id,
            """📋 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

<blockquote>Выберите заявку для просмотра:</blockquote>""",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_view_'))
    def view_withdraw_request(call):
        try:
            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            req = None
            for r in requests:
                if r.get('id') == req_id:
                    req = r
                    break

            if not req:
                bot.answer_callback_query(call.id, "❌ Заявка не найдена!")
                return

            user_id = req.get('user_id')
            amount = req.get('amount', 0)
            method = req.get('method', 'Неизвестно')
            data = req.get('data', 'Не указано')
            status = req.get('status', 'pending')
            created_at = req.get('created_at', 'Неизвестно')

            markup = types.InlineKeyboardMarkup(row_width=2)

            if status == 'pending':
                markup.add(
                    types.InlineKeyboardButton("✅ Одобрить", callback_data=f"withdraw_approve_{req_id}"),
                    types.InlineKeyboardButton("❌ Отклонить", callback_data=f"withdraw_reject_{req_id}")
                )

            markup.add(types.InlineKeyboardButton("⬅️ Назад к заявкам", callback_data="admin_withdrawals"))

            status_text = {
                'pending': '⏳ Ожидает',
                'approved': '✅ Одобрено',
                'rejected': '❌ Отклонено'
            }.get(status, status)

            bot.edit_message_text(
                f"""📋 <b>ЗАЯВКА НА ВЫВОД #{req_id}</b>

<blockquote>👤 <b>Пользователь:</b> ID {user_id}
💰 <b>Сумма:</b> {amount}₽
📋 <b>Метод:</b> {method}
📝 <b>Реквизиты:</b> {data}
📅 <b>Дата:</b> {created_at}
📊 <b>Статус:</b> {status_text}</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_approve_'))
    def approve_withdraw_request(call):
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
                        bot.send_message(
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
            bot.answer_callback_query(call.id, "✅ Заявка одобрена!")
            view_withdraw_request(call)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_reject_'))
    def reject_withdraw_request(call):
        try:
            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            for i, req in enumerate(requests):
                if req.get('id') == req_id:
                    req['status'] = 'rejected'

                    user_id = req.get('user_id')
                    try:
                        bot.send_message(
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
            bot.answer_callback_query(call.id, "❌ Заявка отклонена!")
            view_withdraw_request(call)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    def process_broadcast(message):
        broadcast_text = message.text
        users_data = load_users_data()

        bot.send_message(
            message.chat.id,
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
                bot.send_message(
                    user_id,
                    f"""📢 <b>ОБЪЯВЛЕНИЕ ОТ АДМИНИСТРАЦИИ</b>

<blockquote>{broadcast_text}</blockquote>""",
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                fail_count += 1

        bot.send_message(
            message.chat.id,
            f"""✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>

<blockquote>📊 <b>Статистика:</b>
✅ Успешно: {success_count}
❌ Не доставлено: {fail_count}
👥 Всего получателей: {len(users_data)}</blockquote>""",
            parse_mode="HTML"
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_back")
    def handle_back_button(call):
        admin_panel(call.message)
        bot.answer_callback_query(call.id)

    def process_give_balance(message):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден.")
                return

            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = current_balance + amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            bot.send_message(
                message.chat.id,
                f"""✅ <b>БАЛАНС ВЫДАН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💰 <b>Выдано:</b> {amount}₽
💳 <b>Новый баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                parse_mode="HTML"
            )

            try:
                bot.send_message(
                    user_id,
                    f"""🎉 <b>Вам начислены средства!</b>

<blockquote>💰 <b>Сумма:</b> {amount}₽
💳 <b>Текущий баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                    parse_mode="HTML"
                )
            except:
                pass

        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

    def process_set_balance(message):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден.")
                return

            users_data[user_id]['balance'] = amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            bot.send_message(
                message.chat.id,
                f"""⚡ <b>БАЛАНС УСТАНОВЛЕН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💳 <b>Новый баланс:</b> {amount}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

    def process_remove_balance(message):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            user_id = parts[0]
            amount = float(parts[1])

            users_data = load_users_data()

            if user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден.")
                return

            current_balance = users_data[user_id].get('balance', 0)
            if current_balance < amount:
                bot.send_message(message.chat.id, f"❌ Недостаточно средств. У пользователя только {current_balance}₽")
                return

            users_data[user_id]['balance'] = current_balance - amount
            save_users_data(users_data)

            username = users_data[user_id].get('username', 'Неизвестно')
            bot.send_message(
                message.chat.id,
                f"""➖ <b>БАЛАНС СНЯТ</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {user_id})
💰 <b>Снято:</b> {amount}₽
💳 <b>Новый баланс:</b> {users_data[user_id]['balance']}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

    def process_user_stats(message):
        user_id = message.text
        users_data = load_users_data()

        if user_id not in users_data:
            bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден.")
            return

        user_data = users_data[user_id]
        username = user_data.get('username', 'Неизвестно')
        balance = user_data.get('balance', 0)
        level = user_data.get('level', 1)
        first_seen = user_data.get('first_seen', 'Неизвестно')

        bot.send_message(
            message.chat.id,
            f"""📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>👤 <b>Username:</b> @{username}
🆔 <b>ID:</b> {user_id}
💰 <b>Баланс:</b> {balance}₽
🏅 <b>Уровень:</b> {level}
📅 <b>Первый вход:</b> {first_seen}</blockquote>""",
            parse_mode="HTML"
        )

    def show_all_users(message):
        users_data = load_users_data()

        if not users_data:
            bot.send_message(message.chat.id, "❌ Нет зарегистрированных пользователей.")
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

        bot.send_message(message.chat.id, stats_text, parse_mode="HTML")

    print(" Админ-команды зарегистрированы!")
