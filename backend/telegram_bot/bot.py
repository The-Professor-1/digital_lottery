import os
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, BotCommand, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, connections
from api.models import Game, Deposit, DepositRequest, WithdrawRequest, GameSettings, Transfer, Transaction
from api.auth_utils import generate_jwt_token
from api.game_logic import get_available_card_numbers
from api.phone_utils import normalize_phone_number, find_user_by_phone
from decimal import Decimal
from asgiref.sync import sync_to_async
import asyncio

User = get_user_model()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def ensure_db_connection():
    """Ensure database connection is fresh and valid"""
    try:
        # Close all existing connections to force fresh connections
        # This is important for Neon databases that may have gone to sleep
        for conn in connections.all():
            try:
                # Try to ensure connection is valid
                if conn.connection is not None:
                    # Test the connection with a simple query
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                else:
                    # Connection is None, close it
                    conn.close()
            except Exception as e:
                # Connection is stale or invalid, close it
                logger.debug(f"Closing stale database connection: {e}")
                try:
                    conn.close()
                except:
                    pass
        
        # Force a new connection by getting the default connection
        # This will create a fresh connection if needed
        default_conn = connections['default']
        default_conn.ensure_connection()
        
        # Test the connection with a simple query
        with default_conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
    except Exception as e:
        logger.warning(f"Error ensuring DB connection: {e}")
        # Close all connections and let the next operation create fresh ones
        try:
            for conn in connections.all():
                try:
                    conn.close()
                except:
                    pass
        except:
            pass


