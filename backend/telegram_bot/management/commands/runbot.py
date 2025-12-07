import os
import django
import signal
import sys
import logging
from django.core.management.base import BaseCommand

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from telegram_bot.bot import setup_bot
from telegram import Update

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the Telegram bot'

    def __init__(self):
        super().__init__()
        self.application = None

    def handle(self, *args, **options):
        # Detect if running in production (Fly.io)
        is_production = os.getenv('FLY_APP_NAME') is not None
        
        if is_production:
            self.stdout.write(self.style.SUCCESS('Starting Telegram bot (PRODUCTION MODE)...'))
            logger.info('Telegram bot starting in PRODUCTION MODE on Fly.io')
        else:
            self.stdout.write(self.style.SUCCESS('Starting Telegram bot (DEVELOPMENT MODE)...'))
            logger.info('Telegram bot starting in DEVELOPMENT MODE')
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            self.application = setup_bot()
            
            if not self.application:
                error_msg = 'Bot token not configured. Set TELEGRAM_BOT_TOKEN in environment.'
                self.stdout.write(self.style.ERROR(error_msg))
                logger.error(error_msg)
                sys.exit(1)
            
            self.stdout.write(self.style.SUCCESS('Bot initialized successfully. Starting polling...'))
            logger.info('Bot initialized successfully. Starting polling...')
            
            # Run bot with polling (works for both development and production)
            # The webhook deletion is handled in set_bot_commands (post_init hook)
            # This will run continuously until stopped
            self.stdout.write(self.style.SUCCESS('✅ Bot is now running and listening for messages!'))
            logger.info('✅ Bot is now running and listening for messages!')
            
            if not is_production:
                self.stdout.write(self.style.WARNING('📱 Test it by sending /start to your bot in Telegram'))
                self.stdout.write(self.style.WARNING('⏹️  Press CTRL+C to stop the bot'))
            
            self.stdout.write('')
            
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,  # Drop pending updates on restart
                stop_signals=None  # We handle signals ourselves
            )
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nReceived interrupt signal. Shutting down gracefully...'))
            self._shutdown()
        except Exception as e:
            logger.error(f'Error running bot: {e}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            self._shutdown()
            raise

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.stdout.write(self.style.WARNING(f'\nReceived signal {signum}. Shutting down gracefully...'))
        self._shutdown()
        sys.exit(0)

    def _shutdown(self):
        """Gracefully shutdown the bot"""
        if self.application:
            try:
                logger.info('Shutting down bot...')
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, schedule shutdown
                        asyncio.create_task(self.application.stop())
                        asyncio.create_task(self.application.shutdown())
                    else:
                        loop.run_until_complete(self.application.stop())
                        loop.run_until_complete(self.application.shutdown())
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self.application.stop())
                    asyncio.run(self.application.shutdown())
                self.stdout.write(self.style.SUCCESS('Bot stopped successfully.'))
            except Exception as e:
                logger.error(f'Error during shutdown: {e}', exc_info=True)
                self.stdout.write(self.style.ERROR(f'Error during shutdown: {e}'))

