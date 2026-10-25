"""Language-aware Telegram notification text for lottery users.

Only Amharic and English are exposed by the mini-app. Unknown/legacy language
values fall back to Amharic so existing users keep receiving readable messages.
"""


def user_language(user):
    lang = (getattr(user, 'preferred_language', '') or '').strip().lower()
    return lang if lang in ('am', 'en') else 'am'


def _number(value):
    try:
        return str(int(value)).zfill(3)
    except (TypeError, ValueError):
        return str(value or '')


def _amount(value):
    try:
        return f'{int(value or 0):,}'
    except (TypeError, ValueError):
        return '0'


def _place_label(lang, place):
    labels = {
        'am': {1: '1ኛ እጣ', 2: '2ኛ እጣ', 3: '3ኛ እጣ'},
        'en': {1: '1st Prize', 2: '2nd Prize', 3: '3rd Prize'},
    }
    try:
        return labels[lang].get(int(place), '')
    except (TypeError, ValueError):
        return ''


def receipt_received_text(user, numbers, item_name='', round_name=''):
    lang = user_language(user)
    if lang == 'en':
        title = '📥 Receipt received.'
        hint = 'Waiting for admin approval.'
        labels = ('Lottery', 'Round', 'Tickets')
    else:
        title = '📥 ደረሰኝ ተቀብለናል።'
        hint = 'የአስተዳዳሪ ማረጋገጫ በመጠበቅ ላይ።'
        labels = ('ሎተሪ', 'ዙር', 'ቲኬቶች')

    details = []
    if item_name:
        details.append(f'{labels[0]}: {item_name}')
    if round_name:
        details.append(f'{labels[1]}: {round_name}')
    if numbers:
        details.append(f'{labels[2]}: {numbers}')
    return '\n\n'.join([title, '\n'.join(details), hint]).strip()


def receipt_verified_text(user, numbers):
    lang = user_language(user)
    if lang == 'en':
        return f'✅ Your payment has been verified!\n\nTicket numbers: {numbers}'
    return f'✅ ክፍያው ልክ መሆኑ ተረጋግጧል!\n\nየእጣ ቁጥርዎች: {numbers}'


def receipt_rejected_text(user, note=''):
    lang = user_language(user)
    if lang == 'en':
        text = '❌ Your payment request was rejected.\nPlease try again with a valid receipt.'
        if note:
            text += f'\n\nNote: {note}'
        return text
    text = '❌ የክፍያ ጥያቄዎ ተቀባይነት አላገኘም።\nእባክዎ እንደገና በትክክል ይሞክሩ።'
    if note:
        text += f'\n\nማስታወሻ: {note}'
    return text


def winner_dm_text(user, place, number, amount):
    lang = user_language(user)
    place_label = _place_label(lang, place)
    if lang == 'en':
        return (
            '🏆 Congratulations!\n\n'
            f'You won the {place_label}!\n'
            f'Winning number: {_number(number)}\n'
            f'Prize: {_amount(amount)} Birr'
        )
    return (
        '🏆 እንኳን ደስ አለዎት!\n\n'
        f'{place_label} አሸንፈዋል!\n'
        f'አሸናፊ ቁጥር: {_number(number)}\n'
        f'ገንዘብ: {_amount(amount)} ብር'
    )


def winner_announcement_text(user, lottery_label, name, phone, number, prize_name, message=''):
    lang = user_language(user)
    if lang == 'en':
        text = (
            '🏆 Winner announced!\n\n'
            f'Lottery: {lottery_label}\n'
            f'Name: {name or "—"}\n'
            f'Phone: {phone or "—"}\n'
            f'Winning ticket: #{_number(number)}\n'
            f'Prize: {prize_name or "—"}'
        )
        if message:
            text += f'\n\n{message}'
        return text
    text = (
        '🏆 አሸናፊ ተገለጸ!\n\n'
        f'ሎተሪ: {lottery_label}\n'
        f'ስም: {name or "—"}\n'
        f'ስልክ: {phone or "—"}\n'
        f'አሸናፊ ቲኬት: #{_number(number)}\n'
        f'ዕጣ: {prize_name or "—"}'
    )
    if message:
        text += f'\n\n{message}'
    return text


def legacy_announcement_text(user, number, is_holder=False, message=''):
    lang = user_language(user)
    if lang == 'en':
        title = '🎉 Winners announced!'
        body = f'Winning number: {_number(number)}'
        prefix = '🏆 Congratulations!\n\n' if is_holder else ''
        text = f'{prefix}{title}\n\n{body}'
    else:
        title = '🎉 አሸናፊዎች ታውቀዋል!'
        body = f'አሸናፊ ቁጥር: {_number(number)}'
        prefix = '🏆 እንኳን ደስ አለዎት!\n\n' if is_holder else ''
        text = f'{prefix}{title}\n\n{body}'
    if message:
        text += f'\n\n{message}'
    return text
