import logging
import re
from aiogram import Bot, Dispatcher, executor, types

# Configure logging
logging.basicConfig(level=logging.INFO)

# Bot token (replace with your actual bot token)
TOKEN = '8469867586:AAEZs4-PX8vj3AzeYVZJkhpd6KP53PxZNZM'

# Channel ID (replace with your actual channel ID, e.g., -1001234567890)
CHANNEL_ID = -1003146486725

# The appendix text with link (using MarkdownV2 for better parsing)
APPENDIX = '\n\n[Проект Chrime Team \- подписаться](https://t.me/+wVKJFn0WxN0yMDQy)'

def escape_markdown_v2(text):
    return re.sub(r'([_\*\[\]\(\)\~`>\#\+\-=\|\{\}\.\!])', r'\\\1', text)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.channel_post_handler(content_types=types.ContentTypes.ANY)
async def handle_channel_post(message: types.Message):
    logging.info(f"Handling channel post in chat {message.chat.id}")
    if message.chat.id != CHANNEL_ID:
        logging.info("Not the target channel")
        return

    # Skip if the message is from the bot itself to avoid infinite loops
    bot_info = await bot.get_me()
    if message.from_user and message.from_user.id == bot_info.id:
        logging.info("Message from bot, skipping")
        return

    # For anonymous posts, from_user is None, which is fine - proceed to edit
    try:
        if message.text:
            # For text messages, append to text
            escaped_text = escape_markdown_v2(message.text)
            new_text = escaped_text + APPENDIX
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text=new_text,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )
            logging.info("Edited text message")
        elif message.caption:
            # For media messages with captions, append to caption
            escaped_caption = escape_markdown_v2(message.caption)
            new_caption = escaped_caption + APPENDIX
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=new_caption,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )
            logging.info("Edited media caption")
        elif (message.photo or message.video or message.document or 
              message.audio or message.voice or message.animation):
            # For media messages without caption, add new caption
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=APPENDIX,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )
            logging.info("Added caption to media message")
        # If neither (e.g., poll, location, sticker), ignore
    except Exception as e:
        logging.error(f"Error editing message: {e}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)