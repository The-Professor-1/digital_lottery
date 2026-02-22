"""
Management command to prune old records and free disk space.
Keeps only the last N records (default 20) in Game, Transfer, WithdrawRequest,
DepositRequest, BroadcastMessage. Does NOT touch User or Transaction.

Run every 20 minutes via cron. Safe: never deletes users or transaction history.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


KEEP_LAST = 20  # Keep last N records per table


class Command(BaseCommand):
    help = 'Prune old records (games, transfers, withdraws, deposits, broadcasts) to free space. Keeps last 20. Never touches users or transactions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep',
            type=int,
            default=KEEP_LAST,
            help=f'Number of records to keep per table (default: {KEEP_LAST})',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only report what would be deleted, do not delete',
        )

    def handle(self, *args, **options):
        keep = max(1, options['keep'])
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN: no changes will be made.'))

        from api.models import (
            Game,
            Transfer,
            WithdrawRequest,
            DepositRequest,
            BroadcastMessage,
        )

        total_deleted = 0

        with transaction.atomic():
            # 1) Games: keep last `keep` by created_at, AND keep all non-completed (waiting/active)
            games = Game.objects.all().order_by('-created_at')
            keep_ids = set(games[:keep].values_list('id', flat=True))
            active_ids = set(Game.objects.filter(status__in=['waiting', 'active']).values_list('id', flat=True))
            keep_ids |= active_ids
            to_delete = Game.objects.exclude(pk__in=keep_ids)
            count = to_delete.count()
            if count > 0 and not dry_run:
                to_delete.delete()
            total_deleted += count
            self.stdout.write(f'   Games: would delete {count} (kept {len(keep_ids)} incl. active)' + (' [deleted]' if count and not dry_run else ''))

            # 2) Transfers: keep last `keep`
            transfers = Transfer.objects.all().order_by('-created_at')
            keep_ids = set(transfers[:keep].values_list('id', flat=True))
            to_delete = Transfer.objects.exclude(pk__in=keep_ids)
            count = to_delete.count()
            if count > 0 and not dry_run:
                to_delete.delete()
            total_deleted += count
            self.stdout.write(f'   Transfers: would delete {count}' + (' [deleted]' if count and not dry_run else ''))

            # 3) WithdrawRequest: keep last `keep`
            withdraws = WithdrawRequest.objects.all().order_by('-created_at')
            keep_ids = set(withdraws[:keep].values_list('id', flat=True))
            to_delete = WithdrawRequest.objects.exclude(pk__in=keep_ids)
            count = to_delete.count()
            if count > 0 and not dry_run:
                to_delete.delete()
            total_deleted += count
            self.stdout.write(f'   WithdrawRequests: would delete {count}' + (' [deleted]' if count and not dry_run else ''))

            # 4) DepositRequest: keep last `keep`
            deposits = DepositRequest.objects.all().order_by('-created_at')
            keep_ids = set(deposits[:keep].values_list('id', flat=True))
            to_delete = DepositRequest.objects.exclude(pk__in=keep_ids)
            count = to_delete.count()
            if count > 0 and not dry_run:
                to_delete.delete()
            total_deleted += count
            self.stdout.write(f'   DepositRequests: would delete {count}' + (' [deleted]' if count and not dry_run else ''))

            # 5) BroadcastMessage (sent messages via Telegram): keep last `keep`. Recipients CASCADE.
            broadcasts = BroadcastMessage.objects.all().order_by('-created_at')
            keep_ids = set(broadcasts[:keep].values_list('id', flat=True))
            to_delete = BroadcastMessage.objects.exclude(pk__in=keep_ids)
            count = to_delete.count()
            if count > 0 and not dry_run:
                to_delete.delete()
            total_deleted += count
            self.stdout.write(f'   BroadcastMessages: would delete {count}' + (' [deleted]' if count and not dry_run else ''))

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'\nDry run complete. Total rows that would be removed: {total_deleted}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nPrune complete. Total rows removed: {total_deleted}'))
