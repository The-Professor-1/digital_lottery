from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import json


class User(AbstractUser):
    """Custom User model for Telegram users"""
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals', help_text='User who referred this user')
    referral_reward_given = models.BooleanField(default=False, help_text='Whether referral reward was already given for THIS user\'s registration (prevents duplicate rewards if user re-registers)')
    withdrawal_approved = models.BooleanField(default=False, help_text='True when user has deposited at least 50 BR and played at least 5 games (allows withdrawal)')
    # Cached totals (updated on game/deposit/withdraw; used when detail records are pruned)
    total_games_played = models.PositiveIntegerField(default=0, help_text='Total games user has played (survives prune)')
    total_wins = models.PositiveIntegerField(default=0, help_text='Total games user has won (survives prune)')
    total_deposits_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='Sum of all deposits (survives prune)')
    total_withdrawals_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='Sum of all withdrawals (survives prune)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['telegram_id'], name='user_telegram_id_idx'),
            models.Index(fields=['referred_by'], name='user_referred_by_idx'),
            models.Index(fields=['created_at'], name='user_created_at_idx'),
        ]

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


class GameSettings(models.Model):
    """Game configuration settings - Singleton pattern"""
    # Game timing settings
    time_between_calls = models.IntegerField(default=3, help_text="Seconds between each number call")
    card_selection_timer = models.IntegerField(default=20, help_text="Seconds for card selection window")
    
    # Game financial settings
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Default bet amount per card")
    percentage_cut = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Percentage to cut from total derash (e.g., 10.00 for 10%)")
    min_withdraw = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, help_text="Minimum withdrawal amount")
    
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
        except (AttributeError, Exception):
            # If accessing fields fails (migration not run), set defaults on object
            try:
                obj.system_accounts_min = 15
                obj.system_accounts_max = 30
                obj.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
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
    """Stores used Telebirr transaction references to prevent reuse (double-credit)."""
    reference = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telebirr_receipts')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'telebirr_receipts'
        ordering = ['-created_at']

    def __str__(self):
        return f"Telebirr {self.reference} - {self.user.username} - {self.amount}"


class CbeReceipt(models.Model):
    """Stores used CBE transaction reference+suffix to prevent reuse (double-credit)."""
    reference = models.CharField(max_length=64, db_index=True)
    account_suffix = models.CharField(max_length=16, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cbe_receipts')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cbe_receipts'
        ordering = ['-created_at']
        unique_together = [['reference', 'account_suffix']]

    def __str__(self):
        return f"CBE {self.reference}/{self.account_suffix} - {self.user.username} - {self.amount}"


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
    """Second admin credentials for limited access dashboard"""
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)  # Will store hashed password
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'second_admin'
        ordering = ['-created_at']

    def __str__(self):
        return f"SecondAdmin: {self.username}"


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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'total_stats'
        verbose_name_plural = 'Total stats'

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            'total_games': 0, 'total_revenue': 0, 'total_deposits': 0,
            'total_withdrawals': 0, 'total_balance': 0,
        })
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