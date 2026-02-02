import telebot
from telebot import types
import json
import random
import string
from datetime import datetime
import html
import os
import time

def safe_file_operation(filename, mode='r', default=None, data=None, max_size_mb=50):
    """Безопасная операция с файлами"""
    try:
        # Защита от Path Traversal
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, filename)
        
        # Проверяем, что файл находится в нужной директории
        if not os.path.commonpath([base_dir, os.path.dirname(file_path)]) == base_dir:
            raise ValueError(f"Попытка доступа к файлу вне рабочей директории: {filename}")
        
        if mode == 'r' and data is not None:
            raise ValueError("Режим 'r' не поддерживает запись данных")
            
        if mode == 'w' or mode == 'a':
            if data is None:
                raise ValueError("Для записи данные обязательны")
            
            # Проверка размера данных
            data_size = len(json.dumps(data, ensure_ascii=False))
            if data_size > max_size_mb * 1024 * 1024:
                raise ValueError(f"Данные слишком большие: {data_size} байт")
            
            # Атомарная запись через временный файл
            temp_file = file_path + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, file_path)
            return True
            
        elif mode == 'r':
            # Проверка существования файла
            if not os.path.exists(file_path):
                return default
            
            # Проверка размера файла
            if os.path.getsize(file_path) > max_size_mb * 1024 * 1024:
                raise ValueError(f"Файл слишком большой: {filename}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
    except json.JSONDecodeError as e:
        # Создаем backup поврежденного файла
        if os.path.exists(file_path):
            backup_path = file_path + '.backup_' + str(int(time.time()))
            os.rename(file_path, backup_path)
        raise ValueError(f"Ошибка парсинга JSON в файле {filename}: {e}")
    except Exception as e:
        raise ValueError(f"Ошибка работы с файлом {filename}: {e}")

def load_users_data():
    try:
        return safe_file_operation('users_data.json', mode='r', default={})
    except Exception as e:
        print(f"Ошибка загрузки users_data: {e}")
        return {}

def save_users_data(data):
    try:
        return safe_file_operation('users_data.json', mode='w', data=data)
    except Exception as e:
        print(f"Ошибка сохранения users_data: {e}")
        return False

def load_withdraw_requests():
    try:
        return safe_file_operation('withdraw_requests.json', mode='r', default=[])
    except Exception as e:
        print(f"Ошибка загрузки withdraw_requests: {e}")
        return []

def save_withdraw_requests(data):
    try:
        return safe_file_operation('withdraw_requests.json', mode='w', data=data)
    except Exception as e:
        print(f"Ошибка сохранения withdraw_requests: {e}")
        return False

def log_admin_action(admin_id, action, target_user=None, amount=None, details=None):
    """Логирование действий администратора"""
    try:
        logs = safe_file_operation('admin_logs.json', mode='r', default=[])
        
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'admin_id': admin_id,
            'action': action,
            'target_user': target_user,
            'amount': amount,
            'details': details,
            'ip': 'N/A'  # В реальном приложении можно добавить IP
        }
        
        logs.append(log_entry)
        if len(logs) > 10000:  # Ограничиваем лог
            logs = logs[-5000:]
        
        safe_file_operation('admin_logs.json', mode='w', data=logs)
    except Exception as e:
        print(f"Ошибка логирования: {e}")

# ВНИМАНИЕ: Админ ID остаются хардкодированными по вашему требованию
# В реальном проекте их нужно вынести в конфигурационный файл или переменные окружения
ADMIN_IDS = [8118184388, 5046075976]

def is_admin(user_id):
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS

def validate_user_id(user_id_str):
    """Валидация ID пользователя"""
    try:
        user_id = int(user_id_str)
        if 0 < user_id < 10**12:  # Разумные ограничения
            return str(user_id)
        return None
    except (ValueError, TypeError):
        return None

