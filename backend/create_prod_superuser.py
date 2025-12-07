"""
Temporary script to create superuser on production
This will be executed via fly ssh console
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from api.models import User

# Create superuser
username = 'professor'
email = 'maymerlibe@gmail.com'
password = 'Pro@0952Bingo'

# Check if user already exists
if User.objects.filter(username=username).exists():
    user = User.objects.get(username=username)
    # Always update to ensure superuser status and correct password
    user.is_superuser = True
    user.is_staff = True
    user.is_active = True
    user.email = email
    user.set_password(password)
    user.save()
    print(f'✅ User "{username}" updated to superuser with new password!')
else:
    # Create new superuser
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_superuser=True,
        is_staff=True,
        is_active=True
    )
    print(f'✅ Superuser created successfully!')
    print(f'   Username: {user.username}')
    print(f'   Email: {user.email}')

