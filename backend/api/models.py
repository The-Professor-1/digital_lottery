from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import json
import os

class User(AbstractUser):
    """Custom User model for Telegram users"""
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    preferred_language = models.CharField(
        max_length=5,
        default='am',
        blank=True,
        help_text="User preferred language: am, en, om",
    )
    # Two-balance system: unwithdrawable (bonus/play-only), withdrawable (after deposit >= min_withdraw)
    unwithdrawable_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], help_text='Balance for gameplay only (bonus, registration reward, wins before deposit)')
    withdrawable_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], help_text='Balance that can be withdrawn (deposits + wins after deposit >= min)')
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals', help_text='User who referred this user')
    referral_reward_given = models.BooleanField(default=False, help_text='Whether referral reward was already given for THIS user\'s registration (prevents duplicate rewards if user re-registers)')
    withdrawal_approved = models.BooleanField(default=False, help_text='True when user has deposited at least 50 BR and played at least 5 games (allows withdrawal)')
    # Cached totals (updated on game/deposit/withdraw; used when detail records are pruned)
    total_games_played = models.PositiveIntegerField(default=0, help_text='Total games user has played (survives prune)')
    total_wins = models.PositiveIntegerField(default=0, help_text='Total games user has won (survives prune)')
    free_play_allowed = models.BooleanField(default=True, help_text='True=fair play. False=restricted call-order filtering for anti-abuse.')
    first_win = models.BooleanField(default=False, help_text='True if user won on their first played game.')
    number_of_deposits = models.PositiveIntegerField(default=0, help_text='Approved deposit count used for anti-abuse trust transitions.')
    total_deposits_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='Sum of all deposits (survives prune)')
    total_withdrawals_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='Sum of all withdrawals (survives prune)')
    last_withdrawal_approved_at = models.DateTimeField(null=True, blank=True, help_text='When the user\'s last withdrawal was approved; 24h cooldown for next request starts here')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['telegram_id'], name='user_telegram_id_idx'),
            models.Index(fields=['referred_by'], name='user_referred_by_idx'),
            models.Index(fields=['created_at'], name='user_created_at_idx'),
        ]

    @property
    def balance(self):
        """Total effective balance (unwithdrawable + withdrawable) for display/checks."""
        from decimal import Decimal
        u = getattr(self, 'unwithdrawable_balance', None) or Decimal('0')
        w = getattr(self, 'withdrawable_balance', None) or Decimal('0')
        return Decimal(str(u)) + Decimal(str(w))

    def has_withdrawable_active(self):
        """True if user has deposited at least 10 (min to earn withdrawable wins). New wins/refunds go to withdrawable_balance.
        Uses total_deposits_amount; every path that credits a deposit must call record_deposit() so this is correct.
        Withdrawal itself uses min_withdraw from GameSettings (independent logic)."""
        from decimal import Decimal
        min_deposit_for_wins = Decimal('10')  # User has right to win and claim by depositing at least bid amount (10)
        total = getattr(self, 'total_deposits_amount', None) or Decimal('0')
        return (total or Decimal('0')) >= min_deposit_for_wins

    def deduct_bid(self, amount):
        """Deduct from unwithdrawable_balance first, then withdrawable_balance. Caller must ensure total balance >= amount."""
        from decimal import Decimal
        amt = Decimal(str(amount))
        self.refresh_from_db()
        u = Decimal(str(self.unwithdrawable_balance or 0))
        w = Decimal(str(self.withdrawable_balance or 0))
        if u >= amt:
            self.unwithdrawable_balance = u - amt
            self.save(update_fields=['unwithdrawable_balance'])
            return
        rem = amt - u
        self.unwithdrawable_balance = Decimal('0')
        self.withdrawable_balance = w - rem
        self.save(update_fields=['unwithdrawable_balance', 'withdrawable_balance'])

    def credit_bid_refund(self, from_unwithdrawable, from_withdrawable):
        """Restore amounts to the same buckets used by deduct_bid (inverse split). Caller must lock row if needed."""
        from decimal import Decimal
        u_amt = Decimal(str(from_unwithdrawable or 0))
        w_amt = Decimal(str(from_withdrawable or 0))
        if u_amt < 0 or w_amt < 0:
            raise ValueError('Refund split cannot be negative')
        self.refresh_from_db()
        u = Decimal(str(self.unwithdrawable_balance or 0))
        w = Decimal(str(self.withdrawable_balance or 0))
        self.unwithdrawable_balance = u + u_amt
        self.withdrawable_balance = w + w_amt
        self.save(update_fields=['unwithdrawable_balance', 'withdrawable_balance'])

    def __str__(self):
        return f"{self.username} ({self.telegram_id})"


