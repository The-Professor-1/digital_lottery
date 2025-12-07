"""
Management command to create a superuser non-interactively
Usage: python manage.py create_superuser --username admin --email admin@example.com --password mypassword
"""
from django.core.management.base import BaseCommand
from api.models import User


class Command(BaseCommand):
    help = 'Create a superuser account non-interactively'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True, help='Username for the superuser')
        parser.add_argument('--email', type=str, default='', help='Email for the superuser')
        parser.add_argument('--password', type=str, required=True, help='Password for the superuser')
        parser.add_argument('--no-input', action='store_true', help='Run non-interactively')

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.ERROR(f'❌ User with username "{username}" already exists!')
            )
            return
        
        # Create superuser
        try:
            user = User.objects.create_user(
                username=username,
                email=email if email else None,
                password=password,
                is_superuser=True,
                is_staff=True,
                is_active=True
            )
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Superuser created successfully!\n')
            )
            self.stdout.write(f'  Username: {self.style.SUCCESS(username)}')
            if email:
                self.stdout.write(f'  Email: {email}')
            self.stdout.write(f'  Password: {"*" * len(password)}')
            self.stdout.write('')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error creating superuser: {str(e)}')
            )

