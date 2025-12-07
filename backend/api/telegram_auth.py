"""Telegram Web App initData verification"""
import hmac
import hashlib
import urllib.parse
from django.conf import settings
from django.contrib.auth import get_user_model
from api.phone_utils import normalize_phone_number

User = get_user_model()


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Verify Telegram Web App initData signature
    
    Algorithm from Telegram docs:
    1. Parse init_data string
    2. Extract hash from query string
    3. Create data-check-string from all pairs except hash
    4. Create secret_key = HMAC_SHA256(bot_token, "WebAppData")
    5. Calculate signature = HMAC_SHA256(secret_key, data-check-string)
    6. Compare signature with hash
    """
    try:
        # Parse init_data (can be URL-encoded or plain query string)
        if '?' in init_data:
            init_data = init_data.split('?', 1)[1]
        
        parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)
        
        # Extract hash
        if 'hash' not in parsed or not parsed['hash']:
            return None
        received_hash = parsed['hash'][0]
        
        # Create data-check-string (all pairs except hash, sorted by key)
        data_check_pairs = []
        for key, value_list in parsed.items():
            if key != 'hash' and value_list:
                data_check_pairs.append(f"{key}={value_list[0]}")
        
        data_check_pairs.sort()
        data_check_string = '\n'.join(data_check_pairs)
        
        # Create secret_key
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            return None
        
        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # Calculate signature
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Verify
        if calculated_hash != received_hash:
            return None
        
        # Extract user data
        user_data = {}
        if 'user' in parsed and parsed['user']:
            import json
            try:
                # URL decode the user data if needed
                user_json_str = parsed['user'][0]
                # Try to decode if it's URL encoded
                try:
                    user_json_str = urllib.parse.unquote(user_json_str)
                except:
                    pass
                user_data = json.loads(user_json_str)
            except json.JSONDecodeError:
                return None
        
        # Extract phone number from user_data (phone_number is in the user object if shared)
        phone_number = user_data.get('phone_number') or None
        
        # Also check phone_number parameter (if provided separately in query string)
        if not phone_number:
            phone_number_param = parsed.get('phone_number', [None])[0] if parsed.get('phone_number') else None
            if phone_number_param:
                # URL decode phone number if needed
                try:
                    phone_number = urllib.parse.unquote(phone_number_param)
                except:
                    phone_number = phone_number_param
        
        # Add phone number to user_data if found
        if phone_number and not user_data.get('phone_number'):
            user_data['phone_number'] = phone_number
        
        return {
            'user': user_data,
            'auth_date': parsed.get('auth_date', [None])[0] if parsed.get('auth_date') else None,
            'query_id': parsed.get('query_id', [None])[0] if parsed.get('query_id') else None,
            'phone_number': phone_number,
        }
    except Exception as e:
        print(f"Error verifying init_data: {e}")
        return None


def get_or_create_user_from_telegram(telegram_user_data: dict):
    """Get or create user from Telegram user data"""
    telegram_id = telegram_user_data.get('id')
    if not telegram_id:
        return None
    
    username = telegram_user_data.get('username') or f"user_{telegram_id}"
    first_name = telegram_user_data.get('first_name', '')
    last_name = telegram_user_data.get('last_name', '')
    phone_number = telegram_user_data.get('phone_number', '')
    
    # Normalize phone number (remove 251 country code and add 0)
    normalized_phone = normalize_phone_number(phone_number) if phone_number else None
    
    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'phone_number': normalized_phone,
        }
    )
    
    # Update phone number if it's provided and user doesn't have one
    if normalized_phone and not user.phone_number:
        user.phone_number = normalized_phone
        user.save()
    
    return user

