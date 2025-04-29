from telegram.ext import ApplicationBuilder, MessageHandler, filters
from config import TELEGRAM_TOKEN

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

if __name__ == "__main__":
    # Import the main function from our local celery_app.py file
    from celery_app import process_msg
    run_telegram_bot(process_msg)