def validate_amount(amount_str, max_amount=1000000):
    """Валидация суммы"""
    try:
        amount = float(amount_str)
        if amount <= 0:
            return None, "Сумма должна быть положительной"
        if amount > max_amount:
            return None, f"Максимальная сумма: {max_amount}₽"
        # Округляем до 2 знаков
        return round(amount, 2), None
    except (ValueError, TypeError):
        return None, "Некорректная сумма"

def sanitize_text(text, max_length=1000):
    """Очистка текста"""
    if not text:
        return ""
    # Ограничение длины
    text = str(text)[:max_length]
    # Удаляем опасные символы
    dangerous_chars = ['<', '>', '&', '"', "'", '`', ';']
    for char in dangerous_chars:
        text = text.replace(char, '')
    return text

def register_admin_handlers(bot):
    """Регистрирует только админ-обработчики"""

    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        user_id = message.from_user.id
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "❌ У вас нет прав доступа к админ-панели.")
            log_admin_action(user_id, "unauthorized_access_attempt")
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

        log_admin_action(user_id, "admin_panel_opened")
        
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
            log_admin_action(user_id, "unauthorized_callback", details=call.data)
            return

        if call.data == "admin_give_balance":
            log_admin_action(user_id, "give_balance_requested")
            bot.edit_message_text(
                """💰 <b>ВЫДАЧА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 100</code> - выдать 100₽ пользователю с ID 123456789

⚠️ <b>Максимальная сумма за раз:</b> 1,000,000₽</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_give_balance)

        elif call.data == "admin_set_balance":
            log_admin_action(user_id, "set_balance_requested")
            bot.edit_message_text(
                """⚡ <b>УСТАНОВКА БАЛАНСА</b>

<blockquote>Введите данные в формате:
<code>ID_пользователя сумма</code>

📝 <b>Пример:</b>
<code>123456789 200</code> - установить баланс 200₽ пользователю с ID 123456789

⚠️ <b>Максимальный баланс:</b> 10,000,000₽</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_set_balance)

        elif call.data == "admin_user_stats":
            log_admin_action(user_id, "user_stats_requested")
            bot.edit_message_text(
                """📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>Введите ID пользователя:</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_user_stats)

        elif call.data == "admin_all_users":
            log_admin_action(user_id, "all_users_requested")
            show_all_users(call.message)

        elif call.data == "admin_broadcast":
            log_admin_action(user_id, "broadcast_requested")
            bot.edit_message_text(
                """📢 <b>РАССЫЛКА СООБЩЕНИЙ</b>

<blockquote>Введите сообщение для рассылки всем пользователям:</blockquote>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(call.message, process_broadcast)

        elif call.data == "admin_withdrawals":
            log_admin_action(user_id, "withdrawals_view_requested")
            show_withdrawals_menu(call.message)

        elif call.data == "admin_remove_balance":
            log_admin_action(user_id, "remove_balance_requested")
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
            status = req.get('status', 'pending')

            status_emoji = '⏳' if status == 'pending' else '✅' if status == 'approved' else '❌'
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{status_emoji} #{req_id} | {amount}₽",
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
            user_id = call.from_user.id
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав доступа!")
                return

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

            # Валидация данных
            user_id_req = req.get('user_id', '0')
            amount = req.get('amount', 0)
            method = req.get('method', 'Неизвестно')
            data = req.get('data', 'Не указано')
            status = req.get('status', 'pending')
            created_at = req.get('created_at', 'Неизвестно')

            # Ограничение длины реквизитов для безопасности
            if len(str(data)) > 500:
                data = str(data)[:497] + "..."

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

<blockquote>👤 <b>Пользователь:</b> ID {user_id_req}
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
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_approve_'))
    def approve_withdraw_request(call):
        try:
            admin_id = call.from_user.id
            if not is_admin(admin_id):
                bot.answer_callback_query(call.id, "❌ Нет прав доступа!")
                return

            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            for i, req in enumerate(requests):
                if req.get('id') == req_id:
                    # Проверяем, что заявка еще не обработана
                    if req.get('status') != 'pending':
                        bot.answer_callback_query(call.id, "⚠️ Заявка уже обработана")
                        return
                    
                    req['status'] = 'approved'
                    req['processed_by'] = admin_id
                    req['processed_at'] = datetime.now().strftime('%d.%m.%Y %H:%M')

                    user_id = req.get('user_id')
                    amount = req.get('amount', 0)
                    
                    # Проверяем баланс пользователя
                    users_data = load_users_data()
                    
                    if str(user_id) in users_data:
                        current_balance = users_data[str(user_id)].get('balance', 0)
                        
                        if current_balance >= amount:
                            users_data[str(user_id)]['balance'] = current_balance - amount
                            save_users_data(users_data)
                            
                            # Логируем действие
                            log_admin_action(admin_id, "withdraw_approved", 
                                           target_user=user_id, amount=amount)
                            
                            try:
                                bot.send_message(
                                    user_id,
                                    f"""✅ <b>ЗАЯВКА НА ВЫВОД ОДОБРЕНА</b>

<blockquote>💰 <b>Сумма:</b> {amount}₽
📋 <b>Метод:</b> {req.get('method', 'Неизвестно')}
📝 <b>Реквизиты:</b> {req.get('data', 'Не указано')}
📅 <b>Дата обработки:</b> {req['processed_at']}</blockquote>

💸 <i>Средства будут переведены в течение 24 часов</i>""",
                                    parse_mode="HTML"
                                )
                            except:
                                pass
                        else:
                            bot.answer_callback_query(call.id, "❌ У пользователя недостаточно средств!")
                            return

                    break

            save_withdraw_requests(requests)
            bot.answer_callback_query(call.id, "✅ Заявка одобрена!")
            view_withdraw_request(call)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_reject_'))
    def reject_withdraw_request(call):
        try:
            admin_id = call.from_user.id
            if not is_admin(admin_id):
                bot.answer_callback_query(call.id, "❌ Нет прав доступа!")
                return

            req_id = int(call.data.split('_')[-1])
            requests = load_withdraw_requests()

            for i, req in enumerate(requests):
                if req.get('id') == req_id:
                    # Проверяем, что заявка еще не обработана
                    if req.get('status') != 'pending':
                        bot.answer_callback_query(call.id, "⚠️ Заявка уже обработана")
                        return
                    
                    req['status'] = 'rejected'
                    req['processed_by'] = admin_id
                    req['processed_at'] = datetime.now().strftime('%d.%m.%Y %H:%M')
                    req['rejection_reason'] = 'Отклонено администратором'

                    user_id = req.get('user_id')
                    amount = req.get('amount', 0)
                    
                    # Логируем действие
                    log_admin_action(admin_id, "withdraw_rejected", 
                                   target_user=user_id, amount=amount)
                    
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
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}")

    def process_broadcast(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        broadcast_text = sanitize_text(message.text, max_length=4000)
        
        if not broadcast_text or len(broadcast_text) < 5:
            bot.send_message(message.chat.id, "❌ Сообщение слишком короткое.")
            return

        users_data = load_users_data()
        
        bot.send_message(
            message.chat.id,
            f"""📢 <b>НАЧАЛО РАССЫЛКИ</b>

<blockquote>📝 <b>Сообщение:</b>
{broadcast_text[:200]}...

👥 <b>Получателей:</b> {len(users_data)}
⏳ <b>Начинаем отправку...</b></blockquote>""",
            parse_mode="HTML"
        )

        success_count = 0
        fail_count = 0
        start_time = time.time()
        
        # Ограничиваем скорость рассылки (не более 30 сообщений в секунду)
        max_messages_per_second = 30
        
        for i, (user_id, user_data) in enumerate(users_data.items()):
            try:
                # Задержка для ограничения скорости
                if i % max_messages_per_second == 0 and i > 0:
                    time.sleep(1)
                
                bot.send_message(
                    user_id,
                    f"""📢 <b>ОБЪЯВЛЕНИЕ ОТ АДМИНИСТРАЦИИ</b>

<blockquote>{broadcast_text}</blockquote>""",
                    parse_mode="HTML"
                )
                success_count += 1
                
            except Exception as e:
                fail_count += 1
            
            # Периодический отчет о прогрессе
            if i % 100 == 0 and i > 0:
                progress = (i / len(users_data)) * 100
                bot.edit_message_text(
                    f"""📢 <b>РАССЫЛКА В ПРОЦЕССЕ...</b>

<blockquote>📊 <b>Прогресс:</b> {i}/{len(users_data)} ({progress:.1f}%)
✅ Успешно: {success_count}
❌ Не доставлено: {fail_count}</blockquote>""",
                    message.chat.id,
                    message.message_id + 1,
                    parse_mode="HTML"
                )

        elapsed_time = time.time() - start_time
        
        # Логируем рассылку
        log_admin_action(admin_id, "broadcast_sent", 
                        details=f"success:{success_count}, fail:{fail_count}, time:{elapsed_time:.1f}s")
        
        bot.send_message(
            message.chat.id,
            f"""✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>

<blockquote>📊 <b>Статистика:</b>
✅ Успешно: {success_count}
❌ Не доставлено: {fail_count}
👥 Всего получателей: {len(users_data)}
⏱️ <b>Время выполнения:</b> {elapsed_time:.1f} сек.</blockquote>""",
            parse_mode="HTML"
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_back")
    def handle_back_button(call):
        admin_id = call.from_user.id
        if not is_admin(admin_id):
            bot.answer_callback_query(call.id, "❌ Нет прав доступа!")
            return
        
        log_admin_action(admin_id, "navigated_back")
        admin_panel(call.message)
        bot.answer_callback_query(call.id)

    def process_give_balance(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            # Валидация user_id
            target_user_id = validate_user_id(parts[0])
            if not target_user_id:
                bot.send_message(message.chat.id, "❌ Некорректный ID пользователя.")
                return

            # Валидация суммы
            amount, error = validate_amount(parts[1], max_amount=1000000)
            if error:
                bot.send_message(message.chat.id, f"❌ {error}")
                return

            users_data = load_users_data()

            if target_user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден.")
                return

            current_balance = users_data[target_user_id].get('balance', 0)
            new_balance = current_balance + amount
            
            # Проверка на максимальный баланс
            if new_balance > 10000000:  # Макс 10 млн
                bot.send_message(message.chat.id, "❌ Баланс пользователя превысит максимально допустимый (10,000,000₽)")
                return
            
            users_data[target_user_id]['balance'] = new_balance
            save_users_data(users_data)

            username = users_data[target_user_id].get('username', 'Неизвестно')
            
            # Логируем действие
            log_admin_action(admin_id, "balance_given", 
                           target_user=target_user_id, amount=amount)
            
            bot.send_message(
                message.chat.id,
                f"""✅ <b>БАЛАНС ВЫДАН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {target_user_id})
💰 <b>Выдано:</b> {amount}₽
💳 <b>Новый баланс:</b> {new_balance}₽</blockquote>""",
                parse_mode="HTML"
            )

            try:
                bot.send_message(
                    target_user_id,
                    f"""🎉 <b>Вам начислены средства!</b>

<blockquote>💰 <b>Сумма:</b> {amount}₽
💳 <b>Текущий баланс:</b> {new_balance}₽</blockquote>""",
                    parse_mode="HTML"
                )
            except:
                bot.send_message(message.chat.id, "⚠️ Не удалось уведомить пользователя")

        except ValueError as e:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

    def process_set_balance(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            # Валидация user_id
            target_user_id = validate_user_id(parts[0])
            if not target_user_id:
                bot.send_message(message.chat.id, "❌ Некорректный ID пользователя.")
                return

            # Валидация суммы
            amount, error = validate_amount(parts[1], max_amount=10000000)  # Макс 10 млн
            if error:
                bot.send_message(message.chat.id, f"❌ {error}")
                return

            users_data = load_users_data()

            if target_user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден.")
                return

            old_balance = users_data[target_user_id].get('balance', 0)
            users_data[target_user_id]['balance'] = amount
            save_users_data(users_data)

            username = users_data[target_user_id].get('username', 'Неизвестно')
            
            # Логируем действие
            log_admin_action(admin_id, "balance_set", 
                           target_user=target_user_id, amount=amount,
                           details=f"old_balance:{old_balance}")
            
            bot.send_message(
                message.chat.id,
                f"""⚡ <b>БАЛАНС УСТАНОВЛЕН</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {target_user_id})
💳 <b>Новый баланс:</b> {amount}₽
📊 <b>Старый баланс:</b> {old_balance}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError as e:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

    def process_remove_balance(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: <code>ID сумма</code>", parse_mode="HTML")
                return

            # Валидация user_id
            target_user_id = validate_user_id(parts[0])
            if not target_user_id:
                bot.send_message(message.chat.id, "❌ Некорректный ID пользователя.")
                return

            # Валидация суммы
            amount, error = validate_amount(parts[1], max_amount=1000000)
            if error:
                bot.send_message(message.chat.id, f"❌ {error}")
                return

            users_data = load_users_data()

            if target_user_id not in users_data:
                bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден.")
                return

            current_balance = users_data[target_user_id].get('balance', 0)
            if current_balance < amount:
                bot.send_message(message.chat.id, f"❌ Недостаточно средств. У пользователя только {current_balance}₽")
                return

            new_balance = current_balance - amount
            users_data[target_user_id]['balance'] = new_balance
            save_users_data(users_data)

            username = users_data[target_user_id].get('username', 'Неизвестно')
            
            # Логируем действие
            log_admin_action(admin_id, "balance_removed", 
                           target_user=target_user_id, amount=amount)
            
            bot.send_message(
                message.chat.id,
                f"""➖ <b>БАЛАНС СНЯТ</b>

<blockquote>👤 <b>Пользователь:</b> @{username} (ID: {target_user_id})
💰 <b>Снято:</b> {amount}₽
💳 <b>Новый баланс:</b> {new_balance}₽</blockquote>""",
                parse_mode="HTML"
            )

        except ValueError as e:
            bot.send_message(message.chat.id, "❌ Неверная сумма. Введите число.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

    def process_user_stats(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        user_id_str = message.text.strip()
        target_user_id = validate_user_id(user_id_str)
        
        if not target_user_id:
            bot.send_message(message.chat.id, f"❌ Некорректный ID пользователя.")
            return

        users_data = load_users_data()

        if target_user_id not in users_data:
            bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден.")
            return

        user_data = users_data[target_user_id]
        username = user_data.get('username', 'Неизвестно')
        balance = user_data.get('balance', 0)
        level = user_data.get('level', 1)
        first_seen = user_data.get('first_seen', 'Неизвестно')
        
        # Логируем запрос статистики
        log_admin_action(admin_id, "user_stats_viewed", target_user=target_user_id)

        bot.send_message(
            message.chat.id,
            f"""📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>

<blockquote>👤 <b>Username:</b> @{username}
🆔 <b>ID:</b> {target_user_id}
💰 <b>Баланс:</b> {balance}₽
🏅 <b>Уровень:</b> {level}
📅 <b>Первый вход:</b> {first_seen}</blockquote>""",
            parse_mode="HTML"
        )

    def show_all_users(message):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return

        users_data = load_users_data()

        if not users_data:
            bot.send_message(message.chat.id, "❌ Нет зарегистрированных пользователей.")
            return

        total_balance = sum(user_data.get('balance', 0) for user_data in users_data.values())
        total_users = len(users_data)
        
        # Логируем запрос списка пользователей
        log_admin_action(admin_id, "all_users_viewed", details=f"total:{total_users}")

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

    print("✅ Админ-команды зарегистрированы!")
