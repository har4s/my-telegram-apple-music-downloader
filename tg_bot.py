import re

from telegram.ext import ApplicationBuilder, MessageHandler, filters
from config import TELEGRAM_TOKEN,TELEGRAM_ADMIN_ID

def run_telegram_bot(message_handler=None):
    """Initialize and run the Telegram bot.

    Args:
        message_handler: The function to handle incoming text messages.
    """
    if message_handler is None:
        raise ValueError("Message handler function must be provided")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, message_handler))
    app.run_polling()

async def my_msg_handler(update, context):
    user_id = update.message.from_user.id
    if user_id not in TELEGRAM_ADMIN_ID:
        return await update.message.reply_text("You are not authorized!")
    message_text = update.message.text
    url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"  # Regular expression for URLs
    urls: list[str] = re.findall(url_regex, message_text)
    if len(urls) <= 0:
        return None

    from celery_app import process_msg

    process_msg.delay(urls,update.message.chat_id)

    return None


if __name__ == "__main__":
    run_telegram_bot(my_msg_handler)