class Game(models.Model):
    """Bingo Game model"""
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    derash_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bet_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    current_call_count = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_games')
    winners = models.ManyToManyField(User, blank=True, related_name='shared_wins', help_text="All winners (for split derash)")
    fake_win_preference_snapshot = models.PositiveSmallIntegerField(default=0, null=True, blank=True, help_text='Fake win preference level at game start (0/1/2) for win stats.')
    spectator_count = models.PositiveIntegerField(
        default=0,
        help_text='Reserved for future use (not updated by gameplay currently).',
    )
    avoid_list_numbers = models.JSONField(default=list, blank=True, help_text='Snapshot of anti-abuse avoid-list numbers for this game (when prepared).')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'games'
        ordering = ['-created_at']

    def __str__(self):
        return f"Game {self.id} - {self.status}"

    @property
    def total_players(self):
        """Count both real and fake players"""
        real_count = self.gamecards.count()
        try:
            from .fake_user_manager import get_fake_user_count_for_game
            fake_count = get_fake_user_count_for_game(self)
        except:
            fake_count = 0
        return real_count + fake_count

    def recalculate_derash(self):
        """Recalculate derash_amount from actual cards to ensure accuracy (includes fake users)
        Also ensures consistency with total_players property
        """
        from decimal import Decimal
        from .models import GameSettings
        
        # Get settings for bid_amount and percentage_cut
        settings = GameSettings.get_settings()
        bid_amount = Decimal(str(settings.bid_amount))
        percentage_cut = Decimal(str(settings.percentage_cut))
        
        # Count real users who have cards (each user pays once per game)
        unique_users = self.gamecards.values_list('user_id', flat=True).distinct()
        real_player_count = len(list(unique_users))
        
        # Count fake users
        try:
            from .fake_user_manager import get_fake_user_count_for_game
            fake_player_count = get_fake_user_count_for_game(self)
        except:
            fake_player_count = 0
        
        # Total players (real + fake) - use same logic as total_players property
        total_player_count = real_player_count + fake_player_count
        
        # Calculate derash: (total_players * bid_amount) - (total_players * bid_amount * percentage_cut / 100)
        # This is: total_collected - percentage_cut_amount
        total_collected = Decimal(str(total_player_count)) * bid_amount
        percentage_amount = (total_collected * percentage_cut) / Decimal('100')
        self.derash_amount = total_collected - percentage_amount
        
        self.save(update_fields=['derash_amount'])
        
        # CONSISTENCY CHECK: Verify that derash matches player count
        # Recalculate to ensure they're in sync
        expected_derash = (Decimal(str(total_player_count)) * bid_amount) - ((Decimal(str(total_player_count)) * bid_amount * percentage_cut) / Decimal('100'))
        if abs(self.derash_amount - expected_derash) > Decimal('0.01'):
            # If mismatch, fix it
            print(f"WARNING: Derash mismatch detected. Expected: {expected_derash}, Got: {self.derash_amount}. Fixing...")
            self.derash_amount = expected_derash
            self.save(update_fields=['derash_amount'])
        
        # Invalidate cache
        from django.core.cache import cache
        if cache:
            cache.delete('game:current')

    @property
    def total_derash(self):
        """Calculate total derash after percentage cut
        Formula: (total_players * bid_amount) - percentage_cut
        Note: derash_amount already stores the total collected amount (includes fake users)
        """
        from decimal import Decimal
        # derash_amount is already calculated by recalculate_derash() and includes fake users
        # Just return derash_amount directly - it's already the correct value after percentage cut
        return self.derash_amount if self.derash_amount > 0 else Decimal('0')


class GameCard(models.Model):
    """Bingo Card model - represents a card purchased by a user for a game"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='gamecards')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamecards')
    card_number = models.IntegerField()  # Card identifier (1-90 or custom range)
    card_layout = models.JSONField(default=dict)  # 5x5 grid layout with numbers
    selected_numbers = models.JSONField(default=list)  # Numbers user has marked
    is_winner = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when bingo was claimed")
    # Track mode usage - JSON field storing timestamps when user switched modes
    mode_history = models.JSONField(default=list, help_text="List of mode changes: [{'mode': 'automatic', 'timestamp': '...'}, ...]")

    class Meta:
        db_table = 'game_cards'
        unique_together = ['game', 'user']  # One card per user per game
        indexes = [
            models.Index(fields=['game', 'user']),
            models.Index(fields=['game', 'card_number']),
        ]

    def __str__(self):
        return f"Card {self.card_number} - Game {self.game.id} - {self.user.username}"

    def mark_number(self, number):
        """Mark a number as selected on this card"""
        if number not in self.selected_numbers:
            self.selected_numbers.append(number)
            self.save(update_fields=['selected_numbers'])

    def check_win(self, called_numbers):
        """Check if this card has a winning pattern"""
        # Check if all marked numbers are in called numbers
        if not all(num in called_numbers for num in self.selected_numbers):
            return False

        # Check for winning patterns
        layout = self.card_layout
        if not layout:
            return False

        # Check horizontal lines
        for row in layout:
            if all(cell.get('marked', False) for cell in row):
                return True

        # Check vertical lines
        for col_idx in range(5):
            if all(layout[row_idx][col_idx].get('marked', False) for row_idx in range(5)):
                return True

        # Check diagonal (top-left to bottom-right)
        if all(layout[i][i].get('marked', False) for i in range(5)):
            return True

        # Check diagonal (top-right to bottom-left)
        if all(layout[i][4-i].get('marked', False) for i in range(5)):
            return True

        # Check full card
        if all(cell.get('marked', False) for row in layout for cell in row):
            return True

        return False


class CalledNumber(models.Model):
    """Numbers called during a game"""
    LETTER_CHOICES = [
        ('B', 'B (1-15)'),
        ('I', 'I (16-30)'),
        ('N', 'N (31-45)'),
        ('G', 'G (46-60)'),
        ('O', 'O (61-75)'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='called_numbers')
    number = models.IntegerField()
    letter = models.CharField(max_length=1, choices=LETTER_CHOICES)
    called_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'called_numbers'
        unique_together = ['game', 'number']  # Each number can only be called once per game
        ordering = ['called_at']
        indexes = [
            models.Index(fields=['game', 'called_at']),
        ]

    def __str__(self):
        return f"{self.letter}-{self.number}"

    @staticmethod
    def get_letter_for_number(number):
        """Get the letter (B/I/N/G/O) for a given number"""
        if 1 <= number <= 15:
            return 'B'
        elif 16 <= number <= 30:
            return 'I'
        elif 31 <= number <= 45:
            return 'N'
        elif 46 <= number <= 60:
            return 'G'
        elif 61 <= number <= 75:
            return 'O'
        return None


class Deposit(models.Model):
    """Deposit requests with manual verification"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposits')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    bank_text = models.TextField()  # Text pasted by user from bank
    admin_text = models.TextField(null=True, blank=True)  # Text pasted by admin
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deposits'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Deposit {self.id} - {self.user.username} - {self.amount} - {self.status}"

    def normalize_text(self, text):
        """Normalize text for comparison"""
        import re
        # Remove spaces, convert to lowercase, remove special characters
        text = re.sub(r'[^a-z0-9]', '', text.lower())
        return text

    def match_texts(self):
        """Check if bank_text and admin_text match"""
        if not self.admin_text:
            return False
        normalized_bank = self.normalize_text(self.bank_text)
        normalized_admin = self.normalize_text(self.admin_text)
        return normalized_bank == normalized_admin


