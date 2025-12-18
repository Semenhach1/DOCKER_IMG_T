import sqlite3
import asyncio
import requests
import os
import random
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.middlewares import BaseMiddleware
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.events import NewMessage, MessageEdited
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError
from telethon.tl.types import User

# ==================== КОНФИГУРАЦИЯ ====================
API_TOKEN = '8561321074:AAE31isq5h4BteSIEG21FUsrn03lrBr6vsE'
ADMIN_ID = 8065283718

CRYPTO_PAY_TOKEN = '493329:AAC01t5EBcKTvSiZImN8qPHHatX5Nu9mqRa'
BASE_URL = 'https://pay.crypt.bot/api'

SESSION_NAME = 'session_name.session'
TARGET_BOT = '@ikeafryyyyyyyyyyyyyyzebot'   # бот для фриза

API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

DB_NAME = 'web.db'

telethon_lock = asyncio.Lock()

# ==================== БАЗА ДАННЫХ ====================
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    subscription_end TEXT
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    dc_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS daily_limits (
                    user_id INTEGER PRIMARY KEY,
                    limit_count INTEGER DEFAULT 0,
                    used_today INTEGER DEFAULT 0,
                    last_date TEXT
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    queued_at DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS last_submission_time (
                    key TEXT PRIMARY KEY,
                    timestamp DATETIME
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    days INTEGER,
                    used INTEGER DEFAULT 0
                 )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (
                    user_id INTEGER PRIMARY KEY,
                    warn_count INTEGER DEFAULT 0
                 )''')

# Значения по умолчанию
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('accept_username', '1')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_daily_limit', '5')")  # По умолчанию 5 отправок в день
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('max_warnings', '3')")  # По умолчанию максимум 3 предупреждения
conn.commit()

# ==================== AIOGRAM ====================
class Form(StatesGroup):
    username = State()
    set_limit = State()
    promo_code = State()
    set_max_warns = State()

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ==================== MIDDLEWARE ДЛЯ ЗАЩИТЫ ОТ DDoS ====================
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit=5, period=60):
        super().__init__()
        self.limit = limit
        self.period = period
        self.last_times = {}

    async def on_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        now = datetime.now()
        if user_id in self.last_times:
            times = [t for t in self.last_times[user_id] if now - t < timedelta(seconds=self.period)]
            if len(times) >= self.limit:
                await message.reply("🚫 Слишком много запросов. Подождите минуту.")
                return True  # Прерываем обработку
            times.append(now)
            self.last_times[user_id] = times
        else:
            self.last_times[user_id] = [now]

dp.middleware.setup(RateLimitMiddleware())

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def has_subscription(user_id):
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return datetime.fromisoformat(row[0]) > datetime.now()
    return False

def get_subscription_end(user_id):
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return datetime.fromisoformat(row[0])
    return None

def extend_subscription(user_id, days=30):
    current_end = get_subscription_end(user_id) or datetime.now()
    end = current_end + timedelta(days=days)
    cursor.execute("""INSERT OR REPLACE INTO users (user_id, subscription_end)
                      VALUES (?, ?)""", (user_id, end.isoformat()))
    conn.commit()

def revoke_subscription(user_id):
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()

def is_accepting_usernames():
    cursor.execute("SELECT value FROM settings WHERE key='accept_username'")
    row = cursor.fetchone()
    return row and row[0] == '1'

def set_accept_usernames(enabled: bool):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('accept_username', ?)",
                   ('1' if enabled else '0',))
    conn.commit()

def get_default_daily_limit():
    cursor.execute("SELECT value FROM settings WHERE key='default_daily_limit'")
    row = cursor.fetchone()
    return int(row[0]) if row else 5

def set_default_daily_limit(limit: int):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_daily_limit', ?)", (str(limit),))
    # Обновляем лимит для всех существующих пользователей
    cursor.execute("UPDATE daily_limits SET limit_count = ?", (limit,))
    conn.commit()

def get_max_warnings():
    cursor.execute("SELECT value FROM settings WHERE key='max_warnings'")
    row = cursor.fetchone()
    return int(row[0]) if row else 3

def set_max_warnings(max_warns: int):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('max_warnings', ?)", (str(max_warns),))
    conn.commit()

def get_user_warnings(user_id):
    cursor.execute("SELECT warn_count FROM warnings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute("INSERT INTO warnings (user_id, warn_count) VALUES (?, 0)", (user_id,))
        conn.commit()
        return 0

def add_warning(user_id):
    cursor.execute("UPDATE warnings SET warn_count = warn_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    warn_count = get_user_warnings(user_id)
    max_warns = get_max_warnings()
    if warn_count >= max_warns:
        revoke_subscription(user_id)
        return True  # Подписка снята
    return False

def remove_warning(user_id):
    cursor.execute("UPDATE warnings SET warn_count = warn_count - 1 WHERE user_id = ? AND warn_count > 0", (user_id,))
    conn.commit()

def get_user_daily_limit(user_id):
    today = datetime.now().date().isoformat()
    cursor.execute("SELECT limit_count, used_today, last_date FROM daily_limits WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        limit_count, used_today, last_date = row
        if last_date != today:
            used_today = 0
            cursor.execute("UPDATE daily_limits SET used_today = 0, last_date = ? WHERE user_id = ?", (today, user_id))
            conn.commit()
        return limit_count, used_today
    else:
        default_limit = get_default_daily_limit()
        cursor.execute("INSERT INTO daily_limits (user_id, limit_count, used_today, last_date) VALUES (?, ?, 0, ?)", (user_id, default_limit, today))
        conn.commit()
        return default_limit, 0

def increment_user_used_today(user_id):
    cursor.execute("UPDATE daily_limits SET used_today = used_today + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_last_submission_time():
    cursor.execute("SELECT timestamp FROM last_submission_time WHERE key = 'last'")
    row = cursor.fetchone()
    return datetime.fromisoformat(row[0]) if row else None

def set_last_submission_time(ts):
    cursor.execute("INSERT OR REPLACE INTO last_submission_time (key, timestamp) VALUES ('last', ?)", (ts.isoformat(),))
    conn.commit()

def generate_promo_code(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def create_promo_code(days):
    code = generate_promo_code()
    cursor.execute("INSERT INTO promo_codes (code, days) VALUES (?, ?)", (code, days))
    conn.commit()
    return code

def activate_promo_code(user_id, code):
    cursor.execute("SELECT days, used FROM promo_codes WHERE code = ?", (code,))
    row = cursor.fetchone()
    if row and row[1] == 0:
        days, _ = row
        extend_subscription(user_id, days)
        cursor.execute("UPDATE promo_codes SET used = 1 WHERE code = ?", (code,))
        conn.commit()
        return True, days
    return False, 0

async def process_queue():
    while True:
        last_ts = get_last_submission_time()
        now = datetime.now()
        if last_ts is None or now - last_ts >= timedelta(minutes=6):
            cursor.execute("SELECT id, user_id, username FROM queue ORDER BY queued_at ASC LIMIT 1")
            row = cursor.fetchone()
            if row:
                q_id, user_id, username = row
                await process_username(username, user_id)
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                set_last_submission_time(now)
        await asyncio.sleep(60)  # Проверять каждую минуту

# ==================== ОПЛАТА ====================
async def create_invoice():
    headers = {'Crypto-Pay-API-Token': CRYPTO_PAY_TOKEN}
    payload = {
        'asset': 'USDT',
        'amount': '4.00',
        'description': 'Подписка 1 месяц — Freezer Bot'
    }
    r = requests.post(f'{BASE_URL}/createInvoice', headers=headers, json=payload)
    data = r.json().get('result', {})
    return data.get('invoice_id'), data.get('bot_invoice_url')

async def check_payment(invoice_id):
    headers = {'Crypto-Pay-API-Token': CRYPTO_PAY_TOKEN}
    r = requests.post(f'{BASE_URL}/getInvoices', headers=headers, json={'invoice_ids': str(invoice_id)})
    items = r.json().get('result', {}).get('items', [])
    return len(items) > 0 and items[0]['status'] == 'paid'

# ==================== ОСНОВНАЯ ЛОГИКА (С EVENT HANDLER ДЛЯ NEW И EDITED) ====================
async def process_username(username: str, user_id: int):
    if not is_accepting_usernames():
        await bot.send_message(user_id, "🚫 Отправка временно отключена администратором.")
        return

    # Проверка ежедневного лимита
    daily_limit, used_today = get_user_daily_limit(user_id)
    if used_today >= daily_limit:
        await bot.send_message(user_id, f"🚫 Вы достигли ежедневного лимита отправок ({daily_limit}). Подождите до завтра.")
        return

    increment_user_used_today(user_id)  # Засчитываем попытку сразу

    async with telethon_lock:
        client = TelegramClient(SQLiteSession(SESSION_NAME), API_ID, API_HASH, timeout=60)
        await client.start()

        message_handler = None
        dc_id = 0  # По умолчанию 0 на ошибку
        try:
            # Проверка существования username и DC
            try:
                entity = await client.get_entity(username)
                if isinstance(entity, User) and entity.photo:
                    dc_id = entity.photo.dc_id
                    if dc_id not in [1, 3, 5]:
                        await bot.send_message(user_id, "❌ Username должен быть на DC1, DC3 или DC5.")
                        cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                        conn.commit()
                        return
                else:
                    await bot.send_message(user_id, "⚠️ Не удалось определить DC (пользователь без фото или не пользователь).")
                    cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                    conn.commit()
                    return
            except (UsernameNotOccupiedError, UsernameInvalidError):
                await bot.send_message(user_id, "❌ Invalid username.")
                cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                conn.commit()
                return

            # Лог админу
            user_chat = await bot.get_chat(user_id)
            user_username = user_chat.username or 'no_username'
            await bot.send_message(ADMIN_ID, f"🔍 Запрос от @{user_username} (ID: {user_id})\n"
                                       f"Username: {username}")

            # Получаем entity бота
            bot_entity = await client.get_entity(TARGET_BOT)
            bot_id = bot_entity.id

            button_pressed = asyncio.Event()
            input_requested = asyncio.Event()

            # Event handler для новых и отредактированных сообщений
            async def message_handler(event):
                if event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for btn in row.buttons:
                            if hasattr(btn, 'data') and btn.data:
                                try:
                                    await client(GetBotCallbackAnswerRequest(
                                        peer=TARGET_BOT,
                                        msg_id=event.message.id,
                                        data=btn.data
                                    ))
                                    print(f"Pressed button: {btn.text}")
                                    button_pressed.set()
                                    await asyncio.sleep(3)
                                except Exception as e:
                                    print(f"Button press error: {e}")
                                break
                        if button_pressed.is_set():
                            break
                elif event.message.message and ("@username" in event.message.message.lower() or "введите username" in event.message.message.lower() or "username" in event.message.message.lower()):
                    await client.send_message(TARGET_BOT, username)
                    # Красивая анимация 50/50
                    animation_msg = await bot.send_message(user_id, "🎲 50/50 анимация: Подбрасываем монетку...")
                    await asyncio.sleep(1)
                    await bot.edit_message_text("🎲 50/50: Орёл или решка? 🔄", user_id, animation_msg.message_id)
                    await asyncio.sleep(1)
                    await bot.edit_message_text("🎲 50/50: Крутится... 🔄", user_id, animation_msg.message_id)
                    await asyncio.sleep(1)
                    result = "✅ Успех!" if datetime.now().second % 2 == 0 else "❌ Неудача!"  # Симуляция 50/50
                    await bot.edit_message_text(f"🎲 50/50: {result}\n✅ 50/50 успешно отправлены на {username}", user_id, animation_msg.message_id)
                    
                    cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                    conn.commit()
                    input_requested.set()

            # Добавляем handlers для NewMessage и MessageEdited
            client.add_event_handler(message_handler, NewMessage(from_users=bot_id))
            client.add_event_handler(message_handler, MessageEdited(from_users=bot_id))

            # Отправляем /start
            await client.send_message(TARGET_BOT, '/start')

            # Ждём кнопку
            try:
                await asyncio.wait_for(button_pressed.wait(), timeout=15)
            except asyncio.TimeoutError:
                await bot.send_message(user_id, "⚠️ Упс, отправил с запасных сессий, так как обычные не отвечают.")
                cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                conn.commit()
                return

            # Ждём запрос ввода с увеличенным таймаутом
            try:
                await asyncio.wait_for(input_requested.wait(), timeout=20)
            except asyncio.TimeoutError:
                await bot.send_message(user_id, "⚠️ Сессия занята или что-то ебнулось.")
                cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
                conn.commit()
                return

        except Exception as e:
            await bot.send_message(user_id, "❗ Ошибка при работе с сессией. Повторите через 5 минут.")
            print("Telethon error:", e)
            cursor.execute("INSERT INTO submissions (user_id, username, dc_id) VALUES (?, ?, ?)", (user_id, username, dc_id))
            conn.commit()
        finally:
            if message_handler is not None:
                client.remove_event_handler(message_handler, NewMessage)
                client.remove_event_handler(message_handler, MessageEdited)
            await client.disconnect()

async def handle_submission(username: str, tg_message: types.Message):
    last_ts = get_last_submission_time()
    now = datetime.now()
    user_id = tg_message.from_user.id
    if last_ts and now - last_ts < timedelta(minutes=6):
        # Ставим в очередь
        cursor.execute("INSERT INTO queue (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        await tg_message.reply(f"⏳ Ваш username {username} поставлен в очередь. Он будет обработан после истечения таймера.")
    else:
        await process_username(username, user_id)
        set_last_submission_time(now)

# ==================== ХЕНДЛЕРЫ ====================
@dp.message_handler(commands=['start'], state='*')
async def start_cmd(message: types.Message, state: FSMContext):
    await state.finish()
    uid = message.from_user.id
    daily_limit, used_today = get_user_daily_limit(uid)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Запустить 🚀", callback_data='send_username'))
    kb.add(InlineKeyboardButton("Профиль 👤", callback_data='profile'))
    if has_subscription(uid):
        await message.reply(f"👋 Добро пожаловать!\nУ вас активная подписка — можно запускать 🚀\nЕжедневный лимит: {used_today}/{daily_limit}", reply_markup=kb)
    else:
        await message.reply(f"👋 Добро пожаловать!\nУ вас нет подписки. Для запуска оплатите подписку.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('check_'))
async def check_pay(cb: types.CallbackQuery):
    inv_id = int(cb.data.split('_')[1])
    if await check_payment(inv_id):
        extend_subscription(cb.from_user.id, days=30)
        await cb.answer("✅ Оплата подтверждена!", show_alert=True)
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("Запустить 🚀", callback_data='send_username'))
        kb.add(InlineKeyboardButton("Профиль 👤", callback_data='profile'))
        await bot.send_message(cb.from_user.id, "🎉 Подписка активирована!\nТеперь можно запускать 🚀", reply_markup=kb)
    else:
        await cb.answer("⚠️ Оплата не найдена. Повторите позже.", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'send_username')
async def ask_username(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    if has_subscription(user_id):
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("OK ✅", callback_data='ok_rules'))
        await bot.send_message(user_id, "📜 Правила пользования web 2.0: \n"
                                        "1. Не злоупотребляйте сносом (не закидывайте на один и тот же аккаунт фризер несколько раз, это ничем не поможет).\n"
                                        "2. Сносите только новореги (может ебнуть и отлегу до 5-ти лет, но это редко)\n"
                                        "3. Сносите ОБЯЗАТЕЛЬНО только DC1, DC3, DC5 (на других дата центрах фризер не работает!!!)\n"
                                        "4. Не ломайте бота (не отправляйте фризер на несуществующие юзернеймы и тд — это только портит наши сессии!!!)\n"
                                        "Ответы на вопросы:\n"
                                        "— Как посмотреть DC и ID у аккаунта?\n"
                                        "Чтобы это сделать вам нужно скачать моды на телеграм, либо пользоваться @dateregbot.\n"
                                        "Например из модов на IOS есть SwiftGram, а на Android — AuyGram.\n"
                                        "— Почему не сносит?\n"
                                        "Вы неправильно что-либо сделали, либо система решила оставить аккаунт.\n"
                                        "Подарки в профиле и премка так же усложняют процесс сноса.\n"
                                        "— Что такое DC?\n"
                                        "DC — это Data Center. Значение присваивается при регистрации аккаунта. Например, если это США — DC будет 1. Если Бангладеш — DC5. Если снг страны — DC2 и так далее.", reply_markup=kb)
    else:
        inv_id, url = await create_invoice()
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("💳 Оплатить 4 USDT", url=url))
        kb.add(InlineKeyboardButton("🔄 Проверить оплату", callback_data=f'check_{inv_id}'))
        await bot.send_message(user_id, "❌ Подписка не активна.\nОплатите доступ:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == 'ok_rules')
async def ok_rules(cb: types.CallbackQuery):
    await cb.answer()
    await Form.username.set()
    await bot.send_message(cb.from_user.id, "📩 Пришли username в формате:\n@username")

@dp.message_handler(state=Form.username)
async def receive_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith('@'):
        await message.reply("❌ Ошибка: username должен начинаться с @")
        return
    await handle_submission(username, message)
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'profile')
async def show_profile(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id

    # Получаем общее количество отправленных
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()[0]

    # Получаем последние 5 username с dc_id
    cursor.execute("SELECT username, dc_id FROM submissions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
    last5 = cursor.fetchall()

    daily_limit, used_today = get_user_daily_limit(user_id)
    warn_count = get_user_warnings(user_id)
    max_warns = get_max_warnings()

    sub_end = get_subscription_end(user_id)
    if sub_end:
        if sub_end > datetime.now():
            sub_text = f"📅 Подписка активна до: {sub_end.strftime('%Y-%m-%d %H:%M')}\n"
        else:
            sub_text = "❌ Подписка истекла\n"
    else:
        sub_text = "❌ Нет подписки\n"

    async with telethon_lock:
        client = TelegramClient(SQLiteSession(SESSION_NAME), API_ID, API_HASH, timeout=60)
        await client.start()
        try:
            entity = await client.get_entity(user_id)
            if isinstance(entity, User) and entity.photo:
                user_dc = entity.photo.dc_id
                path = await client.download_profile_photo(entity)
            else:
                user_dc = "Неизвестно (нет фото)"
                path = None
        except Exception as e:
            user_dc = "Не удалось получить"
            path = None
            print(f"Error fetching user DC: {e}")
        finally:
            await client.disconnect()

    text = f"🆔 ID: {user_id}\n"
    text += f"🌐 Ваш DC: {user_dc}\n"
    text += sub_text
    text += f"⚠️ Предупреждения: {warn_count}/{max_warns}\n"
    text += f"📊 Всего отправлено: {total}\n"
    text += f"📅 Ежедневный лимит: {used_today}/{daily_limit}\n"
    text += "📜 Последние 5 username:\n"
    if last5:
        for un, dc in last5:
            text += f"{un} (DC {dc})\n"
    else:
        text += "Нет отправленных username.\n"

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu'))
    kb.add(InlineKeyboardButton("🔑 Активировать промокод", callback_data='activate_promo'))

    if path:
        await bot.send_photo(cb.from_user.id, photo=open(path, 'rb'), caption=text, reply_markup=kb)
        os.remove(path)
    else:
        await bot.send_message(cb.from_user.id, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == 'activate_promo')
async def activate_promo(cb: types.CallbackQuery):
    await cb.answer()
    await Form.promo_code.set()
    await bot.send_message(cb.from_user.id, "🔑 Введите промокод:")

@dp.message_handler(state=Form.promo_code)
async def receive_promo(message: types.Message, state: FSMContext):
    code = message.text.strip()
    success, days = activate_promo_code(message.from_user.id, code)
    if success:
        await message.reply(f"✅ Промокод активирован! Подписка продлена на {days} дней.")
    else:
        await message.reply("❌ Неверный или уже использованный промокод.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'back_to_menu')
async def back_to_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    daily_limit, used_today = get_user_daily_limit(uid)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Запустить 🚀", callback_data='send_username'))
    kb.add(InlineKeyboardButton("Профиль 👤", callback_data='profile'))
    if has_subscription(uid):
        await bot.send_message(cb.from_user.id, f"👋 Добро пожаловать!\nУ вас активная подписка — можно запускать 🚀\nЕжедневный лимит: {used_today}/{daily_limit}", reply_markup=kb)
    else:
        await bot.send_message(cb.from_user.id, f"👋 Добро пожаловать!\nУ вас нет подписки. Для запуска оплатите подписку.", reply_markup=kb)

# ==================== АДМИН-ПАНЕЛЬ ====================
@dp.message_handler(commands=['admin'], user_id=ADMIN_ID)
async def admin_menu(m: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Выдать подписку", callback_data='adm_subscribe'))
    kb.add(InlineKeyboardButton("Отозвать подписку", callback_data='adm_revoke'))
    kb.add(InlineKeyboardButton("Рассылка", callback_data='adm_broadcast'))
    kb.add(InlineKeyboardButton("Вкл/Выкл username", callback_data='adm_toggle_username'))
    kb.add(InlineKeyboardButton("Установить ежедневный лимит", callback_data='adm_set_limit'))
    kb.add(InlineKeyboardButton("Установить макс. предупреждений", callback_data='adm_set_max_warns'))
    kb.add(InlineKeyboardButton("Выдать предупреждение", callback_data='adm_warn'))
    kb.add(InlineKeyboardButton("Снять предупреждение", callback_data='adm_unwarn'))
    await m.reply("🛠 Админ-меню:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == 'adm_subscribe', user_id=ADMIN_ID)
async def adm_sub(cb: types.CallbackQuery):
    await cb.answer("Отправьте /subscribe <id> <дней> в чат")

@dp.callback_query_handler(lambda c: c.data == 'adm_revoke', user_id=ADMIN_ID)
async def adm_revoke(cb: types.CallbackQuery):
    await cb.answer("Отправьте /revoke <id> в чат")

@dp.callback_query_handler(lambda c: c.data == 'adm_broadcast', user_id=ADMIN_ID)
async def adm_broadcast(cb: types.CallbackQuery):
    await cb.answer("Отправьте /broadcast <текст> в чат")

@dp.callback_query_handler(lambda c: c.data == 'adm_toggle_username', user_id=ADMIN_ID)
async def adm_toggle(cb: types.CallbackQuery):
    current = is_accepting_usernames()
    set_accept_usernames(not current)
    await cb.answer(f"Приём username {'включён ✅' if not current else 'отключён ❌'}")

@dp.callback_query_handler(lambda c: c.data == 'adm_set_limit', user_id=ADMIN_ID)
async def adm_set_limit(cb: types.CallbackQuery):
    await cb.answer()
    await Form.set_limit.set()
    await bot.send_message(cb.from_user.id, "Введите новый ежедневный лимит (число):")

@dp.callback_query_handler(lambda c: c.data == 'adm_set_max_warns', user_id=ADMIN_ID)
async def adm_set_max_warns(cb: types.CallbackQuery):
    await cb.answer()
    await Form.set_max_warns.set()
    await bot.send_message(cb.from_user.id, "Введите максимальное количество предупреждений (число):")

@dp.message_handler(state=Form.set_max_warns, user_id=ADMIN_ID)
async def receive_max_warns(message: types.Message, state: FSMContext):
    try:
        max_warns = int(message.text.strip())
        set_max_warnings(max_warns)
        await message.reply(f"✅ Максимальное количество предупреждений установлено на {max_warns}")
    except ValueError:
        await message.reply("❌ Введите число")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'adm_warn', user_id=ADMIN_ID)
async def adm_warn(cb: types.CallbackQuery):
    await cb.answer("Отправьте /warn <id> в чат")

@dp.callback_query_handler(lambda c: c.data == 'adm_unwarn', user_id=ADMIN_ID)
async def adm_unwarn(cb: types.CallbackQuery):
    await cb.answer("Отправьте /unwarn <id> в чат")

@dp.message_handler(state=Form.set_limit, user_id=ADMIN_ID)
async def receive_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        set_default_daily_limit(limit)
        await message.reply(f"✅ Ежедневный лимит установлен на {limit}")
    except ValueError:
        await message.reply("❌ Введите число")
    await state.finish()

@dp.message_handler(commands=['subscribe'], user_id=ADMIN_ID)
async def adm_sub_cmd(m: types.Message):
    try:
        _, uid, days = m.text.split()
        extend_subscription(int(uid), int(days))
        await m.reply(f"✅ Подписка выдана на {days} дней")
    except:
        await m.reply("❌ Формат: /subscribe 123456789 30")

@dp.message_handler(commands=['revoke'], user_id=ADMIN_ID)
async def adm_revoke_cmd(m: types.Message):
    try:
        uid = int(m.text.split()[1])
        revoke_subscription(uid)
        await m.reply("✅ Подписка отозвана")
    except:
        await m.reply("❌ Формат: /revoke 123456789")

@dp.message_handler(commands=['warn'], user_id=ADMIN_ID)
async def adm_warn_cmd(m: types.Message):
    try:
        uid = int(m.text.split()[1])
        revoked = add_warning(uid)
        if revoked:
            await m.reply(f"⚠️ Предупреждение выдано пользователю {uid}. Достигнут максимум — подписка снята.")
            await bot.send_message(uid, "⚠️ Вы получили предупреждение. Достигнут максимум — ваша подписка снята.")
        else:
            await m.reply(f"⚠️ Предупреждение выдано пользователю {uid}")
            await bot.send_message(uid, "⚠️ Вы получили предупреждение от администратора.")
    except:
        await m.reply("❌ Формат: /warn 123456789")

@dp.message_handler(commands=['unwarn'], user_id=ADMIN_ID)
async def adm_unwarn_cmd(m: types.Message):
    try:
        uid = int(m.text.split()[1])
        remove_warning(uid)
        await m.reply(f"✅ Предупреждение снято с пользователя {uid}")
        await bot.send_message(uid, "✅ Одно предупреждение снято администратором.")
    except:
        await m.reply("❌ Формат: /unwarn 123456789")

@dp.message_handler(commands=['create_promo'], user_id=ADMIN_ID)
async def create_promo_cmd(m: types.Message):
    try:
        days = int(m.text.split()[1])
        code = create_promo_code(days)
        await m.reply(f"✅ Промокод создан: {code} на {days} дней")
    except:
        await m.reply("❌ Формат: /create_promo 30")

@dp.message_handler(commands=['broadcast'], user_id=ADMIN_ID)
async def broadcast(m: types.Message):
    text = m.text.partition(' ')[2]
    cursor.execute("SELECT user_id FROM users")
    for (uid,) in cursor.fetchall():
        try:
            await bot.send_message(uid, text)
            await asyncio.sleep(0.05)
        except:
            pass
    await m.reply("📢 Рассылка завершена")

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(process_queue())
    executor.start_polling(dp, skip_updates=True)