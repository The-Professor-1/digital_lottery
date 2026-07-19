"""
Telegram bot entry for the money lottery mini-app.
Only registers lottery onboarding handlers (no bingo menus).
"""
import logging
from django.conf import settings
from telegram.ext import Application, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)


async def error_handler(update, context):
    """Log errors and notify the user briefly."""
    logger.error('Telegram bot error: %s', context.error, exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                'Please try again in a moment.'
            )
    except Exception as e:
        logger.error('Error sending error message to user: %s', e)


def setup_bot():
    """Setup lottery bot: /start → language → contact → mini-app only."""
    token = settings.TELEGRAM_BOT_TOKEN

    if not token:
        logger.warning('TELEGRAM_BOT_TOKEN not set. Bot will not start.')
        return None

    try:
        from telegram.ext import CallbackQueryHandler
        from .lottery_handlers import (
            start_command as lottery_start,
            handle_contact as lottery_contact,
            language_callback,
            configure_bot_profile,
        )

        application = Application.builder().token(token).build()
        application.post_init = configure_bot_profile
        application.add_error_handler(error_handler)

        application.add_handler(CommandHandler('start', lottery_start))
        application.add_handler(CallbackQueryHandler(language_callback, pattern=r'^lang_'))
        application.add_handler(MessageHandler(filters.CONTACT, lottery_contact))

        logger.info('Lottery bot application setup completed successfully')
        return application

    except Exception as e:
        logger.error('Error setting up bot: %s', e, exc_info=True)
        return None
