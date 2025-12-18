import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import asyncio
import os
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode, InputFile
import requests
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BadRequest
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights

API_TOKEN = '8172301299:AAF8vVBfKpg-1nmLJJn1yb-mg2A6Y3UqH8E'
ADMIN_ID = 8065283718
CHANNEL_ID = -1003146486725
logs = -1003417010845   # писать с -100, наверху тоже
API_ID = 2040#апи айди
API_HASH = 'b18441a1ff607e10a989891a5462e627' #- сюда апи хаш

crypto_token = '502869:AA44jKY43RV6kudg4TePJHGbHKEhFsekA0F'
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
last_message_id = {}

def create_invoice(asset, amount):
    url = 'https://pay.crypt.bot/api/createInvoice'
    params = {
        'asset': asset,
        'amount': str(amount)
    }
    headers = {'Crypto-Pay-API-Token': crypto_token}
    response = requests.get(url, params=params, headers=headers)
    return response.json()

def get_invoices(invoice_id):
    url = 'https://pay.crypt.bot/api/getInvoices'
    params = {
        'invoice_ids': str(invoice_id)
    }
    headers = {'Crypto-Pay-API-Token': crypto_token}
    response = requests.get(url, params=params, headers=headers)
    return response.json()

class GlobalBan:
    def __init__(self):
        self.clients = []
        
    def find_sessions(self):
        session_files = []
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.endswith('.session'):
                    session_files.append(os.path.join(root, file[:-8]))
        return session_files
    
    async def init_clients(self):
        sessions = self.find_sessions()
        print(f"[GlobalBan] Найдено сессий: {len(sessions)}")
        
        for session in sessions:
            try:
                client = TelegramClient(session, API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    self.clients.append(client)
                    print(f"[GlobalBan] Активна сессия: {os.path.basename(session)}")
                else:
                    await client.disconnect()
            except Exception as e:
                print(f"[GlobalBan] Ошибка подключения сессии {os.path.basename(session)}: {e}")
                continue
        return len(self.clients) > 0

    async def get_channels(self, client):
        channels = []
        try:
            async for dialog in client.iter_dialogs():
                chat = dialog.entity
                # Ищем только каналы, где есть права на бан
                if isinstance(chat, Channel) and getattr(chat, 'broadcast', False):
                    if hasattr(chat, 'admin_rights') and chat.admin_rights and chat.admin_rights.ban_users:
                        channels.append(chat)
        except Exception as e:
            print(f"[GlobalBan] Ошибка итерации диалогов для клиента {client.session.filename}: {e}")
        return channels
    
    async def ban_target(self, client, channel, target_entity):
        try:
            rights = ChatBannedRights(
                until_date=None,
                view_messages=True,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                send_games=True,
                send_inline=True,
                send_polls=True,
                change_info=True,
                invite_users=True,
                pin_messages=True,
            )
            await client(EditBannedRequest(
                channel=channel,
                participant=target_entity,
                banned_rights=rights
            ))
            print(f"[GlobalBan] Забанено в канале: {getattr(channel, 'title', 'Channel')}")
            return True, getattr(channel, 'title', 'Channel')
        except Exception:
            return False, None
    
    async def log_channel_counts(self):
        print("[GlobalBan] Запуск логирования количества каналов...")
        if not await self.init_clients():
            print("[GlobalBan] Нет активных сессий для логирования.")
            return

        with open('bot.log', 'w', encoding='utf-8') as f:
            f.write("--- Лог каналов для сессий ---\n")
            for client in self.clients:
                channels = await self.get_channels(client)
                count = len(channels)
                log_line = f"Сессия: {os.path.basename(client.session.filename)}, Найдено каналов: {count}\n"
                f.write(log_line)
                print(log_line.strip())
            f.write("--- Конец лога ---\n")
        
        await self.disconnect_all()
        print("[GlobalBan] Логирование завершено. Сессии отключены.")

    async def execute_ban(self, target_str):
        if not await self.init_clients():
            return 0, []
        total_bans = 0
        successful_bans_info = []

        for client in self.clients:
            try:
                target_entity = await client.get_entity(target_str)
                if not target_entity:
                    continue
                    
                channels = await self.get_channels(client)
                if not channels:
                    continue
                
                tasks = [self.ban_target(client, channel, target_entity) for channel in channels]
                results = await asyncio.gather(*tasks)
                
                for success, channel_title in results:
                    if success:
                        total_bans += 1
                        successful_bans_info.append(channel_title)
                        
            except Exception as e:
                print(f"[GlobalBan] Ошибка в цикле для клиента {client.session.filename}: {e}")
                continue
        
        print(f"[GlobalBan] Завершено. Всего банов в каналах: {total_bans}")
        await self.disconnect_all()
        return total_bans, successful_bans_info

    async def disconnect_all(self):
        for client in self.clients:
            try: 
                await client.disconnect()
            except: 
                pass
        self.clients = []

def check_subscription(user_id):
    try:
        with open('bd.txt', 'r') as file:
            subscribers = set(line.strip() for line in file)
        return str(user_id) in subscribers
    except FileNotFoundError:
        return False

def add_subscription(user_id):
    with open('bd.txt', 'a') as file:
        file.write(f"{user_id}\n")

def is_whitelisted(user_id):
    try:
        with open('whitelist.txt', 'r') as file:
            whitelisted_ids = set(line.strip() for line in file)
        return str(user_id) in whitelisted_ids
    except FileNotFoundError:
        return False

async def send_message(user_id, text, reply_markup=None):
    global last_message_id
    try:
        if user_id in last_message_id:
            try:
                await bot.delete_message(user_id, last_message_id[user_id])
            except BadRequest as e:
                if "message to delete not found" in str(e):
                    pass
            except Exception as e:
                print(f"Ошибка при удалении сообщения для {user_id}: {e}")
        
        photo_message = await bot.send_photo(user_id, photo=InputFile('main.jpg'), caption=text, reply_markup=reply_markup)
        last_message_id[user_id] = photo_message.message_id
    except Exception as e:
        print(f"Ошибка отправки сообщения {user_id}: {e}")

async def check_channel_subscription(user_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return chat_member.status != 'left'
    except Exception as e:
        print(f"Ошибка проверки подписки {user_id}: {e}")
        return False

class BanState(StatesGroup):
    waiting_for_target = State()

async def welcome_start(user_id):
    await bot.send_sticker(user_id, 'CAACAgIAAxkBAAEI3Ppm-t0AAcwFpwGZtsqH0outXE-Z670AAmUgAAKBfylK3PLk7j0nC4U2BA')
    if await check_channel_subscription(user_id):
        if check_subscription(user_id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='⚡️ Snos', callback_data='menu')],
                [InlineKeyboardButton(text='👤 Профиль', callback_data='view_profile')],
                [InlineKeyboardButton(text='📝 О функциях', url='https://telegra.ph/Manual-po-rabote-Master-Sn0s-10-02')],
                [InlineKeyboardButton(text='📝 Пользовательское соглашение', url='https://telegra.ph/Polzovatelskoe-soglashenie-10-02-7')]
            ])
            await send_message(user_id, "👋 <b>Добро пожаловать в Lustify Freezer</b>\n\nВы можете использовать все функции бота", reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='💳 Купить подписку', callback_data='buy_subscription')],
                [InlineKeyboardButton(text='👤 Профиль', callback_data='view_profile')],
                [InlineKeyboardButton(text='📝 Канал', url='https://t.me/BotReporte')]
            ])
            await send_message(user_id, "<b>🧛‍♂️Вы присоединились к Lustify Freezer</b>\n<b>Lustify Freezer - лучший бот для сноса Аккаунтов в Telegram!</b>\n\n⚡️ Snos: блокировка пользователя во всех ваших КАНАЛАХ\n\nСтоимость подписки - 3$/месяц", reply_markup=kb)
    else:
        await send_message(user_id, "<b>🔔 Чтобы использовать бота, вам нужно подписаться на канал: https://t.me/+wVKJFn0WxN0yMDQy</b>")

