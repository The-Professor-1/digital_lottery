"""
Car lottery bot onboarding:
  /start → language → share contact → open mini-app
No deposit/withdraw/play menus — everything runs inside the web app.
"""
import logging
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    WebAppInfo,
    BotCommand,
)
from telegram.ext import ContextTypes

from api.models import User, LotterySettings
from api.auth_utils import generate_jwt_token

logger = logging.getLogger(__name__)

try:
    from telegram import BotCommandScopeAllPrivateChats
except ImportError:
    BotCommandScopeAllPrivateChats = None


BOT_DESCRIPTION = (
    "🚗 Getachew Fikadu Jirata\n\n"
    "Baga gara bootii keenyaa dhuftan.\n"
    "ወደ መተግበሪያችን እንኳን በደህና መጡ።\n"
    "Welcome to our Bot."
)

LANG_PROMPT = (
    "🚗 Getachew Fikadu Jirata\n\n"
    "Maaloo afaan filadhu.\n"
    "እባክዎ ቋንቋ ይምረጡ።\n"
    "Please select your language."
)

SHARE_PHONE = {
    'am': 'ለመቀጠል የስልክ ቁጥርዎን ያጋሩ።',
    'en': 'To continue, please share your phone number.',
    'om': 'Itti fufuuf lakkoofsa bilbilaa kee maxxansi.',
}

SHARE_PHONE_BUTTON = {
    'am': '📱 ስልክ ቁጥር ያጋሩ',
    'en': '📱 Share phone number',
    'om': '📱 Lakkoofsa bilbilaa maxxansi',
}

PHONE_RECEIVED = {
    'am': 'የስልክ ቁጥር ተቀብለናል ✅',
    'en': 'Phone number received ✅',
    'om': 'Lakkoofsi bilbilaa fudhatameera ✅',
}

OPEN_APP_HINT = {
    'am': 'መተግበሪያውን ለመክፈት ከታች ያለውን ቁልፍ ይጫኑ።',
    'en': 'To open the application, press the button below.',
    'om': 'Appii banuuf qabduu armaan gadii tuqi.',
}

OWN_CONTACT_ONLY = {
    'am': 'እባክዎ የእርስዎን ስልክ ቁጥር ያጋሩ።',
    'en': 'Please share your own phone number.',
    'om': 'Maaloo lakkoofsa bilbilaa kee qofa maxxansi.',
}


def _brand_app_label():
    try:
        brand = LotterySettings.get_settings().brand_name or 'Getachew Fikadu'
    except Exception:
        brand = 'Getachew Fikadu'
    return f'{brand} app 🚗'


def _lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🇪🇹 Afaan Oromo', callback_data='lang_om')],
        [InlineKeyboardButton('🇪🇹 አማርኛ', callback_data='lang_am')],
        [InlineKeyboardButton('🇬🇧 English', callback_data='lang_en')],
    ])


def _normalize_phone(phone_number: str) -> str:
    digits = ''.join(ch for ch in (phone_number or '') if ch.isdigit())
    if digits.startswith('251') and len(digits) >= 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '251' + digits[1:]
    if len(digits) == 9:
        return '251' + digits
    return digits or (phone_number or '')


def _mini_app_url(user: User) -> str:
    token = generate_jwt_token(user)
    base = (getattr(settings, 'TELEGRAM_WEB_APP_URL', '') or '').strip()
    if not base:
        base = 'https://example.com'
    sep = '&' if '?' in base else '?'
    return f'{base}{sep}token={token}'


async def _get_or_create_tg_user(tg_user):
    def _go():
        try:
            obj, _ = User.objects.get_or_create(
                telegram_id=tg_user.id,
                defaults={
                    'username': (tg_user.username or f'user_{tg_user.id}')[:150],
                    'first_name': (tg_user.first_name or '')[:150],
                    'last_name': (tg_user.last_name or '')[:150],
                    'password': make_password(None),
                },
            )
            return obj
        except IntegrityError:
            # Username collision — force unique telegram-based username
            obj, _ = User.objects.get_or_create(
                telegram_id=tg_user.id,
                defaults={
                    'username': f'tg_{tg_user.id}',
                    'first_name': (tg_user.first_name or '')[:150],
                    'last_name': (tg_user.last_name or '')[:150],
                    'password': make_password(None),
                },
            )
            return obj

    return await sync_to_async(_go)()


def _open_app_markup(url: str, label: str):
    """HTTPS → Mini App button. HTTP → normal URL button (Telegram WebApp needs HTTPS)."""
    if url.startswith('https://'):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(label, web_app=WebAppInfo(url=url))]
        ])
    if url.startswith('http://'):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(label, url=url)]
        ])
    return None