async def db_operation_with_retry(operation, max_retries=5, retry_delay=2):
    """Execute a database operation with retry logic for stale connections and machine wake-up
    
    Increased retries and delays to handle:
    - Machine wake-up scenarios (can take 5-10 seconds)
    - Database connection establishment after wake-up
    - Neon database connection pool issues
    """
    for attempt in range(max_retries):
        try:
            # Ensure connection is fresh before each attempt
            await sync_to_async(ensure_db_connection)()
            # Execute the operation
            return await operation()
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            # Check if it's a connection-related error (including Neon-specific errors)
            connection_errors = [
                'connection', 'closed', 'lost', 'timeout', 'server closed',
                'operationalerror', 'interfaceerror', 'databaseerror',
                'connection refused', 'connection reset', 'broken pipe',
                'connection pool', 'connection limit', 'too many connections',
                'server closed the connection', 'connection terminated',
                'neon', 'pg_', 'postgresql', 'could not connect', 'network',
                'unreachable', 'name resolution', 'dns'
            ]
            is_connection_error = (
                any(keyword in error_str for keyword in connection_errors) or
                'OperationalError' in error_type or
                'InterfaceError' in error_type or
                'DatabaseError' in error_type
            )
            
            if is_connection_error:
                if attempt < max_retries - 1:
                    # Check if this looks like a machine wake-up scenario (connection refused/unreachable)
                    # vs a stale connection (connection closed/lost)
                    wake_up_indicators = [
                        'connection refused', 'could not connect', 'unreachable',
                        'name resolution', 'dns', 'network', 'timeout'
                    ]
                    is_wake_up_scenario = any(indicator in error_str for indicator in wake_up_indicators)
                    
                    # Only use 5-second delay on first retry if it looks like machine wake-up
                    # For stale connections, use shorter delays
                    if attempt == 0 and is_wake_up_scenario:
                        delay = 5  # Give machine time to wake up
                    else:
                        delay = retry_delay * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s, 8s
                    
                    logger.warning(f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                    # Close all connections before retry to force fresh connections
                    try:
                        await sync_to_async(lambda: [conn.close() for conn in connections.all()])()
                    except:
                        pass
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                    raise
            else:
                # Not a connection error, re-raise immediately
                raise
    raise Exception("Database operation failed after retries")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        
        if not user:
            logger.warning("No user in update")
            return
        
        # Check if user exists and has phone number
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            
            # User exists - check if registered (has phone number)
            if telegram_user.phone_number:
                # User is registered, show normal menu
                welcome_msg = f"እንኳን ደህና መጡ፣ {user.first_name or user.username}!"
                await show_main_menu(update, context, welcome_msg)
            else:
                # User exists but not registered (no phone), show registration prompt
                welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
                # Show only register button
                keyboard = [
                    [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if update.message:
                    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
                elif update.callback_query:
                    await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
                    await update.callback_query.answer()
        except User.DoesNotExist:
            # New user - create user record but don't register yet
            async def create_user():
                return await sync_to_async(User.objects.create)(
                    telegram_id=user.id,
                    username=user.username or f"user_{user.id}",
                    first_name=user.first_name or '',
                    last_name=user.last_name or '',
                )
            telegram_user = await db_operation_with_retry(create_user)
            
            # Show registration prompt
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            # Show only register button
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.message:
                await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
                await update.callback_query.answer()
    except Exception as e:
        logger.error(f"Error in start_command: {e}", exc_info=True)
        if update and update.message:
            try:
                await update.message.reply_text("😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።")
            except:
                pass


async def is_user_registered(user_id: int) -> bool:
    """Check if user is registered (has phone number)"""
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user_id)
        telegram_user = await db_operation_with_retry(get_user)
        return bool(telegram_user.phone_number)
    except User.DoesNotExist:
        return False
    except Exception as e:
        logger.error(f"Error checking if user is registered: {e}")
        return False


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register command or register button click"""
    try:
        user = update.effective_user
        
        if not user:
            logger.warning("No user in register_command update")
            return
        
        # Check if user already exists and has phone number
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            if telegram_user.phone_number:
                # User already registered with phone number
                keyboard = [
                    [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message_text = (
                    "✅ አስቀድመው ተመዝግበዋል!\n\n"
                    f"ያለዎት ሂሳብ: {telegram_user.balance} ብር\n\n"
                )
                if update.message:
                    await update.message.reply_text(message_text, reply_markup=reply_markup)
                elif update.callback_query:
                    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
                    await update.callback_query.answer()
                return
        except User.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error checking user registration: {e}")
            # Continue to registration flow even if there's an error
        
        # Request phone number if user doesn't have one
        from telegram import ReplyKeyboardMarkup, KeyboardButton
        keyboard = [
            [KeyboardButton("📱 ስልክ ቁጥር ያጋሩ", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        message_text = (
            "📝 ለመመዝገብ እባክዎ 'ስልክ ቁጥር ያጋሩ' የሚለውን ይጫኑ:"
        )
        
        if update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        elif update.callback_query:
            # For callback queries, send a new message instead of editing
            # because we're switching to ReplyKeyboardMarkup
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error in register_command: {e}", exc_info=True)
        error_msg = "😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።"
        try:
            if update.message:
                await update.message.reply_text(error_msg)
            elif update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.message.reply_text(error_msg)
        except Exception as e2:
            logger.error(f"Error sending error message: {e2}")


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /play command - redirect to mini app"""
    try:
        user = update.effective_user
        
        if not user:
            logger.warning("No user in play_command update")
            return
        
        # Check if user is registered
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
                await update.callback_query.answer()
            return
        
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
            return
        
        # Always open web app - let the web app handle game state
        # Generate JWT token
        token = generate_jwt_token(telegram_user)
        
        # Create mini app URL - opens the web app on Fly.io
        mini_app_url = f"{settings.TELEGRAM_WEB_APP_URL}?token={token}"
        logger.info(f"Opening web app for user {telegram_user.telegram_id}: {settings.TELEGRAM_WEB_APP_URL}")
        
        # Get current game info for display (optional) with retry
        async def get_current_game():
            return await sync_to_async(
                lambda: Game.objects.filter(
                    status__in=['waiting', 'active']
                ).order_by('-created_at').first()
            )()
        current_game = await db_operation_with_retry(get_current_game)
        
        # Get bet_amount from current game, or from GameSettings if no game exists
        if current_game:
            # For waiting games with no cards, use settings bid_amount to ensure it's up-to-date
            if current_game.status == 'waiting':
                async def count_gamecards():
                    return await sync_to_async(current_game.gamecards.count)()
                gamecards_count = await db_operation_with_retry(count_gamecards)
                if gamecards_count == 0:
                    # No cards selected yet, use current settings value
                    async def get_settings():
                        return await sync_to_async(GameSettings.get_settings)()
                    game_settings = await db_operation_with_retry(get_settings)
                    bet_amount = game_settings.bid_amount
                    # Also update the game's bet_amount to match settings
                    current_game.bet_amount = game_settings.bid_amount
                    async def save_game():
                        await sync_to_async(current_game.save)(update_fields=['bet_amount'])
                    await db_operation_with_retry(save_game)
                else:
                    # Cards already selected, use game's bet_amount
                    bet_amount = current_game.bet_amount
            else:
                # Active game, use game's bet_amount
                bet_amount = current_game.bet_amount
                async def count_gamecards():
                    return await sync_to_async(current_game.gamecards.count)()
                gamecards_count = await db_operation_with_retry(count_gamecards)
        else:
            # No current game, get bet_amount from GameSettings
            async def get_settings():
                return await sync_to_async(GameSettings.get_settings)()
            game_settings = await db_operation_with_retry(get_settings)
            bet_amount = game_settings.bid_amount
            gamecards_count = 0
        
        # Check if URL is HTTPS (required for Telegram web apps)
        # If HTTP (local development), show URL as text instead of web app button
        if settings.TELEGRAM_WEB_APP_URL.startswith('http://'):
            # Local development - can't use web app button with HTTP
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"🍀 በጨዋታዎ ላይ መልካም ዕድል!\n\n"
                f"መደብ: {bet_amount} ብር\n"
                f"🔗 የጨዋታ ማስጀመሪያ:\n{mini_app_url}",
                reply_markup=reply_markup
            )
        else:
            # Production - use web app button
            keyboard = [
                [InlineKeyboardButton(
                    "🎮 ጨዋታ ይጀምሩ",
                    web_app=WebAppInfo(url=mini_app_url)
                )],
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"🍀 በጨዋታዎ ላይ መልካም ዕድል!\n\n"
                f"መደብ: {bet_amount} ብር\n",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in play_command: {e}", exc_info=True)
        if update and update.message:
            try:
                await update.message.reply_text("😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።")
            except:
                pass


def clear_financial_command_states(context: ContextTypes.DEFAULT_TYPE):
    """Clear all financial command states to prevent interference between commands"""
    # Clear deposit states
    context.user_data.pop('waiting_for_deposit_amount', None)
    context.user_data.pop('waiting_for_deposit', None)
    context.user_data.pop('waiting_for_deposit_text', None)
    context.user_data.pop('deposit_amount', None)
    context.user_data.pop('deposit_platform', None)
    context.user_data.pop('deposit_text', None)
    context.user_data.pop('deposit_photo_id', None)
    
    # Clear withdraw states
    context.user_data.pop('waiting_for_withdraw_amount', None)
    context.user_data.pop('waiting_for_withdraw_account_name', None)
    context.user_data.pop('waiting_for_withdraw_account_number', None)
    context.user_data.pop('withdraw_amount', None)
    context.user_data.pop('withdraw_platform', None)
    context.user_data.pop('withdraw_account_name', None)
    context.user_data.pop('waiting_for_withdraw', None)
    
    # Clear transfer states
    context.user_data.pop('waiting_for_transfer_phone', None)
    context.user_data.pop('waiting_for_transfer_amount', None)
    context.user_data.pop('waiting_for_transfer_confirm', None)
    context.user_data.pop('transfer_phone', None)
    context.user_data.pop('transfer_to_user_id', None)
    context.user_data.pop('transfer_amount', None)


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deposit command - Show platform options"""
    # Clear any existing financial command states
    clear_financial_command_states(context)
    
    user = update.effective_user
    
    # Check if user is registered
    if not await is_user_registered(user.id):
        welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
        keyboard = [
            [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
            await update.callback_query.answer()
        return
    
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
    except User.DoesNotExist:
        error_msg = "እባክዎ በመጀመሪያ ይመዝገቡ።"
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
            await update.callback_query.answer()
        await show_main_menu(update, context)
        return
    
    # Get settings to fetch account details
    from api.models import GameSettings
    async def get_settings():
        return await sync_to_async(GameSettings.get_settings)()
    settings = await db_operation_with_retry(get_settings)
    accounts = settings.deposit_accounts
    
    # Show platform selection buttons
    keyboard = [
        [InlineKeyboardButton("🏦 BOA(አቢሲኒያ ባንክ)", callback_data="deposit_platform_BOA")],
        [InlineKeyboardButton("🏦 CBE(ንግድ ባንክ)", callback_data="deposit_platform_CBE")],
        [InlineKeyboardButton("📱 Telebirr(ቴሌብር)", callback_data="deposit_platform_Telebirr")],
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    deposit_msg = "💰 ገንዘብ ለማስገባት\n\nእባክዎ ገቢ የሚያደርጉበትን ይምረጡ:"
    
    if update.message:
        await update.message.reply_text(deposit_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(deposit_msg, reply_markup=reply_markup)
        await update.callback_query.answer()


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /withdraw command - Ask for amount first"""
    # Clear any existing financial command states
    clear_financial_command_states(context)
    
    user = update.effective_user
    
    # Check if user is registered
    if not await is_user_registered(user.id):
        welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
        keyboard = [
            [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
            await update.callback_query.answer()
        return
    
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
    except User.DoesNotExist:
        error_msg = "እባክዎ በመጀመሪያ ይመዝገቡ።"
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
            await update.callback_query.answer()
        await show_main_menu(update, context)
        return
    
    # Get minimum withdraw amount from settings
    from api.models import GameSettings
    async def get_settings():
        return await sync_to_async(GameSettings.get_settings)()
    settings = await db_operation_with_retry(get_settings)
    min_withdraw = settings.min_withdraw
    
    keyboard = [
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    withdraw_msg = (
        f"💸 ገንዘብ ለማውጣት\n\n"
        f"💰 ያለዎት ሂሳብ: {telegram_user.balance} ብር\n"
        f"📊 ዝቅተኛ መጠን: {min_withdraw} ብር\n\n"
        "እባክዎ ለመውጣት የሚፈልጉትን መጠን ያስገቡ:"
    )
    
    if update.message:
        await update.message.reply_text(withdraw_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(withdraw_msg, reply_markup=reply_markup)
        await update.callback_query.answer()
    
    context.user_data['waiting_for_withdraw_amount'] = True


async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /transfer command - transfer money to another user"""
    # Clear any existing financial command states
    clear_financial_command_states(context)
    
    try:
        user = update.effective_user
        
        if not user:
            logger.warning("No user in transfer_command update")
            return
        
        # Check if user is registered
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
                await update.callback_query.answer()
            return
        
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
        
        # Check if user has any balance
        if telegram_user.balance <= 0:
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message_text = "❌ በቂ ሂሳብ የለዎትም"
            
            if update.message:
                await update.message.reply_text(message_text, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
                await update.callback_query.answer()
            return
        
        # Ask for phone number first (changed order)
        context.user_data['waiting_for_transfer_phone'] = True
        
        keyboard = [
            [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"💸 ገንዘብ ማስተላለፍ\n\n"
            f"ያለዎት ሂሳብ: {telegram_user.balance} ብር\n\n"
            f"እባክዎ ለማስተላለፍ የሚፈልጉትን የተጠቃሚ ስልክ ቁጥር ያስገቡ:"
        )
        
        if update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
            await update.callback_query.answer()
            
    except User.DoesNotExist:
        error_msg = "እባክዎ በመጀመሪያ ይመዝገቡ።"
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
            await update.callback_query.answer()
    except Exception as e:
        logger.error(f"Error in transfer_command: {e}", exc_info=True)
        error_msg = "😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።"
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
            await update.callback_query.answer()


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command"""
    user = update.effective_user
    
    # Check if user is registered
    if not await is_user_registered(user.id):
        welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
        keyboard = [
            [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
            await update.callback_query.answer()
        return
    
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
    except User.DoesNotExist:
        error_msg = "እባክዎ በመጀመሪያ ይመዝገቡ።"
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
            await update.callback_query.answer()
        await show_main_menu(update, context)
        return
    
    keyboard = [
        [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    balance_msg = (
        f"💰 የእርስዎ ሂሳብ\n\n"
        f"ያለዎት ሂሳብ: {telegram_user.balance} ብር"
    )
    
    if update.message:
        await update.message.reply_text(balance_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(balance_msg, reply_markup=reply_markup)
        await update.callback_query.answer()


async def instruction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /instruction command"""
    instructions = (
        "📋 አሪፍ ቢንጎ የጨዋታ መመሪያ:\n\n"
        "1. **ለመመዝገብ**: /register(ለመመዝገብ) የሚለውን ይጫኑ፡፡\n\n"
        "2. **ለመጫወት**:\n"
        "   - ጨዋታ ለመቀላቀል /play(ጨዋታ ለመጀመር) ይጫኑ፡፡\n"
        "   - በመቀጠለ ካሉት ካርቴላ ቁጥር ይምረጡ\n"
        "   - ቀይ ሆነው የሚታዩት ካርቴላዎች በሌላ ተጫዋች የተያዙ ናቸው\n"
        "   - የሚጠሩ ቁጥሮችን ይመልከቱ\n"
        "   - ቁጥሮች ሲጠሩ በካርድዎ ላይ ይጫኑ\n"
        "   - መስመር ሲሰሩ ቢንጎ የሚለውን ይጫኑ\n\n"
        "3. **ጨዋታ ሞድ (Game Modes)**:\n"
        "   - **Manual Mode**: እርስዎ የሚጠሩ ቁጥሮችን እራስዎ ይጫኑ\n"
        "   - **Automatic Mode**: ቁጥሮች በራሳቸው ይነካሉ (ካርድ ላይ ካሉ) ከዛም በራሱ ቢንጎ ይነካልዎታል \n"
        "   - የጨዋታ ሞድ በጨዋታ ወቅት መቀየር ይችላሉ\n\n"
        "4. **ማሸነፊያ መንገዶች**:\n"
        "   - አግድም መስመር (ማንኛውም ረድፍ)\n"
        "   - ቋሚ መስመር (ማንኛውም አምድ)\n"
        "   - ሰያፍ መስመር\n"
        "   - ሙሉ ካርድ\n\n"
        "5. **ብዙ አሸናፊዎች**:\n"
        "   - በአንድ ጊዜ ወይም በ1 ሰከንድ ውስጥ ብዙ አሸናፊዎች ከተገኙ ደራሹን በእኩል ይከፋፈላሉ\n\n"
        "6. **ገንዘብ ለማስገባት**: /deposit(ለማስገባት) ይጫኑ፡፡\n\n"
        "7. **ገንዘብ ለማውጣት**: /withdraw(ለማውጣት) ይጫኑ፡፡\n\n"
        "8. **ገንዘብ ለማስተላለፍ**: /transfer(ገንዘብ ማስተላለፍ) ለሌላ ተጠቃሚ ማስተላለፍ፡፡\n\n"
        "መልካም ዕድል! 🍀"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(instructions, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(instructions, reply_markup=reply_markup)
        await update.callback_query.answer()


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /support command"""
    keyboard = [
        [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Get support phone from GameSettings
    async def get_settings():
        return await sync_to_async(GameSettings.get_settings)()
    game_settings = await db_operation_with_retry(get_settings)
    support_phone = game_settings.support_phone or '0952838412'
    
    support_msg = (
        "🆘 የድጋፍ ቡድን\n\n"
        "ለእርዳታ፣ እባክዎ የእኛን የድጋፍ ቡድን ያግኙ።\n"
        f"ስልክ: {support_phone}\n"
    )
    
    if update.message:
        await update.message.reply_text(support_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(support_msg, reply_markup=reply_markup)
        await update.callback_query.answer()


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invite command"""
    user = update.effective_user
    # Get bot username from bot info
    try:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    except Exception as e:
        logger.error(f"Error getting bot info: {e}")
        bot_username = "your_bot_username"  # Fallback
    invite_link = f"https://t.me/{bot_username}?start={user.id}"
    
    # Fix URL encoding - use proper encoding for Amharic text
    import urllib.parse
    invite_text = "አሪፍ ቢንጎ ጨዋታ ይጫወቱ!"
    encoded_text = urllib.parse.quote(invite_text)
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={encoded_text}"
    
    keyboard = [
        [InlineKeyboardButton("📤 ሰዎችን ለመጋበዝ", url=share_url)],
        [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    invite_msg = (
        f"👥 ጓደኞችዎን ይጋብዙ!\n\n"
        f"ይህንን ሊንክ ይላኩ: {invite_link}\n\n"
    )
    
    if update.message:
        await update.message.reply_text(invite_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(invite_msg, reply_markup=reply_markup)
        await update.callback_query.answer()


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact sharing for phone number registration"""
    try:
        user = update.effective_user
        contact = update.message.contact
        
        if not user or not contact:
            return
        
        # Verify the contact belongs to the user who sent it
        if contact.user_id != user.id:
            await update.message.reply_text("እባክዎ የእርስዎን ስልክ ቁጥር ያጋሩ።")
            return
        
        phone_number = contact.phone_number
        
        # Normalize phone number (remove 251 country code and add 0)
        normalized_phone = normalize_phone_number(phone_number)
        
        # Get or create user and update phone number
        async def get_or_create_user():
            return await sync_to_async(User.objects.get_or_create)(
                telegram_id=user.id,
                defaults={
                    'username': user.username or f"user_{user.id}",
                    'first_name': user.first_name or '',
                    'last_name': user.last_name or '',
                    'phone_number': normalized_phone,
                }
            )
        telegram_user, created = await db_operation_with_retry(get_or_create_user)
        
        # Get bid_amount from GameSettings for registration gift
        from api.models import GameSettings
        async def get_settings():
            return await sync_to_async(GameSettings.get_settings)()
        game_settings = await db_operation_with_retry(get_settings)
        bid_amount = game_settings.bid_amount
        
        # Check if this is first-time registration (user didn't have phone number before)
        is_first_registration = False
        if created:
            # New user - definitely first registration
            is_first_registration = True
        elif not telegram_user.phone_number or telegram_user.phone_number.strip() == '':
            # Existing user but no phone number - first time registering
            is_first_registration = True
        
        # Update phone number if user already exists
        if not created and telegram_user.phone_number != normalized_phone:
            telegram_user.phone_number = normalized_phone
            async def save_user():
                await sync_to_async(telegram_user.save)()
            await db_operation_with_retry(save_user)
        
        keyboard = [
            [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if is_first_registration:
            # First-time registration - add registration gift (bid_amount)
            telegram_user.balance = Decimal(str(telegram_user.balance)) + Decimal(str(bid_amount))
            async def save_user():
                await sync_to_async(telegram_user.save)()
            await db_operation_with_retry(save_user)
            
            # Create transaction record for the gift
            from api.models import Transaction
            async def create_transaction():
                await sync_to_async(Transaction.objects.create)(
                    user=telegram_user,
                    transaction_type='deposit',
                    amount=Decimal(str(bid_amount)),
                    description=f'Registration gift'
                )
            await db_operation_with_retry(create_transaction)
            
            message_text = (
                f"ተመዝግበዋል! ስጦታ {bid_amount} ብር ተበርክቶሎታል፡፡"
            )
        else:
            message_text = (
                "✅ ስልክ ቁጥርዎ ተመዝግቧል!\n\n"
                f"ያለዎት ሂሳብ: {telegram_user.balance} ብር\n\n"
            )
        
        await update.message.reply_text(message_text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in handle_contact: {e}", exc_info=True)
        await update.message.reply_text("😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages (for deposit screenshots)"""
    user = update.effective_user
    photo = update.message.photo[-1]  # Get highest resolution photo
    
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
    except User.DoesNotExist:
        await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
        await show_main_menu(update, context)
        return
    
    # Check if user is in deposit flow
    if context.user_data.get('waiting_for_deposit_amount'):
        # Photo sent before amount - reject it and ask for text only
        await update.message.reply_text(
            "❌ እባክዎ ቴክስት ብቻ ያስገቡ።\n\n"
            "ምስል አይቀበልም። እባክዎ የገንዘብ መጠንን በቁጥር ያስገቡ:"
        )
    elif context.user_data.get('waiting_for_deposit'):
        # Amount already provided, but user sent photo - reject it and ask for text only
        keyboard = [
            [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ እባክዎ ቴክስት ብቻ ያስገቡ።\n\n"
            "ምስል አይቀበልም። እባክዎ ከባንክ የተላከልዎትን ቴክስት ብቻ ያስገቡ።",
            reply_markup=reply_markup
        )
    else:
        # Photo sent without context - ask to start deposit flow
        await update.message.reply_text(
            "እባክዎ ገንዘብ ለማስገባት ከዋና ማውጫ '💰 ገንዘብ ለማስገባት' ይምረጡ።"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user = update.effective_user
    text = update.message.text
    
    # Handle menu button clicks (from persistent keyboard)
    if text == "📝 ለመመዝገብ":
        await register_command(update, context)
        return
    elif text == "🎮 ጨዋታ ለመጀመር":
        # Check registration before allowing play
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            return
        await play_command(update, context)
        return
    elif text == "💰 ገንዘብ ለማስገባት":
        # Clear any existing states before starting deposit
        clear_financial_command_states(context)
        # Check registration before allowing deposit
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            return
        await deposit_command(update, context)
        return
    elif text == "💸 ገንዘብ ለማውጣት":
        # Clear any existing states before starting withdraw
        clear_financial_command_states(context)
        # Check registration before allowing withdraw
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            return
        await withdraw_command(update, context)
        return
    elif text == "💵 ሂሳብዎን ለማወቅ":
        # Check registration before allowing balance
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            return
        await balance_command(update, context)
        return
    elif text == "💸 ገንዘብ ለማስተላለፍ":
        # Clear any existing states before starting transfer
        clear_financial_command_states(context)
        # Check registration before allowing transfer
        if not await is_user_registered(user.id):
            welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
            keyboard = [
                [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            return
        await transfer_command(update, context)
        return
    elif text == "📋 የጨዋታ መመሪያ":
        await instruction_command(update, context)
        return
    elif text == "🆘 የድጋፍ ቡድን":
        await support_command(update, context)
        return
    elif text == "👥 ሰዎችን ለመጋበዝ":
        await invite_command(update, context)
        return
    
    # IMPORTANT: Check states in order of specificity to prevent interference
    # Transfer states (most specific - check first)
    if context.user_data.get('waiting_for_transfer_phone'):
        try:
            phone_number = text.strip()
            
            if not phone_number:
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "እባክዎ ስልክ ቁጥር ያስገቡ:",
                    reply_markup=reply_markup
                )
                return
            
            # Normalize phone number (remove 251 country code and add 0)
            normalized_phone = normalize_phone_number(phone_number)
            
            # Get sender and refresh from DB to get latest balance
            async def get_from_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            from_user = await db_operation_with_retry(get_from_user)
            async def refresh_user():
                await sync_to_async(from_user.refresh_from_db)()
            await db_operation_with_retry(refresh_user)
            
            # Find recipient by phone number with backward compatibility
            to_user = await sync_to_async(find_user_by_phone)(phone_number)
            
            if not to_user:
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"❌ ተጠቃሚ አልተገኘም!\n\n"
                    f"በ '{normalized_phone}' የተመዘገበ ተጠቃሚ አልተገኘም።\n"
                    f"እባክዎ ትክክለኛ ስልክ ቁጥር ያስገቡ:",
                    reply_markup=reply_markup
                )
                return
            
            # Check if trying to transfer to self
            if to_user.id == from_user.id:
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ ወደ ራስዎ ማስተላለፍ አይችሉም!\n\nእባክዎ የሌላ ተጠቃሚ ስልክ ቁጥር ያስገቡ:",
                    reply_markup=reply_markup
                )
                return
            
            # Store phone and ask for amount
            context.user_data['transfer_phone'] = normalized_phone
            context.user_data['transfer_to_user_id'] = to_user.id
            context.user_data['waiting_for_transfer_phone'] = False
            context.user_data['waiting_for_transfer_amount'] = True
            
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ ስልክ ቁጥር ተቀብሏል: {normalized_phone}\n\n"
                f"ያለዎት ሂሳብ: {from_user.balance} ብር\n\n"
                f"እባክዎ ለማስተላለፍ የሚፈልጉትን መጠን ያስገቡ:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error processing transfer phone: {e}", exc_info=True)
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "ስህተት ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።",
                reply_markup=reply_markup
            )
            context.user_data.pop('waiting_for_transfer_phone', None)
    
    elif context.user_data.get('waiting_for_transfer_amount'):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            from_user = await db_operation_with_retry(get_user)
            async def refresh_user():
                await sync_to_async(from_user.refresh_from_db)()
            await db_operation_with_retry(refresh_user)
            
            transfer_phone = context.user_data.get('transfer_phone', '')
            to_user_id = context.user_data.get('transfer_to_user_id')
            
            if not to_user_id:
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "ስህተት ተፈጥሯል። እባክዎ እንደገና ይጀምሩ።",
                    reply_markup=reply_markup
                )
                context.user_data.pop('waiting_for_transfer_amount', None)
                context.user_data.pop('transfer_phone', None)
                context.user_data.pop('transfer_to_user_id', None)
                return
            
            async def get_to_user():
                return await sync_to_async(User.objects.get)(id=to_user_id)
            to_user = await db_operation_with_retry(get_to_user)
            
            if from_user.balance < Decimal(str(amount)):
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"❌ በቂ ሂሳብ የሎትም!\n\n"
                    f"ያለዎት ሂሳብ: {from_user.balance} ብር",
                    reply_markup=reply_markup
                )
                # Clear context
                context.user_data.pop('waiting_for_transfer_amount', None)
                context.user_data.pop('transfer_phone', None)
                context.user_data.pop('transfer_to_user_id', None)
                return
            
            # Store amount and show confirmation
            context.user_data['transfer_amount'] = Decimal(str(amount))
            context.user_data['waiting_for_transfer_amount'] = False
            context.user_data['waiting_for_transfer_confirm'] = True
            
            keyboard = [
                [InlineKeyboardButton("✅ አዎ", callback_data="transfer_confirm_yes"),
                 InlineKeyboardButton("❌ አይ", callback_data="transfer_confirm_no")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"ይህንን {amount} ብር ለ {transfer_phone} ማስተላለፍ ይፈልጋሉ?",
                reply_markup=reply_markup
            )
            
        except ValueError:
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "ልክ ያልሆነ መጠን። እባክዎ ትክክለኛ የገንዘብ መጠን ያስገቡ:",
                reply_markup=reply_markup
            )
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            context.user_data.pop('waiting_for_transfer_amount', None)
            context.user_data.pop('transfer_phone', None)
            context.user_data.pop('transfer_to_user_id', None)
    
    elif context.user_data.get('waiting_for_transfer_confirm'):
        # User sent text instead of clicking button, ask them to use buttons
        keyboard = [
            [InlineKeyboardButton("✅ አዎ", callback_data="transfer_confirm_yes"),
             InlineKeyboardButton("❌ አይ", callback_data="transfer_confirm_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "እባክዎ ከላይ ያሉትን ቁልፎች ይጠቀሙ:",
            reply_markup=reply_markup
        )
    
    # Deposit states
    elif context.user_data.get('waiting_for_deposit'):
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            
            platform = context.user_data.get('deposit_platform', '')
            amount = context.user_data.get('deposit_amount', 0)
            photo_id = context.user_data.get('deposit_photo_id', '')
            
            # Store the text/screenshot
            deposit_text = text
            if photo_id:
                deposit_text = f"{deposit_text}\nPhoto file_id: {photo_id}".strip()
            
            # Create deposit request
            async def create_deposit_request():
                return await sync_to_async(DepositRequest.objects.create)(
                    user=telegram_user,
                    amount=Decimal(str(amount)),
                    platform=platform,
                    deposit_text=deposit_text or f"Amount: {amount}",
                    photo_file_id=photo_id or None,
                    status='pending'
                )
            deposit_request = await db_operation_with_retry(create_deposit_request)
            
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ የገንዘብ ማስገቢያ ጥያቄዎ ተልኳል!\n\n"
                f"💰 መጠን: {amount} ብር\n"
                f"🏦 ወደ: {platform}\n"
                f"📋 ሁኔታ: በማረጋገጥ ላይ\n\n"
                f"እባክዎ እስኪረጋገጥ ትንሽ ይጠብቁ።",
                reply_markup=reply_markup
            )
            
            # Clear context
            context.user_data.pop('deposit_text', None)
            context.user_data.pop('deposit_amount', None)
            context.user_data.pop('waiting_for_deposit', None)
            context.user_data.pop('deposit_photo_id', None)
            context.user_data.pop('deposit_platform', None)
            
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            context.user_data['waiting_for_deposit'] = False
    
    elif context.user_data.get('waiting_for_deposit_amount'):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            
            # Store amount and ask for screenshot/text
            context.user_data['deposit_amount'] = amount
            context.user_data['waiting_for_deposit_amount'] = False
            context.user_data['waiting_for_deposit'] = True
            
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ መጠን ተቀብሏል: {amount} ብር\n\n"
                f"እባክዎ ከባንክ የተላከልዎትን ቴክስት ብቻ ያስገቡ።",
                reply_markup=reply_markup
            )
            
        except ValueError:
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "ልክ ያልሆነ መጠን። እባክዎ ትክክለኛ የገንዘብ መጠን ያስገቡ:",
                reply_markup=reply_markup
            )
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
            context.user_data.pop('waiting_for_deposit_amount', None)
    
    elif context.user_data.get('waiting_for_deposit_text'):
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            platform = context.user_data.get('deposit_platform', '')
            amount = context.user_data.get('deposit_amount', 0)
            
            # Update deposit request with text
            async def get_deposit_request():
                return await sync_to_async(
                    lambda: DepositRequest.objects.filter(
                        user=telegram_user,
                        platform=platform,
                        amount=Decimal(str(amount)),
                        status='pending'
                    ).order_by('-created_at').first()
                )()
            deposit_request = await db_operation_with_retry(get_deposit_request)
            
            if deposit_request:
                deposit_request.deposit_text = text
                async def save_deposit_request():
                    await sync_to_async(deposit_request.save)()
                await db_operation_with_retry(save_deposit_request)
            
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ ጥያቄዎ ተልኳል!\n"
                f"መጠን: {amount} ብር\n"
                f"ሁኔታ: በማረጋገጥ ላይ\n\n"
                f"እባክዎ እስኪረጋገጥ ትንሽ ይጠብቁ።",
                reply_markup=reply_markup
            )
            
            # Clear context
            context.user_data.pop('waiting_for_deposit_text', None)
            context.user_data.pop('deposit_platform', None)
            context.user_data.pop('deposit_amount', None)
            
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
    
    # Withdraw states
    elif context.user_data.get('waiting_for_withdraw_amount'):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            async def get_settings():
                return await sync_to_async(GameSettings.get_settings)()
            settings = await db_operation_with_retry(get_settings)
            min_withdraw = settings.min_withdraw
            
            if amount < float(min_withdraw):
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"ዝቅተኛ መጠን: {min_withdraw} ብር\n"
                    f"እባክዎ {min_withdraw} ብር ወይም ከዚያ በላይ ያስገቡ:",
                    reply_markup=reply_markup
                )
                return
            
            if telegram_user.balance < Decimal(str(amount)):
                keyboard = [
                    [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"በቂ ሂሳብ የሎትም። ያለዎት ሂሳብ: {telegram_user.balance} ብር",
                    reply_markup=reply_markup
                )
                return
            
            # Show platform selection
            keyboard = [
                [InlineKeyboardButton("🏦 BOA(አቢሲኒያ ባንክ)", callback_data="withdraw_platform_BOA")],
                [InlineKeyboardButton("🏦 CBE(ንግድ ባንክ)", callback_data="withdraw_platform_CBE")],
                [InlineKeyboardButton("📱 Telebirr(ቴሌብር)", callback_data="withdraw_platform_Telebirr")],
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.user_data['withdraw_amount'] = amount
            context.user_data['waiting_for_withdraw_amount'] = False
            
            await update.message.reply_text(
                f"💰 መጠን: {amount} ብር\n\n"
                f"ወደ የት ወጭ ማድረግ እንደሚፈልጉ ይምረጡ:",
                reply_markup=reply_markup
            )
            
        except ValueError:
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "ልክ ያልሆነ መጠን። እባክዎ ትክክለኛ የገንዘብ መጠን ያስገቡ:",
                reply_markup=reply_markup
            )
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
            context.user_data.pop('waiting_for_withdraw_amount', None)
    
    elif context.user_data.get('waiting_for_withdraw_account_name'):
        try:
            account_name = text.strip()
            if not account_name:
                await update.message.reply_text("እባክዎ የሂሳብ ባለቤት ስም ያስገቡ:")
                return
            
            context.user_data['withdraw_account_name'] = account_name
            context.user_data['waiting_for_withdraw_account_name'] = False
            context.user_data['waiting_for_withdraw_account_number'] = True
            
            keyboard = [
                [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "እባክዎ የሂሳብ ቁጥር ያስገቡ:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error handling withdraw account name: {e}")
            await update.message.reply_text("ስህተት ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።")
    
    elif context.user_data.get('waiting_for_withdraw_account_number'):
        try:
            account_number = text.strip()
            if not account_number:
                await update.message.reply_text("እባክዎ የሂሳብ ቁጥር ያስገቡ:")
                return
            
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
            platform = context.user_data.get('withdraw_platform', '')
            amount = Decimal(str(context.user_data.get('withdraw_amount', 0)))
            account_name = context.user_data.get('withdraw_account_name', '')
            
            # Create withdraw request
            async def create_withdraw_request():
                return await sync_to_async(WithdrawRequest.objects.create)(
                    user=telegram_user,
                    amount=amount,
                    platform=platform,
                    account_holder_name=account_name,
                    account_number=account_number,
                    status='pending'
                )
            withdraw_request = await db_operation_with_retry(create_withdraw_request)
            
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ የገንዘብ ማውጣት ጥያቄዎ ተልኳል!\n\n"
                f"💰 መጠን: {amount} ብር\n"
                f"🏦 ወደ: {platform}\n"
                f"📋 ሁኔታ: በማረጋገጥ ላይ\n\n"
                f"እባክዎ እስኪረጋገጥ ትንሽ ይጠብቁ።",
                reply_markup=reply_markup
            )
            
            # Clear context
            context.user_data.pop('waiting_for_withdraw_account_number', None)
            context.user_data.pop('waiting_for_withdraw_account_name', None)
            context.user_data.pop('withdraw_platform', None)
            context.user_data.pop('withdraw_amount', None)
            context.user_data.pop('withdraw_account_name', None)
            
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
        except Exception as e:
            logger.error(f"Error creating withdraw request: {e}")
            await update.message.reply_text("ስህተት ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።")
            
            context.user_data.pop('waiting_for_withdraw', None)
            
        except ValueError:
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "ልክ ያልሆነ መጠን። እባክዎ ቁጥር ያስገቡ (ምሳሌ: 100)",
                reply_markup=reply_markup
            )
        except User.DoesNotExist:
            await update.message.reply_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
            context.user_data.pop('waiting_for_withdraw', None)
    
    else:
        # Default response
        keyboard = [
            [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "ዋና ማውጫን ለማየት /start(ዋና ማውጫ) ይጠቀሙ።",
            reply_markup=reply_markup
        )


def get_main_menu_keyboard():
    """Get persistent ReplyKeyboardMarkup for main menu"""
    keyboard = [
        [KeyboardButton("📝 ለመመዝገብ"), KeyboardButton("🎮 ጨዋታ ለመጀመር")],
        [KeyboardButton("💰 ገንዘብ ለማስገባት"), KeyboardButton("💸 ገንዘብ ለማውጣት")],
        [KeyboardButton("💵 ሂሳብዎን ለማወቅ"), KeyboardButton("💸 ገንዘብ ለማስተላለፍ")],
        [KeyboardButton("📋 የጨዋታ መመሪያ"), KeyboardButton("🆘 የድጋፍ ቡድን")],
        [KeyboardButton("👥 ሰዎችን ለመጋበዝ")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = None):
    """Show main menu with persistent keyboard"""
    menu_text = message or "አማራጭ ይምረጡ:"
    reply_markup = get_main_menu_keyboard()
    
    # Check if user is registered
    user = update.effective_user or (update.callback_query and update.callback_query.from_user)
    is_registered = False
    if user:
        is_registered = await is_user_registered(user.id)
    
    try:
        if update.callback_query:
            # For callback queries, use inline keyboard
            # Only show register button if not registered, disable other buttons
            if not is_registered:
                inline_keyboard = [
                    [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")],
                ]
            else:
                inline_keyboard = [
                    [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register"),
                     InlineKeyboardButton("🎮 ጨዋታ ለመጀመር", callback_data="play")],
                    [InlineKeyboardButton("💰 ገንዘብ ለማስገባት", callback_data="deposit"),
                     InlineKeyboardButton("💸 ገንዘብ ለማውጣት", callback_data="withdraw")],
                    [InlineKeyboardButton("💵 ሂሳብዎን ለማወቅ", callback_data="balance"),
                     InlineKeyboardButton("💸 ገንዘብ ለማስተላለፍ", callback_data="transfer")],
                    [InlineKeyboardButton("📋 የጨዋታ  መመሪያ", callback_data="instructions"),
                     InlineKeyboardButton("🆘 የድጋፍ ቡድን", callback_data="support")],
                    [InlineKeyboardButton("👥 ሰዎችን ለመጋበዝ", callback_data="invite")],
                ]
            await update.callback_query.edit_message_text(
                menu_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard)
            )
            await update.callback_query.answer()
        elif update.message:
            await update.message.reply_text(
                menu_text,
                reply_markup=reply_markup
            )
        else:
            logger.warning("show_main_menu called but no message or callback_query available")
    except Exception as e:
        logger.error(f"Error in show_main_menu: {e}", exc_info=True)
        # Try to send message as fallback
        if update.message:
            try:
                await update.message.reply_text(menu_text, reply_markup=reply_markup)
            except:
                pass
        elif update.callback_query:
            try:
                await update.callback_query.answer()
            except:
                pass


async def handle_deposit_platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, platform: str):
    """Handle deposit platform selection - Show account details"""
    query = update.callback_query
    user = query.from_user
    
    try:
        async def get_user():
            return await sync_to_async(User.objects.get)(telegram_id=user.id)
        telegram_user = await db_operation_with_retry(get_user)
    except User.DoesNotExist:
        await query.edit_message_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
        return
    
    # Get account details from settings
    async def get_settings():
        return await sync_to_async(GameSettings.get_settings)()
    settings = await db_operation_with_retry(get_settings)
    accounts = settings.deposit_accounts
    account_info = accounts.get(platform, {})
    
    account_name = account_info.get('name', 'N/A')
    account_number = account_info.get('number', 'N/A')
    
    keyboard = [
        [InlineKeyboardButton("✅ ገቢ አድርጌዋለሁ", callback_data=f"deposit_confirm_{platform}")],
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    platform_names = {
        'BOA': 'Bank of Abyssinia',
        'CBE': 'Commercial Bank of Ethiopia',
        'Telebirr': 'Telebirr'
    }
    platform_name = platform_names.get(platform, platform)
    
    message = (
        f"🏦 {platform_name}\n\n"
        f"የሂሳብ ባለቤት: {account_name}\n"
        f"የሂሳብ ቁጥር: {account_number}\n\n"
        f"እባክዎ ወደ ላይ የተጠቀሰው ሂሳብ ገንዘብ ያስገቡ።\n"
        f"ከዚያ ገቢ አድርጌዋለሁ የሚለውን ይጫኑ።"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup)
    context.user_data['deposit_platform'] = platform


async def handle_deposit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit confirmation - Ask for amount"""
    query = update.callback_query
    platform = context.user_data.get('deposit_platform', '')
    
    keyboard = [
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"እባክዎ ገቢ ያደረጉትን የገንዘብ መጠን ያስገቡ:\n\n"
        f"ወደ: {platform}"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup)
    await query.answer()
    context.user_data['waiting_for_deposit_amount'] = True


async def handle_withdraw_platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, platform: str):
    """Handle withdraw platform selection - Ask for account details"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    platform_names = {
        'BOA': 'Bank of Abyssinia',
        'CBE': 'Commercial Bank of Ethiopia',
        'Telebirr': 'Telebirr'
    }
    platform_name = platform_names.get(platform, platform)
    
    message = (
        f"🏦 {platform_name}\n\n"
        f"እባክዎ የሂሳብ ባለቤት ስም ያስገቡ:"
    )
    
    await query.edit_message_text(message, reply_markup=reply_markup)
    await query.answer()
    context.user_data['withdraw_platform'] = platform
    context.user_data['waiting_for_withdraw_account_name'] = True


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    if not query:
        logger.warning("button_callback called but no callback_query available")
        return
    
    await query.answer()
    
    user = query.from_user
    is_registered = await is_user_registered(user.id) if user else False
    
    if query.data == "main_menu":
        # Clear all financial command states when returning to main menu
        clear_financial_command_states(context)
        await show_main_menu(update, context)
    elif query.data == "register":
        await register_command(update, context)
    elif not is_registered:
        # User not registered, show registration prompt
        welcome_msg = "እንኳን ወደ አሪፍ ቢንጎ በደህና መጡ! 🎉\n\n/register በመንካት ይመዝገቡ፡፡"
        keyboard = [
            [InlineKeyboardButton("📝 ለመመዝገብ", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_msg, reply_markup=reply_markup)
    elif query.data == "play":
        # Handle play from callback - need to send new message
        user = query.from_user
        try:
            async def get_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            telegram_user = await db_operation_with_retry(get_user)
        except User.DoesNotExist:
            await query.edit_message_text("እባክዎ በመጀመሪያ ይመዝገቡ።")
            await show_main_menu(update, context)
            return
        
        # Always open web app - let the web app handle game state
        token = generate_jwt_token(telegram_user)
        mini_app_url = f"{settings.TELEGRAM_WEB_APP_URL}?token={token}"
        logger.info(f"Opening web app for user {telegram_user.telegram_id}: {settings.TELEGRAM_WEB_APP_URL}")
        
        # Get current game info for display (optional)
        async def get_current_game():
            return await sync_to_async(
                lambda: Game.objects.filter(
                    status__in=['waiting', 'active']
                ).order_by('-created_at').first()
            )()
        current_game = await db_operation_with_retry(get_current_game)
        
        # Get bet_amount from current game, or from GameSettings if no game exists
        if current_game:
            # For waiting games with no cards, use settings bid_amount to ensure it's up-to-date
            if current_game.status == 'waiting':
                async def count_gamecards():
                    return await sync_to_async(current_game.gamecards.count)()
                gamecards_count = await db_operation_with_retry(count_gamecards)
                if gamecards_count == 0:
                    # No cards selected yet, use current settings value
                    async def get_settings():
                        return await sync_to_async(GameSettings.get_settings)()
                    game_settings = await db_operation_with_retry(get_settings)
                    bet_amount = game_settings.bid_amount
                    # Also update the game's bet_amount to match settings
                    current_game.bet_amount = game_settings.bid_amount
                    async def save_game():
                        await sync_to_async(current_game.save)(update_fields=['bet_amount'])
                    await db_operation_with_retry(save_game)
                else:
                    # Cards already selected, use game's bet_amount
                    bet_amount = current_game.bet_amount
            else:
                # Active game, use game's bet_amount
                bet_amount = current_game.bet_amount
                async def count_gamecards():
                    return await sync_to_async(current_game.gamecards.count)()
                gamecards_count = await db_operation_with_retry(count_gamecards)
        else:
            # No current game, get bet_amount from GameSettings
            async def get_settings():
                return await sync_to_async(GameSettings.get_settings)()
            game_settings = await db_operation_with_retry(get_settings)
            bet_amount = game_settings.bid_amount
            gamecards_count = 0
        
        # Check if URL is HTTPS (required for Telegram web apps)
        # If HTTP (local development), show URL as text instead of web app button
        if settings.TELEGRAM_WEB_APP_URL.startswith('http://'):
            # Local development - can't use web app button with HTTP
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"🍀 በጨዋታዎ ላይ መልካም ዕድል!\n\n"
                f"መደብ: {bet_amount} ብር\n"
                f"🔗 የጨዋታ ማስጀመሪያ:\n{mini_app_url}",
                reply_markup=reply_markup
            )
        else:
            # Production - use web app button
            keyboard = [
                [InlineKeyboardButton("🎮 ጨዋታ ይጀምሩ", web_app=WebAppInfo(url=mini_app_url))],
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"🍀 በጨዋታዎ ላይ መልካም ዕድል!\n\n"
                f"መደብ: {bet_amount} ብር\n",
                reply_markup=reply_markup
            )
    elif query.data == "deposit":
        # Clear any existing states before starting deposit
        clear_financial_command_states(context)
        await deposit_command(update, context)
    elif query.data.startswith("deposit_platform_"):
        # Handle platform selection for deposit
        platform = query.data.replace("deposit_platform_", "")
        await handle_deposit_platform_selection(update, context, platform)
    elif query.data.startswith("deposit_confirm_"):
        # Handle deposit confirmation - ask for amount
        await handle_deposit_confirm(update, context)
    elif query.data == "withdraw":
        # Clear any existing states before starting withdraw
        clear_financial_command_states(context)
        await withdraw_command(update, context)
    elif query.data == "transfer":
        # Clear any existing states before starting transfer
        clear_financial_command_states(context)
        await transfer_command(update, context)
    elif query.data == "transfer_confirm_yes":
        # User confirmed transfer
        try:
            user = query.from_user
            async def get_from_user():
                return await sync_to_async(User.objects.get)(telegram_id=user.id)
            from_user = await db_operation_with_retry(get_from_user)
            async def refresh_user():
                await sync_to_async(from_user.refresh_from_db)()
            await db_operation_with_retry(refresh_user)
            
            transfer_amount = context.user_data.get('transfer_amount')
            transfer_phone = context.user_data.get('transfer_phone', '')
            to_user_id = context.user_data.get('transfer_to_user_id')
            
            if not transfer_amount or not to_user_id:
                await query.edit_message_text("ስህተት ተፈጥሯል። እባክዎ እንደገና ይጀምሩ።")
                context.user_data.pop('waiting_for_transfer_confirm', None)
                context.user_data.pop('transfer_amount', None)
                context.user_data.pop('transfer_phone', None)
                context.user_data.pop('transfer_to_user_id', None)
                return
            
            async def get_to_user():
                return await sync_to_async(User.objects.get)(id=to_user_id)
            to_user = await db_operation_with_retry(get_to_user)
            
            # Check balance again
            if from_user.balance < transfer_amount:
                keyboard = [
                    [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"❌ በቂ ሂሳብ የሎትም!\n\nያለዎት ሂሳብ: {from_user.balance} ብር",
                    reply_markup=reply_markup
                )
                context.user_data.pop('waiting_for_transfer_confirm', None)
                context.user_data.pop('transfer_amount', None)
                context.user_data.pop('transfer_phone', None)
                context.user_data.pop('transfer_to_user_id', None)
                return
            
            # Perform transfer
            async def refresh_to_user():
                await sync_to_async(to_user.refresh_from_db)()
            await db_operation_with_retry(refresh_to_user)
            
            # Deduct from sender
            from_user.balance = Decimal(str(from_user.balance)) - transfer_amount
            async def save_from_user():
                await sync_to_async(from_user.save)()
            await db_operation_with_retry(save_from_user)
            
            # Add to recipient
            to_user.balance = Decimal(str(to_user.balance)) + transfer_amount
            async def save_to_user():
                await sync_to_async(to_user.save)()
            await db_operation_with_retry(save_to_user)
            
            # Refresh to_user from DB to ensure we have the latest balance
            async def refresh_to_user_after_save():
                await sync_to_async(to_user.refresh_from_db)()
            await db_operation_with_retry(refresh_to_user_after_save)
            
            # Create Transfer record
            from api.models import Transfer
            async def create_transfer():
                return await sync_to_async(Transfer.objects.create)(
                    from_user=from_user,
                    to_user=to_user,
                    amount=transfer_amount
                )
            transfer = await db_operation_with_retry(create_transfer)
            
            # Create transaction records
            async def create_transaction_from():
                await sync_to_async(Transaction.objects.create)(
                    user=from_user,
                    transaction_type='transfer',
                    amount=-transfer_amount,
                    transfer=transfer,
                    description=f'Transfer to {to_user.username} ({transfer_phone})'
                )
            await db_operation_with_retry(create_transaction_from)
            
            async def create_transaction_to():
                await sync_to_async(Transaction.objects.create)(
                    user=to_user,
                    transaction_type='transfer',
                    amount=transfer_amount,
                    transfer=transfer,
                    description=f'Transfer from {from_user.username}'
                )
            await db_operation_with_retry(create_transaction_to)
            
            # Clear context
            context.user_data.pop('waiting_for_transfer_confirm', None)
            context.user_data.pop('transfer_amount', None)
            context.user_data.pop('transfer_phone', None)
            context.user_data.pop('transfer_to_user_id', None)
            
            keyboard = [
                [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ ገንዘቡ በተሳካ ሁኔታ ተላልፏል!\n\n"
                f"💰 መጠን: {transfer_amount} ብር\n"
                f"👤 ወደ: {to_user.username} ({transfer_phone})\n"
                f"💵 ያለዎት ቀሪ ሂሳብ: {from_user.balance} ብር",
                reply_markup=reply_markup
            )
            
            # Notify recipient - ensure it's sent (use async version since we're in async context)
            try:
                if to_user.telegram_id:
                    # Get the latest balance after the transfer
                    final_balance = to_user.balance
                    notification_msg = (
                        f"💰 ገንዘብ ተቀብለዋል!\n\n"
                        f"መጠን: {transfer_amount} ብር\n"
                        f"ከ: {from_user.username}\n"
                        f"አዲስ ሂሳብዎ: {final_balance} ብር"
                    )
                    from telegram_bot.notifications import send_notification
                    logger.info(f"Attempting to send transfer notification to {to_user.telegram_id} (recipient: {to_user.username})")
                    result = await send_notification(to_user.telegram_id, notification_msg)
                    if not result:
                        logger.warning(f"Failed to send transfer notification to {to_user.telegram_id}")
                    else:
                        logger.info(f"Successfully sent transfer notification to {to_user.telegram_id} (recipient: {to_user.username})")
                else:
                    logger.warning(f"Recipient {to_user.username} (ID: {to_user.id}) has no telegram_id, cannot send notification")
            except Exception as e:
                logger.error(f"Error notifying recipient {to_user.username} (telegram_id: {to_user.telegram_id}): {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Error confirming transfer: {e}", exc_info=True)
            await query.edit_message_text("ስህተት ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።")
            context.user_data.pop('waiting_for_transfer_confirm', None)
            context.user_data.pop('transfer_amount', None)
            context.user_data.pop('transfer_phone', None)
            context.user_data.pop('transfer_to_user_id', None)
    elif query.data == "transfer_confirm_no":
        # User cancelled transfer
        context.user_data.pop('waiting_for_transfer_confirm', None)
        context.user_data.pop('transfer_amount', None)
        context.user_data.pop('transfer_phone', None)
        context.user_data.pop('transfer_to_user_id', None)
        
        keyboard = [
            [InlineKeyboardButton("🏠 ዋና ማውጫ", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ ማስተላለፍ ተሰርዟል።", reply_markup=reply_markup)
    elif query.data.startswith("withdraw_platform_"):
        # Handle platform selection for withdraw
        platform = query.data.replace("withdraw_platform_", "")
        await handle_withdraw_platform_selection(update, context, platform)
    elif query.data == "balance":
        await balance_command(update, context)
    elif query.data == "instructions":
        await instruction_command(update, context)
    elif query.data == "support":
        await support_command(update, context)
    elif query.data == "invite":
        await invite_command(update, context)


async def ping_health_endpoint():
    """Ping health endpoint to wake machines on Fly.io"""
    try:
        import aiohttp
        api_url = settings.TELEGRAM_WEB_APP_URL or 'http://localhost:8000'
        # Remove path if present, keep just base URL
        base_url = api_url.split('/api')[0].split('/admin')[0].rstrip('/')
        health_url = f"{base_url}/api/health/"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    logger.debug("Health check ping successful")
                else:
                    logger.warning(f"Health check returned status {response.status}")
    except Exception as e:
        logger.debug(f"Health check ping failed (expected if not deployed): {e}")


async def set_bot_commands(application: Application):
    """Set bot commands menu"""
    try:
        # Ensure database connection is fresh when bot starts
        await sync_to_async(ensure_db_connection)()
        logger.info("✅ Database connection validated on bot startup")
    except Exception as e:
        logger.warning(f"Database connection check failed on startup: {e}")
    
    try:
        # Delete webhook first to avoid conflicts
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted successfully - bot is ready for polling")
    except Exception as e:
        logger.warning(f"Could not delete webhook (may not exist): {e}")
    
    # Get bot info to confirm it's working
    try:
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot is ready! Username: @{bot_info.username}, Name: {bot_info.first_name}")
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
    
    commands = [
        BotCommand("register", "ለመመዝገብ"),
        BotCommand("play", "ጨዋታ ለመጀመር"),
        BotCommand("deposit", "ገንዘብ ለማስገባት"),
        BotCommand("withdraw", "ገንዘብ ለማውጣት"),
        BotCommand("balance", "ሂሳብዎን ለማወቅ"),
        BotCommand("transfer", "ገንዘብ ለማስተላለፍ"),
        BotCommand("instruction", "የጨዋታ መመሪያ"),
        BotCommand("support", "ድጋፍ ከፈለጉ"),
        BotCommand("invite", "ሰዎችን ለመጋበዝ"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("✅ Bot commands menu set successfully")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}", exc_info=True)
        # Don't fail completely if commands can't be set, but log the error
    
    # Start periodic health check ping to wake machines (every 4 minutes)
    async def periodic_health_check():
        import asyncio
        await asyncio.sleep(60)  # Wait 1 minute after startup
        logger.info("Starting periodic health check pings...")
        while True:
            try:
                # Validate database connection periodically
                await sync_to_async(ensure_db_connection)()
                logger.debug("Database connection health check passed")
            except Exception as e:
                logger.warning(f"Database connection health check failed: {e}")
            
            try:
                await ping_health_endpoint()
            except Exception as e:
                logger.debug(f"Health check ping error: {e}")
            await asyncio.sleep(240)  # Wait 4 minutes between pings
    
    # Start health check task in background when application starts
    async def start_health_check():
        import asyncio
        await asyncio.sleep(60)  # Wait 1 minute after startup
        asyncio.create_task(periodic_health_check())
    
    # Schedule health check to start after polling begins
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(start_health_check())
        else:
            # Will be started when polling begins
            pass
    except RuntimeError:
        # Event loop not available yet - will be created when polling starts
        pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot"""
    error = context.error
    
    # Handle Conflict errors (multiple bot instances) - don't show to user
    if isinstance(error, Exception) and "Conflict" in str(error):
        logger.warning(f"Bot conflict detected (another instance may be running): {error}")
        return  # Don't show error to user for conflicts
    
    logger.error(f"Exception while handling an update: {error}", exc_info=error)
    
    # Try to send error message to user if update is available
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😔 እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።"
            )
        except Exception as e:
            logger.error(f"Error sending error message to user: {e}")


def setup_bot():
    """Setup and return bot application"""
    token = settings.TELEGRAM_BOT_TOKEN
    
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Bot will not start.")
        return None
    
    try:
        application = Application.builder().token(token).build()
        
        # Set bot commands menu
        application.post_init = set_bot_commands
        
        # Add error handler (must be added first)
        application.add_error_handler(error_handler)
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("register", register_command))
        application.add_handler(CommandHandler("play", play_command))
        application.add_handler(CommandHandler("deposit", deposit_command))
        application.add_handler(CommandHandler("withdraw", withdraw_command))
        application.add_handler(CommandHandler("balance", balance_command))
        application.add_handler(CommandHandler("transfer", transfer_command))
        application.add_handler(CommandHandler("instruction", instruction_command))
        application.add_handler(CommandHandler("support", support_command))
        application.add_handler(CommandHandler("invite", invite_command))
        
        # Add message handler (including photos for deposit screenshots and contacts for phone numbers)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
        
        # Add callback query handler
        from telegram.ext import CallbackQueryHandler
        application.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("Bot application setup completed successfully")
        return application
        
    except Exception as e:
        logger.error(f"Error setting up bot: {e}", exc_info=True)
        return None

