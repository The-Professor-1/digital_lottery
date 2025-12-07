"""Utility functions for sending Telegram bot notifications"""
import logging
from django.conf import settings
from telegram import Bot
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


async def send_notification(telegram_id: int, message: str, photo_file_id: str = None):
    """Send a notification message to a user via Telegram bot"""
    try:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set. Cannot send notification.")
            return False
        
        bot = Bot(token=token)
        
        if photo_file_id:
            # Send photo with caption
            await bot.send_photo(
                chat_id=telegram_id,
                photo=photo_file_id,
                caption=message
            )
        else:
            # Send text message
            await bot.send_message(
                chat_id=telegram_id,
                text=message
            )
        
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram notification to {telegram_id}: {e}")
        return False


def send_notification_sync(telegram_id: int, message: str, photo_file_id: str = None):
    """Synchronous wrapper for send_notification - works in both sync and async contexts"""
    import asyncio
    import concurrent.futures
    import threading
    
    async def _send():
        return await send_notification(telegram_id, message, photo_file_id)
    
    def _run_in_thread():
        """Run the async function in a new event loop in a separate thread"""
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_send())
        finally:
            new_loop.close()
    
    try:
        # Check if there's a running event loop
        try:
            asyncio.get_running_loop()
            # We're in an async context, need to run in a separate thread with new event loop
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_in_thread)
                return future.result(timeout=10)  # 10 second timeout
        except RuntimeError:
            # No running loop, we can use asyncio.run() directly
            return asyncio.run(_send())
    except concurrent.futures.TimeoutError:
        logger.error(f"Timeout sending notification to {telegram_id}")
        return False
    except Exception as e:
        logger.error(f"Error in send_notification_sync for telegram_id {telegram_id}: {e}", exc_info=True)
        return False

