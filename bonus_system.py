import json
import time
import logging
from datetime import datetime, timedelta
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы бонусной системы
BONUS_AMOUNT = 10  # Сумма бонуса в рублях
BONUS_COOLDOWN = 24 * 60 * 60  # 24 часа в секундах
PENALTY_DAYS = 3  # Дней блокировки при удалении приписки
CHECK_INTERVAL = 2 * 60 * 60  # Проверка каждые 2 часа

# Требования для получения бонуса
REQUIRED_USERNAME_TAG = "@festery"  # В нике
REQUIRED_BIO_TAG = "@festery-лучшая игровая зона"  # В описании

BONUS_DATA_FILE = 'bonus_data.json'

def load_bonus_data():
    """Загружает данные о бонусах"""
    try:
        with open(BONUS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных бонусов: {e}")
        return {}

def save_bonus_data(data):
    """Сохраняет данные о бонусах"""
    try:
        with open(BONUS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных бонусов: {e}")
        return False

def load_users_data():
    """Загружает данные пользователей"""
    try:
        with open('users_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных пользователей: {e}")
        return {}

def save_users_data(data):
    """Сохраняет данные пользователей"""
    try:
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных пользователей: {e}")
        return False

def check_user_tags(bot, user_id):
    """
    Проверяет наличие требуемых приписок у пользователя
    
    Returns:
        tuple: (has_username_tag, has_bio_tag, username, bio)
    """
    try:
        # Получаем информацию о пользователе
        chat = bot.get_chat(user_id)
        
        # Проверяем username (имя в Telegram)
        username = chat.username or ""
        first_name = chat.first_name or ""
        
        # Проверяем наличие @festery в никнейме (username или first_name)
        has_username_tag = REQUIRED_USERNAME_TAG.lower() in username.lower() or \
                          REQUIRED_USERNAME_TAG.lower() in first_name.lower()
        
        # Проверяем bio (описание профиля)
        bio = chat.bio or ""
        has_bio_tag = REQUIRED_BIO_TAG.lower() in bio.lower()
        
        logger.info(f"Проверка тегов для {user_id}: username={has_username_tag}, bio={has_bio_tag}")
        
        return has_username_tag, has_bio_tag, username or first_name, bio
        
    except Exception as e:
        logger.error(f"Ошибка проверки тегов пользователя {user_id}: {e}")
        return False, False, "", ""

def can_claim_bonus(user_id):
    """
    Проверяет, может ли пользователь получить бонус
    
    Returns:
        tuple: (can_claim, reason, time_left)
    """
    bonus_data = load_bonus_data()
    user_bonus = bonus_data.get(str(user_id), {})
    
    current_time = int(time.time())
    
    # Проверка на блокировку за удаление приписки
    penalty_until = user_bonus.get('penalty_until', 0)
    if penalty_until > current_time:
        time_left = penalty_until - current_time
        days_left = time_left // (24 * 60 * 60)
        hours_left = (time_left % (24 * 60 * 60)) // 3600
        return False, "penalty", (days_left, hours_left)
    
    # Проверка кулдауна
    last_claim = user_bonus.get('last_claim', 0)
    cooldown_end = last_claim + BONUS_COOLDOWN
    
    if cooldown_end > current_time:
        time_left = cooldown_end - current_time
        hours_left = time_left // 3600
        minutes_left = (time_left % 3600) // 60
        return False, "cooldown", (hours_left, minutes_left)
    
    return True, "ok", None

def claim_bonus(bot, user_id):
    """
    Выдает бонус пользователю
    
    Returns:
        tuple: (success, message)
    """
    try:
        # Проверяем теги
        has_username_tag, has_bio_tag, username, bio = check_user_tags(bot, user_id)
        
        if not has_username_tag or not has_bio_tag:
            # Формируем инструкцию
            missing = []
            if not has_username_tag:
                missing.append(f"❌ В нике должно быть: <code>{REQUIRED_USERNAME_TAG}</code>")
            if not has_bio_tag:
                missing.append(f"❌ В описании должно быть: <code>{REQUIRED_BIO_TAG}</code>")
            
            instruction = f"""
<blockquote expandable>╔══════════════════════╗
   ⚠️ <b>ТРЕБОВАНИЯ НЕ ВЫПОЛНЕНЫ</b>
╚══════════════════════╝</blockquote>

<b>Для получения бонуса необходимо:</b>

{chr(10).join(missing)}

<blockquote>
📋 <b>Инструкция:</b>

1️⃣ Добавьте <code>{REQUIRED_USERNAME_TAG}</code> в ваш ник
2️⃣ Добавьте <code>{REQUIRED_BIO_TAG}</code> в описание профиля

💡 Как добавить описание:
   Настройки → Редактировать профиль → Био
</blockquote>

✅ После выполнения требований снова используйте команду /bonus
"""
            return False, instruction
        
        # Проверяем возможность получения бонуса
        can_claim, reason, time_data = can_claim_bonus(user_id)
        
        if not can_claim:
            if reason == "penalty":
                days, hours = time_data
                return False, f"""
<blockquote expandable>╔══════════════════════╗
   🚫 <b>БОНУС ЗАБЛОКИРОВАН</b>
╚══════════════════════╝</blockquote>

<blockquote>
⚠️ Вы удалили приписку бота!
🔒 Бонус заблокирован на <b>{days} дней {hours} часов</b>

💡 Не удаляйте приписку для получения бонусов
</blockquote>
"""
            elif reason == "cooldown":
                hours, minutes = time_data
                return False, f"""
<blockquote expandable>╔══════════════════════╗
   ⏰ <b>БОНУС УЖЕ ПОЛУЧЕН</b>
╚══════════════════════╝</blockquote>

<blockquote>
⏳ Следующий бонус через: <b>{hours} ч {minutes} мин</b>
💰 Сумма бонуса: <b>{BONUS_AMOUNT} ₽</b>
</blockquote>

💡 Бонус доступен раз в 24 часа!
"""
        
        # Выдаем бонус
        users_data = load_users_data()
        user_id_str = str(user_id)
        
        if user_id_str not in users_data:
            users_data[user_id_str] = {'balance': 0}
        
        users_data[user_id_str]['balance'] = round(
            users_data[user_id_str].get('balance', 0) + BONUS_AMOUNT, 2
        )
        
        save_users_data(users_data)
        
        # Обновляем данные бонуса
        bonus_data = load_bonus_data()
        bonus_data[user_id_str] = {
            'last_claim': int(time.time()),
            'total_claimed': bonus_data.get(user_id_str, {}).get('total_claimed', 0) + 1,
            'last_check': int(time.time()),
            'has_tags': True,
            'penalty_until': 0
        }
        save_bonus_data(bonus_data)
        
        new_balance = users_data[user_id_str]['balance']
        total_bonuses = bonus_data[user_id_str]['total_claimed']
        
        success_msg = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>БОНУС ПОЛУЧЕН!</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Начислено:</b> +{BONUS_AMOUNT} ₽
💎 <b>Новый баланс:</b> {new_balance} ₽
🎁 <b>Всего бонусов:</b> {total_bonuses}
</blockquote>

⏰ Следующий бонус через: <b>24 часа</b>

💡 Не забывайте сохранять приписку в нике и описании!
"""
        
        logger.info(f"Бонус {BONUS_AMOUNT}₽ выдан пользователю {user_id}")
        return True, success_msg
        
    except Exception as e:
        logger.error(f"Ошибка выдачи бонуса: {e}")
        return False, "❌ Произошла ошибка при начислении бонуса. Попробуйте позже."

def check_tags_periodically(bot):
    """
    Периодически проверяет наличие приписок у пользователей, получивших бонусы
    Запускается каждые 2 часа
    """
    def check_loop():
        while True:
            try:
                time.sleep(CHECK_INTERVAL)
                
                logger.info("Начало периодической проверки приписок...")
                
                bonus_data = load_bonus_data()
                current_time = int(time.time())
                
                for user_id, data in bonus_data.items():
                    # Проверяем только тех, кто получал бонусы
                    if data.get('total_claimed', 0) == 0:
                        continue
                    
                    # Пропускаем тех, кто уже под блокировкой
                    if data.get('penalty_until', 0) > current_time:
                        continue
                    
                    # Проверяем теги
                    has_username_tag, has_bio_tag, username, bio = check_user_tags(bot, int(user_id))
                    
                    # Если раньше были теги, а сейчас нет - блокируем
                    if data.get('has_tags', False) and (not has_username_tag or not has_bio_tag):
                        logger.warning(f"Пользователь {user_id} удалил приписку! Блокируем бонус на {PENALTY_DAYS} дней")
                        
                        penalty_until = current_time + (PENALTY_DAYS * 24 * 60 * 60)
                        bonus_data[user_id]['penalty_until'] = penalty_until
                        bonus_data[user_id]['has_tags'] = False
                        
                        # Отправляем уведомление пользователю
                        try:
                            bot.send_message(
                                int(user_id),
                                f"""
<blockquote expandable>╔══════════════════════╗
   ⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>
╚══════════════════════╝</blockquote>

<blockquote>
🚫 Вы удалили приписку бота!
🔒 Бонус заблокирован на <b>{PENALTY_DAYS} дней</b>

❌ Отсутствует:
{'• Приписка в нике' if not has_username_tag else ''}
{'• Приписка в описании' if not has_bio_tag else ''}
</blockquote>

💡 Верните приписку, чтобы получать бонусы в будущем!
""",
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления {user_id}: {e}")
                    
                    # Обновляем статус проверки
                    elif has_username_tag and has_bio_tag:
                        bonus_data[user_id]['has_tags'] = True
                        bonus_data[user_id]['last_check'] = current_time
                
                save_bonus_data(bonus_data)
                logger.info("Периодическая проверка приписок завершена")
                
            except Exception as e:
                logger.error(f"Ошибка в периодической проверке: {e}")
    
    # Запускаем в отдельном потоке
    thread = threading.Thread(target=check_loop, daemon=True)
    thread.start()
    logger.info("Запущена периодическая проверка приписок (каждые 2 часа)")

def register_bonus_handlers(bot):
    """Регистрирует обработчики команд бонусной системы"""
    
    @bot.message_handler(commands=['bonus', 'бонус'])
    def bonus_command(message):
        """Обработчик команды /bonus и /бонус"""
        try:
            user_id = message.from_user.id
            
            success, response = claim_bonus(bot, user_id)
            
            bot.send_message(
                message.chat.id,
                response,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Ошибка в обработчике /bonus: {e}")
            bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка. Попробуйте позже."
            )
    
    # Запускаем периодическую проверку
    check_tags_periodically(bot)
    
    logger.info("✅ Обработчики бонусной системы зарегистрированы")