@dp.callback_query_handler(lambda c: c.data == 'back')
async def process_back(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    await welcome_start(user_id)
    await callback_query.answer()

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    await welcome_start(user_id)

@dp.callback_query_handler(lambda c: c.data == 'view_profile')
async def process_view_profile(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    subscription_active = check_subscription(user_id)
    expiration_date = "Бесконечно" if subscription_active else "0"
    message_text = f"👤 <b>Профиль</b>\n\n🆔 <b>ID:</b> <code>{user_id}</code>\n💎 <b>Подписка:</b> {'✅ Активна' if subscription_active else '❌ Неактивна'}\n\n🔔 <b>Подписка активна до:</b> {expiration_date}\n\n❓ <b>Если у вас есть вопросы, нажмите кнопку ниже, чтобы связаться с администратором.</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Admin', url='https://t.me/ovi_user')],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='back')]
    ])
    await send_message(user_id, message_text, reply_markup=kb)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'buy_subscription')
async def process_subscription_request(callback_query: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💵 USDT', callback_data='buy_subscription_usdt')],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='back')]
    ])
    await send_message(callback_query.from_user.id, "<b>⚙️ Lustify Freezer - подписка!\nLustify Freezer - это бот для глобального бана в Telegram.\nВыберите криптовалюту:</b>", reply_markup=kb)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('buy_subscription_'))
