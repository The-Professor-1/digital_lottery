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


def _place_text(lang, place):
    raw = str(place or '').strip()
    normalized = raw.lower()
    if normalized in ('1', '1st', 'first'):
        return '1st' if lang == 'en' else '1ኛ'
    if normalized in ('2', '2nd', 'second'):
        return '2nd' if lang == 'en' else '2ኛ'
    if normalized in ('3', '3rd', 'third'):
        return '3rd' if lang == 'en' else '3ኛ'
    return raw


def _winner_lines(winners):
    lines = []
    for index, winner in enumerate(winners or [], 1):
        order = winner.get('order') or index
        prize = winner.get('prize') or 'Prize'
        number = _number(winner.get('number'))
        # Winners are identified by phone number, never by name, so a wrong
        # name/phone pairing cannot create a false announcement.
        phone = winner.get('phone') or '—'
        line = f'{order}. {prize} — #{number} — {phone}'.rstrip(' —')
        lines.append(line)
    return lines


def winner_announcement_text(user, lottery_label, place_label, number, prize_name, other_winners=None, message=''):
    lang = user_language(user)
    place_text = _place_text(lang, place_label)
    if lang == 'en':
        title = f'🏆 You Won {place_text} Prize!' if place_text else '🏆 You Won Prize!'
        lines = [
            title,
            '',
            f'Lottery: {lottery_label or "—"}',
            f'Winning ticket: #{_number(number)}',
            f'Prize: {prize_name or "—"}',
        ]
        if other_winners:
            lines.extend(['', 'Other winners:', *_winner_lines(other_winners)])
    else:
        title = f'🏆 {place_text} ዕጣ ደርሶታል!' if place_text else '🏆 ዕጣ ደርሶታል!'
        lines = [
            title,
            '',
            f'ሎተሪ: {lottery_label or "—"}',
            f'አሸናፊ ቲኬት: #{_number(number)}',
            f'ዕጣ: {prize_name or "—"}',
        ]
        if other_winners:
            lines.extend(['', 'ሌሎች አሸናፊዎች:', *_winner_lines(other_winners)])
    text = '\n'.join(lines)
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



def lottery_results_text(user, lottery_label, winners, message=''):
    """Generic results announcement for every participant of a lottery."""
    lang = user_language(user)
    if lang == 'en':
        title = '🎉 Lottery results are out!'
        lottery_label_text = f'Lottery: {lottery_label or "—"}'
    else:
        title = '🎉 የዕጣ ውጤት ወጥቷል!'
        lottery_label_text = f'ሎተሪ: {lottery_label or "—"}'
    lines = [title, '', lottery_label_text]
    lines.extend(_winner_lines(winners))
    text = '\n'.join(lines)
    if message:
        text += f'\n\n{message}'
    return text
