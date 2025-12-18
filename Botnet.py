import subprocess
import os
import asyncio
import logging
import smtplib
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User
from telethon.errors import AuthKeyDuplicatedError
from pystyle import Colors, Colorate, Center, Anime
from colorama import Fore, Style, init

init(autoreset=True)
from config import SESSION_DIR, senders, smtp_servers, clients

logging.basicConfig(level=logging.CRITICAL)
 

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_session_info(session_name, info, delete_reason=None):
    info_lines = info.split('\n')
    if delete_reason:
        info_lines.append(delete_reason)  
    max_length = max(len(line) for line in info_lines)  
    max_length = max(max_length, len(session_name) + 10)  
    border = "╔" + "═" * (max_length + 2) + "╗"
    bottom_border = "╚" + "═" * (max_length + 2) + "╝"
    session_line = f"║ Сессия: {session_name.ljust(max_length - 8)} ║"
    info_lines_formatted = [f"║ {line.ljust(max_length)} ║" for line in info_lines]
    info_text = f"{border}\n{session_line}\n" + "\n".join(info_lines_formatted) + f"\n{bottom_border}"
    print(Colorate.Horizontal(Colors.red_to_green, info_text))

def print_email_info(email, info, delete_reason=None):
    info_lines = info.split('\n')
    if delete_reason:
        info_lines.append(delete_reason)  
    max_length = max(len(line) for line in info_lines)  
    max_length = max(max_length, len(email) + 10)  
    border = "╔" + "═" * (max_length + 2) + "╗"
    bottom_border = "╚" + "═" * (max_length + 2) + "╝"
    email_line = f"║ Почта: {email.ljust(max_length - 8)}  ║"
    info_lines_formatted = [f"║ {line.ljust(max_length)} ║" for line in info_lines]
    info_text = f"{border}\n{email_line}\n" + "\n".join(info_lines_formatted) + f"\n{bottom_border}"
    print(Colorate.Horizontal(Colors.red_to_green, info_text))

async def check_session(session_file, api_id, api_hash):
    session_name = os.path.basename(session_file).replace('.session', '')
    client = None
    try:        
        client = TelegramClient(SQLiteSession(session_file), api_id, api_hash, timeout=10)
        await client.connect()

        if not await client.is_user_authorized():
            raise ValueError("Сессия не авторизована.")

        me = await client.get_me()
        if isinstance(me, User):
            auth_info = f"Авторизован как: {me.first_name} (id: {me.id})"
            account_type = "Бот" if me.bot else "Пользователь"
        else:
            auth_info = "Сессия не авторизована."
            account_type = "Неизвестно"

        full_user = await client(GetFullUserRequest(me))
        premium_status = "Premium: Да" if getattr(full_user, 'premium', False) else "Premium: Нет"
        if premium_status == "Premium: Нет":
            if hasattr(me, 'premium') and me.premium:
                premium_status = "Premium: Да"
            else:
                premium_status = "Premium: Нет"

        username = f"username: @{me.username}" if me.username else "Нет username"
        session_info = (
            f"{auth_info}\n"
            f"{username}\n"
            f"{premium_status}\n"
            f"Тип аккаунта: {account_type}"
        )
        if me.bot:
            os.remove(session_file)
            print_session_info(session_name, session_info, "Сессия удалена (это бот).")
        else:
            print_session_info(session_name, session_info)

    except AuthKeyDuplicatedError:
        os.remove(session_file)
        print_session_info(session_name, "Ошибка: Сессия используется под разными IP.", "Сессия удалена.")
    except asyncio.TimeoutError:
        os.remove(session_file)
        print_session_info(session_name, "Ошибка: Тайм-аут подключения.", "Сессия удалена.")
    except Exception as e:
        error_info = f"Ошибка при проверке сессии"
        if os.path.exists(session_file):
            os.remove(session_file)
        print_session_info(session_name, error_info, "Сессия удалена.")
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception as e:
                pass

def find_session_files():
    if not os.path.exists(SESSION_DIR):
        print(Colorate.Horizontal(Colors.red_to_green, "Папка Session не найдена."))
        return []
    session_files = []
    for client_folder in os.listdir(SESSION_DIR):
        client_path = os.path.join(SESSION_DIR, client_folder)
        if os.path.isdir(client_path):
            for file in os.listdir(client_path):
                if file.endswith('.session'):
                    session_files.append((os.path.join(client_path, file), client_folder))
    return session_files

def check_email(sender_email, sender_password):
    domain = sender_email.split('@')[1]
    if domain not in smtp_servers:
        print_email_info(sender_email, f"   ➥ Неизвестный домен")
        return False

    smtp_server, smtp_port = smtp_servers[domain]

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            print_email_info(sender_email, f"   ➥ работает")
            return True
    except smtplib.SMTPAuthenticationError as e:
        print_email_info(sender_email, f"   ➥ Ошибка аутентификации")
        logging.error(f"   ➥ Ошибка аутентификации")
        return False
    except (smtplib.SMTPException, TimeoutError, OSError) as e:
        print_email_info(sender_email, f"   ➥ не работает")
        logging.error(f"   ➥ не работает")
        return False

async def check_emails(email_list):
    working_emails = []
    for email, password in email_list.items():
        if check_email(email, password):
            working_emails.append((email, password))
    return working_emails

menu_text = f"""
"""
async def run_checker():
    session_files = find_session_files()
    session_count = len(session_files)
    text = f"Количество сессий: {session_count}"
    text_width = len(text) + 4  
    border = "╔" + "═" * text_width + "╗\n"
    border += "║ " + text.center(text_width - 4) + "   ║\n"  
    border += "╚" + "═" * text_width + "╝"
    print(Colorate.Horizontal(Colors.red_to_green, menu_text))
    print(Colorate.Horizontal(Colors.red_to_green, border))
    if session_files:
        for session_file, client_folder in session_files:
            client_info = next((client for client in clients if client["name"] == client_folder), None)
            if client_info:
                await check_session(session_file, client_info["api_id"], client_info["api_hash"])

    working_emails = await check_emails(senders)
    if working_emails:
        email_count = len(working_emails)
        text = f"Количество работающих почт: {email_count}"
        text_width = len(text) + 4  
        border = "╔" + "═" * text_width + "╗\n"
        border += "║ " + text.center(text_width - 4) + "   ║\n"  
        border += "╚" + "═" * text_width + "╝"
        print(Colorate.Horizontal(Colors.red_to_green, border))
    else:
        print(Colorate.Horizontal(Colors.red_to_green, "Нет работающих почт."))

    try:
        print(Colorate.Horizontal(Colors.red_to_green, f"╔"+"═"*21+" Запуск бота "+"═"*21+ "╗"))
        subprocess.run(["python", "бот.py"], check=True)
    except FileNotFoundError:
        print(Colorate.Horizontal(Colors.red_to_green, "Файл бот.py не найден."))
    except subprocess.CalledProcessError as e:
        print(Colorate.Horizontal(Colors.red_to_green, f"Ошибка при запуске: {e}"))

if __name__ == "__main__":
    asyncio.run(run_checker())