async def process_subscription_purchase(callback_query: types.CallbackQuery):
    currency = callback_query.data.split('_')[-1].upper()
    amount = 3
    invoice_data = create_invoice(currency, amount)
    if 'ok' in invoice_data and invoice_data['ok']:
        invoice = invoice_data['result']
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='✅ Проверить оплату', callback_data=f'check_payment:{invoice["invoice_id"]}')],
            [InlineKeyboardButton(text='🔙 Назад', callback_data='back')]
        ])
        await send_message(callback_query.from_user.id, f"🔗 <b>Оплата {currency}:</b> {invoice['bot_invoice_url']}\n\n📜 <b>ID инвойса:</b> <code>{invoice['invoice_id']}</code>", reply_markup=kb)
    else:
        await send_message(callback_query.from_user.id, "❌ <b>Ошибка создания инвойса.</b>")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('check_payment:'))
async def process_callback_check_payment(callback_query: types.CallbackQuery):
    invoice_id = callback_query.data.split(':')[1]
    invoices_data = get_invoices(invoice_id)
    if 'ok' in invoices_data and invoices_data['ok']:
        items = invoices_data['result'].get('items', [])
        if items:
            invoice = items[0]
            user_id = callback_query.from_user.id
            if invoice['status'] == 'paid':
                if not check_subscription(user_id):
                    add_subscription(user_id)
                    await send_message(user_id, "✅ <b>Подписка успешно активирована!</b>")
                else:
                    await send_message(user_id, "❌ <b>У вас уже активирована подписка.</b>")
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔙 Назад', callback_data='back')]])
                await send_message(user_id, f"⚠️ <b>Статус инвойса:</b> {invoice['status']}", reply_markup=kb)
        else:
            await send_message(callback_query.from_user.id, "❌ <b>Инвойс не найден.</b>")
    else:
        await send_message(callback_query.from_user.id, "❌ <b>Ошибка получения инвойса.</b>")
    await callback_query.answer()

