"""Phone number normalization utilities"""
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number by removing country code 251 and adding 0 prefix.
    
    Converts phone numbers like:
    - 251909090909 -> 0909090909
    - +251909090909 -> 0909090909
    - 251909090909 -> 0909090909
    
    Args:
        phone: Phone number string (may contain +, spaces, or country code)
        
    Returns:
        Normalized phone number with 0 prefix (without country code)
    """
    if not phone:
        return phone
    
    # Remove whitespace, +, and hyphens
    normalized = phone.strip().replace('+', '').replace(' ', '').replace('-', '')
    
    # If starts with 251 (country code), remove it and add 0
    if normalized.startswith('251') and len(normalized) > 3:
        normalized = '0' + normalized[3:]
    
    return normalized


def find_user_by_phone(phone: str):
    """
    Find user by phone number with backward compatibility.
    Tries multiple phone formats to find the user.
    
    Args:
        phone: Phone number string (can be in any format)
        
    Returns:
        User object or None if not found
    """
    if not phone:
        return None
    
    # Normalize the input phone
    normalized_phone = normalize_phone_number(phone)
    
    # Clean the original phone for comparison
    clean_phone = phone.strip().replace('+', '').replace(' ', '').replace('-', '')
    
    # Try to find user with normalized phone (new format: 0909090909)
    user = User.objects.filter(phone_number=normalized_phone).first()
    if user:
        return user
    
    # Try original format (as entered)
    if clean_phone != normalized_phone:
        user = User.objects.filter(phone_number=clean_phone).first()
        if user:
            return user
    
    # Try old format (with 251: 251909090909)
    if clean_phone.startswith('0') and len(clean_phone) == 10:
        old_format = '251' + clean_phone[1:]
        user = User.objects.filter(phone_number=old_format).first()
        if user:
            return user
    elif not clean_phone.startswith('251') and len(clean_phone) == 9:
        # If it's 9 digits without 0 or 251, try both formats
        old_format = '251' + clean_phone
        user = User.objects.filter(phone_number=old_format).first()
        if user:
            return user
        zero_format = '0' + clean_phone
        user = User.objects.filter(phone_number=zero_format).first()
        if user:
            return user
    
    # Try with + prefix
    if not clean_phone.startswith('+'):
        plus_format = '+' + clean_phone
        user = User.objects.filter(phone_number=plus_format).first()
        if user:
            return user
    
    return None

