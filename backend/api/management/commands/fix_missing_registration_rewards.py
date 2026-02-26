"""
Management command to fix users who didn't receive registration rewards
"""
from django.core.management.base import BaseCommand
from api.models import User, Transaction, GameSettings
from django.db.models import F
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix users who should have received registration rewards but didn\'t'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Fix specific user by ID',
        )
        parser.add_argument(
            '--telegram-id',
            type=int,
            help='Fix specific user by Telegram ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        telegram_id = options.get('telegram_id')
        dry_run = options.get('dry_run', False)

        game_settings = GameSettings.get_settings()
        bid_amount = Decimal(str(game_settings.bid_amount))

        if user_id:
            users = User.objects.filter(id=user_id)
        elif telegram_id:
            users = User.objects.filter(telegram_id=telegram_id)
        else:
            # Find all users with phone numbers but no registration gift transaction
            users = User.objects.filter(
                phone_number__isnull=False
            ).exclude(
                phone_number=''
            ).exclude(
                id__in=Transaction.objects.filter(
                    transaction_type='deposit',
                    description='Registration gift'
                ).values_list('user_id', flat=True)
            )

        if not users.exists():
            self.stdout.write(self.style.SUCCESS('No users found that need fixing.'))
            return

        self.stdout.write(f'Found {users.count()} user(s) to process:')

        for user in users:
            # Check if user already has a registration gift transaction
            has_gift = Transaction.objects.filter(
                user=user,
                transaction_type='deposit',
                description='Registration gift'
            ).exists()

            if has_gift:
                self.stdout.write(
                    self.style.WARNING(
                        f'  User {user.telegram_id} (ID: {user.id}) already has registration gift transaction, skipping.'
                    )
                )
                continue

            self.stdout.write(
                f'  User {user.telegram_id} (ID: {user.id}, Phone: {user.phone_number}): '
                f'Current balance: {user.balance}, Will add: {bid_amount}'
            )

            if not dry_run:
                try:
                    # Registration gift → unwithdrawable_balance
                    User.objects.filter(id=user.id).update(unwithdrawable_balance=F('unwithdrawable_balance') + bid_amount)
                    user.refresh_from_db()

                    # Create transaction record
                    Transaction.objects.create(
                        user=user,
                        transaction_type='deposit',
                        amount=bid_amount,
                        description='Registration gift (manually fixed)'
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'    ✅ Fixed! New balance: {user.balance}'
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'    ❌ Error: {e}')
                    )

        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a dry run. Use without --dry-run to apply changes.'))