@dp.message_handler(lambda message: message.text.startswith('/givesub'))
async def give_subscription(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            add_subscription(user_id)
            await bot.send_message(message.from_user.id, f"✅ <b>Пользователю {user_id} выдана подписка.</b>")
        except (ValueError, TypeError, IndexError):
            await bot.send_message(message.from_user.id, "⚠️ <b>Использование:</b> /givesub user_id")
    else:
        await bot.send_message(message.from_user.id, "❌ <b>У вас нет прав на использование этой команды.</b>")

@dp.callback_query_handler(lambda c: c.data == 'menu')
async def show_menu(call: types.CallbackQuery):
    if not check_subscription(call.from_user.id):
        await call.message.answer("<b>❌ У вас нет активной подписки. Пожалуйста, купите подписку, чтобы использовать эту команду.</b>")
        await call.answer()
        return
    await call.message.answer("<b>⚡️ Введите юзернейм или ID цели для сноса:</b>\n\n<i>Пользователь будет заблокирован во всех ваших КАНАЛАХ, где вы являетесь администратором.</i>")
    await BanState.waiting_for_target.set()
    await call.answer()

@dp.message_handler(state=BanState.waiting_for_target)
async def process_ban_target(message: types.Message, state: FSMContext):
    target_input = message.text.strip()
    initiator = message.from_user
    ban_system = GlobalBan()

    if target_input.lstrip('@').isdigit():
        if is_whitelisted(target_input.lstrip('@')):
            log_text = f"🛡️ <b>Попытка сноса на пользователя из Whitelist!</b>\n\n<b>Инициатор:</b> @{initiator.username or 'N/A'} (<code>{initiator.id}</code>)\n<b>Цель:</b> ID: {target_input}"
            await bot.send_message(logs, log_text)
            await message.answer("🛡️ <b>Этот пользователь находится под защитой и не может быть забанен.</b>")
            await state.finish()
            return

    await message.answer("<b>🔄 Начинаю процесс сноса... Это может занять некоторое время.</b>")
    
    total_bans, successful_channels = await ban_system.execute_ban(target_input)
    
    target_entity = None
    if ban_system.clients:
        try:
            target_entity = await ban_system.clients[0].get_entity(target_input)
        except:
            pass

    target_id = "N/A"
    target_username = target_input
    if target_entity:
        target_id = target_entity.id
        target_username = f"@{target_entity.username}" if target_entity.username else f"ID: {target_id}"
        if is_whitelisted(target_id):
             log_text = f"🛡️ <b>Попытка сноса на пользователя из Whitelist (проверка после поиска)!</b>\n\n<b>Инициатор:</b> @{initiator.username or 'N/A'} (<code>{initiator.id}</code>)\n<b>Цель:</b> {target_username} (<code>{target_id}</code>)"
             await bot.send_message(logs, log_text)
             await message.answer("🛡️ <b>Этот пользователь находится под защитой и не может быть забанен.</b>")
             await state.finish()
             return

    await message.answer(f"✅ <b>Снос завершен.</b>\n\n<b>Цель:</b> {target_username}\n<b>Успешно забанено в каналах:</b> {total_bans}")

    if total_bans > 0:
        log_message = f"🚨 <b>Новый снос!</b>\n\n<b>Исполнитель:</b> @{initiator.username or 'N/A'} (<code>{initiator.id}</code>)\n<b>Цель:</b> {target_username} (<code>{target_id}</code>)\n\n<b>Успешные баны ({total_bans} шт.):</b>\n" + "\n".join(f"• {channel_title}" for channel_title in successful_channels)
        await bot.send_message(logs, log_message)
    else:
        await bot.send_message(logs, f"⚠️ <b>Попытка сноса не удалась.</b>\n\n<b>Исполнитель:</b> @{initiator.username or 'N/A'} (<code>{initiator.id}</code>)\n<b>Цель:</b> {target_username}")

    await state.finish()

@dp.message_handler(lambda message: message.text.startswith('/list'))
async def manage_whitelist(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) > 1:
        user_id_to_add = args[1]
        with open('whitelist.txt', 'a') as file:
            file.write(f"{user_id_to_add.strip()}\n")
        await message.reply(f"✅ <b>Пользователь {user_id_to_add.strip()} добавлен в whitelist.</b>")
    else:
        try:
            with open('whitelist.txt', 'r') as file:
                whitelisted_ids = [line.strip() for line in file]
            await message.reply("<b>📝 Whitelist:</b>\n" + "\n".join(whitelisted_ids) if whitelisted_ids else "<b>📝 Whitelist пуст.</b>")
        except FileNotFoundError:
            await message.reply("<b>📝 Whitelist пуст или не найден.</b>")

async def on_startup(dp):
    ban_system_logger = GlobalBan()
    await ban_system_logger.log_channel_counts()
    await bot.delete_webhook()

if __name__ == '__main__':
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
