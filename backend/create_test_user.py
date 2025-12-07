"""
Create a test user for development
Run: python create_test_user.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from api.models import User

# Create or get test user
test_user, created = User.objects.get_or_create(
    username='test_user',
    defaults={
        'telegram_id': 123456789,
        'balance': 100.00,
        'is_active': True
    }
)

if created:
    test_user.set_password('test123')
    test_user.save()
    print(f"✅ Test user created!")
else:
    print(f"✅ Test user already exists!")
    
print(f"   Username: {test_user.username}")
print(f"   ID: {test_user.id}")
print(f"   Balance: {test_user.balance} ETB")
print(f"   Password: test123")

