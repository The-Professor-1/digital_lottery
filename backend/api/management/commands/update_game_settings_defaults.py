from django.core.management.base import BaseCommand
from api.models import GameSettings


class Command(BaseCommand):
    help = 'Update existing GameSettings to use new defaults (20s timer, 100 cards)'

    def handle(self, *args, **options):
        try:
            settings, created = GameSettings.objects.get_or_create(pk=1)
            
            # Update to new defaults if they're still at old values
            updated = False
            if settings.card_selection_timer == 30:
                settings.card_selection_timer = 20
                updated = True
                self.stdout.write(self.style.SUCCESS(f'Updated card_selection_timer from 30 to 20'))
            
            if settings.total_cards == 90:
                settings.total_cards = 100
                updated = True
                self.stdout.write(self.style.SUCCESS(f'Updated total_cards from 90 to 100'))
            
            if updated:
                settings.save()
                self.stdout.write(self.style.SUCCESS('Successfully updated GameSettings'))
            else:
                self.stdout.write(self.style.SUCCESS('GameSettings already have correct values'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error updating GameSettings: {e}'))

