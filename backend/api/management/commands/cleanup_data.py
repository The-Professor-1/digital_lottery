"""
Management command to clean up old game and user records for fresh start
Usage: python manage.py cleanup_data
"""
from django.core.management.base import BaseCommand
from api.models import Game, GameCard, CalledNumber, User, Transaction, Deposit, DepositRequest, WithdrawRequest


class Command(BaseCommand):
    help = 'Remove old game and user records for fresh start'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion (required to actually delete)',
        )
        parser.add_argument(
            '--keep-users',
            action='store_true',
            help='Keep user records, only delete games',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  This will delete all game records and optionally user records!\n'
                    'Run with --confirm to proceed.\n'
                    'Use --keep-users to keep user records.'
                )
            )
            return

        keep_users = options['keep_users']
        
        # Count records before deletion
        game_count = Game.objects.count()
        gamecard_count = GameCard.objects.count()
        called_number_count = CalledNumber.objects.count()
        transaction_count = Transaction.objects.count()
        deposit_count = Deposit.objects.count()
        deposit_request_count = DepositRequest.objects.count()
        withdraw_request_count = WithdrawRequest.objects.count()
        user_count = User.objects.count() if not keep_users else 0

        self.stdout.write(f'📊 Current records:')
        self.stdout.write(f'   Games: {game_count}')
        self.stdout.write(f'   Game Cards: {gamecard_count}')
        self.stdout.write(f'   Called Numbers: {called_number_count}')
        self.stdout.write(f'   Transactions: {transaction_count}')
        self.stdout.write(f'   Deposits: {deposit_count}')
        self.stdout.write(f'   Deposit Requests: {deposit_request_count}')
        self.stdout.write(f'   Withdraw Requests: {withdraw_request_count}')
        if not keep_users:
            self.stdout.write(f'   Users: {user_count}')

        # Delete in correct order (respecting foreign keys)
        self.stdout.write('\n🗑️  Deleting records...')
        
        # Delete game-related records first
        CalledNumber.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {called_number_count} called numbers'))
        
        GameCard.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {gamecard_count} game cards'))
        
        Game.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {game_count} games'))
        
        # Delete transaction records
        Transaction.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {transaction_count} transactions'))
        
        # Delete deposit/withdraw requests
        DepositRequest.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {deposit_request_count} deposit requests'))
        
        WithdrawRequest.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {withdraw_request_count} withdraw requests'))
        
        Deposit.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {deposit_count} deposits'))
        
        # Delete users if requested
        if not keep_users:
            User.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {user_count} users'))
        else:
            # Reset user balances to 0
            User.objects.all().update(unwithdrawable_balance=0, withdrawable_balance=0)
            self.stdout.write(self.style.SUCCESS(f'   ✓ Reset all user balances to 0'))

        self.stdout.write(self.style.SUCCESS('\n✅ Cleanup complete!'))
        self.stdout.write('   Database is now ready for fresh start.')