class Transaction(models.Model):
    """Transaction history"""
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdraw', 'Withdrawal'),
        ('bet', 'Bet'),
        ('win', 'Win'),
        ('transfer', 'Transfer'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    deposit = models.ForeignKey(Deposit, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    transfer = models.ForeignKey('Transfer', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    description = models.TextField(null=True, blank=True)
    # For bet transactions: amounts taken from each bucket (mirrors deduct_bid); used for correct unselect refund
    bet_from_unwithdrawable = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Portion of this bet deducted from unwithdrawable_balance',
    )
    bet_from_withdrawable = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Portion of this bet deducted from withdrawable_balance',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.user.username} - {self.amount}"


class CardUnselectRefund(models.Model):
    """One row per user per game after a successful unselect; prevents double-refund credits."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='card_unselect_refunds')
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='card_unselect_refunds')
    card_number = models.PositiveIntegerField(help_text='Last unselected card (audit)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'card_unselect_refunds'
        constraints = [
            models.UniqueConstraint(fields=['user', 'game'], name='uniq_card_unselect_refund_user_game'),
        ]
        indexes = [
            models.Index(fields=['user', 'game']),
        ]

    def __str__(self):
        return f"unselect refund marker u={self.user_id} g={self.game_id} card={self.card_number}"


class GameSettings(models.Model):
    """Game configuration settings - Singleton pattern"""
    # Game timing settings
    time_between_calls = models.IntegerField(default=3, help_text="Seconds between each number call")
    card_selection_timer = models.IntegerField(default=20, help_text="Seconds for card selection window")
    
    # Game financial settings
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Default bet amount per card")
    percentage_cut = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Percentage to cut from total derash (e.g., 10.00 for 10%)")
    min_withdraw = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, help_text="Minimum withdrawal amount")
    max_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Max withdrawal per 24h (from approval time). Null/0 = no limit.")
    give_register_reward = models.BooleanField(default=True, help_text="If True, new users get bid_amount as registration bonus (unwithdrawable). If False, no bonus, balance stays 0.")
    deposit_bonus_percent = models.PositiveSmallIntegerField(default=0, help_text="Percent of deposit to add to unwithdrawable (e.g. 10 = 10%% of deposit also added as bonus). 0 = no bonus.")
    
    # Card settings
    total_cards = models.IntegerField(default=100, help_text="Total number of cards available")
    
    # Game mode settings
    automatic_mode_enabled = models.BooleanField(default=False, help_text="If enabled, automatic mode will be available for all players")
    
    # Fake user system settings
    allow_system_account = models.BooleanField(default=True, help_text="Enable fake system accounts to join games")
    free_play = models.BooleanField(default=False, help_text="Allow real users to win even when fake accounts are active (only available if allow_system_account is on)")
    system_accounts_min = models.IntegerField(default=15, help_text="Minimum number of system accounts to join each game")
    system_accounts_max = models.IntegerField(default=100, help_text="Maximum number of system accounts to join each game")
    
    # Winning patterns (stored as JSON list of enabled patterns)
    winning_patterns = models.JSONField(
        default=list,
        help_text="List of enabled winning patterns: ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']"
    )
    
    # Deposit account information (stored as JSON)
    deposit_accounts = models.JSONField(
        default=dict,
        help_text="Bank account details: {'BOA': {'name': '...', 'number': '...'}, 'CBE': {...}, 'Telebirr': {...}}"
    )
    
    # Telebirr receipt verification API (optional - when set, Telebirr deposits are auto-verified)
    telebirr_verify_api_key = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="API key for verifyapi.leulzenebe.pro to verify Telebirr receipts"
    )
    # CBE verification from foreign servers (e.g. AWS): enable to ask API to use fallback proxy
    cbe_use_fallback_proxy = models.BooleanField(
        default=False,
        help_text="If server is outside Ethiopia: ask verify API to use fallback proxy for CBE (skipPrimaryVerification)"
    )
    # Support phone number
    support_phone = models.CharField(
        max_length=20,
        default='0952838412',
        help_text="Support phone number displayed in bot support command"
    )
    # Instruction text for /instruction command (if set, shown in Telegram bot; else bot uses default)
    instruction_text = models.TextField(
        blank=True,
        default='',
        help_text="Text shown when user sends /instruction in the bot. Leave empty to use default text from bot."
    )
    # Bot: max new /start (new user) registrations per calendar day; 0 = no limit
    daily_new_start_limit = models.PositiveIntegerField(
        default=100,
        help_text="Max new /start (new user) registrations per day. Set to 0 for no limit. Set to 1 to test (only one new user per day)."
    )
    # Bot: disable menu commands (when enabled, bot does not respond to these commands)
    disable_bot_start = models.BooleanField(
        default=False,
        help_text="When enabled, the Telegram bot will not respond to /start (no welcome, no menu)."
    )
    disable_bot_register = models.BooleanField(
        default=False,
        help_text="When enabled, the bot will not respond to /register or contact share (no new registrations)."
    )
    disable_bot_transfer = models.BooleanField(
        default=False,
        help_text="When enabled, the bot will not process transfer (button, /transfer, or cached menu)."
    )
    disable_bot_deposit = models.BooleanField(
        default=False,
        help_text="When enabled, the bot will not process deposit (button or /deposit)."
    )
    disable_bot_withdraw = models.BooleanField(
        default=False,
        help_text="When enabled, the bot will not process withdraw (button or /withdraw)."
    )
    # Fake win preference (only when allow_system_account=True and free_play=False). 0=current behavior (no extra work). 1=prefer numbers that give fake bingo when safe. 2=stronger: prefer numbers that help multiple fakes; when no safe number, pick number that maximizes fake wins.
    fake_win_preference = models.PositiveSmallIntegerField(
        default=0,
        help_text="0=default (current). 1=prefer fake wins when safe. 2=stronger preference (multi-fake, fallback). Only applies when system accounts on and not free play."
    )
    anti_abuse_filter_enabled = models.BooleanField(
        default=False,
        help_text="Enable anti-abuse filtering for users with free_play_allowed=False (avoid-list delayed numbers)."
    )
    default_free_play_for_new_users = models.BooleanField(
        default=True,
        help_text="If True, first-time phone registration sets user free_play_allowed=True. If False, sets False.",
    )
    allow_free_play_after_real_win = models.BooleanField(
        default=True,
        help_text="If True, real wins do not change free_play_allowed (first_win is still recorded). If False, every real win sets free_play_allowed=False.",
    )
    # When True, the next started game arms test co-win mode (1 real + 1 fake, predetermined call order, fake auto-claims on last number).
    test_co_win_next_game = models.BooleanField(
        default=False,
        help_text="If True, the next game that starts will run in test co-win mode (admin QA: same last call, banner shows both, payout real-only)."
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'game_settings'
        verbose_name = 'Game Settings'
        verbose_name_plural = 'Game Settings'
    
    def __str__(self):
        return "Game Settings"
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super().save(*args, **kwargs)
        # Invalidate cache when settings are saved
        from django.core.cache import cache
        cache.delete('game_settings')
    
    @classmethod
    def get_settings(cls, game_id=None):
        """
        Get or create the singleton settings instance
        If game_id is provided and game is active, use cached settings from game start
        This prevents mid-game setting changes from affecting active games
        """
        from django.core.cache import cache
        
        # If game_id provided, check for cached game-specific settings (set at game start)
        if game_id:
            game_settings_cache_key = f'game:{game_id}:settings'
            cached_game_settings = cache.get(game_settings_cache_key)
            if cached_game_settings is not None:
                # Return a settings-like object with cached values
                # This prevents mid-game changes
                class CachedSettings:
                    def __init__(self, data):
                        for key, value in data.items():
                            setattr(self, key, value)
                        # Keep reference to original for methods that need it
                        self._original = None
                        # Ensure new fields exist with defaults (for backward compatibility)
                        if not hasattr(self, 'system_accounts_min'):
                            self.system_accounts_min = 15
                        if not hasattr(self, 'system_accounts_max'):
                            self.system_accounts_max = 30
                        if not hasattr(self, 'winning_patterns'):
                            self.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
                        if not hasattr(self, 'fake_win_preference'):
                            self.fake_win_preference = 0
                        if not hasattr(self, 'test_co_win_mode'):
                            self.test_co_win_mode = False
                        if not hasattr(self, 'anti_abuse_filter_enabled'):
                            self.anti_abuse_filter_enabled = False

                cached_obj = CachedSettings(cached_game_settings)
                # Also fetch original for any methods that might be called
                cached_obj._original = cls.get_settings()
                return cached_obj
        
        # Try to get from general cache first
        cache_key = 'game_settings'
        cached_settings = cache.get(cache_key)
        if cached_settings is not None:
            return cached_settings
        
        # Cache miss - fetch from database
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            # Initialize default deposit accounts
            obj.deposit_accounts = {
                'BOA': {'name': '', 'number': ''},
                'CBE': {'name': '', 'number': ''},
                'Telebirr': {'name': '', 'number': ''}
            }
            # Initialize default winning patterns (all enabled by default)
            if not obj.winning_patterns:
                obj.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
            obj.save()
        
        # Ensure new fields exist with defaults (for backward compatibility if migration not run)
        try:
            if not hasattr(obj, 'system_accounts_min') or getattr(obj, 'system_accounts_min', None) is None:
                obj.system_accounts_min = 15
            if not hasattr(obj, 'system_accounts_max') or getattr(obj, 'system_accounts_max', None) is None:
                obj.system_accounts_max = 30
            if not hasattr(obj, 'winning_patterns') or not obj.winning_patterns:
                obj.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
            if not hasattr(obj, 'anti_abuse_filter_enabled'):
                obj.anti_abuse_filter_enabled = False
        except (AttributeError, Exception):
            # If accessing fields fails (migration not run), set defaults on object
            try:
                obj.system_accounts_min = 15
                obj.system_accounts_max = 30
                obj.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
                obj.anti_abuse_filter_enabled = False
            except:
                pass  # If we can't set attributes, continue anyway
        
        # Cache for 60 seconds (settings don't change often)
        cache.set(cache_key, obj, 60)
        
        return obj


class DepositRequest(models.Model):
    """Enhanced deposit requests with platform and account info"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PLATFORM_CHOICES = [
        ('BOA', 'Bank of Abyssinia'),
        ('CBE', 'Commercial Bank of Ethiopia'),
        ('Telebirr', 'Telebirr'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    deposit_text = models.TextField(help_text="Text or screenshot description from user")
    photo_file_id = models.CharField(max_length=255, null=True, blank=True, help_text="Telegram file_id for screenshot")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_deposits')
    transaction_reference = models.CharField(max_length=128, null=True, blank=True, help_text="CBE/Telebirr transaction id when manually approved (prevents reuse)")

    class Meta:
        db_table = 'deposit_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['transaction_reference']),
        ]

    def __str__(self):
        return f"Deposit {self.id} - {self.user.username} - {self.amount} {self.platform} - {self.status}"


class FailedDepositRequest(models.Model):
    """Store failed deposit attempts (user mistake or system) for support reference."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='failed_deposit_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    platform = models.CharField(max_length=20)
    deposit_text = models.TextField(blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=64, blank=True, db_index=True)
    account_suffix = models.CharField(max_length=16, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'failed_deposit_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Failed deposit {self.id} - {self.user.username} - {self.platform} - {self.failure_reason}"


class TelebirrReceipt(models.Model):
    """Stores used Telebirr transaction references to prevent reuse (double-credit). Same model for auto-verified and manual. user=null, amount=0 = block-only."""
    reference = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telebirr_receipts', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'telebirr_receipts'
        ordering = ['-created_at']

    def __str__(self):
        if self.user_id:
            return f"Telebirr {self.reference} - {self.user.username} - {self.amount}"
        return f"Telebirr {self.reference} (block only)"


class CbeReceipt(models.Model):
    """Stores used CBE transaction reference+suffix to prevent reuse (double-credit). Same model for auto-verified and manual approvals. user=null, amount=0 means manually added block-only (e.g. past approval where ref was not saved)."""
    reference = models.CharField(max_length=64, db_index=True)
    account_suffix = models.CharField(max_length=16, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cbe_receipts', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cbe_receipts'
        ordering = ['-created_at']
        unique_together = [['reference', 'account_suffix']]

    def __str__(self):
        if self.user_id:
            return f"CBE {self.reference}/{self.account_suffix} - {self.user.username} - {self.amount}"
        return f"CBE {self.reference}/{self.account_suffix} (block only)"


class WithdrawRequest(models.Model):
    """Withdrawal requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PLATFORM_CHOICES = [
        ('BOA', 'Bank of Abyssinia'),
        ('CBE', 'Commercial Bank of Ethiopia'),
        ('Telebirr', 'Telebirr'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdraw_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_withdrawals')

    class Meta:
        db_table = 'withdraw_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Withdraw {self.id} - {self.user.username} - {self.amount} {self.platform} - {self.status}"


class Transfer(models.Model):
    """Transfer transactions between users"""
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfers_sent')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfers_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transfers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_user', 'created_at']),
            models.Index(fields=['to_user', 'created_at']),
        ]

    def __str__(self):
        return f"Transfer {self.id} - {self.from_user.username} → {self.to_user.username} - {self.amount}"


class AdminMessage(models.Model):
    """Admin messages to players during active games"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='admin_messages', null=True, blank=True)
    message = models.TextField()
    show_refund = models.BooleanField(default=False)
    show_cancel = models.BooleanField(default=False)
    refund_processed = models.BooleanField(default=False)
    cancel_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'admin_messages'
        ordering = ['-created_at']


class BroadcastMessage(models.Model):
    """Track broadcast messages sent to users for deletion"""
    message_text = models.TextField()
    amount_added = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, null=True, blank=True)
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='broadcasts_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'broadcast_messages'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Broadcast {self.id} - {self.created_at}"


class BroadcastMessageRecipient(models.Model):
    """Track individual message recipients and their message IDs for deletion"""
    broadcast = models.ForeignKey(BroadcastMessage, on_delete=models.CASCADE, related_name='recipients')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='broadcast_messages_received')
    telegram_id = models.BigIntegerField()
    message_id = models.IntegerField(help_text="Telegram message ID for deletion")
    sent_at = models.DateTimeField(auto_now_add=True)
    deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'broadcast_message_recipients'
        unique_together = ['broadcast', 'user']
        indexes = [
            models.Index(fields=['broadcast', 'deleted']),
            models.Index(fields=['telegram_id', 'message_id']),
        ]
    
    def __str__(self):
        return f"Broadcast {self.broadcast.id} -> User {self.user.id} (Message ID: {self.message_id})"


class SecondAdmin(models.Model):
    """Credentials for Admin View panel (/admin-view)."""
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)  # hashed for login
    # Stored so main admin can re-display credentials in the Access tab
    password_plain = models.CharField(max_length=128, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'second_admin'
        ordering = ['-created_at']

    def __str__(self):
        return f"AdminView: {self.username}"

class FakeUser(models.Model):
    """Fake system accounts for simulating players"""
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, help_text="Whether this fake user can be selected for games")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'fake_users'
        ordering = ['name']
    
    def __str__(self):
        return f"FakeUser: {self.name}"


class FakeUserGameCard(models.Model):
    """Tracks fake user cards in games"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='fake_cards')
    fake_user = models.ForeignKey(FakeUser, on_delete=models.CASCADE, related_name='game_cards')
    card_number = models.IntegerField()
    card_layout = models.JSONField(default=dict)  # 5x5 grid layout with numbers
    selected_numbers = models.JSONField(default=list)  # Numbers that have been called
    is_winner = models.BooleanField(default=False)
    winning_pattern = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'fake_user_game_cards'
        unique_together = ['game', 'fake_user']
        indexes = [
            models.Index(fields=['game', 'fake_user']),
            models.Index(fields=['game', 'card_number']),
        ]
    
    def __str__(self):
        return f"FakeCard {self.card_number} - Game {self.game.id} - {self.fake_user.name}"


class TotalStats(models.Model):
    """Singleton: site-wide totals. Updated on every game/deposit/withdraw. Survives prune."""
    total_games = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_deposits = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_withdrawals = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    total_real_wins = models.PositiveIntegerField(default=0, help_text='Games won by real users')
    total_fake_wins = models.PositiveIntegerField(default=0, help_text='Games won by system/fake users')
    real_wins_level_0 = models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=0')
    real_wins_level_1 = models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=1')
    real_wins_level_2 = models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=2')
    fake_wins_level_0 = models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=0')
    fake_wins_level_1 = models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=1')
    fake_wins_level_2 = models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=2')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'total_stats'
        verbose_name_plural = 'Total stats'

    @classmethod
    def get_singleton(cls):
        defaults = {
            'total_games': 0, 'total_revenue': 0, 'total_deposits': 0,
            'total_withdrawals': 0, 'total_balance': 0,
            'total_real_wins': 0, 'total_fake_wins': 0,
            'real_wins_level_0': 0, 'real_wins_level_1': 0, 'real_wins_level_2': 0,
            'fake_wins_level_0': 0, 'fake_wins_level_1': 0, 'fake_wins_level_2': 0,
        }
        obj, _ = cls.objects.get_or_create(pk=1, defaults=defaults)
        return obj


class DailyStats(models.Model):
    """One row per calendar day. Updated on every game/deposit/withdraw. Survives prune."""
    date = models.DateField(unique=True, db_index=True)
    games_count = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    deposits = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    withdrawals = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_stats'
        ordering = ['-date']
        verbose_name_plural = 'Daily stats'

    @classmethod
    def get_or_create_for_date(cls, d):
        obj, _ = cls.objects.get_or_create(date=d, defaults={'games_count': 0, 'revenue': 0, 'deposits': 0, 'withdrawals': 0})
        return obj


def default_payment_accounts():
    return [
        {
            'id': 'telebirr',
            'name': 'Telebirr',
            'holder': 'Getachew',
            'account': '0924242419',
        },
        {
            'id': 'cbe',
            'name': 'Commercial Bank of Ethiopia',
            'holder': 'Getachew Fikadu Jirata',
            'account': '1000528139489',
        },
    ]


def _force_https_url(url: str) -> str:
    if not url:
        return url
    from django.conf import settings as dj_settings
    use_https = getattr(dj_settings, 'SESSION_COOKIE_SECURE', False) or (
        str(os.getenv('USE_HTTPS', '')).lower() in ('1', 'true', 'yes')
    )
    if use_https and url.startswith('http://'):
        return 'https://' + url[len('http://'):]
    return url


def _absolute_file_url(file_field, request=None, cache_bust=None):
    if not file_field:
        return ''
    url = file_field.url
    if request is not None:
        url = request.build_absolute_uri(url)
    url = _force_https_url(url)
    if cache_bust:
        sep = '&' if '?' in url else '?'
        url = f'{url}{sep}v={int(cache_bust)}'
    return url


class LotterySettings(models.Model):
    """Singleton settings for the money lottery mini-app (admin-configurable)."""
    brand_name = models.CharField(max_length=120, default='Markos Digital Lottery')
    car_name = models.CharField(max_length=120, default='Cash Prize', help_text='Legacy field; prefer hero_title')
    car_color = models.CharField(max_length=80, default='', blank=True)
    car_image = models.ImageField(upload_to='lottery/cars/', blank=True, null=True)
    car_image_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Legacy image URL (homepage now uses prize text)',
    )
    hero_title = models.CharField(
        max_length=160,
        default='markos digital lottery',
        help_text='Text shown at top of homepage prize section',
    )
    prize_1st = models.PositiveIntegerField(default=100000, help_text='1st prize amount in Birr')
    prize_2nd = models.PositiveIntegerField(default=50000, help_text='2nd prize amount in Birr')
    prize_3rd = models.PositiveIntegerField(default=25000, help_text='3rd prize amount in Birr')
    verify_api_key = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='API key for Telebirr/CBE receipt verification (verifyapi.leulzenebe.pro)',
    )
    display_name = models.CharField(
        max_length=160,
        default='Markos Digital Lottery',
        help_text='Name shown on checkout / tickets',
    )
    ticket_price = models.PositiveIntegerField(default=3000)
    total_tickets = models.PositiveIntegerField(default=3500)
    sold_count = models.PositiveIntegerField(default=0)
    DRAW_MODE_DATE = 'date'
    DRAW_MODE_SOLD_OUT = 'sold_out'
    DRAW_MODE_MANUAL = 'manual'
    DRAW_MODE_CHOICES = [
        (DRAW_MODE_DATE, 'Date deadline'),
        (DRAW_MODE_SOLD_OUT, 'When all tickets sold'),
        (DRAW_MODE_MANUAL, 'Admin starts draw'),
    ]
    draw_mode = models.CharField(
        max_length=20,
        choices=DRAW_MODE_CHOICES,
        default=DRAW_MODE_DATE,
        help_text='How the draw is triggered: date countdown, sold out, or admin start',
    )
    draw_timer_seconds = models.PositiveIntegerField(
        default=60,
        help_text='Default pre-draw countdown seconds when admin clicks Start Draw',
    )
    countdown_days = models.PositiveIntegerField(default=12)
    countdown_hours = models.PositiveIntegerField(default=10)
    countdown_minutes = models.PositiveIntegerField(default=24)
    countdown_seconds = models.PositiveIntegerField(default=45)
    ends_at = models.DateTimeField(null=True, blank=True)
    payment_accounts = models.JSONField(default=default_payment_accounts)
    # Numbers force-marked taken by admin (ints). Verified user tickets also count as taken.
    admin_blocked_numbers = models.JSONField(default=list, blank=True)
    winner_number = models.CharField(max_length=16, blank=True, default='')
    winner_message = models.TextField(blank=True, default='')
    winner_announced_at = models.DateTimeField(null=True, blank=True)
    winner_1st = models.PositiveIntegerField(null=True, blank=True)
    winner_2nd = models.PositiveIntegerField(null=True, blank=True)
    winner_3rd = models.PositiveIntegerField(null=True, blank=True)
    draw_completed = models.BooleanField(default=False)
    next_round_minutes = models.PositiveIntegerField(
        default=10,
        help_text='Minutes to wait after winners are announced before starting a new round',
    )
    next_round_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the next round auto-starts after a draw',
    )
    winner_reveal_seconds = models.PositiveIntegerField(
        default=6,
        help_text='Seconds to show each place (1st/2nd/3rd) during live announce',
    )
    winners_notified = models.BooleanField(
        default=False,
        help_text='True after Telegram winner DMs have been sent (after live announce)',
    )
    automatic_announcement = models.BooleanField(
        default=True,
        help_text='If True, run in-app shuffle/reveal. If False, show manual announcement message.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lottery_settings'
        verbose_name = 'Lottery Settings'
        verbose_name_plural = 'Lottery Settings'

    def __str__(self):
        return 'Lottery Settings'

    def compute_ends_at(self):
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() + timedelta(
            days=int(self.countdown_days or 0),
            hours=int(self.countdown_hours or 0),
            minutes=int(self.countdown_minutes or 0),
            seconds=int(self.countdown_seconds or 0),
        )

    def uses_date_deadline(self):
        return (self.draw_mode or self.DRAW_MODE_DATE) == self.DRAW_MODE_DATE

    def save(self, *args, **kwargs):
        self.pk = 1
        reset_timer = kwargs.pop('reset_timer', False)
        clear_timer = kwargs.pop('clear_timer', False)
        if clear_timer:
            self.ends_at = None
        elif reset_timer:
            if self.uses_date_deadline():
                self.ends_at = self.compute_ends_at()
            else:
                # Non-date modes wait for admin Start Draw
                self.ends_at = None
        elif not self.ends_at and self.uses_date_deadline():
            self.ends_at = self.compute_ends_at()
        super().save(*args, **kwargs)

    def resolved_image_url(self, request=None):
        # Prefer uploaded car photo over external URL placeholder
        if self.car_image:
            bust = int(self.updated_at.timestamp()) if self.updated_at else None
            return _absolute_file_url(self.car_image, request, cache_bust=bust)
        url = self.car_image_url or ''
        if url and self.updated_at:
            sep = '&' if '?' in url else '?'
            url = f'{url}{sep}v={int(self.updated_at.timestamp())}'
        return url

    def taken_numbers_set(self):
        """Admin-blocked + pending/verified purchase numbers."""
        taken = set()
        for n in self.admin_blocked_numbers or []:
            try:
                taken.add(int(n))
            except (TypeError, ValueError):
                pass
        for purchase in LotteryPurchase.objects.filter(status__in=['pending', 'verified']).only('numbers'):
            for n in purchase.numbers or []:
                try:
                    taken.add(int(n))
                except (TypeError, ValueError):
                    pass
        return taken

    def resolved_verify_api_key(self):
        """Prefer lottery setting; fall back to GameSettings for older installs."""
        key = (self.verify_api_key or '').strip()
        if key:
            return key
        try:
            gs = GameSettings.get_settings()
            return (getattr(gs, 'telebirr_verify_api_key', None) or '').strip()
        except Exception:
            return ''

    def to_public_dict(self, request=None):
        ends = self.ends_at
        if ends is None and self.uses_date_deadline():
            ends = self.compute_ends_at()
        taken = sorted(self.taken_numbers_set())
        sold = len(taken)
        mode = self.draw_mode or self.DRAW_MODE_DATE
        return {
            'brand_name': self.brand_name,
            'car_name': self.car_name,
            'car_color': self.car_color,
            'car_image_url': self.resolved_image_url(request),
            'hero_title': self.hero_title or 'markos digital lottery',
            'prize_1st': int(self.prize_1st or 0),
            'prize_2nd': int(self.prize_2nd or 0),
            'prize_3rd': int(self.prize_3rd or 0),
            'display_name': self.display_name,
            'ticket_price': self.ticket_price,
            'total_tickets': self.total_tickets,
            'sold_count': sold,
            'taken_numbers': taken,
            'verified_taken_numbers': self.verified_taken_numbers(),
            'draw_mode': mode,
            'draw_timer_seconds': max(5, int(self.draw_timer_seconds or 60)),
            'countdown_days': self.countdown_days,
            'countdown_hours': self.countdown_hours,
            'countdown_minutes': self.countdown_minutes,
            'countdown_seconds': self.countdown_seconds,
            'ends_at': ends.isoformat() if ends else None,
            'ends_at_ms': int(ends.timestamp() * 1000) if ends else None,
            'payment_accounts': self.payment_accounts or [],
            'winner_number': self.winner_number or '',
            'winner_message': self.winner_message or '',
            'winner_announced_at': self.winner_announced_at.isoformat() if self.winner_announced_at else None,
            'winner_1st': self.winner_1st,
            'winner_2nd': self.winner_2nd,
            'winner_3rd': self.winner_3rd,
            'draw_completed': bool(self.draw_completed),
            'next_round_minutes': int(self.next_round_minutes or 10),
            'next_round_at': self.next_round_at.isoformat() if self.next_round_at else None,
            'next_round_at_ms': int(self.next_round_at.timestamp() * 1000) if self.next_round_at else None,
            'winner_reveal_seconds': max(2, int(self.winner_reveal_seconds or 6)),
            'winners_notified': bool(self.winners_notified),
            'automatic_announcement': bool(self.automatic_announcement),
        }

    def verified_taken_numbers(self):
        """Numbers from verified purchases only (real ticket owners)."""
        taken = set()
        for purchase in LotteryPurchase.objects.filter(status='verified').only('numbers'):
            for n in purchase.numbers or []:
                try:
                    taken.add(int(n))
                except (TypeError, ValueError):
                    pass
        return sorted(taken)

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        if created or (obj.uses_date_deadline() and not obj.ends_at):
            obj.save(reset_timer=True)
            obj.refresh_from_db()
        return obj


class LotteryPurchase(models.Model):
    """Ticket purchase / receipt verification request."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='lottery_purchases'
    )
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, db_index=True)
    numbers = models.JSONField(default=list, help_text='Selected lottery numbers as ints')
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bank_name = models.CharField(max_length=120, blank=True, default='')
    bank_holder = models.CharField(max_length=160, blank=True, default='')
    bank_account = models.CharField(max_length=64, blank=True, default='')
    paid_from_account = models.CharField(max_length=64, blank=True, default='')
    receipt_image = models.ImageField(upload_to='lottery/receipts/', blank=True, null=True)
    receipt_sms = models.TextField(blank=True, default='', help_text='Full SMS text pasted by user')
    payment_provider = models.CharField(
        max_length=20, blank=True, default='',
        help_text='telebirr or cbe',
    )
    transaction_ref = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='Parsed transaction / receipt reference for dedup',
    )
    receipt_hash = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    admin_note = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='lottery_verifications'
    )

    class Meta:
        db_table = 'lottery_purchases'
        ordering = ['-created_at']

    def __str__(self):
        return f'LotteryPurchase {self.id} {self.phone} {self.status}'

    def to_dict(self, request=None):
        img = ''
        if self.receipt_image:
            img = _absolute_file_url(self.receipt_image, request)
        return {
            'id': self.id,
            'full_name': self.full_name,
            'phone': self.phone,
            'numbers': self.numbers or [],
            'quantity': self.quantity,
            'amount': float(self.amount or 0),
            'bank_name': self.bank_name,
            'bank_holder': self.bank_holder,
            'bank_account': self.bank_account,
            'paid_from_account': self.paid_from_account,
            'receipt_image_url': img,
            'receipt_sms': self.receipt_sms or '',
            'payment_provider': self.payment_provider or '',
            'transaction_ref': self.transaction_ref or '',
            'status': self.status,
            'admin_note': self.admin_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'telegram_id': self.user.telegram_id if self.user_id and self.user else None,
        }


class LotteryFailedDeposit(models.Model):
    """Failed checkout / SMS verification requests awaiting manual admin approval."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='lottery_failed_deposits'
    )
    full_name = models.CharField(max_length=160, blank=True, default='')
    phone = models.CharField(max_length=32, blank=True, default='', db_index=True)
    numbers = models.JSONField(default=list, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credited_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_provider = models.CharField(max_length=20, blank=True, default='')
    bank_name = models.CharField(max_length=120, blank=True, default='')
    bank_holder = models.CharField(max_length=160, blank=True, default='')
    bank_account = models.CharField(max_length=64, blank=True, default='')
    transaction_ref = models.CharField(max_length=64, blank=True, default='', db_index=True)
    account_suffix = models.CharField(max_length=16, blank=True, default='')
    receipt_sms = models.TextField(blank=True, default='')
    failure_reason = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    admin_txn_no = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Txn number confirmed by admin on approve (blocks reuse)',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='lottery_failed_resolutions'
    )

    class Meta:
        db_table = 'lottery_failed_deposits'
        ordering = ['-created_at']

    def __str__(self):
        return f'LotteryFailedDeposit {self.id} {self.payment_provider} {self.status}'

    def to_admin_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'phone': self.phone,
            'numbers': self.numbers or [],
            'quantity': self.quantity,
            'expected_amount': float(self.expected_amount or 0),
            'credited_amount': float(self.credited_amount) if self.credited_amount is not None else None,
            'payment_provider': self.payment_provider or '',
            'bank_name': self.bank_name or '',
            'bank_holder': self.bank_holder or '',
            'bank_account': self.bank_account or '',
            'transaction_ref': self.transaction_ref or '',
            'account_suffix': self.account_suffix or '',
            'receipt_sms': self.receipt_sms or '',
            'failure_reason': self.failure_reason or '',
            'status': self.status,
            'admin_txn_no': self.admin_txn_no or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'telegram_id': self.user.telegram_id if self.user_id and self.user else None,
        }