async def send_open_app(update: Update, user: User, lang: str, include_received: bool = False):
    lang = lang if lang in SHARE_PHONE else 'am'
    parts = []
    if include_received:
        parts.append(PHONE_RECEIVED[lang])
    parts.append(OPEN_APP_HINT[lang])
    text = '\n\n'.join(parts)

    url = await sync_to_async(_mini_app_url)(user)
    label = await sync_to_async(_brand_app_label)()
    markup = _open_app_markup(url, label)

    if markup is None:
        text = f'{text}\n\n{url}'

    target = update.effective_message
    if target:
        await target.reply_text(text, reply_markup=markup)


async def ask_share_phone(update: Update, lang: str):
    lang = lang if lang in SHARE_PHONE else 'am'
    keyboard = [[KeyboardButton(SHARE_PHONE_BUTTON[lang], request_contact=True)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    msg = SHARE_PHONE[lang]
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(msg, reply_markup=markup)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Language first (or open app if already registered)."""
    try:
        tg = update.effective_user
        if not tg:
            return

        user = await _get_or_create_tg_user(tg)

        if user.phone_number:
            lang = user.preferred_language or 'am'
            await send_open_app(update, user, lang)
            return

        if update.message:
            await update.message.reply_text(LANG_PROMPT, reply_markup=_lang_keyboard())
        elif update.callback_query:
            await update.callback_query.edit_message_text(LANG_PROMPT, reply_markup=_lang_keyboard())
            await update.callback_query.answer()
    except Exception as e:
        logger.error(f'Error in lottery start_command: {e}', exc_info=True)
        if update and update.effective_message:
            await update.effective_message.reply_text('Please try again in a moment.')


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    lang = query.data.replace('lang_', '')
    if lang not in ('am', 'en', 'om'):
        await query.answer()
        return

    tg = update.effective_user
    user = await _get_or_create_tg_user(tg)

    def _save_lang():
        user.preferred_language = lang
        user.save(update_fields=['preferred_language'])

    await sync_to_async(_save_lang)()
    context.user_data['lang'] = lang

    if user.phone_number:
        await query.answer()
        await send_open_app(update, user, lang)
        return

    await ask_share_phone(update, lang)


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tg = update.effective_user
        contact = update.message.contact if update.message else None
        if not tg or not contact:
            return

        lang = context.user_data.get('lang')
        user = await _get_or_create_tg_user(tg)
        if not lang:
            lang = getattr(user, 'preferred_language', None) or 'am'

        # request_contact shares usually include user_id; if missing, still accept
        if contact.user_id is not None and int(contact.user_id) != int(tg.id):
            await update.message.reply_text(OWN_CONTACT_ONLY.get(lang, OWN_CONTACT_ONLY['am']))
            return

        normalized = _normalize_phone(contact.phone_number)
        if not normalized:
            await update.message.reply_text(OWN_CONTACT_ONLY.get(lang, OWN_CONTACT_ONLY['am']))
            return

        def _save_phone():
            user.phone_number = normalized
            user.preferred_language = lang
            user.save(update_fields=['phone_number', 'preferred_language'])
            return user

        user = await sync_to_async(_save_phone)()

        # Real visible text (Telegram rejects empty / zero-width-only messages)
        await update.message.reply_text(
            PHONE_RECEIVED.get(lang, PHONE_RECEIVED['am']),
            reply_markup=ReplyKeyboardRemove(),
        )
        await send_open_app(update, user, lang, include_received=False)
    except Exception as e:
        logger.error(f'Error in lottery handle_contact: {e}', exc_info=True)
        if update.message:
            await update.message.reply_text('Please try again in a moment.')


async def configure_bot_profile(application):
    """Set description (pre-/start), short description, and only /start command."""
    bot = application.bot
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f'Could not delete webhook: {e}')

    try:
        info = await bot.get_me()
        logger.info(f'Lottery bot ready @{info.username}')
    except Exception as e:
        logger.error(f'get_me failed: {e}')

    try:
        await bot.set_my_description(BOT_DESCRIPTION)
        await bot.set_my_short_description('Getachew Fikadu Jirata — Car Lottery')
    except Exception as e:
        logger.warning(f'Could not set bot description (needs Bot API support): {e}')

    commands = [BotCommand('start', 'Start / መጀመር / Jalqabi')]
    try:
        await bot.set_my_commands(commands)
        if BotCommandScopeAllPrivateChats:
            await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
    except Exception as e:
        logger.error(f'Failed to set bot commands: {e}')
