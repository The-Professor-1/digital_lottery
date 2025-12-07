"""
Management command to list all superuser accounts
Usage: python manage.py list_superusers
"""
from django.core.management.base import BaseCommand
from api.models import User


class Command(BaseCommand):
    help = 'List all superuser accounts with their usernames and emails'

    def handle(self, *args, **options):
        superusers = User.objects.filter(is_superuser=True)
        
        if not superusers.exists():
            self.stdout.write(
                self.style.WARNING('⚠️  No superuser accounts found!')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Found {superusers.count()} superuser account(s):\n')
        )
        
        for user in superusers:
            self.stdout.write(f"  Username: {self.style.SUCCESS(user.username)}")
            if user.email:
                self.stdout.write(f"  Email: {user.email}")
            self.stdout.write(f"  Staff: {'Yes' if user.is_staff else 'No'}")
            self.stdout.write(f"  Active: {'Yes' if user.is_active else 'No'}")
            self.stdout.write('-' * 50)
        
        self.stdout.write('')