class DeletedLotteryReceipt(models.Model):
    """Snapshot of a receipt removed/rejected by Admin View (second admin)."""
    ACTION_CHOICES = [
        ('reject', 'Rejected'),
        ('delete', 'Deleted'),
    ]

    original_purchase_id = models.IntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    prior_status = models.CharField(max_length=20, blank=True, default='')
    full_name = models.CharField(max_length=160, blank=True, default='')
    phone = models.CharField(max_length=32, blank=True, default='')
    numbers = models.JSONField(default=list, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bank_name = models.CharField(max_length=120, blank=True, default='')
    bank_holder = models.CharField(max_length=160, blank=True, default='')
    bank_account = models.CharField(max_length=64, blank=True, default='')
    paid_from_account = models.CharField(max_length=64, blank=True, default='')
    receipt_hash = models.CharField(max_length=64, blank=True, default='')
    admin_note = models.CharField(max_length=255, blank=True, default='')
    telegram_id = models.BigIntegerField(null=True, blank=True)
    original_created_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.CharField(max_length=120, blank=True, default='admin-view')
    removed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'lottery_deleted_receipts'
        ordering = ['-removed_at']

    def to_admin_dict(self):
        """Full snapshot for main-admin analysis only."""
        return {
            'id': self.id,
            'kind': 'receipt',
            'original_purchase_id': self.original_purchase_id,
            'action': self.action,
            'prior_status': self.prior_status or '',
            'full_name': self.full_name or '',
            'phone': self.phone or '',
            'numbers': self.numbers or [],
            'quantity': self.quantity,
            'amount': float(self.amount or 0),
            'bank_name': self.bank_name or '',
            'bank_holder': self.bank_holder or '',
            'bank_account': self.bank_account or '',
            'paid_from_account': self.paid_from_account or '',
            'admin_note': self.admin_note or '',
            'telegram_id': self.telegram_id,
            'original_created_at': self.original_created_at.isoformat() if self.original_created_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'removed_by': self.removed_by or 'admin-view',
        }


class DeletedLotteryUser(models.Model):
    """Snapshot of a user removed by Admin View (second admin)."""

    original_user_id = models.IntegerField(null=True, blank=True, db_index=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True, default='')
    first_name = models.CharField(max_length=150, blank=True, default='')
    username = models.CharField(max_length=150, blank=True, default='')
    preferred_language = models.CharField(max_length=5, blank=True, default='')
    is_guest = models.BooleanField(default=False)
    purchase_count = models.PositiveIntegerField(default=0)
    verified_numbers = models.JSONField(default=list, blank=True)
    pending_numbers = models.JSONField(default=list, blank=True)
    total_spent_verified = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_joined = models.DateTimeField(null=True, blank=True)
    removed_by = models.CharField(max_length=120, blank=True, default='admin-view')
    removed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'lottery_deleted_users'
        ordering = ['-removed_at']

    def to_admin_dict(self):
        """Full snapshot for main-admin analysis only."""
        return {
            'id': self.id,
            'kind': 'user',
            'action': 'delete',
            'original_user_id': self.original_user_id,
            'telegram_id': self.telegram_id,
            'phone': self.phone or '',
            'first_name': self.first_name or '',
            'username': self.username or '',
            'preferred_language': self.preferred_language or '',
            'is_guest': bool(self.is_guest),
            'purchase_count': self.purchase_count,
            'verified_numbers': self.verified_numbers or [],
            'pending_numbers': self.pending_numbers or [],
            'total_spent_verified': float(self.total_spent_verified or 0),
            'date_joined': self.date_joined.isoformat() if self.date_joined else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'removed_by': self.removed_by or 'admin-view',
        }